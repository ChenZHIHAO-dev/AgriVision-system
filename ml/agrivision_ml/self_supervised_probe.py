"""DINOv2 冻结特征对照；只训练线性头，不自动注册或启用后端模型。

沿用已有观察组划分、读图/在线增强、特征缓存和线性头选择。原始 final test
由 load_plan 排除；这里的 test 是开发折外层。权重仅从明确指定的本地缓存读取。
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import ctypes
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
import timm
import torch

from . import linear_probe as probe
from .cached_probe_cv import load_plan, select_head, evaluate_head, logits_for, save_predictions
from .experiment_report import save_confusion
from .probe_diagnostics import confidence_summary
from .train import _task_metadata

MODEL = 'vit_base_patch14_reg4_dinov2.lvd142m'
WEIGHT_URL = 'https://dl.fbaipublicfiles.com/dinov2/dinov2_vitb14/dinov2_vitb14_reg4_pretrain.pth'


def prepare_fold(args):
    """先检查固定折和原始 test 隔离，再加载骨干，避免在错误划分上耗时提特征。"""
    if args.input_size <= 0 or args.input_size % 14:
        raise ValueError('DINOv2 输入边长必须为正且是 14 的倍数，禁止静默裁切')
    if args.views < 0 or min(args.batch_size, args.threads) < 1 or any(c <= 0 for c in args.c_values):
        raise ValueError('视图数不能为负；批量、线程和 C 必须大于 0')
    config = json.loads(args.labels.read_text(encoding='utf-8-sig'))
    _task_metadata(config)
    labels = list(config['labels'])
    # 复用完整计划审计：原图身份、同源组、重复图、原 test 和每折外层覆盖。
    plan_args = SimpleNamespace(manifest=args.manifest, cv_root=args.cv_root)
    original, _, folds, plan = load_plan(plan_args, labels)
    selected = next((rows for number, rows in folds if number == args.fold), None)
    item = next((entry for entry in plan['folds'] if entry['fold'] == args.fold), None)
    if selected is None or item is None:
        raise ValueError('选择的开发折不存在')
    if {row['label'] for row in selected} != set(labels):
        raise ValueError('开发折类别与标签表不一致')
    return config, labels, selected, args.cv_root / item['manifest'], original


def build_encoder(weights, size):
    """使用 timm 的官方权重键转换与位置编码缩放，不自己实现 Transformer。

    原预训练位置编码对应 518；timm 按声明的 224/336 输入调整它。num_classes=0
    返回最后一层归一化后的 CLS 特征。四个 register token 不当作类别或均值池化项。
    """
    return timm.create_model(MODEL, pretrained=True, num_classes=0, img_size=size,
        pretrained_cfg_overlay={'file': str(weights.resolve()), 'hf_hub_id': None}
    ).eval().requires_grad_(False)


def peak_memory_mb():
    """Windows 进程峰值工作集；包含 Python/库/权重和激活，不等同于权重文件大小。"""
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    kernel, psapi = ctypes.WinDLL('kernel32'), ctypes.WinDLL('psapi')
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize / 1024 ** 2


def benchmark(args, model, rows, labels):
    """只拿训练折前 16 张测速；计入解码和哈希检查，不计算它们的准确率。"""
    selected = [row for row in rows if row['split'] == 'train'][:16]
    with torch.inference_mode():
        model(torch.zeros(1, 3, args.input_size, args.input_size))
    started = time.perf_counter()
    features, _ = probe.encode(model, args.data_root, selected, labels, args.input_size,
                               batch_size=args.batch_size)
    seconds = time.perf_counter() - started
    views = sum(1 + args.views if row['split'] == 'train' else 1 for row in rows)
    result = {'model': MODEL, 'device': 'cpu', 'threads': args.threads, 'batch_size': args.batch_size,
        'input_size': args.input_size, 'images': len(selected), 'feature_dimension': features.shape[1],
        'seconds': seconds, 'seconds_per_image': seconds / len(selected),
        'peak_process_memory_mb': peak_memory_mb(), 'parameters': sum(p.numel() for p in model.parameters()),
        'full_fold_feature_views': views, 'estimated_feature_seconds': seconds / len(selected) * views,
        'estimate_note': '小样本线性外推，只估提特征；不含下载、初始化、线性头选择且受并行CPU负载影响。'}
    probe.write_json(args.output / 'benchmark.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def partition(data, rows, split):
    """核对缓存视图和标签顺序；验证/外层始终一图一个固定视图。"""
    selected = [row for row in rows if row['split'] == split]
    vectors, targets = data[split + '_x'], data[split + '_y']
    expected = np.array([row['_target'] for row in selected])
    if split == 'train':
        if len(targets) % len(expected):
            raise ValueError('训练缓存不是完整视图批次')
        expected = np.tile(expected, len(targets) // len(expected))
    if len(vectors) != len(targets) or not np.array_equal(targets, expected):
        raise ValueError(f'{split} 缓存数量或标签顺序错误')
    return vectors, targets, selected


def run(args):
    config, labels, rows, fold_manifest, original = prepare_fold(args)
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    # 适配代码/权重/原始划分也绑定身份。共享 feature_cache 会另外绑定实际骨干张量。
    identity = {'model': MODEL, 'pooling': 'normalized_final_cls_token', 'timm': timm.__version__,
        'weight_url': WEIGHT_URL, 'weight_sha256': probe.digest(args.weights), 'weight_license': 'Apache-2.0',
        'original_manifest_sha256': probe.digest(args.manifest), 'fold_manifest_sha256': probe.digest(fold_manifest),
        'fold_plan_sha256': probe.digest(args.cv_root / 'folds.json'), 'input_size': args.input_size,
        'views': args.views, 'augmentation': args.augmentation, 'seed': args.seed, 'c_values': args.c_values,
        'code': {name: probe.digest(Path(__file__).with_name(name)) for name in
                 ('self_supervised_probe.py', 'cached_probe_cv.py', 'probe_diagnostics.py')}}
    identity_path = args.output / 'probe-recipe.json'
    if identity_path.exists() and json.loads(identity_path.read_text(encoding='utf-8')) != identity:
        raise ValueError('已有实验身份不同，请先核对配置；不能覆盖原结果')
    probe.write_json(identity_path, identity)
    model = build_encoder(args.weights, args.input_size)
    if args.benchmark_only:
        return benchmark(args, model, rows, labels)
    started = time.perf_counter()
    cache_args = SimpleNamespace(**{**vars(args), 'architecture': MODEL, 'manifest': fold_manifest})
    data = probe.feature_cache(cache_args, model, rows, labels)
    indexed = [{**row, '_target': labels.index(row['label'])} for row in rows]
    training, validation = (partition(data, indexed, split) for split in ('train', 'val'))
    # 线性头优化与已有监督骨干对照完全相同；外层标签不传给 select_head。
    classifier, search = select_head(training, validation, args.c_values, len(labels))
    probe.write_json(args.output / 'probe-search.json', search)
    weights, bias = probe.linear_weights(classifier)
    np.savez_compressed(args.output / 'head.npz', weights=weights, bias=bias)
    metadata = {**_task_metadata(config), 'labels': labels}
    # 保持与原两项 probe 相同的未校准分析规则，既报告全量结果也报告拒识覆盖。
    fixed = {'temperature': 1., 'threshold': .7, 'margin': .12}
    sources = {}
    with (args.data_root.parent / 'sources.csv').open(encoding='utf-8-sig', newline='') as stream:
        sources = {row['path']: row for row in csv.DictReader(stream)}
    result = {'method': 'frozen_self_supervised_dinov2_linear_probe', 'recipe': identity,
        'evaluation_scope': 'fixed grouped outer development fold; original final test excluded',
        'original_final_test_excluded': sum(row['split'] == 'test' for row in original),
        'fold': args.fold, 'selected_C': classifier.C, 'labels': labels,
        'parameters': sum(p.numel() for p in model.parameters()) + weights.size + bias.size,
        'head_parameters': weights.size + bias.size, 'training_views_per_photo': 1 + args.views,
        'release_eligible': False, 'calibrated': False,
        'curves_note': '冻结骨干无训练epoch/loss曲线；probe-search记录每个C的迭代数、收敛和内val结果。全微调另有训练曲线。'}
    for split in ('val', 'test'):
        values = partition(data, indexed, split)
        score, predictions = evaluate_head(classifier, values, labels, fixed, metadata)
        probabilities = logits_for(classifier, values[0]).softmax(1).numpy()
        score['confidence'] = confidence_summary(probabilities, values[1], .7, .12)
        score['top3_accuracy'] = float(np.any(np.argsort(-probabilities, axis=1)[:, :3] == values[1][:, None], axis=1).mean())
        for row in predictions:
            source = sources.get(row['path'], {})
            row['source'], row['country'] = source.get('source', 'unknown'), source.get('country', '')
        score['by_source'] = {}
        for source in sorted({row['source'] for row in predictions}):
            indexes = [i for i, row in enumerate(predictions) if row['source'] == source]
            source_score = probe.prediction_metrics(values[1][indexes], probabilities[indexes].argmax(1), len(labels))
            present = np.asarray(source_score['counts']) > 0
            source_score['present_classes'] = [label for label, yes in zip(labels, present) if yes]
            source_score['present_class_macro_f1'] = float(np.asarray(source_score['f1'])[present].mean())
            score['by_source'][source] = source_score
        wrong = [row for row in predictions if not row['correct']]
        score['highest_confidence_errors'] = sorted(wrong, key=lambda row: row['confidence'], reverse=True)[:20]
        score['top_confusions'] = [{'true': a, 'predicted': b, 'images': n} for (a, b), n in
                                  Counter((row['true'], row['predicted']) for row in wrong).most_common(15)]
        result[split] = score
        save_predictions(args.output / f'predictions-{split}.csv', predictions)
        save_confusion(score['confusion_matrix'], labels, args.output / f'confusion-{split}.png')
    result.update(seconds=time.perf_counter() - started, peak_process_memory_mb=peak_memory_mb())
    # 不复制冻结骨干，不生成假装可部署的现有架构模型包；head + 编码器身份供后续复核。
    probe.write_json(args.output / 'encoder.json', {**identity, 'checkpoint': str(args.weights.resolve())})
    probe.write_json(args.output / 'probe-result.json', result)
    print(json.dumps({key: result['test'][key] for key in ('accuracy', 'macro_f1', 'top3_accuracy')}, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True, help='原始 prepared 清单，用于排除最终test')
    parser.add_argument('--cv-root', type=Path, required=True)
    parser.add_argument('--fold', type=int, default=1)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True, help='已下载的官方 DINOv2 reg4 权重')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input-size', type=int, default=224)
    parser.add_argument('--views', type=int, default=2)
    parser.add_argument('--augmentation', choices=['light', 'field'], default='light')
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--c-values', nargs='+', type=float, default=[.1, 1., 10.])
    parser.add_argument('--benchmark-only', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()

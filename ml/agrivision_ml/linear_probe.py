"""冻结 ImageNet 骨干的线性分类基线：用 CPU 缓存特征，再比较分类头。

这是与全量微调不同的便宜对照，并不冒充端到端训练。增强只对训练图进行；
验证和测试只用固定变换。输出沿用 Predictor 的模型包，方便与完整微调比较。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import warnings

import numpy as np
import PIL
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
import torch
import torchvision
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from .model import build_model
from .train import Images, metrics, read_manifest, _task_metadata
from .experiment_report import save_confusion


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replace_head(model, architecture, head):
    """只换最后的线性层；ConvNeXt 自带的归一化层仍参与特征提取。"""
    if architecture == 'swin_t':
        previous, model.head = model.head, head
    else:
        previous, model.classifier[-1] = model.classifier[-1], head
    return previous


def linear_weights(classifier):
    """把 sklearn 的线性判别式搬到 PyTorch，不改变类别顺序或预测分数。

    二分类 sklearn 用一个 sigmoid 分数；对称的两个 logits 经过 softmax 等价。
    多类别直接使用每类一行的权重。导出后仍由原 Predictor 做统一图像变换。
    """
    weights = classifier.coef_
    bias = classifier.intercept_
    if len(classifier.classes_) == 2:
        weights = np.concatenate([-weights / 2, weights / 2])
        bias = np.concatenate([-bias / 2, bias / 2])
    return weights.astype('float32'), bias.astype('float32')


def install_head(model, architecture, classifier, classes):
    if not np.array_equal(classifier.classes_, np.arange(classes)):
        raise ValueError('分类头缺少类别，不能导出不对应标签顺序的权重')
    weights, bias = linear_weights(classifier)
    head = nn.Linear(weights.shape[1], classes)
    with torch.no_grad():
        head.weight.copy_(torch.from_numpy(weights))
        head.bias.copy_(torch.from_numpy(bias))
    replace_head(model, architecture, head)
    return model.eval()


def prediction_metrics(truth, predicted, classes):
    matrix = np.zeros((classes, classes), dtype=int)
    np.add.at(matrix, (truth, predicted), 1)
    return metrics(matrix)


@torch.inference_mode()
def encode(model, root, rows, labels, size, *, training=False, augmentation='light', batch_size=16):
    """复用训练模块的图像变换和 SHA 校验；只存特征张量，不存增强图片副本。"""
    dataset = Images(root, rows, labels, size, training, resize='letterbox', augmentation=augmentation)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    vectors, targets = [], []
    for images, truth in tqdm(loader, desc='增强特征' if training else '固定特征', unit='batch'):
        vectors.append(model(images).cpu().numpy())
        targets.append(truth.numpy())
    return np.concatenate(vectors), np.concatenate(targets)


def validate_source_images(root, rows):
    """即使命中特征缓存也校验原图，避免缓存掩盖后来改图或错误目录。"""
    root = root.resolve()
    for row in tqdm(rows, desc='核对特征来源', unit='image', leave=False):
        path = (root / row['path']).resolve()
        if not path.is_relative_to(root) or digest(path) != row['sha256']:
            raise ValueError('图片路径或内容与清单不一致，不能复用特征缓存')


def backbone_digest(model):
    """摘要覆盖实际冻结权重及缓冲区，不能只靠架构名推测预训练版本。"""
    result = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        tensor = tensor.detach().cpu().contiguous()
        result.update(json.dumps([name, str(tensor.dtype), list(tensor.shape)]).encode())
        result.update(tensor.numpy().tobytes())
    return result.hexdigest()


def feature_cache(args, model, rows, labels):
    """缓存与数据、骨干、变换和随机种子绑定。改配置后必须明确换实验目录。

    原图训练特征一遍，额外增强 views 遍；每一遍都读取全部训练照片。验证/测试
    不生成随机视图。固定骨干不使用任何本项目标签训练，预提取测试特征不拟合参数。
    """
    validate_source_images(args.data_root, rows)
    # Images 定义在 train.py；Pillow/torchvision 也会影响解码和图像变换。
    files = [Path(__file__), *(Path(__file__).with_name(name) for name in
                              ('model.py', 'augmentation.py', 'train.py'))]
    identity = dict(manifest=digest(args.manifest), labels=digest(args.labels), architecture=args.architecture,
                    input_size=args.input_size, views=args.views, augmentation=args.augmentation,
                    seed=args.seed, torch=torch.__version__, torchvision=torchvision.__version__,
                    pillow=PIL.__version__, numpy=np.__version__, backbone_sha256=backbone_digest(model),
                    code={p.name: digest(p) for p in files})
    cache = args.output / 'features.npz'
    sidecar = args.output / 'features.json'
    if cache.exists() and sidecar.exists():
        saved = json.loads(sidecar.read_text(encoding='utf-8'))
        checksum = saved.pop('cache_sha256', None)
        if saved != identity:
            raise ValueError('特征缓存与当前实验配置或冻结骨干不同，请核对实验目录；不修改数据目录')
        if checksum != digest(cache):
            raise ValueError('特征缓存内容校验失败，不能继续导出模型')
        print('复用已完成特征缓存：', cache, flush=True)
        with np.load(cache) as data:
            return {name: data[name] for name in data.files}
    values = {}
    for split in ('train', 'val', 'test'):
        selected = [row for row in rows if row['split'] == split]
        if not selected:
            raise ValueError(f'{split} 划分没有照片')
        vectors, target = encode(model, args.data_root, selected, labels, args.input_size, batch_size=args.batch_size)
        if split == 'train':
            all_vectors, all_targets = [vectors], [target]
            for view in range(args.views):
                torch.manual_seed(args.seed + view)
                random.seed(args.seed + view)
                np.random.seed(args.seed + view)
                augmented, augmented_target = encode(model, args.data_root, selected, labels, args.input_size,
                    training=True, augmentation=args.augmentation, batch_size=args.batch_size)
                all_vectors.append(augmented)
                all_targets.append(augmented_target)
            vectors, target = np.concatenate(all_vectors), np.concatenate(all_targets)
        values[split + '_x'], values[split + '_y'] = vectors, target
    # 写完后再替换正式文件，断电或中止不会把半个 npz 当成已完成缓存。
    temporary = cache.with_name('.features.pending.npz')
    temporary_sidecar = sidecar.with_suffix('.json.tmp')
    try:
        np.savez_compressed(temporary, **values)
        write_json(temporary_sidecar, {**identity, 'cache_sha256': digest(temporary)})
        temporary.replace(cache)
        temporary_sidecar.replace(sidecar)
    finally:
        temporary.unlink(missing_ok=True)
        temporary_sidecar.unlink(missing_ok=True)
    return values


def run(args):
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.labels.read_text(encoding='utf-8-sig'))
    task_metadata = _task_metadata(config)
    labels = list(config['labels'])
    rows = read_manifest(args.manifest)
    if set(row['label'] for row in rows) != set(labels):
        raise ValueError('数据类别与标签表不一致')
    for split in ('train', 'val', 'test'):
        if {row['label'] for row in rows if row['split'] == split} != set(labels):
            raise ValueError(f'{split} 没有覆盖全部类别')
    model = build_model(args.architecture, len(labels), pretrained=True).eval().requires_grad_(False)
    replace_head(model, args.architecture, nn.Identity())
    data = feature_cache(args, model, rows, labels)
    candidates, best, best_score = [], None, -1.0
    # C 是正则强度的倒数；仅验证集选择它，测试集完全不参与选参数。
    for strength in args.c_values:
        classifier = LogisticRegression(C=strength, class_weight='balanced', max_iter=2000, tol=1e-4)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ConvergenceWarning)
            classifier.fit(data['train_x'], data['train_y'])
        converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
        validation = prediction_metrics(data['val_y'], classifier.predict(data['val_x']), len(labels))
        result = dict(C=strength, converged=converged, iterations=classifier.n_iter_.tolist(), validation=validation)
        candidates.append(result)
        write_json(args.output / 'probe-search.json', candidates)
        print(json.dumps({'C': strength, 'converged': converged, 'val_macro_f1': validation['macro_f1']}), flush=True)
        if converged and validation['macro_f1'] > best_score:
            best, best_score = classifier, validation['macro_f1']
    if best is None:
        raise RuntimeError('分类头未收敛，请检查特征或增加迭代次数；不发布半成品')
    model = install_head(model, args.architecture, best, len(labels))
    bundle = args.output / 'bundle'
    bundle.mkdir(exist_ok=True)
    torch.save(model.state_dict(), bundle / 'weights.pt')
    validation = prediction_metrics(data['val_y'], best.predict(data['val_x']), len(labels))
    testing = prediction_metrics(data['test_y'], best.predict(data['test_x']), len(labels))
    write_json(args.output / 'probe-result.json', {'method': 'frozen_imagenet_linear_probe',
        'selected_C': best.C, 'validation': validation, 'test': testing,
        'training_views_per_photo': 1 + args.views,
        'limitation': '按观察组留出；不是国内田间外测，也没有未知类别拒识验证。'})
    save_confusion(testing['confusion_matrix'], labels, args.output / 'probe-confusion-test.png')
    metadata = dict(schema_version=1, **task_metadata, architecture=args.architecture, labels=labels,
        label_names=config['labels'], input_size=args.input_size, normalization='imagenet', resize='letterbox',
        augmentation=args.augmentation, version=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'),
        threshold=.7, margin=.12, temperature=1., validated=False, development_only=True,
        manifest_sha256=digest(args.manifest), seed=args.seed, pretrained=True, device='cpu', precision='fp32',
        release_stage='development', method='frozen_imagenet_linear_probe', validation=validation,
        feature_cache=json.loads((args.output / 'features.json').read_text(encoding='utf-8')),
        training_config={key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()})
    write_json(bundle / 'metadata.json', metadata)
    print(json.dumps({'bundle': str(bundle), 'test_accuracy': testing['accuracy'], 'test_macro_f1': testing['macro_f1']}), flush=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--architecture', choices=['swin_t', 'convnext_tiny'], default='convnext_tiny')
    parser.add_argument('--input-size', type=int, default=224)
    parser.add_argument('--views', type=int, default=2, help='每张训练图额外增强视图数量；不增加独立样本数')
    parser.add_argument('--augmentation', choices=['light', 'field'], default='light')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--c-values', nargs='+', type=float, default=[.1, 1., 10.])
    args = parser.parse_args()
    if args.views < 0 or args.threads < 1 or args.batch_size < 1 or any(c <= 0 for c in args.c_values):
        parser.error('视图数不能为负，线程、批量和 C 必须大于 0')
    run(args)


if __name__ == '__main__':
    main()

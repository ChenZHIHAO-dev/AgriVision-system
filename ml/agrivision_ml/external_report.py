"""独立来源的开发诊断：复用真实模型推理，不改训练包、训练清单或阈值。

外域图片与训练清单不同是预期行为，因此不能通过替换 metadata 中的哈希去
绕过 experiment_report 的同数据版本检查。本入口另外记录训练与外域身份，
默认只声明 external_development_diagnostic，不充当最终田间验收。
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from .experiment_report import save_confusion
from .inference import Predictor, rejection_indices
from .train import Images, metrics


UNKNOWN_GROUPS = {'', 'unknown', 'none', 'null', 'n/a'}


def digest(path):
    """流式校验避免一次把整套原图读进内存；哈希描述本次实际使用的字节。"""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_external_rows(manifest, data_root, labels, *, allow_partial_labels=False):
    """只接收已明确映射的单标签外域清单，不悄悄丢掉模型不支持的类别。

    保留原作者标签、许可、地区及 unknown 采集身份。unknown 不是一个实际的
    同株组，也不能给每张图伪造采集组；统计时会单独报告未知身份的图片数。
    """
    root = data_root.resolve()
    with manifest.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('外域清单没有图片')
    seen = set()
    for row in rows:
        if row['label'] not in labels:
            raise ValueError(f"模型不支持外域类别：{row['label']}")
        if row.get('review', 'review') not in {'review', 'keep'}:
            raise ValueError('外域清单包含 hold/drop，先完成来源筛选')
        if row.get('labels_json') and json.loads(row['labels_json']) != [row['label']]:
            raise ValueError('单标签诊断不能把混合病症当作一个病害标签')
        path = (root / row['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('外域图片路径越过 data-root')
        if path in seen:
            raise ValueError('外域清单重复引用同一张图片')
        seen.add(path)
        # 外域来源表可能只提供像素哈希。另算文件哈希给现有 Images 使用，
        # 不把像素哈希错误地当作文件 SHA-256，也不修改原 CSV。
        file_hash = digest(path)
        if row.get('sha256') and row['sha256'] != file_hash:
            raise ValueError('外域图片与清单文件哈希不同')
        row['sha256'] = file_hash
    if not allow_partial_labels and set(row['label'] for row in rows) != set(labels):
        raise ValueError('外域清单未覆盖全部模型类别，不能生成完整闭集对照')
    return rows


def coverage_metrics(matrix, labels):
    """缺少真实样本的类别不参与宏平均；所有模型输出列仍保留。

    例如外部花生来源没有链格孢叶斑样本，不能声称已验证这一类，也不能
    删除该输出列后重新归一化概率。预测到它仍算错误，计入准确率及真实类漏检。
    """
    result = metrics(matrix)
    observed = np.asarray(result['counts']) > 0
    result['macro_f1_all_model_classes'] = result['macro_f1']
    result['macro_f1'] = float(np.asarray(result['f1'])[observed].mean())
    result['balanced_accuracy'] = float(np.asarray(result['recall'])[observed].mean())
    result['metric_scope'] = 'observed_ground_truth_classes'
    result['evaluated_labels'] = [label for label, present in zip(labels, observed) if present]
    result['missing_labels'] = [label for label, present in zip(labels, observed) if not present]
    return result


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@torch.inference_mode()
def report(bundle, data_root, manifest, output, *, batch_size=16, threads=2, allow_partial_labels=False):
    """CPU 串行前向；只生成诊断材料，不依据此外域数据重新训练、校准或选阈值。"""
    if (output / 'evaluation.json').exists():
        raise FileExistsError('外域诊断已完成，不覆盖既有结果')
    torch.set_num_threads(threads)
    predictor = Predictor(bundle, 'cpu')
    metadata = predictor.metadata
    rows = read_external_rows(manifest, data_root, predictor.labels, allow_partial_labels=allow_partial_labels)
    dataset = Images(data_root, rows, predictor.labels, metadata['input_size'],
                     resize=metadata.get('resize', 'stretch'))
    loader = DataLoader(dataset, batch_size=batch_size, num_workers=0, shuffle=False)
    matrix = np.zeros((len(predictor.labels), len(predictor.labels)), dtype=int)
    by_source = defaultdict(lambda: np.zeros_like(matrix))
    excluded = rejection_indices(metadata)
    predictions, offset, total_nll = [], 0, 0.
    started = perf_counter()
    for images, truth in tqdm(loader, desc='External diagnostic', unit='batch'):
        logits = predictor.model(images).float()
        calibrated_logits = logits / float(metadata.get('temperature', 1.))
        scores = calibrated_logits.softmax(1)
        total_nll += torch.nn.functional.cross_entropy(calibrated_logits, truth, reduction='sum').item()
        top_scores, indices = scores.topk(2, dim=1)
        for index, target in enumerate(truth.tolist()):
            row = rows[offset]
            predicted = int(indices[index, 0])
            confidence = float(top_scores[index, 0])
            margin = float(top_scores[index, 0] - top_scores[index, 1])
            matrix[target, predicted] += 1
            by_source[row['source']][target, predicted] += 1
            # 原作者标签仍留在逐图 CSV 中，便于判断是映射问题、背景偏差还是症状混淆。
            predictions.append({
                'path': row['path'], 'source': row['source'], 'source_labels': row.get('source_labels', ''),
                'source_url': row.get('source_url', ''), 'license': row.get('license', ''),
                'region': row.get('region', ''), 'part': row.get('part', ''),
                'group': row.get('group', ''), 'group_status': row.get('group_status', ''),
                'site_hint': row.get('site_hint', ''), 'review': row.get('review', ''),
                'sha256': row['sha256'], 'pixel_sha256': row.get('pixel_sha256', ''),
                'true': predictor.labels[target], 'predicted': predictor.labels[predicted],
                'correct': target == predicted, 'confidence': confidence, 'margin': margin,
                'accepted': predicted not in excluded and confidence >= metadata['threshold'] and margin >= metadata['margin'],
                'scores': json.dumps(dict(zip(predictor.labels, scores[index].tolist()))),
            })
            offset += 1
    accepted = [row for row in predictions if row['accepted']]
    unknown = [row for row in rows if row.get('group', '').lower().strip() in UNKNOWN_GROUPS]
    result = coverage_metrics(matrix, predictor.labels)
    partial = bool(result['missing_labels'])
    result.update({
        'evaluation_role': 'external_development_label_subset' if partial else 'external_development_diagnostic',
        'partial_label_coverage': partial,
        'model_output_labels_unchanged': True,
        'limitation': '仅评估清单中有真实样本的类别，缺少类别未验收；保留完整模型输出。非国内最终田间验收。若据此调参，需要另留独立外测。',
        'images': len(rows), 'unknown_capture_identity_images': len(unknown),
        'known_capture_groups': len({(row['source'], row['group']) for row in rows if row not in unknown}),
        'training_manifest_sha256': metadata['manifest_sha256'],
        'external_manifest_sha256': digest(manifest), 'weights_sha256': digest(bundle / 'weights.pt'),
        'model_metadata_sha256': digest(bundle / 'metadata.json'),
        'model_version': metadata['version'], 'architecture': metadata['architecture'],
        'method': metadata.get('method', 'end_to_end_finetuning'), 'labels': predictor.labels,
        'input_size': metadata['input_size'], 'resize': metadata.get('resize', 'stretch'),
        'nll': total_nll / len(rows), 'elapsed_seconds': perf_counter() - started,
        'sources': {source: coverage_metrics(value, predictor.labels) for source, value in by_source.items()},
        'code_sha256': {name: digest(Path(__file__).with_name(name)) for name in ('external_report.py', 'train.py', 'inference.py', 'augmentation.py')},
        'regions': dict(Counter(row.get('region', '') for row in rows)),
        'source_label_mapping': {label: sorted({row.get('source_labels', '') for row in rows if row['label'] == label}) for label in predictor.labels},
        'fixed_rejection_settings': {key: metadata.get(key, 1.) for key in ('threshold', 'margin', 'temperature')},
        'selective': {'coverage': len(accepted) / len(rows), 'accepted': len(accepted),
                      'accuracy': sum(row['correct'] for row in accepted) / len(accepted) if accepted else None},
        'high_confidence_errors_0_9': sum(not row['correct'] and row['confidence'] >= .9 for row in predictions),
    })
    output.mkdir(parents=True, exist_ok=True)
    (output / 'evaluation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fields = list(predictions[0])
    write_csv(output / 'predictions.csv', predictions, fields)
    errors = sorted((row for row in predictions if not row['correct']), key=lambda row: row['confidence'], reverse=True)
    write_csv(output / 'errors.csv', errors, fields)
    save_confusion(matrix, predictor.labels, output / 'confusion.png')
    print(json.dumps({key: result[key] for key in ('images', 'accuracy', 'macro_f1', 'high_confidence_errors_0_9')}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--allow-partial-labels', action='store_true',
                        help='显式允许只覆盖模型的部分类别；不改变模型输出，不作为完整验收')
    args = parser.parse_args()
    if args.batch_size < 1 or args.threads < 1:
        parser.error('batch-size 和 threads 必须为正数')
    report(args.bundle, args.data_root, args.manifest, args.output, batch_size=args.batch_size, threads=args.threads,
           allow_partial_labels=args.allow_partial_labels)


if __name__ == '__main__':
    main()

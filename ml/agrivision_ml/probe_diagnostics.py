"""用冻结骨干特征重建逐图预测，避免诊断时再次对全部图片前向。

仅分析既有 val/test；不训练、调阈值或校准。分数是未校准 softmax，
不能把高分直接解释成真实田间正确率。划分语义由输入清单决定。
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .linear_probe import backbone_digest, digest, prediction_metrics, replace_head, write_json
from .model import build_model
from .train import read_manifest


def confidence_summary(probabilities, truth, threshold, margin):
    """保留错误的高置信情况；示范阈值只用于统计，不在这里选阈值。"""
    ordered = np.sort(probabilities, axis=1)
    confidence = ordered[:, -1]
    separation = ordered[:, -1] - ordered[:, -2]
    predicted = probabilities.argmax(axis=1)
    correct = predicted == truth
    accepted = (confidence >= threshold) & (separation >= margin)
    bins, ece = [], 0.0
    for index in range(10):
        lower, upper = index / 10, (index + 1) / 10
        selected = (confidence >= lower) & ((confidence <= upper) if index == 9 else (confidence < upper))
        count = int(selected.sum())
        if count:
            average, accuracy = float(confidence[selected].mean()), float(correct[selected].mean())
            ece += count / len(truth) * abs(average - accuracy)
            bins.append({'lower': lower, 'upper': upper, 'images': count,
                         'mean_confidence': average, 'accuracy': accuracy})
    return {
        'calibrated': False, 'temperature': 1.0,
        'mean_confidence': float(confidence.mean()),
        'mean_wrong_confidence': float(confidence[~correct].mean()) if (~correct).any() else None,
        'wrong_at_least_90_percent': int(((~correct) & (confidence >= .9)).sum()),
        'nll': float(-np.log(probabilities[np.arange(len(truth)), truth].clip(1e-12, 1)).mean()),
        'ece_10_bins': ece, 'reliability_bins': bins,
        'illustrative_selection': {'threshold': threshold, 'margin': margin,
                                  'images': int(accepted.sum()), 'coverage': float(accepted.mean()),
                                  'accuracy': float(correct[accepted].mean()) if accepted.any() else None},
    }


@torch.inference_mode()
def diagnose(experiment: Path, manifest: Path, sources: Path | None = None, threads: int = 2):
    """清单、特征缓存和冻结权重对应后，按原读图顺序恢复 val/test 结果。"""
    torch.set_num_threads(threads)
    bundle = experiment / 'bundle'
    metadata = json.loads((bundle / 'metadata.json').read_text(encoding='utf-8'))
    identity = json.loads((experiment / 'features.json').read_text(encoding='utf-8'))
    if identity != metadata['feature_cache'] or digest(manifest) != identity['manifest']:
        raise ValueError('诊断清单或特征标识与模型包不一致')
    if digest(experiment / 'features.npz') != identity['cache_sha256']:
        raise ValueError('特征缓存校验失败')
    labels = metadata['labels']
    model = build_model(metadata['architecture'], len(labels), pretrained=False)
    model.load_state_dict(torch.load(bundle / 'weights.pt', map_location='cpu', weights_only=True))
    head = replace_head(model, metadata['architecture'], nn.Identity())
    if backbone_digest(model) != identity['backbone_sha256']:
        raise ValueError('导出模型的冻结骨干与特征缓存不一致')
    if float(metadata.get('temperature', 1)) != 1:
        raise ValueError('本工具分析未校准线性probe；已校准模型应使用正式评估入口')
    rows = read_manifest(manifest)
    source_rows = {}
    if sources is not None:
        with sources.open(encoding='utf-8-sig', newline='') as stream:
            source_rows = {row['path']: row for row in csv.DictReader(stream)}
    result = {'method': 'cached_frozen_features_exported_linear_head',
              'manifest_sha256': digest(manifest), 'manifest': str(manifest),
              'evaluation_scope': 'manifest-defined validation and holdout; not automatically external field testing',
              'parameters': sum(p.numel() for p in model.parameters()) + sum(p.numel() for p in head.parameters()),
              'fitted_head_parameters': sum(p.numel() for p in head.parameters()),
              'confidence_note': '未校准softmax分数；仅已知类别，不代表未知作物拒识或田间正确率。',
              'splits': {}}
    with np.load(experiment / 'features.npz', allow_pickle=False) as cache:
        for split in ('val', 'test'):
            selected = [row for row in rows if row['split'] == split]
            truth = cache[split + '_y']
            # train 缓存有多遍增强视图；这里只使用各自一遍固定变换的 val/test。
            expected = np.array([labels.index(row['label']) for row in selected])
            if not np.array_equal(truth, expected):
                raise ValueError(f'{split} 特征顺序或标签与清单不一致')
            probabilities = head(torch.from_numpy(cache[split + '_x'])).softmax(1).numpy()
            predicted = probabilities.argmax(1)
            metrics = prediction_metrics(truth, predicted, len(labels))
            predictions = []
            for index, row in enumerate(selected):
                order = np.argsort(-probabilities[index])
                source = source_rows.get(row['path'], {})
                predictions.append({'path': row['path'], 'group': row['group'],
                    'source': source.get('source', 'unknown'), 'country': source.get('country', ''),
                    'true': row['label'], 'predicted': labels[int(order[0])],
                    'correct': bool(predicted[index] == truth[index]),
                    'confidence': float(probabilities[index, order[0]]),
                    'margin': float(probabilities[index, order[0]] - probabilities[index, order[1]]),
                    'top3': '|'.join(labels[int(i)] for i in order[:3])})
            with (experiment / f'predictions-{split}.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
                writer.writeheader()
                writer.writerows(predictions)
            by_source = {}
            for source in sorted({row['source'] for row in predictions}):
                indexes = [i for i, row in enumerate(predictions) if row['source'] == source]
                source_metrics = prediction_metrics(truth[indexes], predicted[indexes], len(labels))
                # 单一来源可能没有全部类别；同时给出实有类别的宏F1，避免把缺类当作全判错。
                present = np.asarray(source_metrics['counts']) > 0
                source_metrics['present_classes'] = [label for label, exists in zip(labels, present) if exists]
                source_metrics['present_class_macro_f1'] = float(np.asarray(source_metrics['f1'])[present].mean())
                by_source[source] = source_metrics
            wrong = [row for row in predictions if not row['correct']]
            confusions = Counter((row['true'], row['predicted']) for row in wrong)
            result['splits'][split] = {**metrics, 'images': len(selected), 'groups': len({r['group'] for r in selected}),
                'labels': labels, 'by_source': by_source,
                'confidence': confidence_summary(probabilities, truth, metadata['threshold'], metadata['margin']),
                'top_confusions': [{'true': a, 'predicted': b, 'images': count} for (a, b), count in confusions.most_common(15)],
                'highest_confidence_errors': sorted(wrong, key=lambda row: row['confidence'], reverse=True)[:20]}
    write_json(experiment / 'probe-diagnostics.json', result)
    print(json.dumps({split: {'accuracy': value['accuracy'], 'macro_f1': value['macro_f1'],
                             'wrong_at_least_90_percent': value['confidence']['wrong_at_least_90_percent']}
                      for split, value in result['splits'].items()}, ensure_ascii=False, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('threads必须大于0')
    diagnose(args.experiment, args.manifest, args.sources, args.threads)


if __name__ == '__main__':
    main()

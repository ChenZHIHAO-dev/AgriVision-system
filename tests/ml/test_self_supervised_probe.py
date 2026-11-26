"""自监督对照必须保留固定分组、原test隔离和内层选头边界。"""
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from ml.agrivision_ml import self_supervised_probe as ssl


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / 'images'
    root.mkdir()
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps({'task': 'crop_identification', 'labels': {'a': 'A', 'b': 'B'}}))
    original = []
    for group in range(4):
        for label in ('a', 'b'):
            name = f'{group}-{label}.jpg'
            original.append({'path': name, 'label': label, 'group': name, 'sha256': name,
                             'split': 'test' if group == 3 else 'val' if group == 2 else 'train'})
    manifest = tmp_path / 'manifest.csv'
    write_rows(manifest, original)
    cv_root = tmp_path / 'cv'
    entries = []
    for number in range(3):
        rows = []
        for row in original[:6]:
            group = int(row['path'][0])
            rows.append({**row, 'split': ('train', 'val', 'test')[(group + number) % 3]})
        path = cv_root / f'fold-{number + 1}/manifest.csv'
        write_rows(path, rows)
        entries.append({'fold': number + 1, 'manifest': str(path.relative_to(cv_root)),
                        'sha256': ssl.probe.digest(path)})
    plan = {'identity': {'manifest_sha256': ssl.probe.digest(manifest)}, 'folds': entries}
    (cv_root / 'folds.json').write_text(json.dumps(plan))
    write_rows(tmp_path / 'sources.csv', [{'path': row['path'], 'source': 'fixture', 'country': 'CN'} for row in original])
    weights = tmp_path / 'weights.pt'
    weights.write_bytes(b'fake encoder weights; tests never download models')
    args = SimpleNamespace(data_root=root, manifest=manifest, cv_root=cv_root, fold=1,
        labels=labels, weights=weights, output=tmp_path / 'experiment', input_size=224,
        views=2, augmentation='light', batch_size=2, threads=1, seed=42,
        c_values=[.1, 1., 10.], benchmark_only=False)
    return args, original


def test_final_test_is_rejected_even_if_fold_hash_is_updated(inputs):
    args, original = inputs
    plan_file = args.cv_root / 'folds.json'
    plan = json.loads(plan_file.read_text())
    path = args.cv_root / plan['folds'][0]['manifest']
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    rows[4] = {**original[6], 'split': 'test'}
    write_rows(path, rows)
    plan['folds'][0]['sha256'] = ssl.probe.digest(path)
    plan_file.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='最终 test'):
        ssl.prepare_fold(args)


def test_patch_size_mismatch_is_rejected_before_loading_weights(inputs):
    args, _ = inputs
    args.input_size = 320
    with pytest.raises(ValueError, match='14 的倍数'):
        ssl.prepare_fold(args)


def test_validation_cannot_use_repeated_augmented_views():
    rows = [{'split': 'val', '_target': 0}, {'split': 'val', '_target': 1}]
    cache = {'val_x': np.zeros((4, 2)), 'val_y': np.array([0, 1, 0, 1])}
    with pytest.raises(ValueError, match='数量或标签顺序'):
        ssl.partition(cache, rows, 'val')


def test_probe_uses_inner_val_for_selection_and_preserves_outer_errors(inputs, monkeypatch):
    args, _ = inputs
    monkeypatch.setattr(ssl, 'build_encoder', lambda *args: torch.nn.Linear(2, 2).eval())

    def features(cache_args, model, rows, labels):
        data = {}
        for split in ('train', 'val', 'test'):
            targets = np.array([labels.index(row['label']) for row in rows if row['split'] == split])
            if split == 'train':
                targets = np.tile(targets, 3)
            vectors = np.eye(2, dtype=np.float32)[targets]
            # 外层故意反转，验证高置信错误仍保留，不可拿它重新挑分类头。
            if split == 'test':
                vectors = vectors[:, ::-1].copy()
            data[split + '_x'], data[split + '_y'] = vectors, targets
        return data

    monkeypatch.setattr(ssl.probe, 'feature_cache', features)
    original_select = ssl.select_head
    calls = []

    def select(training, validation, c_values, classes):
        assert {row['split'] for row in training[2]} == {'train'}
        assert {row['split'] for row in validation[2]} == {'val'}
        calls.append(1)
        return original_select(training, validation, c_values, classes)

    monkeypatch.setattr(ssl, 'select_head', select)
    result = ssl.run(args)
    assert calls == [1]
    assert result['original_final_test_excluded'] == 2
    assert result['val']['accuracy'] == 1
    assert result['test']['accuracy'] == 0
    assert len(result['test']['highest_confidence_errors']) == 2
    assert result['test']['by_source']['fixture']['present_classes'] == ['a', 'b']
    assert result['release_eligible'] is False
    assert (args.output / 'head.npz').exists()
    assert not (args.output / 'bundle').exists()

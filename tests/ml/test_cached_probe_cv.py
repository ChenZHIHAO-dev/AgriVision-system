"""共享冻结特征只省骨干计算，不能省掉折隔离、缓存身份和最终测试隔离。"""
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from ml.agrivision_ml import cached_probe_cv as module


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def toy_rows():
    return [{'path': f'{i}.jpg', 'label': ('a', 'b')[i % 2], 'sha256': f'hash-{i}',
             'group': f'g-{i}', 'split': ('train', 'val', 'test')[i // 2]} for i in range(6)]


def test_augmented_views_only_used_in_training():
    rows = toy_rows()
    features = np.array([[[i], [100 + i], [200 + i]] for i in range(6)], dtype='float32')
    data = {'features': features, 'targets': np.arange(6) % 2}
    train_x, train_y, train_rows = module.split_features(data, rows, rows, 'train')
    assert train_x[:, 0].tolist() == [0, 1, 100, 101, 200, 201]
    assert train_y.tolist() == [0, 1, 0, 1, 0, 1]
    for split, expected in [('val', [2, 3]), ('test', [4, 5])]:
        x, _, selected = module.split_features(data, rows, rows, split)
        assert x[:, 0].tolist() == expected
        assert len(selected) == 2


@pytest.fixture
def cache_inputs(tmp_path, monkeypatch):
    rows = toy_rows()
    args = SimpleNamespace(output=tmp_path / 'output', reuse_probes=tmp_path / 'existing',
        cv_root=tmp_path / 'cv', data_root=tmp_path, manifest=tmp_path / 'original.csv',
        labels=tmp_path / 'labels.json', views=2, augmentation='light', seed=42, batch_size=2)
    previous = {}
    for split in ('train', 'val', 'test'):
        subset = [row for row in rows if row['split'] == split]
        views = 3 if split == 'train' else 1
        previous[split + '_x'] = np.array([[int(row['path'][0]) + v * 100] for v in range(views) for row in subset], dtype='float32')
        previous[split + '_y'] = np.tile([0, 1], views)
    folder = args.reuse_probes / 'swin_t/fold-1'; folder.mkdir(parents=True)
    (folder / 'features.npz').write_bytes(b'valid-existing-cache')
    (folder / 'features.json').write_text('{}')
    monkeypatch.setattr(module.probe, 'validate_source_images', lambda *a: None)
    monkeypatch.setattr(module.probe, 'feature_cache', lambda *a: previous)
    calls = []
    def encode(model, root, selected, labels, size, **kwargs):
        calls.append((kwargs['training'], [row['path'] for row in selected]))
        return np.array([[300 + int(row['path'][0])] for row in selected], dtype='float32'), np.array([0, 1, 0, 1])
    monkeypatch.setattr(module.probe, 'encode', encode)
    return args, rows, calls


def test_existing_clean_and_training_views_are_not_reencoded(cache_inputs):
    args, rows, calls = cache_inputs
    model = torch.nn.Identity()
    data = module.development_cache(args, 'swin_t', model, rows, ['a', 'b'], rows, {'recipe': 1})
    assert calls == [(True, ['2.jpg', '3.jpg', '4.jpg', '5.jpg'])] * 2
    assert data['features'][0, :, 0].tolist() == [0, 100, 200]
    assert data['features'][4, :, 0].tolist() == [4, 304, 304]
    again = module.development_cache(args, 'swin_t', model, rows, ['a', 'b'], rows, {'recipe': 1})
    np.testing.assert_array_equal(data['features'], again['features'])
    assert len(calls) == 2
    provenance = json.loads((args.output / 'swin_t/features.json').read_text())
    assert provenance['encoded_missing_views'] == {'0': 0, '1': 4, '2': 4}
    assert provenance['identity']['entries'][0]['sha256'] == 'hash-0'
    assert provenance['view_provenance'][4][0]['origin'] == 'existing_fold1_cache'


def test_feature_bytes_or_identity_change_blocks_reuse(cache_inputs):
    args, rows, _ = cache_inputs
    model = torch.nn.Identity()
    module.development_cache(args, 'swin_t', model, rows, ['a', 'b'], rows, {'recipe': 1})
    with pytest.raises(ValueError, match='缓存身份'):
        module.development_cache(args, 'swin_t', model, rows, ['a', 'b'], rows, {'recipe': 2})
    path = args.output / 'swin_t/features.npz'
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='缓存身份'):
        module.development_cache(args, 'swin_t', model, rows, ['a', 'b'], rows, {'recipe': 1})


def test_plan_keeps_original_test_outside_all_folds(tmp_path):
    original = [{'path': f'{i}.jpg', 'label': ('a', 'b')[i % 2], 'sha256': f'hash-{i}',
        'group': f'g-{i}', 'split': 'train' if i < 4 else 'val' if i < 8 else 'test'} for i in range(10)]
    args = SimpleNamespace(manifest=tmp_path / 'manifest.csv', cv_root=tmp_path / 'cv')
    write_rows(args.manifest, original)
    plan = {'identity': {'manifest_sha256': module.probe.digest(args.manifest)}, 'folds': []}
    for number, outer in enumerate(({0, 1, 2, 3}, {4, 5, 6, 7}), 1):
        remaining = sorted(set(range(8)) - outer)
        rows = [{**r, 'split': 'test' if i in outer else 'train' if i in remaining[:2] else 'val'} for i, r in enumerate(original[:8])]
        path = args.cv_root / f'folds/fold-{number}/manifest.csv'; write_rows(path, rows)
        plan['folds'].append({'fold': number, 'manifest': path.relative_to(args.cv_root).as_posix(), 'sha256': module.probe.digest(path)})
    module.probe.write_json(args.cv_root / 'folds.json', plan)
    _, development, folds, _ = module.load_plan(args, ['a', 'b'])
    assert len(development) == 8 and len(folds) == 2
    bad_path = args.cv_root / plan['folds'][0]['manifest']
    bad = module.read_manifest(bad_path)
    bad[0] = {**original[8], 'split': 'test'}
    write_rows(bad_path, bad)
    plan['folds'][0]['sha256'] = module.probe.digest(bad_path)
    module.probe.write_json(args.cv_root / 'folds.json', plan)
    with pytest.raises(ValueError, match='最终 test'):
        module.load_plan(args, ['a', 'b'])


def test_final_refit_failure_is_recorded_without_auto_activation_and_not_retested(tmp_path, monkeypatch):
    original = toy_rows(); development = original[:4]
    clean = np.array([[-2., 0.], [2., 0.], [-2., 0.], [2., 0.]], dtype='float32')
    values = {'features': clean[:, None, :].repeat(3, axis=1), 'targets': np.array([0, 1, 0, 1])}
    manifest = tmp_path / 'manifest.csv'; write_rows(manifest, original)
    args = SimpleNamespace(output=tmp_path / 'out', data_root=tmp_path, manifest=manifest,
        batch_size=2, c_values=[.1, 1.], min_test_accuracy=.90, min_test_macro_f1=.90,
        augmentation='light', seed=42)
    calls = []
    def encode(model, root, rows, labels, size, **kwargs):
        calls.append([r['path'] for r in rows])
        # 最终测试故意与训练方向相反，确保失败时不改标签、不重选C。
        return np.array([[2., 0.], [-2., 0.]], dtype='float32'), np.array([0, 1])
    monkeypatch.setattr(module.probe, 'encode', encode)
    monkeypatch.setattr(module.probe, 'install_head', lambda model, *a: model)
    monkeypatch.setattr(module, 'save_confusion', lambda matrix, labels, path: path.write_bytes(b'plot'))
    config = {'crop': 'peanut', 'labels': {'a': 'A', 'b': 'B'}}
    model = torch.nn.Linear(2, 2)
    result = module.final_refit(args, 'swin_t', model, values, development, original, ['a', 'b'], config, {'r': 1})
    assert calls == [['4.jpg', '5.jpg']]
    assert result['test']['accuracy'] == 0.
    assert result['internal_acceptance_passed'] is False
    metadata = json.loads((args.output / 'final-refit/bundle/metadata.json').read_text())
    assert metadata['development_only'] is False
    assert metadata['development_ready'] is False
    assert metadata['manifest_sha256'] == module.probe.digest(manifest)
    again = module.final_refit(args, 'swin_t', model, values, development, original, ['a', 'b'], config, {'r': 1})
    assert again == result and len(calls) == 1
    with pytest.raises(ValueError, match='最终测试已经使用'):
        module.final_refit(args, 'swin_t', model, values, development, original, ['a', 'b'], config, {'r': 2})

@pytest.mark.parametrize("field", ["min_test_accuracy", "min_test_macro_f1"])
@pytest.mark.parametrize("value", [.89, 1.01, float("nan")])
@pytest.mark.parametrize("entry", ["run", "final_refit"])
def test_direct_entry_rejects_lowered_or_invalid_acceptance_before_io(field, value, entry):
    # 仅提供验收字段；若先做数据IO/训练，会因缺少其它字段而失败。
    args = SimpleNamespace(min_test_accuracy=.90, min_test_macro_f1=.90)
    setattr(args, field, value)
    with pytest.raises(ValueError, match=".90"):
        if entry == "run":
            module.run(args)
        else:
            module.final_refit(args, None, None, None, None, None, None, None, None)


@pytest.mark.parametrize("value", [.90, .98, 1.])
def test_acceptance_threshold_can_be_made_stricter(value):
    module.validate_acceptance_thresholds(SimpleNamespace(min_test_accuracy=value, min_test_macro_f1=value))


def cli_args():
    result = ["cached_probe_cv"]
    for name in ("data-root", "manifest", "labels", "cv-root", "reuse-probes", "output"):
        result.extend(["--" + name, "unused-test-path"])
    return result


def test_cli_rejects_lowering_acceptance_before_run(monkeypatch):
    monkeypatch.setattr("sys.argv", cli_args() + ["--min-test-accuracy", ".89"])
    monkeypatch.setattr(module, "run", lambda _: pytest.fail("must reject before starting an experiment"))
    with pytest.raises(SystemExit) as failure:
        module.main()
    assert failure.value.code == 2


def test_cli_defaults_are_90_percent(monkeypatch):
    seen = []
    monkeypatch.setattr("sys.argv", cli_args())
    monkeypatch.setattr(module, "run", seen.append)
    module.main()
    assert seen[0].min_test_accuracy == .90
    assert seen[0].min_test_macro_f1 == .90

"""交叉验证边界：原测试隔离、采集组完整、外层样本仅评估一次。"""
from collections import Counter

import pytest

from ml.agrivision_ml.cross_validation import check_partition, make_folds


def sample_rows():
    rows = []
    for label in ('a', 'b'):
        for group in range(40):
            split = 'test' if group >= 36 else ('val' if group >= 28 else 'train')
            for view in range(2):
                key = f'{label}-{group}-{view}'
                rows.append(dict(path=key+'.jpg', label=label, group=f'{label}-{group}', sha256=key, split=split))
    return rows


def test_outer_folds_preserve_groups_and_exclude_original_test():
    rows = sample_rows()
    folds = make_folds(rows, folds=3, inner_folds=3)
    original_test = {r['path'] for r in rows if r['split'] == 'test'}
    heldout = Counter()
    for fold in folds:
        assert not original_test.intersection(r['path'] for r in fold)
        check_partition(fold, {'a', 'b'})
        heldout.update(r['path'] for r in fold if r['split'] == 'test')
    assert set(heldout) == {r['path'] for r in rows if r['split'] != 'test'}
    assert set(heldout.values()) == {1}
    assert folds == make_folds(rows, folds=3, inner_folds=3)


def test_reject_duplicate_bytes_across_fold_subsets():
    rows = [{'path': str(i), 'label': 'a', 'group': str(i), 'sha256': 'same', 'split': split}
            for i, split in enumerate(('train', 'val', 'test'))]
    with pytest.raises(ValueError, match='sha256'):
        check_partition(rows, {'a'})


def test_independent_groups_not_augmented_image_count_determine_fold_feasibility():
    rows = [row for row in sample_rows() if row['split'] != 'test']
    for row in rows:
        row['group'] = row['label']
    with pytest.raises(ValueError, match='独立组数不足'):
        make_folds(rows, folds=3)


def test_manual_links_keep_existing_capture_groups_together():
    rows = sample_rows()
    links = [('a-0-0.jpg', 'a-1-0.jpg'), ('a-1-1.jpg', 'a-2-0.jpg')]
    original = [dict(row) for row in rows]
    for fold in make_folds(rows, folds=3, inner_folds=3, group_links=links):
        linked = [row for row in fold if row['path'].startswith(('a-0-', 'a-1-', 'a-2-'))]
        assert len(linked) == 6
        assert len({row['split'] for row in linked}) == 1
        assert len({row['group'] for row in linked}) == 1
    assert rows == original


def test_manual_link_to_original_test_excludes_the_whole_connected_group():
    rows = sample_rows()
    links = [('a-0-0.jpg', 'a-1-0.jpg'), ('a-1-1.jpg', 'a-36-0.jpg')]
    for fold in make_folds(rows, folds=3, inner_folds=3, group_links=links):
        assert not any(row['path'].startswith(('a-0-', 'a-1-', 'a-36-')) for row in fold)
        assert len(fold) == sum(row['split'] != 'test' for row in rows) - 4


def test_exact_duplicates_in_different_old_groups_are_merged_before_cv():
    rows = sample_rows()
    rows[2]['sha256'] = rows[0]['sha256']
    for fold in make_folds(rows, folds=3, inner_folds=3):
        linked = [row for row in fold if row['path'].startswith(('a-0-', 'a-1-'))]
        assert len({row['split'] for row in linked}) == 1


def test_manual_link_with_unknown_path_is_rejected():
    with pytest.raises(ValueError, match='路径不在清单'):
        make_folds(sample_rows(), folds=3, inner_folds=3,
                   group_links=[('missing.jpg', 'a-0-0.jpg')])


@pytest.fixture
def cv_job(tmp_path):
    import csv
    import json
    from types import SimpleNamespace
    from ml.agrivision_ml import cross_validation as cv

    manifest = tmp_path / 'manifest.csv'
    rows = sample_rows()
    with manifest.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=cv.FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with (tmp_path / 'sources.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=('path', 'source'))
        writer.writeheader()
        writer.writerows({'path': row['path'], 'source': 'fixture'} for row in rows)
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps({'labels': {'a': 'a', 'b': 'b'}}), encoding='utf-8')
    output = tmp_path / 'cv'
    plan = cv.prepare(manifest, output, folds=3, inner_folds=3)
    # 此 fixture 只模拟一个任务的恢复过程，不执行真实训练；分折完整性另有测试覆盖。
    plan = {**plan, 'folds': plan['folds'][:1]}
    args = SimpleNamespace(
        data_root=tmp_path, manifest=manifest, labels=labels, output=output,
        architectures=['swin_t'], epochs=2, patience=1, batch_size=16,
        augmentation='light', class_weight_power=1., seed=42, precision='bf16', device='cuda',
    )
    return args, plan


def fake_process(command, **kwargs):
    """写入训练 / 评估入口承诺的最小产物，不创建模型、不读取图像。"""
    import json
    from pathlib import Path
    from ml.agrivision_ml import cross_validation as cv

    def option(name):
        return command[command.index(name) + 1]

    module = command[2]
    bundle = Path(option('--output' if module.endswith('.train') else '--bundle'))
    if module.endswith('.train'):
        bundle.mkdir(parents=True)
        (bundle / 'weights.pt').write_bytes(b'test-only-weights')
        (bundle / 'training.json').write_text('[{"epoch": 1}]', encoding='utf-8')
        metadata = {
            'manifest_sha256': cv.digest(Path(option('--manifest'))),
            'architecture': option('--architecture'), 'input_size': int(option('--input-size')),
        }
        (bundle / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    elif module.endswith('.experiment_report'):
        result = cv.metrics(cv.np.array([[2, 0], [0, 2]]))
        (bundle / 'evaluation-test.json').write_text(json.dumps(result), encoding='utf-8')


def test_changed_recipe_cannot_reuse_old_completed_fold(cv_job, monkeypatch):
    from ml.agrivision_ml import cross_validation as cv
    args, plan = cv_job
    monkeypatch.setattr(cv.subprocess, 'run', fake_process)
    cv.run(args, plan)
    monkeypatch.setitem(cv.RECIPES, 'swin_t', 384)
    monkeypatch.setattr(cv.subprocess, 'run', lambda *a, **kw: pytest.fail('must reject before training'))
    with pytest.raises(ValueError, match='已有结果配置不同'):
        cv.run(args, plan)


def test_changed_inner_split_setting_cannot_reuse_old_completed_fold(cv_job, monkeypatch):
    from ml.agrivision_ml import cross_validation as cv
    args, plan = cv_job
    monkeypatch.setattr(cv.subprocess, 'run', fake_process)
    cv.run(args, plan)
    plan['identity'] = {**plan['identity'], 'inner_folds': 4}
    with pytest.raises(ValueError, match='已有结果配置不同'):
        cv.run(args, plan)


def test_failed_calibration_resumes_after_successful_training(cv_job, monkeypatch):
    import subprocess
    from ml.agrivision_ml import cross_validation as cv
    args, plan = cv_job
    calls = []

    def fail_calibration(command, **kwargs):
        calls.append(command[2])
        if command[2].endswith('.calibrate'):
            raise subprocess.CalledProcessError(1, command)
        fake_process(command, **kwargs)

    monkeypatch.setattr(cv.subprocess, 'run', fail_calibration)
    with pytest.raises(subprocess.CalledProcessError):
        cv.run(args, plan)
    folder = args.output / 'swin_t/fold-1'
    assert (folder / 'training-complete.json').exists()
    assert not (folder / 'result.json').exists()
    calls.clear()

    def resume(command, **kwargs):
        calls.append(command[2])
        fake_process(command, **kwargs)

    monkeypatch.setattr(cv.subprocess, 'run', resume)
    cv.run(args, plan)
    assert calls == ['ml.agrivision_ml.calibrate', 'ml.agrivision_ml.experiment_report']
    assert (folder / 'result.json').exists()
    calls.clear()
    cv.run(args, plan)
    assert calls == []


def test_interrupted_training_is_not_treated_as_completed(cv_job, monkeypatch):
    import subprocess
    from ml.agrivision_ml import cross_validation as cv
    args, plan = cv_job

    def interrupted(command, **kwargs):
        fake_process(command, **kwargs)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(cv.subprocess, 'run', interrupted)
    with pytest.raises(subprocess.CalledProcessError):
        cv.run(args, plan)
    assert not (args.output / 'swin_t/fold-1/training-complete.json').exists()
    monkeypatch.setattr(cv.subprocess, 'run', lambda *a, **kw: pytest.fail('must not overwrite checkpoint'))
    with pytest.raises(ValueError, match='训练中断'):
        cv.run(args, plan)


def test_prepare_records_manual_links_and_excludes_test_related_development(cv_job):
    from ml.agrivision_ml import cross_validation as cv
    args, _ = cv_job
    links = args.manifest.parent / 'confirmed.csv'
    links.write_text('left,right\na-0-0.jpg,a-36-0.jpg\n', encoding='utf-8')
    output = args.output / 'manual-links'
    plan = cv.prepare(args.manifest, output, folds=3, inner_folds=3, group_links=links)
    assert plan['identity']['group_links_sha256'] == cv.digest(links)
    assert plan['excluded_test_group_development_images'] == 2
    assert plan['confirmed_group_links'] == 1
    links.write_text('left,right\na-1-0.jpg,a-36-0.jpg\n', encoding='utf-8')
    with pytest.raises(ValueError, match='不同数据'):
        cv.prepare(args.manifest, output, folds=3, inner_folds=3, group_links=links)

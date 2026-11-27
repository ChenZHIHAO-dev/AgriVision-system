"""最终留出隔离与独立管理员预览发布；不改原开发折身份。"""
import csv
import json

import pytest

from ml.agrivision_ml import internal_preview as preview


def write_rows(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'label', 'sha256', 'group', 'split'])
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def candidate(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    original = []
    for index in range(8):
        original.append({'path': f'{index}.png', 'label': ['a', 'b'][index % 2],
                         'sha256': f'hash-{index}', 'group': f'group-{index}',
                         'split': 'train' if index < 4 else 'val' if index < 6 else 'test'})
    development = [{**row, 'split': ['train', 'val', 'test'][i // 2]}
                   for i, row in enumerate(original[:6])]
    original_path = tmp_path / 'original.csv'; write_rows(original_path, original)
    development_path = tmp_path / 'development.csv'; write_rows(development_path, development)
    metadata = {'task': 'crop_identification', 'labels': ['a', 'b'], 'version': 'dev-fold',
                'development_only': True, 'validated': False, 'threshold': .95, 'margin': .25,
                'temperature': .9, 'manifest_sha256': preview.digest(development_path)}
    (source / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    (source / 'weights.pt').write_bytes(b'test-only-unloaded-model')
    return source, original_path, development_path, original, development


def test_holdout_excludes_every_development_subset(candidate):
    source, original, development, *_ = candidate
    _, rows, identity = preview.audit_holdout(source, original, development)
    assert [row['path'] for row in rows] == ['6.png', '7.png']
    assert identity['holdout_images'] == 2
    assert identity['overlap_path_sha_group'] == 0
    assert identity['source_development_only'] is True


def test_holdout_cannot_be_inserted_into_outer_model_selection(candidate):
    source, original_path, development_path, original, development = candidate
    development[-2:] = [{**row, 'split': 'test'} for row in original[-2:]]
    write_rows(development_path, development)
    metadata_path = source / 'metadata.json'
    metadata = json.loads(metadata_path.read_text())
    metadata['manifest_sha256'] = preview.digest(development_path)
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='交叉'):
        preview.audit_holdout(source, original_path, development_path)


def test_changed_development_manifest_rejected(candidate):
    source, original_path, development_path, _, development = candidate
    development[0]['label'] = 'b'
    # 同时更新另一张标签，保持每个子集类别齐全，仅改变清单身份。
    development[1]['label'] = 'a'
    write_rows(development_path, development)
    with pytest.raises(ValueError, match='清单'):
        preview.audit_holdout(source, original_path, development_path)


@pytest.mark.parametrize('accuracy', [.929, .93])
def test_preview_gate_and_provenance_without_mutating_source(candidate, tmp_path, accuracy):
    source, original_path, development_path, *_ = candidate
    original_bytes = (source / 'metadata.json').read_bytes()
    _, _, identity = preview.audit_holdout(source, original_path, development_path)
    report = {'accuracy': accuracy, 'macro_f1': .94, 'counts': [20, 20],
              'recall': [.9, .95], 'source_identity': identity}
    report_path = tmp_path / 'evaluation.json'
    report_path.write_text(json.dumps(report), encoding='utf-8')
    output = tmp_path / 'crop-identification'
    if accuracy < .93:
        with pytest.raises(ValueError, match='Activation requires'):
            preview.export_preview(source, output, report, report_path)
        assert not output.exists()
    else:
        metadata = preview.export_preview(source, output, report, report_path)
        assert metadata['validated'] is metadata['field_verified'] is False
        assert metadata['release_stage'] == 'admin_internal_preview'
        assert metadata['development_only'] is False
        assert metadata['source_development_only'] is metadata['development_ready'] is True
        assert metadata['preview_release']['source_identity'] == identity
        assert metadata['threshold'] == .95 and metadata['temperature'] == .9
        assert preview.digest(output / 'weights.pt') == identity['source_weights_sha256']
        assert (output / 'evaluation-holdout.json').read_bytes() == report_path.read_bytes()
        with pytest.raises(FileExistsError):
            preview.export_preview(source, output, report, report_path)
    assert (source / 'metadata.json').read_bytes() == original_bytes


def test_export_rejects_weights_changed_since_evaluation(candidate, tmp_path):
    source, original_path, development_path, *_ = candidate
    _, _, identity = preview.audit_holdout(source, original_path, development_path)
    report = {'accuracy': .94, 'macro_f1': .94, 'counts': [20, 20],
              'recall': [.9, .95], 'source_identity': identity}
    (source / 'weights.pt').write_bytes(b'changed')
    with pytest.raises(ValueError, match='源模型改变'):
        preview.export_preview(source, tmp_path / 'export', report, tmp_path / 'report.json')
    assert not (tmp_path / 'export').exists()

"""外域诊断必须保留真实数据身份，并排除混合病症和待排除图片。"""
import csv
import json
from types import SimpleNamespace

from PIL import Image
import pytest
import torch

from ml.agrivision_ml import external_report


@pytest.fixture
def external_input(tmp_path):
    rows = []
    for index, label in enumerate(('a', 'b')):
        image = tmp_path / f'{label}.png'
        Image.new('RGB', (16, 16), (50 + index * 30, 80, 90)).save(image)
        rows.append({'path': image.name, 'label': label, 'source': 'field-source',
                     'source_labels': f'original-{label}', 'labels_json': json.dumps([label]),
                     'group': 'unknown', 'review': 'review', 'region': 'external'})
    manifest = tmp_path / 'external.csv'

    def write(values):
        with manifest.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(values)
    write(rows)
    return tmp_path, manifest, rows, write


def test_external_rows_preserve_unknown_identity_and_original_labels(external_input):
    root, manifest, _, _ = external_input
    before = manifest.read_bytes()
    rows = external_report.read_external_rows(manifest, root, ['a', 'b'])
    assert rows[0]['source_labels'] == 'original-a'
    assert all(row['group'] == 'unknown' for row in rows)
    assert all(len(row['sha256']) == 64 for row in rows)
    assert manifest.read_bytes() == before


@pytest.mark.parametrize('change,error', [
    ({'labels_json': '["a", "b"]'}, '混合病症'),
    ({'review': 'hold'}, 'hold/drop'),
    ({'label': 'unsupported'}, '不支持'),
    ({'path': '../escape.png'}, '越过'),
])
def test_external_rows_reject_unusable_inputs(external_input, change, error):
    root, manifest, rows, write = external_input
    rows[0].update(change)
    write(rows)
    with pytest.raises(ValueError, match=error):
        external_report.read_external_rows(manifest, root, ['a', 'b'])


def test_diagnostic_keeps_training_identity_and_writes_traceable_errors(external_input, monkeypatch):
    root, manifest, _, _ = external_input
    bundle = root / 'bundle'
    bundle.mkdir()
    (bundle / 'weights.pt').write_bytes(b'test-only-weights')
    metadata = {'input_size': 16, 'resize': 'letterbox', 'temperature': 1.,
                'threshold': .7, 'margin': .12, 'manifest_sha256': 'original-training-hash',
                'version': 'test', 'architecture': 'swin_t', 'labels': ['a', 'b']}
    (bundle / 'metadata.json').write_text(json.dumps(metadata))
    model = lambda images: torch.tensor([[4., 0.]]).repeat(len(images), 1)
    monkeypatch.setattr(external_report, 'Predictor', lambda *_: SimpleNamespace(
        labels=['a', 'b'], metadata=metadata, model=model))
    monkeypatch.setattr(external_report, 'save_confusion', lambda matrix, labels, path: path.write_bytes(b'plot'))
    before = (bundle / 'metadata.json').read_bytes()
    result = external_report.report(bundle, root, manifest, root / 'diagnostic', threads=1)
    assert result['accuracy'] == .5
    assert result['training_manifest_sha256'] == 'original-training-hash'
    assert result['external_manifest_sha256'] == external_report.digest(manifest)
    assert result['evaluation_role'] == 'external_development_diagnostic'
    assert result['known_capture_groups'] == 0
    assert result['unknown_capture_identity_images'] == 2
    assert result['high_confidence_errors_0_9'] == 1
    assert (bundle / 'metadata.json').read_bytes() == before
    with (root / 'diagnostic/errors.csv').open(encoding='utf-8-sig') as stream:
        errors = list(csv.DictReader(stream))
    assert len(errors) == 1
    assert errors[0]['source_labels'] == 'original-b'
    assert errors[0]['true'] == 'b' and errors[0]['predicted'] == 'a'

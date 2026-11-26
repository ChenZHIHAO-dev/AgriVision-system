"""玉米/花生筛选入口：来源限制、人工决定和复用预处理的行为回归测试。"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from ml.agrivision_ml.preprocessing import crop_review
from ml.agrivision_ml.preprocessing.tables import read_rows, write_rows

AUDIT_FIELDS = ('path', 'source', 'source_label', 'label', 'review', 'group', 'license',
                'region', 'part', 'group_status', 'collection_group', 'pixel_sha256',
                'derived_image_hint', 'reason', 'error', 'duplicate_of')


@pytest.fixture
def source_inputs(tmp_path):
    root = tmp_path
    (root / 'configs/datasets').mkdir(parents=True)
    (root / 'configs/labels').mkdir(parents=True)
    review = root / 'data/maize/review'
    review.mkdir(parents=True)
    sources = [
        {'id': 'author', 'crop': 'maize', 'default_review': 'review', 'license': 'CC BY 4.0',
         'url': 'https://example.org/author', 'label_map': {'gray': 'maize_gray_leaf_spot', 'healthy': 'healthy'}},
        {'id': 'second', 'crop': 'maize', 'default_review': 'review',
         'label_map': {'healthy': 'healthy', 'gray': 'maize_gray_leaf_spot'}},
        {'id': 'derived-source', 'crop': 'maize', 'default_review': 'hold',
         'hold_reason': '既有增强图缺少母图映射', 'label_map': {'healthy': 'healthy'}},
    ]
    (root / 'configs/datasets/maize-peanut.json').write_text(json.dumps({'sources': sources}), encoding='utf-8')
    (root / 'configs/labels/maize.json').write_text(
        json.dumps({'crop': 'maize', 'labels': {'maize_gray_leaf_spot': '玉米灰斑病', 'healthy': '健康参考'}}), encoding='utf-8')
    rows = []
    for label_index, source_label in enumerate(['gray', 'healthy']):
        for index in range(4):
            relative = f'data/maize/sources/author/raw/{source_label}-{index}.jpg'
            file = root / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            image = np.random.default_rng(label_index * 100 + index).integers(0, 255, (100, 140, 3), dtype=np.uint8)
            Image.fromarray(image).save(file)
            rows.append({'path': relative, 'source': 'author', 'source_label': source_label,
                         'label': 'healthy' if source_label == 'healthy' else 'maize_gray_leaf_spot',
                         'review': 'review', 'group': 'unknown', 'part': 'leaf', 'license': 'CC BY 4.0',
                         'region': 'test', 'group_status': 'capture_identity_unknown',
                         'collection_group': 'field-1', 'pixel_sha256': 'not-a-file-hash'})
    write_rows(review / 'source-audit.csv', AUDIT_FIELDS, rows)
    return root, rows


def test_default_only_creates_pending_review_with_relative_paths(source_inputs):
    root, _ = source_inputs
    review, labels, rows = crop_review.sync_review(root, 'maize')
    assert len(rows) == 8
    assert {row['decision'] for row in rows} == {''}
    assert {row['group'] for row in rows} == {''}
    assert {row['sha256'] for row in rows} == {''}
    assert {row['collection_group'] for row in rows} == {'field-1'}
    assert all(row['path'].startswith('../sources/author/') for row in rows)
    assert not crop_review.select_with_basis(review, labels, rows).photos
    assert not (root / 'data/maize/prepared').exists()


def test_accept_author_labels_does_not_override_holds_or_manual_drop(source_inputs):
    root, audit = source_inputs
    review, _, rows = crop_review.sync_review(root, 'maize')
    rows[0]['decision'], rows[0]['note'] = 'drop', '手工发现水印'
    rows[1]['decision'], rows[1]['group'] = 'keep', 'manual-plant-1'
    write_rows(review, crop_review.REVIEW_FIELDS, rows)
    for index, override in enumerate([
        {'source': 'derived-source'},
        {'source_label': 'unlabelled'},
        {'review': 'hold'},
        {'derived_image_hint': 'yes_filename_dr'},
        {'duplicate_of': 'earlier-photo'},
    ]):
        audit.append({**audit[-1], 'path': f'data/maize/sources/{override.get("source", "author")}/raw/blocked-{index}.jpg',
                      'source_label': 'healthy', **override})
    write_rows(root / 'data/maize/review/source-audit.csv', AUDIT_FIELDS, audit)
    _, labels, merged = crop_review.sync_review(root, 'maize', accept_source_labels=True)
    by_path = {row['path']: row for row in merged}
    assert by_path[rows[0]['path']]['decision'] == 'drop'
    assert by_path[rows[0]['path']]['note'] == '手工发现水印'
    assert by_path[rows[1]['path']]['group'] == 'manual-plant-1'
    assert by_path[rows[1]['path']]['review_basis'] == 'manual_keep'
    blocked = [row for row in merged if 'blocked-' in row['path']]
    assert len(blocked) == 5
    assert all(row['decision'] == 'drop' and row['exclusion_reason'] for row in blocked)
    selection = crop_review.select_with_basis(review, labels, merged)
    assert len(selection.photos) == 7
    assert all('review_basis=' in photo.note for photo in selection.photos)
    assert any(crop_review.INTERNAL_BASIS in photo.note for photo in selection.photos)


def test_source_filter_preserves_other_decisions_and_removed_rows_are_excluded(source_inputs):
    root, audit = source_inputs
    other = {**audit[0], 'source': 'second', 'path': 'data/maize/sources/second/raw/gray.jpg'}
    audit.append(other)
    audit_path = root / 'data/maize/review/source-audit.csv'
    write_rows(audit_path, AUDIT_FIELDS, audit)
    review, _, rows = crop_review.sync_review(root, 'maize', accept_source_labels=True)
    rows[-1]['note'] = '第二来源备注'
    write_rows(review, crop_review.REVIEW_FIELDS, rows)
    removed_path = '../sources/author/raw/gray-0.jpg'
    write_rows(audit_path, AUDIT_FIELDS, audit[1:])
    _, _, merged = crop_review.sync_review(root, 'maize', sources=['author'])
    assert next(row for row in merged if row['source'] == 'second')['note'] == '第二来源备注'
    removed = next(row for row in merged if row['path'] == removed_path)
    assert removed['decision'] == 'drop'
    assert '已找不到' in removed['exclusion_reason']


def test_explicit_output_reuses_pipeline_and_exports_the_correct_crop(source_inputs, monkeypatch):
    root, _ = source_inputs
    monkeypatch.setattr(crop_review, 'ROOT', root)
    output = root / 'data/maize/prepared'
    crop_review.main(['--crop', 'maize', '--accept-source-labels', '--check', '--output', str(output)])
    assert not output.exists()
    crop_review.main(['--crop', 'maize', '--output', str(output)])
    labels = json.loads((output / 'labels.json').read_text(encoding='utf-8'))
    assert labels['crop'] == 'maize'
    assert set(labels['labels']) == {'maize_gray_leaf_spot', 'healthy'}
    sources = read_rows(output / 'sources.csv')
    assert len(sources) == 8
    assert all(row['source_group'] == '' for row in sources)
    assert all(crop_review.INTERNAL_BASIS in row['note'] for row in sources)
    assert all(row['license'] == 'CC BY 4.0' for row in sources)
    manifest_before = (output / 'manifest.csv').read_bytes()
    with pytest.raises(SystemExit):
        crop_review.main(['--crop', 'maize', '--output', str(output)])
    assert (output / 'manifest.csv').read_bytes() == manifest_before

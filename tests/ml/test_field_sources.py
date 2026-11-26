"""保护外部田间数据的断点完整性和多病标签语义，不调用网络或训练。"""
import csv
import hashlib
import json
import sys

import httpx
import pytest
from PIL import Image

from ml.agrivision_ml.preprocessing import figshare_source, pretoria_field, source_collection


def test_range_download_resumes_prefix_and_verifies_official_md5(tmp_path):
    content = b'a' * (20 * 1024 * 1024) + b'b' * 1024
    target = tmp_path / 'field.zip'
    target.with_suffix('.zip.part').write_bytes(content[:20 * 1024 * 1024])
    requests = []
    def handler(request):
        requested = request.headers['Range']
        requests.append(requested)
        start, end = map(int, requested.removeprefix('bytes=').split('-'))
        return httpx.Response(206, headers={'Content-Range': f'bytes {start}-{end}/{len(content)}'},
                              content=content[start:end + 1])
    record = {'id': 1, 'size': len(content), 'computed_md5': hashlib.md5(content).hexdigest(),
              'download_url': 'https://example.test/file'}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        figshare_source.download_resumable(client, record, target)
    assert requests == [f'bytes={20 * 1024 * 1024}-{len(content) - 1}']
    assert target.read_bytes() == content
    assert not target.with_suffix('.zip.part').exists()
    assert json.loads(target.with_suffix('.zip.resume.json').read_text())['complete']


def test_wrong_range_does_not_publish_download(tmp_path):
    target = tmp_path / 'field.zip'
    record = {'id': 1, 'size': 4, 'computed_md5': hashlib.md5(b'data').hexdigest(),
              'download_url': 'https://example.test/file'}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'data'))) as client:
        with pytest.raises(RuntimeError, match='分段未完成'):
            figshare_source.download_resumable(client, record, target, workers=1)
    assert not target.exists()
    assert target.with_suffix('.zip.part').exists()


def test_field_audit_preserves_multilabel_and_separates_conflicts(tmp_path, monkeypatch):
    source = tmp_path / 'data/maize/sources' / pretoria_field.SOURCE_ID
    (source / 'metadata').mkdir(parents=True)
    (source / 'raw/leaf_images').mkdir(parents=True)
    cases = [(['GLS'], 'green'), (['GLS', 'CR'], 'red'),
             (['NoFoliarSymptoms', 'NCLB'], 'blue'), (['UnidentifiedDisease'], 'yellow'),
             (['NoFoliarSymptoms'], 'white'), (['CR'], 'white')]
    with (source / 'metadata/Database.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['imgID_id', 'filePath', *pretoria_field.LABELS])
        writer.writeheader()
        for i, (active, color) in enumerate(cases):
            name = f'{i}.jpg'
            writer.writerow({'imgID_id': i, 'filePath': name,
                             **{key: int(key in active) for key in pretoria_field.LABELS}})
            Image.new('RGB', (30, 20), color).save(source / 'raw/leaf_images' / name)
    monkeypatch.setattr(pretoria_field, 'ROOT', tmp_path)
    monkeypatch.setattr(source_collection, 'ROOT', tmp_path)
    report = pretoria_field.audit()
    output = tmp_path / 'data/maize/evaluation'
    with (output / 'pretoria-field.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[1]['label'] == ''
    assert json.loads(rows[1]['labels_json']) == ['maize_gray_leaf_spot', 'maize_common_rust']
    assert rows[1]['evaluation_role'] == 'multi_label'
    assert rows[2]['review'] == 'hold'
    assert rows[2]['evaluation_role'] == 'annotation_conflict'
    assert rows[3]['evaluation_role'] == 'out_of_scope'
    # 同像素不同标签，连读取顺序最前的健康图也不能进入外测。
    assert rows[4]['review'] == rows[5]['review'] == 'hold'
    assert report['pixel_label_conflict_groups'] == 1
    assert report['pixel_label_conflict_images'] == 2
    assert {row['split'] for row in rows} == {'external'}
    with (output / 'pretoria-field-single-supported.csv').open(encoding='utf-8-sig', newline='') as stream:
        strict = list(csv.DictReader(stream))
    assert len(strict) == 1 and strict[0]['split'] == 'test'
    assert strict[0]['source_split'] == 'external'
    assert report['decode_errors'] == 0

    # 后续发现与训练来源重图时，外测候选必须移除，空结果也不能残留旧CSV。
    existing = tmp_path / 'data/maize/review/source-audit.csv'
    existing.parent.mkdir(parents=True)
    with existing.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['source', 'path', 'pixel_sha256'])
        writer.writeheader()
        writer.writerow({'source': 'training-source', 'path': 'data/maize/sources/old.jpg',
                         'pixel_sha256': rows[0]['pixel_sha256']})
    updated = pretoria_field.audit()
    assert updated['cross_source_pixel_duplicates'] == 1
    assert updated['strict_single_supported_after_quality_check'] == 0
    with (output / 'pretoria-field-single-supported.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.DictReader(stream)) == []


def test_figshare_catalog_entry_dispatches_versioned_download(tmp_path, monkeypatch):
    source = {'id': 'field-source', 'crop': 'maize', 'provider': 'figshare',
              'article_id': 123, 'version': 2, 'download': True,
              'task': 'multilabel_external_evaluation'}
    config = tmp_path / 'sources.json'
    config.write_text(json.dumps({'sources': [source]}), encoding='utf-8')
    calls = []
    monkeypatch.setattr(figshare_source, 'collect', lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(sys, 'argv', ['source_collection', '--config', str(config),
                        '--source', 'field-source', '--download'])
    source_collection.main()
    assert calls == [((123, 2, 'maize', 'field-source'), {'workers': 4})]


def test_zenodo_checksum_failure_never_publishes_original(tmp_path, monkeypatch):
    from ml.agrivision_ml.preprocessing import zenodo_source
    metadata = {'metadata': {'license': {'id': 'cc-by-4.0'}}, 'files': [
        {'key': 'original.zip', 'size': 4, 'checksum': 'md5:' + hashlib.md5(b'good').hexdigest(),
         'links': {'self': 'https://example.test/original.zip'}}]}
    def handler(request):
        return httpx.Response(200, json=metadata) if '/api/records/' in str(request.url) else httpx.Response(200, content=b'bad!')
    client_type = httpx.Client
    monkeypatch.setattr(zenodo_source, 'ROOT', tmp_path)
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError, match='MD5'):
        zenodo_source.collect(1, 'peanut', 'fixture')
    source = tmp_path / 'data/peanut/sources/fixture'
    assert not (source / 'archives/original.zip').exists()
    assert not (source / 'download-status.json').exists()


def test_peanut_external_labels_preserve_subtypes_and_missing_classes(tmp_path, monkeypatch):
    from ml.agrivision_ml.preprocessing import planthead_peanut
    source = tmp_path / 'data/peanut/sources' / planthead_peanut.SOURCE_ID
    raw = source / 'raw'
    cases = [
        ('ARHHY_MYCOAR_passalora arachidicola', 'red'),
        ('ARHHY_MYCOBE_nothapassalora personata', 'blue'),
        ('ARHHY_PUCCAR_puccinia arachidis', 'green'),
        ('ARHHY_healthy leaves', 'yellow'),
        ('ARHHY_GRV000_groundnut rosette virus', 'purple'),
    ]
    for label, color in cases:
        directory = raw / label
        directory.mkdir(parents=True)
        Image.new('RGB', (30, 20), color).save(directory / 'sample.jpg')
    (source / 'download-status.json').write_text(json.dumps({'complete': True}))
    (source / 'metadata').mkdir()
    (source / 'metadata/visual-review.json').write_text(json.dumps({'decision': 'candidate'}))
    monkeypatch.setattr(planthead_peanut, 'ROOT', tmp_path)
    monkeypatch.setattr(source_collection, 'ROOT', tmp_path)
    report = planthead_peanut.audit()
    assert report['image_count'] == 5
    assert report['strict_supported_count'] == 4
    assert report['strict_supported_classes'] == {'peanut_leaf_spot': 2, 'peanut_rust': 1, 'healthy': 1}
    with (tmp_path / 'data/peanut/evaluation/planthead-peanut.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len({row['source_label'] for row in rows if row['label'] == 'peanut_leaf_spot'}) == 2
    assert next(row for row in rows if 'GRV000' in row['source_label'])['evaluation_role'] == 'out_of_scope'
    assert all(row['split'] == 'external' for row in rows)

    # 水印抽查否决整来源时，原标签和统计仍保留，但清单不留任何可评估旧行。
    (source / 'metadata/visual-review.json').write_text(json.dumps({'decision': 'hold', 'reason': 'watermarked'}))
    held = planthead_peanut.audit()
    assert held['supported_label_candidates_before_visual_review'] == 4
    assert held['strict_supported_count'] == 0
    with (tmp_path / 'data/peanut/evaluation/planthead-peanut-single-supported.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.DictReader(stream)) == []

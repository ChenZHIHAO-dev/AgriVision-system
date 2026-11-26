"""验证按来源增量下载不会丢失同作物旧来源的审计记录。"""
import csv
import json
import sys

from PIL import Image

from ml.agrivision_ml.preprocessing import source_collection


def test_source_download_keeps_existing_crop_audit(tmp_path, monkeypatch):
    def source(name, **extra):
        return {'id': name, 'crop': 'maize', 'provider': 'mendeley',
                'download': True, 'license': 'CC BY 4.0', 'region': 'test fixture',
                'label_map': {'healthy': 'healthy'}, **extra}

    old = source('already-downloaded')
    new = source('new-download')
    external = source('multilabel-field', task='multilabel_external_evaluation')
    config = tmp_path / 'sources.json'
    config.write_text(json.dumps({'sources': [old, new, external]}), encoding='utf-8')

    def add_image(item, color):
        path = tmp_path / 'data/maize/sources' / item['id'] / 'raw/healthy/photo.jpg'
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (24, 18), color).save(path)

    add_image(old, 'green')
    add_image(external, 'blue')
    downloads = []
    def download(item):
        downloads.append(item['id'])
        add_image(item, 'red')

    monkeypatch.setattr(source_collection, 'ROOT', tmp_path)
    monkeypatch.setattr(source_collection, 'collect_source', download)
    monkeypatch.setattr(sys, 'argv', ['source_collection', '--config', str(config),
                        '--source', new['id'], '--download', '--audit'])
    source_collection.main()

    assert downloads == [new['id']]
    output = tmp_path / 'data/maize/review/source-audit.csv'
    with output.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert {row['source'] for row in rows} == {old['id'], new['id']}
    assert len(rows) == 2
    report = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
    assert report['images'] == 2
    assert {item['source']['id'] for item in report['sources']} == {old['id'], new['id']}

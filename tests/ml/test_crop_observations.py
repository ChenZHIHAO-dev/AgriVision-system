"""公开照片进入人工筛选前，验证逐图许可和同一次观察分组。"""
import csv
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    'collect_crop_observations', Path(__file__).resolve().parents[2] / 'scripts/collect_crop_observations.py'
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def test_media_license_and_observation_group_are_not_inferred_from_record():
    target = {'id': 'wheat', 'name': '小麦', 'scientific_name': 'Triticum aestivum'}
    media = lambda number, license: {
        'type': 'StillImage', 'identifier': f'https://example.org/{number}.jpg', 'license': license
    }
    records = [{
        'key': 1, 'occurrenceID': 'https://example.org/observations/7', 'countryCode': 'CN',
        'license': 'https://creativecommons.org/licenses/by/4.0/',
        'media': [media(1, 'https://creativecommons.org/licenses/by/4.0/'),
                  media(2, 'http://creativecommons.org/licenses/by-sa/4.0/'),
                  media(3, 'https://creativecommons.org/licenses/by-nc/4.0/'), media(4, ''),
                  media(5, 'https://example.org/licenses/by/4.0/')],
    }]
    rows = list(collector.select_photos(target, records))
    assert len(rows) == 2
    assert rows[0]['id'] != rows[1]['id']
    assert rows[0]['group'] == rows[1]['group']
    assert {row['review'] for row in rows} == {'review'}
    assert all(row['organ'] == '待看图' for row in rows)


def test_rerun_preserves_manual_rejection_and_does_not_duplicate_rows(tmp_path):
    row = dict.fromkeys(collector.FIELDS, '')
    row.update(id='one', label='wheat', review='review', organ='待看图')
    previous = {'one': {**row, 'review': 'drop', 'reason': '水印', 'organ': '叶片'}}
    output = tmp_path / 'review.csv'
    collector.write_review(output, previous, [row])
    rows = list(csv.DictReader(output.open(encoding='utf-8-sig')))
    assert len(rows) == 1
    assert rows[0]['review'] == 'drop'
    assert rows[0]['reason'] == '水印'
    assert rows[0]['organ'] == '叶片'


def test_wild_soybean_subspecies_is_not_collected_as_cultivated_soybean():
    target = {'id': 'soybean', 'name': '大豆', 'scientific_name': 'Glycine max',
              'excluded_taxa': ['Glycine max subsp. soja']}
    record = {'key': 2, 'scientificName': 'Glycine max subsp. soja (Siebold & Zucc.) H.Ohashi',
              'media': [{'type': 'StillImage', 'identifier': 'https://example.org/soybean.jpg',
                         'license': 'https://creativecommons.org/licenses/by/4.0/'}]}
    assert list(collector.select_photos(target, [record])) == []

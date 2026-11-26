"""按物种收集公开作物实拍供人工筛选；不生成增强图，也不自动生成训练集。

例：python scripts/collect_crop_observations.py --labels wheat maize peanut --max-images 40
同一目录可重复运行：按媒体 URL 命名，保留已有文件和 keep/drop 审核决定。
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.gbif.org/v1/'
FIELDS = ['id', 'label', 'name', 'scientific_name', 'source_scientific_name', 'path', 'group', 'country', 'region',
          'organ', 'width', 'height', 'review', 'reason', 'license', 'author', 'rights_holder',
          'photo_url', 'photo_page', 'gbif_occurrence', 'dataset_key', 'observation_id']


def read_url(url: str, limit: int = 32 * 1024 * 1024) -> bytes:
    """只做有超时的公开 HTTP 下载；有限重试处理临时网络错误，不改变照片内容。"""
    request = Request(url, headers={'User-Agent': 'AgriVision-dataset-research/1.0'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                content = response.read(limit + 1)
            if len(content) > limit:
                raise ValueError('响应超过允许大小')
            return content
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError('unreachable')


def gbif(path: str, **params):
    return json.loads(read_url(API + path + '?' + urlencode(params)))


def allowed_license(value: str) -> bool:
    """逐图许可优先于整个 GBIF 记录许可；NC、ND、无许可不自动纳入。"""
    parsed = urlparse(value)
    return parsed.hostname in {'creativecommons.org', 'www.creativecommons.org'} and (
        parsed.path.startswith('/licenses/by/')
        or parsed.path.startswith('/licenses/by-sa/')
        or parsed.path.startswith('/publicdomain/zero/')
    )


def find_observations(target: dict, country: str, max_records: int) -> dict:
    """先确认学名，再查询记录。缓存包含完整出处，报告区分总记录数与本轮读取数。"""
    matched = gbif('species/match', name=target['scientific_name'], strict='true')
    if matched.get('matchType') != 'EXACT' or matched.get('rank') != 'SPECIES':
        raise ValueError(f'学名需要核对：{target["scientific_name"]} -> {matched}')
    params = dict(taxonKey=matched['usageKey'], mediaType='StillImage',
                  basisOfRecord='HUMAN_OBSERVATION', occurrenceStatus='PRESENT')
    if country != 'ALL':
        params['country'] = country
    rows = []
    count = 0
    while len(rows) < max_records:
        result = gbif('occurrence/search', **params, limit=min(300, max_records-len(rows)), offset=len(rows))
        count = result['count']
        rows.extend(result['results'])
        if result['endOfRecords'] or not result['results']:
            break
    # 不保存精确经纬度等与当前模型任务无关的字段；保留观察标识和粗地区用于分组。
    keys = ['key', 'occurrenceID', 'species', 'scientificName', 'countryCode', 'stateProvince',
            'datasetKey', 'media', 'recordedBy', 'eventDate']
    return {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'taxon': matched,
            'query': params, 'total_occurrences': count,
            'records': [{k: row.get(k) for k in keys} for row in rows]}


def select_photos(target: dict, records: list[dict]):
    """同一次观察的多张照片共享 group。叶/花/果实部位必须看图后标，不能按物种猜。"""
    seen = set()
    for record in records:
        # 上级种的查询可能含野生亚种，配置中的排除项不能被泛化成栽培作物标签。
        if any((record.get('scientificName') or '').startswith(taxon)
               for taxon in target.get('excluded_taxa', [])):
            continue
        for media in record.get('media') or []:
            url = media.get('identifier', '')
            if media.get('type') != 'StillImage' or not url.startswith('https://'):
                continue
            if not allowed_license(media.get('license', '')) or url in seen:
                continue
            seen.add(url)
            identifier = hashlib.sha256(url.encode()).hexdigest()[:20]
            observation = record.get('occurrenceID') or f'gbif:{record["key"]}'
            group = 'observation:' + hashlib.sha256(str(observation).encode()).hexdigest()[:20]
            yield dict(id=identifier, label=target['id'], name=target['name'],
                       scientific_name=target['scientific_name'],
                       source_scientific_name=record.get('scientificName') or '', path='', group=group,
                       country=record.get('countryCode') or '', region=record.get('stateProvince') or '',
                       organ='待看图', width='', height='', review='review', reason='待人工核对物种/器官/水印/拼图',
                       license=media['license'], author=media.get('creator') or record.get('recordedBy') or '',
                       rights_holder=media.get('rightsHolder') or '', photo_url=url,
                       photo_page=media.get('references') or '',
                       gbif_occurrence=f'https://www.gbif.org/occurrence/{record["key"]}',
                       dataset_key=record.get('datasetKey') or '', observation_id=str(observation))


def download_photo(row: dict, folder: Path) -> dict:
    """解码检查后保留原图，不去水印、不裁剪，也不复制成多个数据集版本。"""
    destination = folder / 'images' / row['label'] / (row['id'] + '.jpg')
    destination = next((destination.with_suffix(s) for s in ['.jpg', '.png', '.webp']
                        if destination.with_suffix(s).exists()), destination)
    if destination.exists():
        content = destination.read_bytes()
    else:
        content = read_url(row['photo_url'])
    with Image.open(BytesIO(content)) as image:
        image.verify()
    with Image.open(BytesIO(content)) as image:
        width, height = image.size
        formats = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}
        if image.format not in formats:
            raise ValueError(f'不支持的图片格式：{image.format}')
        suffix = formats[image.format]
    destination = destination.with_suffix(suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(content)
    return {**row, 'path': destination.relative_to(ROOT).as_posix(), 'width': width, 'height': height}


def write_review(path: Path, previous: dict, downloaded: list):
    """重跑不覆盖用户审核：keep/drop、理由、器官会保留；新图统一保持待筛。"""
    for row in downloaded:
        old = previous.get(row['id'], {})
        for key in ['review', 'reason', 'organ', 'label', 'name', 'scientific_name']:
            if key in old:
                row[key] = old[key]
        previous[row['id']] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(previous.values(), key=lambda row: (row['label'], row['id'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', nargs='+', help='只收指定类别；默认配置里的全部目标种')
    parser.add_argument('--country', default='CN', help='国家代码；ALL 表示全球，默认 CN')
    parser.add_argument('--max-records', type=int, default=300, help='每类最多读取记录数（非图片数）')
    parser.add_argument('--max-images', type=int, default=40, help='每类本轮最多下载照片数')
    parser.add_argument('--refresh', action='store_true', help='刷新 GBIF 元数据，已下载照片和审核结果仍保留')
    args = parser.parse_args()
    if not 1 <= args.max_records <= 10000 or args.max_images < 1:
        parser.error('max-records 需为 1–10000，max-images 需大于 0')
    config = json.loads((ROOT / 'configs/datasets/crop-identification.json').read_text(encoding='utf-8-sig'))
    targets = [row for row in config['targets'] if not args.labels or row['id'] in args.labels]
    if args.labels and set(args.labels) - {row['id'] for row in targets}:
        parser.error('存在配置中没有的作物名称')
    country = args.country.upper()
    base = ROOT / 'data/crop-identification'
    source = base / 'sources' / ('gbif-' + country.lower())
    source.mkdir(parents=True, exist_ok=True)
    review = base / 'review' / ('gbif-' + country.lower() + '.csv')
    previous = {row['id']: row for row in csv.DictReader(review.open(encoding='utf-8-sig'))} if review.exists() else {}
    report_path = source / 'source.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {
        'source': 'GBIF public occurrence API', 'task': 'crop_identification', 'country': country,
        'review_status': 'unreviewed', 'classes': {},
        'notice': '照片仅作为待筛候选。按观察组拆分后才可训练；未人工逐图筛选，不保证无水印。',
    }
    for index, target in enumerate(targets, 1):
        label = target['id']
        metadata = source / (label + '.json')
        try:
            if args.refresh or not metadata.exists():
                data = find_observations(target, country, args.max_records)
                metadata.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            else:
                data = json.loads(metadata.read_text(encoding='utf-8'))
            candidates = list(select_photos(target, data['records']))
            downloaded, failures = [], []
            for row in candidates:
                if len(downloaded) >= args.max_images:
                    break
                try:
                    downloaded.append(download_photo(row, source))
                    if len(downloaded) % 10 == 0:
                        print(f'  {label}: 已取得 {len(downloaded)} 张候选照片', flush=True)
                except (OSError, URLError, ValueError) as error:
                    failures.append({'url': row['photo_url'], 'error': str(error)})
            write_review(review, previous, downloaded)
            report['classes'][label] = {
                'name': target['name'], 'scientific_name': target['scientific_name'],
                'total_occurrences': data['total_occurrences'], 'records_scanned': len(data['records']),
                'license_eligible_photos': len(candidates), 'downloaded_this_run': len(downloaded),
                'downloaded_observation_groups': len({row['group'] for row in downloaded}),
                'failures': failures,
            }
            print(f'[{index}/{len(targets)}] {target["name"]}: 记录 {data["total_occurrences"]}，许可筛后 {len(candidates)} 图，本轮取得 {len(downloaded)} 图', flush=True)
        except (OSError, URLError, ValueError) as error:
            report['classes'][label] = {'error': str(error)}
            print(f'[{index}/{len(targets)}] {label}: {error}', flush=True)
        # 每次复跑从筛选表当前状态重算，避免审核决定变了而统计仍沿用旧值。
        rows = list(previous.values())
        report['review_summary'] = {
            'photos_indexed': len(rows),
            'review_decisions': dict(Counter(row['review'] for row in rows)),
            'classes': {
                label: {
                    'photos': sum(row['label'] == label for row in rows),
                    'groups': len({row['group'] for row in rows if row['label'] == label}),
                    'review': sum(row['label'] == label and row['review'] == 'review' for row in rows),
                    'drop': sum(row['label'] == label and row['review'] == 'drop' for row in rows),
                }
                for label in sorted({row['label'] for row in rows})
            },
        }
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('待筛表：', review)
    print('出处/计数：', report_path)


if __name__ == '__main__':
    main()

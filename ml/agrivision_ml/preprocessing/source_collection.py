"""公开数据采集与初审：只下载、验真和统计，不生成训练划分或离线增强图。

例：python -m ml.agrivision_ml.preprocessing.source_collection --download
    python -m ml.agrivision_ml.preprocessing.source_collection --audit

所有原文件留在 data/<作物>/sources/<来源>。审计只生成小型 CSV/JSON 和抽样图；
抽样没有水印不等于逐图通过。每张图片默认 review，人工审核后才决定 keep/drop。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import zipfile
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageOps
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[3]
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}


def save_json(path: Path, value: Any) -> None:
    """同一路径更新统计，避免反复产生 01/02 版本目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    # 即使筛选后为空，也重写表头，避免上次的旧候选清单残留而被误用。
    fieldnames = fieldnames or list(rows[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    """流式计算校验和，不把大压缩包一次读入内存。"""
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def get_json(client: httpx.Client, url: str) -> Any:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def md5_file(path: Path) -> str:
    """MD5 仅用于与源站文件一致性核验，不用于密码安全。"""
    digest = hashlib.md5()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def download_file(client: httpx.Client, record: dict, destination: Path, progress_enabled: bool = True) -> None:
    """依据源站 SHA-256 验证下载；中断文件用 .part，不冒充完整原图。"""
    details = record['content_details']
    expected = details.get('sha256_hash')
    if destination.exists() and expected and sha256(destination) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.part')
    # 三次只重试网络读失败；不绕过登录、许可或服务器的访问限制。
    for attempt in range(3):
        try:
            with client.stream('GET', details['download_url']) as response:
                response.raise_for_status()
                with partial.open('wb') as out, tqdm(total=details.get('size'), unit='B', unit_scale=True, desc=destination.name, disable=not progress_enabled) as progress:
                    for chunk in response.iter_bytes(1024 * 1024):
                        out.write(chunk)
                        progress.update(len(chunk))
            if expected and sha256(partial) != expected:
                raise ValueError(f'文件校验失败：{destination.name}')
            partial.replace(destination)
            return
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def extract_zip(archive: Path, output: Path) -> list[dict]:
    """逐个成员核对路径、解压校验 CRC；已存在且 CRC 相同的成员可直接复用。"""
    output.mkdir(parents=True, exist_ok=True)
    boundary = output.resolve()
    inventory = []
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        for member in members:
            target = (boundary / member.filename).resolve()
            if not target.is_relative_to(boundary):
                raise ValueError(f'ZIP 路径越界：{member.filename}')
            inventory.append({'path': member.filename, 'size': member.file_size,
                              'compressed_size': member.compress_size, 'crc32': f'{member.CRC:08x}', 'directory': member.is_dir()})
        for member in tqdm(members, desc='Extracting original images', unit='file', mininterval=5):
            if member.is_dir():
                continue
            target = boundary / member.filename
            if target.exists() and target.stat().st_size == member.file_size:
                crc = 0
                with target.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        crc = zlib.crc32(block, crc)
                if crc == member.CRC:
                    continue
            # zipfile 在读完成员时校验 CRC，损坏压缩成员会抛错而非悄悄接受。
            zipped.extract(member, boundary)
    return inventory


def mendeley_inventory(client: httpx.Client, source: dict) -> tuple[dict, list[dict], dict[str, Path]]:
    """逐个目录分页枚举，避免只读根目录或遗漏超过 1000 张的类别。"""
    base = f"https://data.mendeley.com/public-api/datasets/{source['dataset_id']}"
    version = source['version']
    metadata = get_json(client, f'{base}?version={version}')
    folders = get_json(client, f'{base}/folders/{version}')
    by_id = {folder['id']: folder for folder in folders}
    paths = {'root': Path()}
    def folder_path(folder_id: str) -> Path:
        if folder_id not in paths:
            folder = by_id[folder_id]
            paths[folder_id] = folder_path(folder.get('parent_id', 'root')) / folder['name']
        return paths[folder_id]
    records = []
    for folder_id in ['root', *by_id]:
        folder_path(folder_id)
        offset = 0
        while True:
            batch = get_json(client, f'{base}/files?folder_id={folder_id}&version={version}&$start={offset}&$limit=1000')
            records.extend(batch)
            if len(batch) < 1000:
                break
            offset += len(batch)
    return metadata, records, paths


def collect_source(source: dict) -> None:
    """原文件按源站目录采集，原始元数据和校验值随数据保存。"""
    target = ROOT / 'data' / source['crop'] / 'sources' / source['id']
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        metadata, records, folders = mendeley_inventory(client, source)
        save_json(target / 'source.json', {'source': source, 'provider_metadata': metadata, 'files': records})
        if not records:
            raise ValueError('公开目录没有文件；不能声称已完整下载。')
        def fetch(record: dict) -> Path:
            filename = record['filename']
            is_zip = Path(filename).suffix.lower() == '.zip'
            destination = target / ('archives' if is_zip else 'raw') / folders.get(record.get('folder_id', 'root'), Path()) / filename
            if not destination.resolve().is_relative_to(target.resolve()):
                raise ValueError(f'来源文件名超出目录：{filename}')
            download_file(client, record, destination, progress_enabled=len(records) <= 3)
            return destination
        # 限制并发为 4，兼顾下载速度、网络负载和 Windows 文件句柄数量。
        failures = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            jobs = {executor.submit(fetch, record): record for record in records}
            for future in tqdm(as_completed(jobs), total=len(jobs), desc=source['id'], unit='file'):
                try:
                    destination = future.result()
                    if destination.suffix.lower() == '.zip':
                        extract_zip(destination, target / 'raw')
                except (httpx.HTTPError, OSError, ValueError) as error:
                    failures.append({'filename': jobs[future]['filename'], 'error': str(error)})
        save_json(target / 'download-status.json', {'expected_files': len(records), 'failed_files': failures, 'complete': not failures})
        if failures:
            raise RuntimeError(f"{source['id']} 有 {len(failures)} 个文件未下载完整；重跑会校验并跳过已完成文件。")


def audit_image(path: Path) -> dict:
    """实际解码并统计尺寸、精确重复。近重复/采集组须在正式预处理阶段再处理。"""
    try:
        with Image.open(path) as opened:
            opened.load()
            rgb = ImageOps.exif_transpose(opened).convert('RGB')
            width, height = rgb.size
            # 将尺寸一起哈希，防止不同形状但相同字节序列意外视为同图。
            pixel_hash = hashlib.sha256(f'{width}x{height}:'.encode() + rgb.tobytes()).hexdigest()
        return {'width': width, 'height': height, 'pixel_sha256': pixel_hash, 'error': ''}
    except (OSError, ValueError) as error:
        return {'width': 0, 'height': 0, 'pixel_sha256': '', 'error': str(error)}


def contact_sheet(paths: list[Path], target: Path, title: str) -> list[str]:
    """按排序均匀抽样，每类最多 8 张；保留抽样清单，明确不是逐张人工审核。"""
    chosen = [paths[i * (len(paths) - 1) // max(min(len(paths), 8) - 1, 1)] for i in range(min(len(paths), 8))]
    sheet = Image.new('RGB', (4 * 260, 2 * 220 + 40), 'white')
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), title[:110], fill='black')
    for i, path in enumerate(chosen):
        try:
            with Image.open(path) as image:
                thumb = ImageOps.contain(ImageOps.exif_transpose(image).convert('RGB'), (250, 180))
                x, y = (i % 4) * 260 + 5, (i // 4) * 220 + 40
                sheet.paste(thumb, (x, y))
                draw.text((x, y + 183), path.name[:31], fill='black')
        except OSError:
            continue
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return [str(path.relative_to(ROOT)).replace('\\', '/') for path in chosen]


def audit_crop(crop: str, sources: list[dict]) -> None:
    """一张图一行清单，保留原始父文件夹标签，不擅自把模糊病名映射成具体病。"""
    output = ROOT / 'data' / crop / 'review'
    output.mkdir(parents=True, exist_ok=True)
    rows, summary, seen_pixels = [], [], {}
    for source in sources:
        source_root = ROOT / 'data' / crop / 'sources' / source['id'] / 'raw'
        paths = sorted(p for p in source_root.rglob('*') if p.is_file() and (p.suffix.lower() in IMAGE_SUFFIXES or p.name.lower() in IMAGE_SUFFIXES))
        leaf_map_path = source_root.parent / 'metadata/leaf_grouping/leaf-map.json'
        leaf_map = json.loads(leaf_map_path.read_text()) if leaf_map_path.exists() else {}
        original_splits = {}
        for split in ('train', 'test'):
            split_file = source_root.parent / 'metadata/splits' / f'color_{split}.txt'
            if split_file.exists():
                for line in split_file.read_text().splitlines():
                    original_splits[Path(line).name] = split
        source_metadata = {}
        if source.get('metadata_csv'):
            with (source_root / source['metadata_csv']).open(encoding='utf-8-sig', newline='') as stream:
                source_metadata = {row['filename'].strip(): {key: value.strip() for key, value in row.items() if isinstance(value, str)}
                                   for row in csv.DictReader(stream, delimiter=source.get('metadata_delimiter', ','))
                                   if row.get('filename', '').strip()}
        by_class = defaultdict(list)
        resolution = Counter()
        corrupt = duplicates = 0
        for path in tqdm(paths, desc=source['id'], unit='image'):
            result = audit_image(path)
            relative = path.relative_to(ROOT).as_posix()
            label = path.parent.name
            digest = result['pixel_sha256']
            duplicate_of = seen_pixels.get(digest, '') if digest else ''
            if digest and not duplicate_of:
                seen_pixels[digest] = relative
            corrupt += bool(result['error'])
            duplicates += bool(duplicate_of)
            by_class[label].append(path)
            resolution[f"{result['width']}x{result['height']}"] += 1
            # 原始病名与统一病名分列：对来源本身含糊的类别留空，不用 AI 描述充当标签。
            canonical = source.get('label_map', {}).get(label, '')
            reason = source.get('hold_labels', {}).get(label, source.get('hold_reason', ''))
            if not canonical and not reason:
                reason = '未配置可信病类映射，暂缓进入监督训练。'
            review = 'hold' if reason or not canonical else source.get('default_review', 'review')
            if result['error']:
                review, reason = 'drop', '无法完整解码'
            # 官方同叶映射优先；没有采集 ID 时明确 unknown，精确相同像素不是独立采集证明。
            group = 'unknown'
            if leaf_map:
                key = path.name.replace('_final_masked', '').split('___')[-1].split('copy')[0]
                for extension in ('.jpg', '.JPG', '.png', '.PNG'):
                    key = key.replace(extension, '')
                suggestions = leaf_map.get(key.lower().strip(), [])
                matches = [value for value in suggestions if label in value]
                if len(matches) == 1:
                    group = f"{source['id']}:{matches[0]}"
            metadata_row = source_metadata.get(path.name, {})
            block = metadata_row.get('plantation_block', '')
            rows.append({'path': relative, 'label': canonical, 'source': source['id'], 'group': group,
                         'license': source['license'], 'region': source['region'], 'part': source.get('part', 'leaf'),
                         'source_label': label, 'collection_group': f"{source['id']}:field:{block}" if block else 'unknown',
                         'collection_canton': metadata_row.get('location_canton', ''), 'cultivar': metadata_row.get('corn_variety', ''),
                         'source_disease_name': metadata_row.get('disease_scientific_name', ''), 'source_split': original_splits.get(path.name, next((part for part in path.relative_to(source_root).parts if part.lower() in ('train', 'test', 'val', 'validation')), '')),
                         'review': review, 'reason': reason, 'duplicate_of': duplicate_of,
                         'group_status': 'author_leaf_id' if group != 'unknown' else 'capture_identity_unknown',
                         'derived_image_hint': 'yes_filename_dr' if path.name.startswith('dr_') else 'unknown', **result})
        sheets = {}
        for index, (label, class_paths) in enumerate(sorted(by_class.items())):
            sheets[label] = contact_sheet(class_paths, output / 'samples' / f"{source['id']}-{index}.jpg", f"{source['id']} | {label}")
        summary.append({'source': source, 'image_count': len(paths), 'corrupt': corrupt, 'exact_pixel_duplicates': duplicates,
                        'class_counts': {key: len(value) for key, value in sorted(by_class.items())},
                        'resolutions': dict(resolution.most_common()), 'sampled_paths': sheets,
                        'visual_review': source.get('visual_review', 'pending; contact sheets are samples, not exhaustive screening')})
    csv_path = output / 'source-audit.csv'
    # source-audit 是可重建的统计清单；人工 keep/drop 应另放 review.csv，防止重跑覆盖手工决定。
    if rows:
        with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    save_json(output / 'source-audit.json', {'crop': crop, 'images': len(rows), 'sources': summary,
              'review_counts': dict(Counter(row['review'] for row in rows)),
              'mapped_class_counts': dict(Counter(row['label'] for row in rows if row['label'] and row['review'] != 'hold')),
              'known_capture_groups': len({row['group'] for row in rows if row['group'] != 'unknown'}),
              'unknown_capture_images': sum(row['group'] == 'unknown' for row in rows),
              'scope': '完整解码+精确像素去重统计；不含近重复分组、病名人工确认或逐图水印审核。'})
    print(f'{crop}: {len(rows):,} images -> {csv_path}', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/datasets/maize-peanut.json')
    parser.add_argument('--source', action='append', help='选择下载来源及审计作物；审计保留同作物所有已下载的分类来源')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    if not args.download and not args.audit:
        parser.error('请选择 --download 或 --audit；两者可同时使用。')
    config = json.loads((ROOT / args.config).read_text(encoding='utf-8'))
    all_sources = config['sources']
    sources = [s for s in all_sources if not args.source or s['id'] in args.source]
    if args.download:
        for source in sources:
            if not source.get('download'):
                continue
            if source['provider'] == 'mendeley':
                collect_source(source)
            elif source['provider'] == 'figshare':
                # 大文件续传与源站校验独立放在提供方模块，审计规则不与下载耦合。
                from .figshare_source import collect as collect_figshare
                collect_figshare(source['article_id'], source['version'], source['crop'], source['id'], workers=4)
            elif source['provider'] == 'zenodo':
                from .zenodo_source import collect as collect_zenodo
                collect_zenodo(source['record'], source['crop'], source['id'])
            else:
                raise ValueError(f"未提供下载适配器：{source['provider']}；请使用来源配置中的专用命令。")
    if args.audit:
        for crop in sorted({s['crop'] for s in sources}):
            # --source 可以缩小下载任务，但 source-audit 是整个作物的固定索引。
            # 从配置重新取该作物所有已落盘来源，避免增量下载后覆盖旧来源的审计。
            # 多标签外部评估有专用清单，不能混入按父目录解释单标签的审计。
            downloaded = [s for s in all_sources if s['crop'] == crop
                          and s.get('task') not in {'multilabel_external_evaluation', 'singlelabel_external_evaluation'}
                          and (ROOT / 'data' / crop / 'sources' / s['id'] / 'raw').is_dir()]
            audit_crop(crop, downloaded)


if __name__ == '__main__':
    main()

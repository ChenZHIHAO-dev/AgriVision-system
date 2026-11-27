"""番茄原图下载→来源审计→可编辑筛选→固定工作集，不在这里训练或增强。"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.parse import quote

import httpx
from tqdm import tqdm

from .crop_review import REVIEW_FIELDS, merge_audit_row, select_with_basis
from .plantvillage_source import git_blob_hash
from .source_collection import ROOT, audit_crop, get_json, save_json
from .tables import read_rows, write_rows
from .wheat_review import build_dataset, print_report, print_selection


def load_config(root=ROOT):
    source = json.loads((root / 'configs/datasets/tomato.json').read_text(encoding='utf-8'))['sources'][0]
    labels = json.loads((root / 'configs/labels/tomato.json').read_text(encoding='utf-8'))['labels']
    return source, labels


def collect(source, root=ROOT, workers=12):
    """固定作者 Git 提交与每图 blob 校验；下载中断后只重取缺失/不匹配的文件。"""
    target = root / 'data/tomato/sources' / source['id']
    target.mkdir(parents=True, exist_ok=True)
    inventory = target / 'source.json'
    repository = source['repository']
    with httpx.Client(timeout=60, follow_redirects=True, limits=httpx.Limits(max_connections=workers+2)) as client:
        if inventory.exists():
            original = json.loads(inventory.read_text(encoding='utf-8'))
            if original['repository'] != repository or set(original['class_counts']) != set(source['label_map']):
                raise ValueError('固定来源范围变化，请人工核对，不能混写原图目录')
            commit, records = original['commit'], original['files']
        else:
            api = f'https://api.github.com/repos/{repository}'
            commit = get_json(client, f'{api}/commits/master')['sha']
            directories = get_json(client, f'{api}/contents/raw/color?ref={commit}')
            records = []
            for directory in directories:
                if directory['name'] not in source['label_map']:
                    continue
                tree = get_json(client, f"{api}/git/trees/{directory['sha']}")
                if tree.get('truncated'):
                    raise ValueError('Git目录被截断，不能声称数据完整')
                records.extend({**item, 'class':directory['name']} for item in tree['tree'] if item['type']=='blob')
            counts = dict(Counter(row['class'] for row in records))
            if set(counts) != set(source['label_map']):
                raise ValueError('作者目录没有覆盖登记类别')
            save_json(inventory, {**source, 'commit':commit, 'class_counts':counts, 'files':records})
        # 同一作者HF的许可/同叶映射/原划分，复用本项目已经下载的元数据；不复制其它作物照片。
        metadata_hashes = {}
        for name in ['README.md','leaf_grouping/leaf-map.json','splits/color_train.txt','splits/color_test.txt']:
            path = target / 'metadata' / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                cached = root / 'data/maize/sources/plantvillage-maize-color/metadata' / name
                if cached.exists():
                    shutil.copy2(cached, path)
                else:
                    response = client.get('https://huggingface.co/datasets/mohanty/PlantVillage/resolve/main/' + name)
                    response.raise_for_status(); path.write_bytes(response.content)
            metadata_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        original = json.loads(inventory.read_text(encoding='utf-8'))
        original['author_metadata_sha256'] = metadata_hashes
        save_json(inventory, original)

        def fetch(record):
            destination = target / 'raw' / record['class'] / record['path']
            if destination.exists() and git_blob_hash(destination.read_bytes()) == record['sha']:
                return
            relative = f"raw/color/{record['class']}/{record['path']}"
            url = f'https://raw.githubusercontent.com/{repository}/{commit}/{quote(relative)}'
            for attempt in range(3):
                try:
                    response = client.get(url); response.raise_for_status()
                    if git_blob_hash(response.content) != record['sha']:
                        raise ValueError('原图Git blob不匹配：' + record['path'])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(response.content)
                    return
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
        failures = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            jobs = {executor.submit(fetch, record):record for record in records}
            for future in tqdm(as_completed(jobs), total=len(jobs), desc='Tomato original images', unit='image', mininterval=10):
                try:
                    future.result()
                except (httpx.HTTPError, ValueError, OSError) as exc:
                    failures.append({'file':jobs[future]['path'],'error':str(exc)})
        save_json(target / 'download-status.json', {'expected_images':len(records),'failed_files':failures,'complete':not failures})
        if failures:
            raise RuntimeError(f'{len(failures)}张原图尚未下载完成，重跑下载可续传')
    return target


def exclude_pixel_conflicts(rows):
    """同像素跨标签时整组暂缓，不能留下碰巧先扫描到的那一类。"""
    groups = defaultdict(list)
    for row in rows:
        if row.get('pixel_sha256'):
            groups[row['pixel_sha256']].append(row)
    conflicts = []
    for digest, members in groups.items():
        if len({row['label'] for row in members}) > 1:
            conflicts.append({'pixel_sha256':digest,'paths':[row['path'] for row in members]})
            for row in members:
                row['review'], row['reason'] = 'hold', '相同像素跨病类标签冲突，整组暂缓人工复核'
    return conflicts


def audit(source, root=ROOT):
    """复用全量解码、像素统计与抽样图；另外汇总叶ID覆盖和跨类冲突。"""
    if root != ROOT:
        raise ValueError('审计入口使用项目固定目录')
    target = root / 'data/tomato/sources' / source['id']
    status = json.loads((target / 'download-status.json').read_text(encoding='utf-8'))
    if not status['complete']:
        raise ValueError('下载未完整，不生成完整来源的训练候选')
    audit_crop('tomato', [source])
    review = root / 'data/tomato/review'
    path = review / 'source-audit.csv'
    rows = read_rows(path)
    conflicts = exclude_pixel_conflicts(rows)
    write_rows(path, list(rows[0]), rows)
    # 来源摘要同步反映跨类冲突的整组排除，避免 JSON 和实际筛选 CSV 计数相互矛盾。
    summary_path = review / 'source-audit.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    summary.update(review_counts=dict(Counter(row['review'] for row in rows)),
                   mapped_class_counts=dict(Counter(row['label'] for row in rows
                       if row['label'] and row['review'] not in {'hold', 'drop'})),
                   pixel_label_conflicts=conflicts)
    save_json(summary_path, summary)
    save_json(review / 'group-audit.json', {'images':len(rows),'pixel_label_conflicts':conflicts,
        'grouped_images_by_label':dict(Counter(row['label'] for row in rows if row['group_status']=='author_leaf_id')),
        'unknown_capture_images_by_label':dict(Counter(row['label'] for row in rows if row['group_status']!='author_leaf_id')),
        'limitation':'unknown表示作者采集ID未匹配，预处理仅补近重复分组；受控叶片内部划分不是田间验证。'})
    return rows


def sync_review(source, labels, *, root=ROOT, accept_source_labels=False):
    """保留原有人工决定；显式接纳作者标签只用于内部实验，不冒称逐图人工审过。"""
    review = root / 'data/tomato/review/disease-review.csv'
    prior = read_rows(review) if review.exists() else []
    previous = {(row['source'],row['path']):row for row in prior}
    audit_rows = read_rows(review.parent / 'source-audit.csv')
    rows = [merge_audit_row(row, source, labels, review, root, previous, accept_source_labels) for row in audit_rows]
    write_rows(review, REVIEW_FIELDS, rows)
    selection = select_with_basis(review, labels, rows)
    print_selection(selection, labels, review)
    return selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--audit',action='store_true')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--accept-source-labels',action='store_true')
    parser.add_argument('--prepare',action='store_true',help='生成固定data/tomato/prepared，不创建01/02副本')
    parser.add_argument('--workers',type=int,default=12)
    args = parser.parse_args()
    source, labels = load_config()
    if args.download:
        collect(source,workers=args.workers)
    if args.audit:
        audit(source)
    if args.check or args.accept_source_labels or args.prepare:
        selection = sync_review(source,labels,accept_source_labels=args.accept_source_labels)
        if args.prepare:
            output=ROOT/'data/tomato/prepared'
            report=build_dataset(selection,labels,output,crop='tomato')
            print_report(report,labels,output)


if __name__=='__main__':
    main()

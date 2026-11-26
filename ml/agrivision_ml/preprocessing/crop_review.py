"""把玉米/花生的来源审计转换为可编辑筛选表，再复用现有预处理流水线。

第一步 --check 生成/更新 disease-review.csv 并统计，不复制图片。
人工把决定填为 keep/drop；留空表示待筛。
--accept-source-labels 仅为内部实验接纳作者标签，不代表逐图人工审核。
只有显式传入 --output 才生成工作图和 manifest；增强仍由训练读取时执行。
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path

from .review import read_selection
from .tables import read_rows, write_rows
from .wheat_review import build_dataset, print_report, print_selection

ROOT = Path(__file__).resolve().parents[3]
REVIEW_FIELDS = (
    'decision', 'label', 'path', 'source', 'sha256', 'group', 'part', 'note',
    'review_basis', 'exclusion_reason', 'source_label', 'source_review', 'source_url',
    'license', 'region', 'source_split', 'group_status', 'collection_group',
    'derived_image_hint', 'pixel_sha256',
)
INTERNAL_BASIS = 'source_labels_internal_experiment'
EXCLUDED_BASIS = 'excluded_by_source_audit'


def normalized_group(value):
    """unknown 只是缺失标记，不能让所有照片被并成一个采集组。"""
    value = (value or '').strip()
    return '' if value.lower() in {'', 'unknown', 'none', 'null', 'n/a'} else value


def load_catalogs(root, crop):
    """类别名来自作物标签表；来源条件来自统一来源配置，不在入口里重复写病名映射。"""
    config = json.loads((root / 'configs/datasets/maize-peanut.json').read_text(encoding='utf-8-sig'))
    sources = {item['id']: item for item in config['sources'] if item['crop'] == crop}
    catalog = json.loads((root / f'configs/labels/{crop}.json').read_text(encoding='utf-8-sig'))
    labels = catalog.get('labels')
    if catalog.get('crop') != crop or not isinstance(labels, dict) or len(labels) < 2:
        raise ValueError(f'标签文件需要 crop={crop} 和至少两个类别。')
    return sources, labels


def exclusion_reason(row, source, mapped_label, labels):
    """来源 hold、未定病类和无母图的增强图始终排除，实验开关不能跳过这些条件。"""
    if source.get('default_review') == 'hold':
        return source.get('hold_reason') or '整个来源暂缓使用'
    if row.get('review') in {'hold', 'drop'}:
        return row.get('reason') or '来源审计已排除'
    if row.get('error'):
        return '来源图片检查失败：' + row['error']
    if row.get('duplicate_of'):
        return '来源审计发现重复图：' + row['duplicate_of']
    if (row.get('derived_image_hint') or '').lower().startswith('yes'):
        return '已有派生增强图，不能作为独立原图使用'
    if row.get('source_label') in source.get('hold_labels', {}):
        return source['hold_labels'][row['source_label']]
    if not mapped_label:
        return '来源没有可核实的疾病标签映射'
    if mapped_label not in labels:
        return f'病类尚未登记到当前作物标签表：{mapped_label}'
    return ''


def merge_audit_row(row, source, labels, review_path, root, previous, accept_source_labels):
    """将一条审计记录换成相对路径；保留人工决定、改标、采集组和备注。"""
    file = (root / row['path']).resolve()
    allowed = (root / 'data' / source['crop'] / 'sources').resolve()
    if not file.is_relative_to(allowed):
        raise ValueError(f'审计照片不在该作物 sources 目录内：{row["path"]}')
    relative = Path(os.path.relpath(file, review_path.parent.resolve())).as_posix()
    old = previous.get((row['source'], relative), {})
    decision = (old.get('decision') or '').strip().lower()
    if decision not in {'', 'keep', 'drop'}:
        raise ValueError(f'无效人工决定 {decision!r}：{relative}，请填 keep、drop 或留空。')
    mapped_label = source.get('label_map', {}).get(row.get('source_label'), '')
    reason = exclusion_reason(row, source, mapped_label, labels)
    label = old.get('label', mapped_label)
    basis = old.get('review_basis') or 'pending_manual_review'
    if reason:
        # 新的来源审计可撤回不可靠样本；即使以前 keep，也不会绕过 hold/无标签/派生限制。
        decision, basis = 'drop', EXCLUDED_BASIS
    elif decision == 'drop':
        basis = 'manual_drop' if basis != EXCLUDED_BASIS else basis
    elif decision == 'keep':
        if basis != INTERNAL_BASIS or label != mapped_label:
            basis = 'manual_keep'
    elif accept_source_labels:
        decision, basis = 'keep', INTERNAL_BASIS
    else:
        basis = 'pending_manual_review'
    # 原采集组加来源前缀，避免两个来源都把第一张叶片叫 leaf-1 而误合并。
    group = normalized_group(row.get('group'))
    if group and not group.startswith(row['source'] + ':'):
        group = row['source'] + ':' + group
    if 'group' in old:
        group = normalized_group(old['group'])
    return {
        'decision': decision, 'label': label, 'path': relative, 'source': row['source'],
        # pixel_sha256 是解码像素哈希，不是原文件字节哈希，绝不能填到 sha256 中。
        'sha256': old.get('sha256', ''), 'pixel_sha256': row.get('pixel_sha256', ''),
        'group': group, 'part': old.get('part', row.get('part') or source.get('part', '')),
        'note': old.get('note', ''), 'review_basis': basis, 'exclusion_reason': reason,
        'source_label': row.get('source_label', ''), 'source_review': row.get('review', ''),
        'source_url': source.get('url', ''), 'license': row.get('license') or source.get('license', ''),
        'region': row.get('region') or source.get('region', ''), 'source_split': row.get('source_split', ''),
        'group_status': row.get('group_status', ''),
        # 地块不是同叶/同株身份，单独留给后续按地点外测，不能代替 group。
        'collection_group': normalized_group(row.get('collection_group')),
        'derived_image_hint': row.get('derived_image_hint', ''),
    }


def sync_review(root, crop, *, sources=(), accept_source_labels=False):
    """同步一份固定筛选表，不新增编号工作集。仅同步指定来源时保留其他来源的人工记录。"""
    source_config, labels = load_catalogs(root, crop)
    unknown = set(sources) - source_config.keys()
    if unknown:
        raise ValueError('未登记来源：' + ', '.join(sorted(unknown)))
    selected_sources = set(sources) if sources else set(source_config)
    review_root = root / 'data' / crop / 'review'
    review_path = review_root / 'disease-review.csv'
    previous_rows = read_rows(review_path, ('decision', 'label', 'path', 'source')) if review_path.exists() else []
    previous = {(row['source'], row['path']): row for row in previous_rows}
    audit = read_rows(review_root / 'source-audit.csv', ('path', 'source', 'source_label', 'review', 'group'))
    updated = {}
    for row in audit:
        if row['source'] not in selected_sources:
            continue
        item = merge_audit_row(row, source_config[row['source']], labels, review_path, root,
                               previous, accept_source_labels)
        key = (item['source'], item['path'])
        if key in updated:
            raise ValueError('来源审计重复引用同一张照片：' + item['path'])
        updated[key] = item
    for key, old in previous.items():
        if key in updated:
            continue
        if old['source'] not in selected_sources:
            updated[key] = old
        else:
            # 刷新审计后已消失的路径不沿用旧 keep；保留记录说明原因，避免悄悄纳入旧数据。
            updated[key] = {**old, 'decision': 'drop', 'review_basis': EXCLUDED_BASIS,
                            'exclusion_reason': '当前来源审计中已找不到这张照片'}
    rows = sorted(updated.values(), key=lambda row: (row['source'], row['label'], row['path']))
    write_rows(review_path, REVIEW_FIELDS, rows)
    return review_path, labels, rows


def select_with_basis(review_path, labels, rows, sources=()):
    """复用 keep/path/类别校验；将审核依据传入来源 note，使 prepared 仍可区分人工和作者标签。"""
    selection = read_selection(review_path, labels, sources=sources)
    metadata = {row['path']: row for row in rows}
    photos = []
    for photo in selection.photos:
        row = metadata[photo.path]
        provenance = '; '.join(f'{key}={row.get(key) or "unknown"}' for key in
                               ['review_basis', 'source_label', 'region', 'group_status', 'collection_group'])
        photos.append(replace(photo, note=provenance + ('; ' + photo.note if photo.note else '')))
    selection.photos = photos
    return selection


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crop', choices=['maize', 'peanut'], required=True)
    parser.add_argument('--source', action='append', default=[], help='只检查/处理这个来源，可重复指定')
    parser.add_argument('--check', action='store_true', help='只同步筛选表和打印统计，不生成工作图')
    parser.add_argument('--accept-source-labels', action='store_true', help='显式接受作者标签用于内部实验，不表示人工审过图')
    parser.add_argument('--output', type=Path, help='显式指定工作集路径，建议 data/<crop>/prepared；不指定时只检查')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)
    try:
        review, labels, rows = sync_review(ROOT, args.crop, sources=args.source,
                                          accept_source_labels=args.accept_source_labels)
        selection = select_with_basis(review, labels, rows, args.source)
        print_selection(selection, labels, review)
        selected = [row for row in rows if not args.source or row['source'] in args.source]
        print('审核依据：', dict(Counter(row['review_basis'] for row in selected)), flush=True)
        print('空 group 表示采集身份未知，后续仅能恢复近重复组；不会声称同叶/同株信息齐全。', flush=True)
        if args.output is not None and not args.check:
            if args.output.exists():
                raise FileExistsError(f'工作集已存在：{args.output}。先用 --check 核对筛选表，本命令不覆盖现有工作集。')
            report = build_dataset(selection, labels, args.output, args.seed, crop=args.crop)
            print_report(report, labels, args.output)
        else:
            print('本次仅更新筛选表，未生成工作图、未做数据增强、未训练。', flush=True)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'作物数据整理未完成：{exc}\n')


if __name__ == '__main__':
    main()

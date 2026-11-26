"""Pretoria 玉米田间库的多标签审计与固定外部评估清单。

python -m ml.agrivision_ml.preprocessing.pretoria_field

本模块只读取原图、统计并建立外部评估候选，不修改训练集。
GLS/NCLB/PLS/CR/SR 可同时为 1；绝不取第一个病名强行当作单标签。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from .source_collection import ROOT, audit_image, contact_sheet, save_json, write_csv

SOURCE_ID = 'pretoria-field-20237613-v1'
# 缩写由作者 ReadMe 与 Database.csv 确认。保留 Other/Unknown，不把它们伪装成健康。
LABELS = {
    'GLS': 'maize_gray_leaf_spot',
    'NCLB': 'maize_northern_blight',
    'PLS': 'maize_phaeosphaeria_leaf_spot',
    'CR': 'maize_common_rust',
    'SR': 'maize_southern_rust',
    'NoFoliarSymptoms': 'healthy',
    'Other': 'other_visible_feature',
    'UnidentifiedDisease': 'unidentified_disease',
}
PV_LABELS = {'GLS', 'NCLB', 'CR', 'NoFoliarSymptoms'}


def read_annotations(path: Path) -> list[dict]:
    """以实际 CSV 的多热格式为准；旧 README 中的逐行格式仅作说明。"""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if len({row['filePath'] for row in rows}) != len(rows):
        raise ValueError('标注文件名不唯一，需核对后再连接图像。')
    for row in rows:
        if any(row[key] not in {'0', '1'} for key in LABELS):
            raise ValueError(f"非二元标签：{row['filePath']}")
    return rows


def evaluation_role(active: list[str]) -> str:
    """评估用途由标签规则预先决定，不根据模型预测挑选容易的图片。"""
    if 'NoFoliarSymptoms' in active and any(key in active for key in ['GLS', 'NCLB', 'PLS', 'CR', 'SR', 'UnidentifiedDisease']):
        return 'annotation_conflict'
    if len(active) == 1 and active[0] in PV_LABELS:
        return 'single_supported'
    if len(active) > 1:
        return 'multi_label'
    return 'out_of_scope'


def mark_pixel_label_conflicts(rows: list[dict]) -> set[str]:
    """相同像素却有不同标签时整组暂缓，不能因读取顺序保留首张冲突图。"""
    labels_by_pixel = defaultdict(set)
    for row in rows:
        if row['pixel_sha256']:
            labels_by_pixel[row['pixel_sha256']].add(row['source_labels'])
    conflicts = {digest for digest, labels in labels_by_pixel.items() if len(labels) > 1}
    for row in rows:
        row['pixel_label_conflict'] = row['pixel_sha256'] in conflicts
        if row['pixel_label_conflict']:
            row['review'] = 'hold'
            row['reason'] = '相同像素的官方标签不一致，整组暂缓；保留原标签供复核'
    return conflicts


def capture_metadata(path: Path) -> dict:
    """仅保留照片实际 EXIF 和文件名明写的站点提示，不推断同株或同叶编号。"""
    output = {'capture_datetime': '', 'camera_model': '', 'site_hint': 'Cedara' if 'Cedara' in path.name else 'unknown',
              'site_hint_basis': 'explicit_filename' if 'Cedara' in path.name else 'not_provided'}
    with Image.open(path) as opened:
        exif = opened.getexif()
        if exif:
            exif_ifd = exif.get_ifd(34665) if 34665 in exif else {}
            output['capture_datetime'] = str(exif_ifd.get(36867) or exif.get(306) or '')
            output['camera_model'] = str(exif.get(272) or '').strip()
    return output


def audit(metadata_only: bool = False) -> dict:
    """完整解码/精确查重与抽样联系表；元数据预览不会宣称原图已经校验。"""
    source_root = ROOT / 'data/maize/sources' / SOURCE_ID
    output = ROOT / 'data/maize/evaluation'
    annotations_path = source_root / 'metadata/Database.csv'
    annotations = read_annotations(annotations_path)
    raw = source_root / 'raw/leaf_images'
    rows, seen_pixels, sampled_groups = [], {}, defaultdict(list)
    # 独立外测先检查是否与已有来源像素完全相同，重复不能再当外部证据。
    existing_audit = ROOT / 'data/maize/review/source-audit.csv'
    existing_pixels = {}
    if existing_audit.exists():
        with existing_audit.open(encoding='utf-8-sig', newline='') as stream:
            existing_pixels = {row['pixel_sha256']: row['path'] for row in csv.DictReader(stream)
                               if row.get('pixel_sha256') and row.get('source') != SOURCE_ID}
    resolution = Counter()
    for item in tqdm(annotations, desc='Pretoria field audit', unit='image', mininterval=5):
        path = raw / item['filePath']
        if not path.resolve().is_relative_to(raw.resolve()):
            raise ValueError('标注文件名超出当前来源的原图目录。')
        active = [key for key in LABELS if item[key] == '1']
        role = evaluation_role(active)
        if metadata_only:
            result = {'width': '', 'height': '', 'pixel_sha256': '', 'error': 'not_audited'}
            capture = {'capture_datetime': '', 'camera_model': '', 'site_hint': 'Cedara' if 'Cedara' in path.name else 'unknown',
                       'site_hint_basis': 'explicit_filename' if 'Cedara' in path.name else 'not_provided'}
        else:
            result = audit_image(path)
            capture = capture_metadata(path) if not result['error'] else {'capture_datetime': '', 'camera_model': '', 'site_hint': 'unknown', 'site_hint_basis': 'unreadable'}
        digest = result['pixel_sha256']
        duplicate_of = seen_pixels.get(digest, '') if digest else ''
        relative = path.relative_to(ROOT).as_posix()
        if digest and not duplicate_of:
            seen_pixels[digest] = relative
        row = {
            'path': relative, 'image_id': item['imgID_id'], 'source': SOURCE_ID,
            'source_url': 'https://doi.org/10.25403/UPresearchdata.20237613.v1',
            'license': 'CC BY 4.0', 'region': 'South Africa',
            # Other 类实际包含采集记录板等非叶片照片，不能一概标成叶片。
            'part': 'unknown' if active == ['Other'] else 'leaf',
            'group': 'unknown', 'group_status': 'capture_identity_not_published',
            'split': 'external', 'source_split': 'external', 'evaluation_role': role,
            # label 只对预先定义的纯单标签四类子集填写；多标签始终保存在 labels_json。
            'label': LABELS[active[0]] if role == 'single_supported' else '',
            'labels_json': json.dumps([LABELS[key] for key in active]),
            'source_labels': '|'.join(active), **{key: int(item[key]) for key in LABELS},
            'review': 'hold' if role == 'annotation_conflict' else 'review',
            'reason': '无叶部症状与病症标签同时为1，需核对' if role == 'annotation_conflict' else '外部评估候选；未逐图人工确认',
            'duplicate_of': duplicate_of, 'cross_source_duplicate_of': existing_pixels.get(digest, ''), **capture, **result,
        }
        rows.append(row)
        if not metadata_only and not result['error']:
            resolution[f"{result['width']}x{result['height']}"] += 1
            for key in active:
                sampled_groups[key].append(path)
            if len(active) > 1:
                sampled_groups['multi_label'].append(path)
    pixel_label_conflicts = mark_pixel_label_conflicts(rows)
    # 整库外测保留全部标签；纯单病4类只用于与 PlantVillage 基线的同标签对照。
    # 其它疾病/多病/未知不能从总报告中消失，也不能算作该4分类器的普通accuracy。
    # 单标签专用清单兼容已有 evaluate --split test；source_split 仍明确为 external。
    strict = [dict(row, split='test') for row in rows if row['evaluation_role'] == 'single_supported'
              and not row['pixel_label_conflict'] and not row['duplicate_of']
              and not row['cross_source_duplicate_of'] and not row['error']]
    sampled = {}
    if not metadata_only:
        for key, paths in sampled_groups.items():
            sampled[key] = contact_sheet(paths, output / 'samples' / f'pretoria-{key}.jpg', f'Pretoria field | {key}')
    report = {
        'source_id': SOURCE_ID, 'doi': '10.25403/UPresearchdata.20237613.v1', 'license': 'CC BY 4.0',
        'metadata_only': metadata_only, 'annotation_sha256': hashlib.sha256(annotations_path.read_bytes()).hexdigest(),
        'image_count': len(rows), 'decode_errors': None if metadata_only else sum(bool(row['error']) for row in rows),
        'exact_pixel_duplicate_entries': None if metadata_only else sum(bool(row['duplicate_of']) for row in rows),
        'cross_source_pixel_duplicates': None if metadata_only else sum(bool(row['cross_source_duplicate_of']) for row in rows),
        'pixel_label_conflict_groups': None if metadata_only else len(pixel_label_conflicts),
        'pixel_label_conflict_images': None if metadata_only else sum(row['pixel_label_conflict'] for row in rows),
        'source_label_counts': {key: sum(row[key] for row in rows) for key in LABELS},
        'evaluation_roles': dict(Counter(row['evaluation_role'] for row in rows)),
        'multi_label_images': sum(len(row['source_labels'].split('|')) > 1 for row in rows),
        'strict_single_supported_after_quality_check': len(strict),
        'strict_single_supported_class_counts': dict(Counter(row['label'] for row in strict)),
        'site_hints': dict(Counter(row['site_hint'] for row in rows)),
        'capture_datetime_available': sum(bool(row['capture_datetime']) for row in rows),
        'camera_models': dict(Counter(row['camera_model'] or 'unknown' for row in rows)),
        'capture_years': dict(Counter(row['capture_datetime'][:4] if row['capture_datetime'][:4].isdigit() else 'unknown' for row in rows)),
        'known_capture_groups': 0, 'resolutions': dict(resolution.most_common()), 'sampled_paths': sampled,
        'visual_review': json.loads((source_root / 'metadata/visual-review.json').read_text(encoding='utf-8')) if (source_root / 'metadata/visual-review.json').exists() else 'pending',
        'assessment': [
            '固定整来源作为田间外部评估候选，不用于选参或训练；报告模型时另外列多标签/未知场景。',
            '实际ZIP只有扁平目录；CSV没有采集站点/植株/叶ID。文件名Cedara仅为站点提示，不视作完整采集分组。',
            'NoFoliarSymptoms不是对一切健康的保证，仅是该来源未标注叶部症状。',
            'Other类别包含非叶片采集情境图，不纳入纯单标签四类子集。',
            '联系表为均匀抽样，不代表全库逐张通过水印、拼图或标签质量审核。',
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    suffix = '.metadata' if metadata_only else ''
    write_csv(output / f'pretoria-field{suffix}.csv', rows)
    if not metadata_only:
        write_csv(output / 'pretoria-field-single-supported.csv', strict, fieldnames=list(rows[0]))
    save_json(output / f'pretoria-field{suffix}.json', report)
    print(json.dumps({key: report[key] for key in ['image_count', 'decode_errors', 'evaluation_roles', 'multi_label_images', 'strict_single_supported_after_quality_check', 'site_hints']}, ensure_ascii=False, indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-only', action='store_true', help='仅在下载过程中核对标签，不宣称图像已验证')
    args = parser.parse_args()
    audit(args.metadata_only)


if __name__ == '__main__':
    main()

"""肯尼亚 PLANTHEAD 花生原图审计；固定为外部评估，不生成训练划分。

python -m ml.agrivision_ml.preprocessing.planthead_peanut

保留早/晚叶斑的原始病原标签；当前模型的混合叶斑类仅在评估标签中合并。
原来源没有 Alternaria 类，因此报告只能覆盖当前花生模型的三个类别。
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict

from tqdm import tqdm

from .source_collection import ROOT, IMAGE_SUFFIXES, audit_image, contact_sheet, save_json, write_csv

SOURCE_ID = 'planthead-peanut-17053222'
LABELS = {
    'ARHHY_GRV000_groundnut rosette virus': '',
    'ARHHY_MYCOAR_passalora arachidicola': 'peanut_leaf_spot',
    'ARHHY_MYCOBE_nothapassalora personata': 'peanut_leaf_spot',
    'ARHHY_healthy leaves': 'healthy',
    'ARHHY_PHOMAR_phoma arachidicola': '',
    'ARHHY_PUCCAR_puccinia arachidis': 'peanut_rust',
}


def audit() -> dict:
    """逐图解码、同来源及跨来源精确查重；仅抽样检查视觉质量。"""
    source = ROOT / 'data/peanut/sources' / SOURCE_ID
    status = json.loads((source / 'download-status.json').read_text(encoding='utf-8'))
    if not status.get('complete'):
        raise ValueError('原始下载尚未完整，不能生成正式外测清单。')
    raw = source / 'raw'
    visual = source / 'metadata/visual-review.json'
    quality = json.loads(visual.read_text(encoding='utf-8')) if visual.exists() else {'decision': 'pending'}
    output = ROOT / 'data/peanut/evaluation'
    existing = ROOT / 'data/peanut/review/source-audit.csv'
    known_pixels = {}
    if existing.exists():
        with existing.open(encoding='utf-8-sig', newline='') as stream:
            known_pixels = {row['pixel_sha256']: row['path'] for row in csv.DictReader(stream)
                            if row.get('pixel_sha256') and row.get('source') != SOURCE_ID}
    rows, seen, by_source_label = [], {}, defaultdict(list)
    paths = sorted(path for path in raw.rglob('*') if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    if not paths:
        raise ValueError('完整原包中没有找到照片。')
    for path in tqdm(paths, desc='PLANTHEAD peanut audit', unit='image', mininterval=5):
        original_label = path.relative_to(raw).parts[0]
        if original_label not in LABELS:
            raise ValueError(f'出现未登记的来源类别：{original_label}')
        result = audit_image(path)
        digest = result['pixel_sha256']
        relative = path.relative_to(ROOT).as_posix()
        duplicate = seen.get(digest, '') if digest else ''
        if digest and not duplicate:
            seen[digest] = relative
        label = LABELS[original_label]
        row = {
            'path': relative, 'source': SOURCE_ID, 'source_url': 'https://doi.org/10.5281/zenodo.17053222',
            'label': label, 'source_label': original_label,
            'license': 'CC BY 4.0', 'region': 'Kenya', 'part': 'leaf',
            'group': 'unknown', 'group_status': 'capture_identity_not_published',
            'split': 'external', 'source_split': 'external',
            'evaluation_role': 'single_supported' if label else 'out_of_scope',
            'review': 'review' if label and quality['decision'] == 'candidate' else 'hold',
            'reason': quality.get('reason', '来源视觉质量待核对') if quality['decision'] != 'candidate' else ('固定外测候选；未逐图人工确认' if label else '当前模型未覆盖，保留原标注供未知场景分析'),
            'duplicate_of': duplicate, 'cross_source_duplicate_of': known_pixels.get(digest, ''), **result,
        }
        rows.append(row)
        if not result['error']:
            by_source_label[original_label].append(path)
    # 仅兼容已有 evaluate --split test，不改变整来源 external 的实际用途。
    compatible = [row for row in rows if row['label'] and not row['error']
                  and not row['duplicate_of'] and not row['cross_source_duplicate_of']]
    # 来源被水印等质量问题否决时，保留审计，不把可映射标签偷换为可用评估图。
    strict = [dict(row, split='test') for row in compatible if row['review'] == 'review']
    sampled = {label: contact_sheet(class_paths, output / 'samples' / f'planthead-{index}.jpg', label)
               for index, (label, class_paths) in enumerate(sorted(by_source_label.items()))}
    report = {
        'source': SOURCE_ID, 'source_url': 'https://doi.org/10.5281/zenodo.17053222',
        'license': 'CC BY 4.0', 'region': 'Kenya', 'image_count': len(rows),
        'decode_errors': sum(bool(row['error']) for row in rows),
        'exact_pixel_duplicate_entries': sum(bool(row['duplicate_of']) for row in rows),
        'cross_source_pixel_duplicates': sum(bool(row['cross_source_duplicate_of']) for row in rows),
        'source_class_counts': dict(Counter(row['source_label'] for row in rows)),
        'resolutions': dict(Counter(f"{row['width']}x{row['height']}" for row in rows)),
        'supported_label_candidates_before_visual_review': len(compatible),
        'strict_supported_count': len(strict), 'strict_supported_classes': dict(Counter(row['label'] for row in strict)),
        'known_capture_groups': 0, 'sampled_paths': sampled,
        'visual_review': quality,
        'assessment': ['固定整个来源供田间外部评估，不用于当前模型训练/交叉验证。',
                       '早、晚叶斑原病原标签分别保留；评估时合并为当前模型支持的叶斑病类。',
                       '当前4类仅覆盖健康、叶斑、锈病3类；缺Alternaria，不代表完整模型表现。',
                       '肯尼亚来源不能替代国内多地验证；没有植株/叶ID，独立采集数量未知。',
                       '抽样联系表不代表全量水印/拼图/标签质量人工审核。'],
    }
    write_csv(output / 'planthead-peanut.csv', rows)
    write_csv(output / 'planthead-peanut-single-supported.csv', strict, fieldnames=list(rows[0]))
    save_json(output / 'planthead-peanut.json', report)
    print(json.dumps({key: report[key] for key in ['image_count', 'decode_errors', 'source_class_counts', 'strict_supported_classes']}, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    audit()

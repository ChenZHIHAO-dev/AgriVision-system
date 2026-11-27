"""台湾番茄无增强分支外域审计；只写评估清单，不并入PlantVillage训练。"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from tqdm import tqdm

from .groups import group_duplicate_photos
from .images import fingerprint
from .source_collection import ROOT, audit_image, contact_sheet, save_json
from .tables import read_rows, write_rows
from .tomato_source import exclude_pixel_conflicts


def audit():
    config=json.loads((ROOT/'configs/datasets/tomato.json').read_text(encoding='utf-8'))
    source=config['external_sources'][0]
    source_root=ROOT/'data/tomato/sources'/source['id']
    raw=source_root/'raw'/source['selected_branch']
    baseline=read_rows(ROOT/'data/tomato/review/source-audit.csv')
    pv_pixels={row['pixel_sha256'] for row in baseline if row['pixel_sha256']}
    paths=sorted(raw.rglob('*'))
    paths=[p for p in paths if p.suffix.lower() in {'.jpg','.jpeg','.png'}]
    # 只接受作者的无增强分支，数量与单独保存的压缩包成员清单一致。
    extraction=json.loads((source_root/'extraction.json').read_text(encoding='utf-8'))
    expected={str(Path(s)) for s in extraction['selected_files']}
    actual={str(p.relative_to(source_root/'raw')) for p in paths}
    if actual != expected:
        raise ValueError('无增强原图成员与已校验压缩包清单不同')
    rows=[]; by_class=defaultdict(list); seen={}; fingerprints=[]
    for path in tqdm(paths,desc='Taiwan original branch audit',unit='image'):
        result=audit_image(path)
        relative=path.relative_to(ROOT).as_posix(); label=path.parent.name
        canonical=source['label_map'].get(label,'')
        reason=source.get('hold_labels',{}).get(label,'')
        if result['error']:
            reason='图片解码失败'
        duplicate=seen.get(result['pixel_sha256'],'')
        if duplicate:
            reason='同来源像素重复：'+duplicate
        elif result['pixel_sha256']:
            seen[result['pixel_sha256']]=relative
        if result['pixel_sha256'] in pv_pixels:
            reason='与PlantVillage原图像素完全重合，不能作独立外测'
        digest,dhash=fingerprint(path)
        rows.append({'path':relative,'label':canonical,'source':source['id'],'source_labels':label,
            'source_url':source['url'],'source_split':path.relative_to(raw).parts[0],
            'split':'test','group':'unknown','group_status':'author_capture_id_unavailable',
            'license':source['license'],'region':source['region'],'part':'leaf',
            'review':'hold' if reason else 'review','reason':reason,'duplicate_of':duplicate,
            'sha256':digest,'near_duplicate_group':'','pixel_sha256':result['pixel_sha256'],
            'width':result['width'],'height':result['height'],'error':result['error']})
        fingerprints.append({'path':relative,'label':canonical or 'unsupported:'+label,'sha256':digest,'dhash':dhash,'external':True})
        by_class[label].append(path)
    # 精确同图跨标签整组暂缓；空 canonical 的类用原标签，不能把所有未知类混成一个。
    temporary=[{**row,'label':row['label'] or 'unsupported:'+row['source_labels']} for row in rows]
    conflicts=exclude_pixel_conflicts(temporary)
    for row, checked in zip(rows,temporary):
        if checked['review']=='hold' and '标签冲突' in checked.get('reason',''):
            row['review'],row['reason']=checked['review'],checked['reason']
    # 两来源共同做近重复候选检测。感知相似不是确证重复，单独列出待人工复核。
    for row in tqdm(baseline,desc='Cross-source perceptual audit',unit='image'):
        digest,dhash=fingerprint(ROOT/row['path'])
        fingerprints.append({'path':row['path'],'label':row['label'],'sha256':digest,'dhash':dhash,'external':False})
    cross=[]; indexed={row['path']:row for row in rows}
    for cluster in group_duplicate_photos(fingerprints):
        external=[r for r in cluster if r['external']]
        if not external:
            continue
        local=[r for r in cluster if not r['external']]
        if local:
            cross.append({'external':[r['path'] for r in external],'plantvillage':[r['path'] for r in local]})
            for r in external:
                indexed[r['path']]['review']='hold'
                indexed[r['path']]['reason']='与PV有感知近重复候选，待人工确认；未据模型对错删图'
        group=hashlib.sha256('|'.join(sorted(r['sha256'] for r in external)).encode()).hexdigest()[:20]
        for r in external:
            indexed[r['path']]['near_duplicate_group']=group
    # 人工图像质量决定独立于模型预测，重跑审计时也要保留排除理由。
    # 此表只检查水印/拼图等可见瑕疵，不代表逐张病理确诊。
    decisions_path=ROOT/'data/tomato/review/taiwan-quality-review.csv'
    if decisions_path.exists():
        for decision in read_rows(decisions_path):
            if decision['review'] not in {'hold', 'drop'}:
                raise ValueError('质量排除表只接受 hold/drop，不能覆盖自动重复检查')
            row=indexed[decision['path']]
            row['review']=decision['review']
            row['reason']=decision['reason']
    output=ROOT/'data/tomato/evaluation'; output.mkdir(parents=True,exist_ok=True)
    write_rows(output/'taiwan-audit.csv',list(rows[0]),rows)
    selected=[row for row in rows if row['review']=='review' and row['label']]
    write_rows(output/'taiwan-supported.csv',list(rows[0]),selected)
    samples={label:contact_sheet(items,output/'samples'/f'taiwan-{i}.jpg',label)
             for i,(label,items) in enumerate(sorted(by_class.items()))}
    summary={'images':len(rows),'source':source,'class_counts':dict(Counter(row['source_labels'] for row in rows)),
             'supported_images':len(selected),'supported_counts':dict(Counter(row['label'] for row in selected)),
             'review_counts':dict(Counter(row['review'] for row in rows)),
             'exclusion_reasons':dict(Counter(row['reason'] for row in rows if row['reason'])),
             'cross_source_near_duplicate_candidates':cross,'pixel_label_conflicts':conflicts,
             'samples':samples,'scope':'独立来源部分标签开发诊断；未用于PV训练/选C/校准，未逐图病名人工核验。'}
    save_json(output/'taiwan-audit.json',summary)
    print(json.dumps({key:summary[key] for key in ['images','supported_images','supported_counts','review_counts','exclusion_reasons']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    audit()

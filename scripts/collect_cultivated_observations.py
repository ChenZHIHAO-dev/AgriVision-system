"""补充 GBIF 不充分覆盖的栽培作物观察；小批量取公开许可照片，不抓取整站。

默认补花生/水稻/大豆；--crops 可补其他稀缺目标。iNaturalist casual 包含栽培记录，不等于专家审核；
保留质量级别和栽培标记，供独立筛图。按照片 ID 复用已有 GBIF 文件。
官方建议元数据约 1 请求/秒，本入口顺序请求且每次间隔 1.1 秒。
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode

from scripts.collect_crop_observations import ROOT, FIELDS, read_url, allowed_license, collect_photos

EXTRA_FIELDS = ['quality_grade', 'captive']
LICENSES = {'cc0':'https://creativecommons.org/publicdomain/zero/1.0/',
            'cc-by':'https://creativecommons.org/licenses/by/4.0/',
            'cc-by-sa':'https://creativecommons.org/licenses/by-sa/4.0/'}


def photo_number(url):
    found=re.search(r'/photos/(\d+)/',url)
    return found.group(1) if found else None


def existing_photos():
    """只复用本项目 sources 下真实存在的文件；不复制 GBIF/CN/ALL 同一原图。"""
    lookup={}
    review=ROOT/'data/crop-identification/review'
    for file in [*review.glob('gbif-*.csv'),*review.glob('inat-*.csv')]:
        for row in csv.DictReader(file.open(encoding='utf-8-sig')):
            number=photo_number(row['photo_url'])
            if number and (ROOT/row['path']).is_file(): lookup[number]=row
    return lookup


def observations(target, folder, refresh=False):
    """去除精确位置和无关账户资料后缓存；照片许可逐张检查，不沿用观察记录许可。"""
    cache=folder/(target['id']+'.json')
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding='utf-8'))
    records=[];page=1;total=0
    while True:
        params=urlencode({'taxon_name':target['scientific_name'],'photos':'true',
                          'photo_license':'cc0,cc-by,cc-by-sa','per_page':200,'page':page})
        data=json.loads(read_url('https://api.inaturalist.org/v1/observations?'+params))
        total=data['total_results']
        for row in data['results']:
            records.append({key:row.get(key) for key in ['id','uri','taxon','quality_grade','captive','photos']})
        time.sleep(1.1)
        if len(records)>=min(total,1000) or not data['results']:break
        page+=1
    result={'provider':'iNaturalist v1 public API','total_records':total,'records':records,
            'scope':'包括栽培和 casual 记录；未逐张人工核对物种'}
    cache.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def candidates(target,data,existing):
    """原标签一致才接纳；不是目标种的属级记录和野大豆不混入栽培类别。"""
    seen=set()
    for record in data['records']:
        name=(record.get('taxon') or {}).get('name','')
        if name.split()[:2]!=target['scientific_name'].split()[:2]:continue
        if any(name.startswith(taxon) for taxon in target.get('excluded_taxa',[])):continue
        observation='https://www.inaturalist.org/observations/'+str(record['id'])
        for photo in record.get('photos') or []:
            license_url=LICENSES.get(photo.get('license_code'),'')
            url=photo.get('url','')
            number=photo_number(url)
            if not number or number in seen or not allowed_license(license_url):continue
            seen.add(number)
            previous=existing.get(number,{})
            row={field:'' for field in [*FIELDS,*EXTRA_FIELDS]}
            row.update(id=previous.get('id') or hashlib.sha256(('inaturalist-photo:'+number).encode()).hexdigest()[:20],
                label=target['id'],name=target['name'],scientific_name=target['scientific_name'],source_scientific_name=name,
                path=previous.get('path',''),width=previous.get('width',''),height=previous.get('height',''),
                group='observation:'+hashlib.sha256(observation.encode()).hexdigest()[:20],
                organ='待看图',review=previous.get('review','review'),reason=previous.get('reason','待人工核对物种/水印/拼图'),
                license=license_url,author=photo.get('attribution',''),rights_holder=photo.get('attribution',''),
                photo_url=previous.get('photo_url') or url,photo_page=observation,observation_id=observation,
                quality_grade=record.get('quality_grade',''),captive=str(record.get('captive','')).lower(),
                download_url=previous.get('download_url',''),download_variant=previous.get('download_variant',''))
            yield row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-images',type=int,default=400)
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--crops',nargs='+',default=['peanut','rice','soybean'],help='目标清单中的作物 ID')
    args=parser.parse_args()
    config=json.loads((ROOT/'configs/datasets/crop-identification.json').read_text(encoding='utf-8-sig'))
    known={row['id'] for row in config['targets']}
    if not set(args.crops)<=known:parser.error('指定的作物不在目标配置中')
    targets=[row for row in config['targets'] if row['id'] in args.crops]
    base=ROOT/'data/crop-identification';folder=base/'sources/inat-cultivated';folder.mkdir(parents=True,exist_ok=True)
    table=base/'review/inat-cultivated.csv';existing=existing_photos()
    previous={row['id']:row for row in csv.DictReader(table.open(encoding='utf-8-sig'))} if table.exists() else {}
    report_path=folder/'source.json'
    report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    for target in targets:
        data=observations(target,folder,args.refresh)
        selected=list(candidates(target,data,existing))[:args.max_images]
        reused=[row for row in selected if row['path']]
        needed=[row for row in selected if not row['path']]
        downloaded,failures=collect_photos(needed,folder,len(needed),workers=4,photo_size='large') if needed else ([],[])
        for row in [*reused,*downloaded]:
            old=previous.get(row['id'],{})
            if old.get('review') in {'keep','drop'}:
                row['review'],row['reason']=old['review'],old.get('reason','')
            previous[row['id']]=row
        temp=table.with_suffix('.tmp')
        with temp.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=[*FIELDS,*EXTRA_FIELDS]);writer.writeheader()
            writer.writerows(sorted(previous.values(),key=lambda row:(row['label'],row['id'])))
        temp.replace(table)
        report[target['id']]={'records_found':data['total_records'],'selected_photos':len(selected),
            'reused_existing_files':len(reused),'new_files':len(downloaded),'failures':failures,
            'observations':len({row['observation_id'] for row in [*reused,*downloaded]}),
            'quality_grade':dict(Counter(row['quality_grade'] for row in [*reused,*downloaded]))}
        (folder/'source.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(target['name'],json.dumps(report[target['id']],ensure_ascii=False),flush=True)
    print('待筛表：',table,flush=True)


if __name__=='__main__':main()

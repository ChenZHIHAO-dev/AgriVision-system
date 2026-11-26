"""Collect openly licensed manual-use photographs; never run the classifier on them."""
import csv
import hashlib
import html
from io import BytesIO
import json
from pathlib import Path
import re
import time

import httpx
import numpy as np
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[1]
QUERIES=[
    ('wheat_stripe_rust','filetype:bitmap incategory:"Puccinia striiformis"'),
    ('wheat_stripe_rust','filetype:bitmap "Puccinia striiformis" "Triticum"'),
    ('wheat_stripe_rust','filetype:bitmap "Stripe rust on wheat"'),
    ('wheat_stripe_rust','filetype:bitmap tarwe "gele roest"'),
    ('wheat_leaf_rust','filetype:bitmap "Puccinia triticina" "Triticum"'),
    ('wheat_leaf_rust','filetype:bitmap incategory:"Puccinia triticina"'),
    ('wheat_leaf_rust','filetype:bitmap "Puccinia recondita" "Triticum"'),
    ('wheat_powdery_mildew','filetype:bitmap "Blumeria graminis" "Triticum"'),
    ('wheat_powdery_mildew','filetype:bitmap "Erysiphe graminis" wheat'),
    ('wheat_powdery_mildew','filetype:bitmap wheat mildew leaf'),
    ('wheat_powdery_mildew','filetype:bitmap tarwe meeldauw'),
    ('wheat_reference','filetype:bitmap "Triticum aestivum" leaves -Stack'),
]


def phash(image):
    values=np.asarray(image.convert('L').resize((9,8)))
    return int(''.join('1' if item else '0' for item in (values[:,1:]>values[:,:-1]).flat),2)


def plain(value): return html.unescape(re.sub('<[^>]*>',' ',value or '')).strip()


def main():
    output=ROOT/'data/manual-tests/wheat-real-photos';output.mkdir(parents=True,exist_ok=True)
    if any(output.glob('sample-*.jpg')):
        raise SystemExit('Output already contains photos. Review it instead of silently overwriting the manual set.')
    with (ROOT/'data/wheat-v1/sources.csv').open(encoding='utf-8') as stream: source_rows=list(csv.DictReader(stream))
    known_pixels={row['pixel_sha256'] for row in source_rows}
    known_hashes=[int(row['dhash']) for row in source_rows]
    for path in (ROOT/'data/wheat/sources/jic-7307816').iterdir():
        if path.suffix.lower() not in {'.jpg','.jpeg','.png'}:continue
        with Image.open(path) as image:
            image=ImageOps.exif_transpose(image).convert('RGB');known_hashes.append(phash(image))
    kept=[];excluded=[];titles=set()
    with httpx.Client(timeout=45,follow_redirects=True,headers={'User-Agent':'AgriVision-local-testing/1.2 (https://github.com/ChenZHIHAO-dev/AgriVision-system)'}) as client:
        for label,query in QUERIES:
            if sum(row['reference_label']==label for row in kept)>=5:continue
            response=client.get('https://commons.wikimedia.org/w/api.php',params={'action':'query','generator':'search','gsrsearch':query,'gsrnamespace':6,'gsrlimit':12,'prop':'imageinfo','iiprop':'url|extmetadata|mime|size','iiurlwidth':1200,'format':'json'})
            response.raise_for_status()
            pages=response.json().get('query',{}).get('pages',{})
            for page in pages.values():
                title=page['title']
                if title in titles:continue
                titles.add(title)
                info=page.get('imageinfo',[{}])[0];metadata=info.get('extmetadata',{})
                license=metadata.get('LicenseShortName',{}).get('value','')
                low=license.lower()
                if not any(allowed in low for allowed in ('cc by','cc0','public domain')) or any(blocked in low for blocked in ('nc','nd')):continue
                if info.get('mime') not in {'image/jpeg','image/png'} or min(info.get('width',0),info.get('height',0))<240:continue
                description=plain(metadata.get('ImageDescription',{}).get('value',''))
                if re.search(r'\(IA |catalogue|field crops \(19|system|diagram|illustration|microscop|spore|drawing|plate |Stack|epidermis|stomata|lifecycle',title+' '+description,re.I):continue
                if re.search(r'Elymus|Hordeum|Secale|Avena|Thalictrum|triticale|tritik',title+' '+description,re.I):continue
                if not re.search(r'Triticum|wheat|tarwe|Weizen',title+' '+description,re.I):continue
                # These metadata descriptions omit the microscope magnification;
                # visual review found them unsuitable for phone-photo testing.
                if title in {
                    'File:Erysiphe graminis.jpg',
                    'File:Puccinia recondita f.sp. tritici on Triticum aestivum, Bruine roest op gewone tarwe uredosori.jpg',
                    'File:Puccinia recondita f.sp. tritici on Triticum aestivum, Bruine roest op gewone tarwe uredosorum.jpg',
                }:continue
                if sum(row['reference_label']==label for row in kept)>=5:break
                url=(info.get('thumburl') if info.get('width',0)>1800 else info.get('url')) or info['url']
                try:
                    result=client.get(url);result.raise_for_status()
                    with Image.open(BytesIO(result.content)) as original:
                        image=ImageOps.exif_transpose(original).convert('RGB')
                        pixel=hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
                        probes=[phash(image),phash(ImageOps.mirror(image)),phash(ImageOps.flip(image)),phash(image.rotate(180))]
                        if pixel in known_pixels or any((probe^known).bit_count()<=8 for probe in probes for known in known_hashes):
                            excluded.append({'source':title,'reason':'matches or nearly matches training/validation/test/JIC imagery'});continue
                        image.thumbnail((1600,1600))
                        filename=f'sample-{len(kept)+1:02d}.jpg'
                        image.save(output/filename,'JPEG',quality=94)
                        known_pixels.add(pixel);known_hashes.extend(probes)
                    kept.append({'file':filename,'reference_label':label,'source_title':title,'source_url':info['descriptionurl'],'author':plain(metadata.get('Artist',{}).get('value','')),'license':license,'license_url':metadata.get('LicenseUrl',{}).get('value',''),'reference_description':plain(metadata.get('ImageDescription',{}).get('value',''))[:1200],'notes':'source reference only; not expert-confirmed Nanyang ground truth; resized, EXIF removed; never used for fitting, calibration or scoring'})
                    print(json.dumps({'saved':filename,'reference_label':label,'license':license,'source_title':title}),flush=True)
                except (httpx.HTTPError,OSError,ValueError) as exc:
                    excluded.append({'source':title,'reason':type(exc).__name__})
                time.sleep(.2)
    if kept:
        with (output/'参考标签与来源.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(kept[0]));writer.writeheader();writer.writerows(kept)
    report={'images':len(kept),'by_reference_label':{label:sum(row['reference_label']==label for row in kept) for label,_ in QUERIES},'excluded':excluded,'not_run_through_model':True,'deduplication':'pixel identity and dHash<=8 across mirrored variants vs all model-source images and JIC; cannot guarantee every crop/derivative relationship is detected'}
    (output/'collection-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'README.md').write_text('# 小麦软件手动试用图片\n\n这些实拍图片单独保留，不参加训练、验证、阈值选择或模型评分，也未预先运行识别。\n\n先在软件中选择小麦，再上传 sample-XX.jpg。参考标签见 CSV；wheat_reference 只表示小麦实拍，不能视为已经证明健康。标签来自原作者描述，不是农技人员对南阳现场样本的确诊。\n\n已做与主数据及 JIC 的像素与感知哈希近重复排除，仍可能存在检测不到的裁剪关系。请记录识别结果、不确定提示和明显错误，后续一起复核，不要把几张试图的结果当成准确率。\n\n来源、作者、许可及图片说明均保存在 CSV。图片仅保存在本地，未上传 GitHub。\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='excluded'}),flush=True)


if __name__=='__main__':main()

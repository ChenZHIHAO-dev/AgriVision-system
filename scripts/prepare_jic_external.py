"""Exclude cross-source duplicates before an exploratory JIC external check."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[1]
MAPPING={'BrownRust':'wheat_leaf_rust','YellowRust':'wheat_stripe_rust','Mildew':'wheat_powdery_mildew','Healthy':'healthy','Septoria':'wheat_other'}


def phash(image):
    values=np.asarray(image.convert('L').resize((9,8)))
    return int(''.join('1' if value else '0' for value in (values[:,1:]>values[:,:-1]).flat),2)


def main():
    dataset=ROOT/'data/wheat-v1'
    with (dataset/'sources.csv').open(encoding='utf-8') as stream: source_rows=list(csv.DictReader(stream))
    known_pixels={row['pixel_sha256'] for row in source_rows}
    known_hashes=[int(row['dhash']) for row in source_rows]
    output=dataset/'external-jic';rows=[];excluded=[];seen=set()
    for path in sorted((ROOT/'data/wheat/sources/jic-7307816').iterdir()):
        if path.suffix.lower() not in {'.jpg','.jpeg','.png'}:continue
        label=next((value for prefix,value in MAPPING.items() if path.name.startswith(prefix)),None)
        if label is None:continue
        with Image.open(path) as original:
            image=ImageOps.exif_transpose(original).convert('RGB')
            pixel=hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
            if pixel in known_pixels or pixel in seen:
                excluded.append({'file':path.name,'reason':'identical pixels'});continue
            image.thumbnail((640,640))
            probes=[phash(image),phash(ImageOps.mirror(image)),phash(ImageOps.flip(image)),phash(image.rotate(180))]
            if any((probe^known).bit_count()<=8 for probe in probes for known in known_hashes):
                excluded.append({'file':path.name,'reason':'near-duplicate of main source (dHash <=8, mirrored variants)'});continue
            seen.add(pixel)
            relative=f'{label}/{path.name.rsplit(".",1)[0]}.jpg'
            target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);image.save(target,'JPEG',quality=94)
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        rows.append({'path':relative,'label':label,'group':'jic-'+pixel[:20],'sha256':digest,'split':'test'})
    manifest=dataset/'external-jic.csv'
    with manifest.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['path','label','group','sha256','split']);writer.writeheader();writer.writerows(rows)
    report={'source':'https://zenodo.org/records/7307816','license':'CC-BY-4.0','kept':len(rows),'excluded_overlap_or_duplicate':len(excluded),'counts':{label:sum(row['label']==label for row in rows) for label in MAPPING.values()},'exclusions':excluded,'scope':'exploratory cross-source subset; not Nanyang field validation; source plot/plant identities unavailable'}
    (dataset/'external-jic-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='exclusions'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

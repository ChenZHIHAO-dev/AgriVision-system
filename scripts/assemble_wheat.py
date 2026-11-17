"""Create a versioned local wheat classifier dataset without copying source archives into Git."""
from collections import Counter
import csv
import hashlib
from io import BytesIO
import json
from pathlib import Path
import random
import re
import zipfile

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'brown rust':'wheat_leaf_rust','yellow rust':'wheat_stripe_rust','mildew':'wheat_powdery_mildew','healthy':'healthy'}


def dhash(image):
    gray = np.asarray(image.convert('L').resize((9,8)))
    return int(''.join('1' if value else '0' for value in (gray[:,1:]>gray[:,:-1]).flat),2)


def main():
    source = ROOT/'data/sources/kaggle-wheat-v6.zip'
    output = ROOT/'data/wheat-v1'
    images = output/'images'
    rows, rejected, seen = [], [], set()
    with zipfile.ZipFile(source) as archive:
        by_category = {}
        for item in archive.infolist():
            parts = item.filename.split('/')
            if len(parts)!=4 or parts[0]!='data' or Path(item.filename).suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}: continue
            category = re.sub(r'_(test|valid)$','',parts[2].lower()).replace('_',' ')
            by_category.setdefault(category, []).append(item)
        chosen = []
        for category, items in sorted(by_category.items()):
            if category not in LABELS:
                random.Random(42).shuffle(items)
                items = items[:150]
            chosen.extend((category,item) for item in items)
        for index,(category,item) in enumerate(chosen):
            try:
                content = archive.read(item)
                raw_hash = hashlib.sha256(content).hexdigest()
                with Image.open(BytesIO(content)) as original:
                    image = ImageOps.exif_transpose(original).convert('RGB')
                    if min(image.size)<64: raise ValueError('small image')
                    pixel_hash = hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
                    if pixel_hash in seen: continue
                    seen.add(pixel_hash)
                    label = LABELS.get(category,'wheat_other')
                    image.thumbnail((640,640))
                    relative = f'{label}/kaggle_{pixel_hash[:24]}.jpg'
                    path = images/relative; path.parent.mkdir(parents=True,exist_ok=True)
                    image.save(path,'JPEG',quality=94)
                    rows.append({'path':relative,'label':label,'source':'kaggle-wheat-v6','original':item.filename,'original_split':item.filename.split('/')[1], 'original_category':category,'raw_sha256':raw_hash,'pixel_sha256':pixel_hash,'dhash':str(dhash(image))})
            except (OSError,ValueError) as exc:
                rejected.append({'file':item.filename,'reason':str(exc)[:120]})
            if (index+1)%250==0: print(json.dumps({'processed':index+1,'total':len(chosen),'unique':len(rows)}),flush=True)
    output.mkdir(parents=True,exist_ok=True)
    with (output/'sources.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader();writer.writerows(rows)
    report={'source':'https://www.kaggle.com/datasets/kushagra3204/wheat-plant-diseases','version':6,'license':'CC0','selected_files':len(chosen),'unique_pixel_images':len(rows),'counts':dict(Counter(row['label'] for row in rows)),'rejected':rejected,'other_sampling':'up to 150 images per unsupported source category; seed=42','source_splits':'pooled then regrouped to reduce duplicate leakage; original split retained in sources.csv'}
    (output/'import-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()

"""只下载作者 PlantVillage 彩色玉米四类；不下载灰度/去背景副本和其它作物。

python -m ml.agrivision_ml.preprocessing.plantvillage_source
数据许可：CC BY-SA 3.0，来源与同叶分组信息一起保留。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha1
from pathlib import Path
from urllib.parse import quote
import time

import httpx
from tqdm import tqdm

from .source_collection import ROOT, get_json, save_json

SOURCE_ID = 'plantvillage-maize-color'
REPOSITORY = 'spMohanty/PlantVillage-Dataset'


def git_blob_hash(content: bytes) -> str:
    """Git 文件对象含头部；这与直接对文件做 SHA-1 不同。"""
    return sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()


def collect() -> None:
    target = ROOT / 'data/maize/sources' / SOURCE_ID
    target.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        api = f'https://api.github.com/repos/{REPOSITORY}'
        commit = get_json(client, f'{api}/commits/master')['sha']
        directories = get_json(client, f'{api}/contents/raw/color?ref={commit}')
        records = []
        for directory in directories:
            if not directory['name'].startswith('Corn_(maize)___'):
                continue
            tree = get_json(client, f"{api}/git/trees/{directory['sha']}")
            if tree.get('truncated'):
                raise ValueError('Git 文件目录不完整，不能声称完整下载。')
            for item in tree['tree']:
                if item['type'] == 'blob':
                    records.append({**item, 'class': directory['name']})
        hf = 'https://huggingface.co/datasets/mohanty/PlantVillage/resolve/main'
        for name in ['leaf_grouping/leaf-map.json', 'README.md', 'splits/color_train.txt', 'splits/color_test.txt']:
            response = client.get(f'{hf}/{name}')
            response.raise_for_status()
            path = target / 'metadata' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
        save_json(target / 'source.json', {'id': SOURCE_ID, 'repository': REPOSITORY, 'commit': commit,
                  'license': 'CC BY-SA 3.0', 'license_evidence': f'{hf}/README.md', 'files': records})
        def fetch(record: dict) -> None:
            destination = target / 'raw' / record['class'] / record['path']
            if destination.exists() and git_blob_hash(destination.read_bytes()) == record['sha']:
                return
            relative = f"raw/color/{record['class']}/{record['path']}"
            url = f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{quote(relative)}'
            for attempt in range(3):
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    if git_blob_hash(response.content) != record['sha']:
                        raise ValueError(f"Git文件校验失败：{record['path']}")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(response.content)
                    return
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
        failures = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            jobs = {executor.submit(fetch, record): record for record in records}
            for future in tqdm(as_completed(jobs), total=len(jobs), desc=SOURCE_ID, unit='image'):
                try:
                    future.result()
                except (httpx.HTTPError, ValueError, OSError) as error:
                    failures.append({'file': jobs[future]['path'], 'error': str(error)})
        save_json(target / 'download-status.json', {'expected_files': len(records), 'failed_files': failures,
                  'complete': not failures})
        if failures:
            raise RuntimeError(f'{len(failures)} 个文件未完成；重跑可跳过已经校验的文件。')


if __name__ == '__main__':
    collect()

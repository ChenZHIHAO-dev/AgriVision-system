"""下载固定 Zenodo 版本的原始文件；源站 MD5 验证后才解压。

python -m ml.agrivision_ml.preprocessing.zenodo_source --record 17053222 --crop peanut --source planthead-peanut-17053222

本模块只负责原文件和许可留档，不修改训练集、类别或数据划分。
"""
from __future__ import annotations

import argparse

import httpx
from tqdm import tqdm

from .source_collection import ROOT, save_json, md5_file, extract_zip


def collect(record: int, crop: str, source: str) -> None:
    """保留发布者元数据；每个原始 ZIP 只下载一份，不使用二次打包镜像。"""
    boundary = (ROOT / 'data' / crop / 'sources').resolve()
    target = (boundary / source).resolve()
    if not target.is_relative_to(boundary):
        raise ValueError('来源目录超出作物目录。')
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, connect=30)) as client:
        response = client.get(f'https://zenodo.org/api/records/{record}')
        response.raise_for_status()
        metadata = response.json()
        save_json(target / 'source.json', metadata)
        print(f"官方许可：{metadata['metadata'].get('license')}；固定记录：{record}", flush=True)
        for item in metadata['files']:
            name = item['key']
            destination = (target / ('archives' if name.lower().endswith('.zip') else 'metadata') / name).resolve()
            if not destination.is_relative_to(target):
                raise ValueError('来源文件名超出来源目录。')
            algorithm, expected = item['checksum'].split(':', 1)
            if algorithm != 'md5':
                raise ValueError(f'未实现的源站校验算法：{algorithm}')
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or md5_file(destination) != expected:
                temporary = destination.with_suffix(destination.suffix + '.part')
                with client.stream('GET', item['links']['self']) as download:
                    download.raise_for_status()
                    with temporary.open('wb') as stream, tqdm(total=item['size'], desc=name, unit='B', unit_scale=True, mininterval=5) as progress:
                        for block in download.iter_bytes(1024 * 1024):
                            stream.write(block)
                            progress.update(len(block))
                if temporary.stat().st_size != item['size'] or md5_file(temporary) != expected:
                    raise ValueError(f'源站 MD5 或大小不一致：{name}')
                temporary.replace(destination)
            if destination.suffix.lower() == '.zip':
                inventory = extract_zip(destination, target / 'raw')
                save_json(target / 'metadata' / f'{destination.stem}.inventory.json', inventory)
    save_json(target / 'download-status.json', {'complete': True, 'record': record,
              'verified': 'All files match official MD5 and archive members pass CRC.'})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=int, required=True)
    parser.add_argument('--crop', choices=['peanut', 'maize', 'wheat'], required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    collect(args.record, args.crop, args.source)


if __name__ == '__main__':
    main()

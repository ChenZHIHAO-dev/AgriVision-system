"""Figshare 原始大文件采集：有限并发、固定路径续传、官方 MD5 校验。

用法：python -m ml.agrivision_ml.preprocessing.figshare_source --article 20237613 --version 1 --crop maize --source pretoria-field-20237613-v1
不生成训练集或增强图。压缩包与解压原图各保留一份，便于追溯。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from tqdm import tqdm

from .source_collection import ROOT, save_json, md5_file, extract_zip


def download_resumable(client: httpx.Client, record: dict, target: Path, workers: int = 4) -> None:
    """分段写同一个 .part；只把完整收到的段记入续传表，重跑不重下已完成段。

    各线程只写自己负责的不重叠字节区间。完成段表由锁保护并原子替换。
    即使断电留下某段半截内容，该段仍不在完成表中，重跑时完整覆盖即可。
    最终大小与官方 MD5 都一致后才将 .part 改为正式文件。
    """
    size = int(record['size'])
    expected = record.get('computed_md5') or record['supplied_md5']
    if target.exists():
        if target.stat().st_size == size and md5_file(target) == expected:
            print(f'已校验，跳过：{target.name}', flush=True)
            return
        raise ValueError(f'已有正式文件与官方校验不符：{target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.part')
    checkpoint = target.with_suffix(target.suffix + '.resume.json')
    chunk_size = 20 * 1024 * 1024
    segments = (size + chunk_size - 1) // chunk_size
    identity = {'file_id': record['id'], 'size': size, 'md5': expected, 'chunk_size': chunk_size}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding='utf-8'))
        if any(state.get(key) != value for key, value in identity.items()):
            raise ValueError('续传表与当前源站文件不匹配，需人工核对来源版本。')
        complete = set(state['completed_segments'])
        if not partial.exists():
            raise ValueError('续传表存在，但 .part 文件缺失。')
    else:
        # 支持此前顺序下载得到的完整前缀；不足一个段的尾部会重新下载。
        prefix = partial.stat().st_size if partial.exists() else 0
        if prefix > size:
            raise ValueError('临时文件大于源文件，停止续传。')
        complete = set(range(prefix // chunk_size))
        with partial.open('ab') as stream:
            stream.truncate(size)
        state = {**identity, 'completed_segments': sorted(complete)}
        save_json(checkpoint, state)
    lock = threading.Lock()
    stop = threading.Event()
    failures = []
    done_bytes = sum(min(chunk_size, size - index * chunk_size) for index in complete)
    with tqdm(total=size, initial=done_bytes, unit='B', unit_scale=True, desc=target.name, mininterval=5) as progress:
        def fetch(index: int) -> None:
            if stop.is_set():
                return
            start = index * chunk_size
            end = min(size, start + chunk_size) - 1
            expected_range = f'bytes {start}-{end}/{size}'
            for attempt in range(4):
                try:
                    with client.stream('GET', record['download_url'], headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}) as response:
                        response.raise_for_status()
                        if response.status_code != 206 or response.headers.get('Content-Range') != expected_range:
                            raise ValueError(f'源站没有返回请求的续传区间：segment {index}')
                        written = 0
                        with partial.open('r+b') as output:
                            output.seek(start)
                            for block in response.iter_bytes(1024 * 1024):
                                if stop.is_set():
                                    raise InterruptedError('用户停止下载；当前未完成段留待重跑。')
                                if written + len(block) > end - start + 1:
                                    raise ValueError('源站返回的字节数超过分段大小。')
                                output.write(block)
                                written += len(block)
                            output.flush()
                        if written != end - start + 1:
                            raise ValueError('分段长度不完整，保留未完成状态。')
                    with lock:
                        complete.add(index)
                        state['completed_segments'] = sorted(complete)
                        temporary = checkpoint.with_suffix('.json.tmp')
                        save_json(temporary, state)
                        temporary.replace(checkpoint)
                        progress.update(written)
                    return
                except httpx.TransportError:
                    if attempt == 3:
                        raise
                    time.sleep(1 + attempt)
        pool = ThreadPoolExecutor(max_workers=workers)
        jobs = {pool.submit(fetch, index): index for index in range(segments) if index not in complete}
        try:
            for future in as_completed(jobs):
                try:
                    future.result()
                except (httpx.HTTPError, ValueError, OSError) as error:
                    failures.append({'segment': jobs[future], 'error': type(error).__name__})
        except KeyboardInterrupt:
            # Ctrl+C 后取消排队段；正在写的段停止后仍为未完成，可安全续传。
            stop.set()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        if failures:
            save_json(target.with_suffix(target.suffix + '.errors.json'), failures)
            raise RuntimeError(f'{len(failures)} 个分段未完成；重跑同一命令可继续。')
    print(f'下载完成，流式核对官方 MD5：{target.name}', flush=True)
    actual = md5_file(partial)
    if actual != expected:
        raise ValueError(f'MD5 不一致，保留临时文件与续传表，不能用于解压：{actual}')
    partial.replace(target)
    state.update({'complete': True, 'verified_md5': actual})
    save_json(checkpoint, state)


def collect(article: int, version: int, crop: str, source: str, workers: int) -> None:
    """固定 Figshare 版本；先保存官方许可和文件目录，再下载原包与元数据。"""
    source_directory = (ROOT / 'data' / crop / 'sources').resolve()
    target = source_directory / source
    if not target.resolve().is_relative_to(source_directory):
        raise ValueError('来源名称超出作物数据目录。')
    target.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(120, connect=30), follow_redirects=True) as client:
        response = client.get(f'https://api.figshare.com/v2/articles/{article}/versions/{version}')
        response.raise_for_status()
        metadata = response.json()
        save_json(target / 'source.json', metadata)
        print(f"官方许可：{metadata['license']['name']}；固定版本：{metadata['version']}", flush=True)
        for record in metadata['files']:
            name = record['name']
            location = target / ('archives' if name.lower().endswith('.zip') else 'metadata') / name
            if not location.resolve().is_relative_to(target.resolve()):
                raise ValueError('来源文件名超出来源目录。')
            if int(record['size']) < 1024 * 1024:
                if location.exists() and md5_file(location) == record['computed_md5']:
                    continue
                file_response = client.get(record['download_url'])
                file_response.raise_for_status()
                if hashlib.md5(file_response.content).hexdigest() != record['computed_md5']:
                    raise ValueError(f'元数据文件校验失败：{name}')
                location.parent.mkdir(parents=True, exist_ok=True)
                location.write_bytes(file_response.content)
            else:
                download_resumable(client, record, location, workers)
            if location.suffix.lower() == '.zip':
                inventory = extract_zip(location, target / 'raw')
                save_json(target / 'metadata/zip-inventory.json', inventory)
    save_json(target / 'download-status.json', {'complete': True, 'provider': 'figshare', 'article': article, 'version': version,
              'verified': 'All original files match official MD5; ZIP members pass CRC when extracted.'})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--article', type=int, required=True)
    parser.add_argument('--version', type=int, default=1)
    parser.add_argument('--crop', choices=['maize', 'peanut', 'wheat'], required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    collect(args.article, args.version, args.crop, args.source, args.workers)


if __name__ == '__main__':
    main()

"""Download the CC BY 4.0 JIC public subset, checking each published checksum."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    metadata = json.loads((root / 'data/wheat/sources/metadata/zenodo-7307816.json').read_text(encoding='utf-8-sig'))
    if metadata['metadata']['license']['id'] != 'cc-by-4.0':
        raise ValueError('Unexpected source license')
    output = root / 'data/wheat/sources/jic-7307816'
    output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=90, limits=httpx.Limits(max_connections=4)) as client:
        def download(item):
            name = item['key']
            if Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('Unexpected source filename')
            path = output / name
            checksum = item['checksum'].split(':', 1)[1]
            if path.is_file() and hashlib.md5(path.read_bytes()).hexdigest() == checksum:
                return name
            for attempt in range(5):
                try:
                    part = path.with_suffix(path.suffix + '.part')
                    digest = hashlib.md5()
                    with client.stream('GET', f'https://zenodo.org/records/7307816/files/{name}?download=1') as response:
                        response.raise_for_status()
                        with part.open('wb') as stream:
                            for chunk in response.iter_bytes(131072):
                                stream.write(chunk); digest.update(chunk)
                    if digest.hexdigest() != checksum:
                        raise ValueError('Source checksum mismatch')
                    part.replace(path)
                    return name
                except (httpx.HTTPError, ValueError, OSError):
                    if attempt == 4: raise
                    time.sleep(min(15, 2 ** attempt))
        completed, failures = 0, []
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(download, item): item['key'] for item in metadata['files']}
            for future in as_completed(jobs):
                try: future.result()
                except Exception as exc: failures.append({'file': jobs[future], 'error_type': type(exc).__name__})
                completed += 1
                if completed % 25 == 0 or completed == len(jobs):
                    print(json.dumps({'source':'JIC-7307816','checked':completed,'total':len(jobs),'failures':len(failures)}), flush=True)
        report = {'source':'https://zenodo.org/records/7307816','license':'CC-BY-4.0','files':completed - len(failures),'failures':failures}
        (output.parent / 'jic-download-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if failures: raise SystemExit('Some source files could not be verified; rerun to resume')


if __name__ == '__main__':
    main()

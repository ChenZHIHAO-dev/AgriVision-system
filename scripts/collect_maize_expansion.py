"""下载 ScienceDB 玉米扩类候选；只做来源审计，不修改 prepared 或模型。

默认取得官方索引；--sample 8 按新类抽样下载，--download-new 下载六个新类原图。
本来源 CC BY-NC-ND 4.0 且混合多个原库，所有条目先 hold，不能自动并入部署训练。
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import time

import httpx
from tqdm import tqdm
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.agrivision_ml.preprocessing.source_collection import (
    ROOT, audit_image, contact_sheet, save_json, write_csv,
)

DATASET = "19536c73f6d74946a212719a94f53ab3"
SOURCE = "sciencedb-agriculture-00226"
VERSION = "V2"
LICENSE = "CC-BY-NC-ND-4.0"
TARGET = ROOT / "data/maize/sources" / SOURCE
NEW_LABELS = {
    "小斑病": "maize_southern_blight", "南方锈病": "maize_southern_rust",
    "矮花叶病": "maize_dwarf_mosaic", "褐斑病": "maize_physoderma_brown_spot",
    "弯孢霉叶斑病": "maize_curvularia_leaf_spot", "圆斑病": "maize_eyespot",
}


def index_source():
    """只访问数据页公开文件树；标签来自作者 desc.json，不按文件名前缀猜病名。"""
    TARGET.mkdir(parents=True, exist_ok=True)
    target = TARGET / "files.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        rows = []
        for offset in range(0, 10000, 100):
            response = client.post("https://www.scidb.cn/api/gin-sdb-filetree/public/file/childrenFileListByPath",
                json={"dataSetId": DATASET, "version": VERSION, "path": "/V2/data",
                      "lastIndex": offset, "pageSize": 100})
            response.raise_for_status()
            result = response.json()
            if result["code"] != 20000:
                raise ValueError("公开文件索引未返回成功，停止而不猜下载路径")
            batch = result["data"]
            rows.extend(batch)
            if len(batch) < 100:
                break
        if len({item["id"] for item in rows}) != len(rows):
            raise ValueError("分页重复，不能把重复文件计入数据量")
        if len(rows) != rows[0]["parentFileCount"]:
            raise ValueError("公开文件索引不完整")
        description = TARGET / "desc.json"
        if not description.exists():
            response = client.get("https://china.scidb.cn/download", params={"fileId": "8566e7f602870e13993bbf60964d4cba"})
            response.raise_for_status()
            if hashlib.md5(response.content).hexdigest() != "d7bac651c03bba23a180cec4f2d394b2":
                raise ValueError("作者标签说明摘要不符")
            description.write_bytes(response.content)
        annotations = {row["image_name"].lower(): row for row in json.loads(description.read_text(encoding="utf-8-sig"))}
        for row in rows:
            row["author_label"] = annotations.get(row["fileName"].lower(), {}).get("label", "")
            row["canonical_candidate"] = NEW_LABELS.get(row["author_label"], "")
        save_json(target, rows)
        return rows


def download_one(row):
    """原字节落盘，核验源站 MD5；MD5 用于传输一致性，非密码安全。"""
    path = TARGET / "raw" / row["author_label"] / row["fileName"]
    if not path.resolve().is_relative_to((TARGET / "raw").resolve()):
        raise ValueError("发布文件名越界")
    if path.exists() and hashlib.md5(path.read_bytes()).hexdigest() == row["md5"]:
        return
    # 只重试临时网络/服务端失败；授权失败不绕过。已完成原图由 MD5 直接复用。
    for attempt in range(3):
        try:
            with httpx.Client(follow_redirects=True, timeout=120) as client:
                response = client.get("https://china.scidb.cn/download", params={"fileId": row["id"]})
                response.raise_for_status()
            break
        except (httpx.NetworkError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {429, 500, 502, 503, 504}:
                raise
            if attempt == 2:
                raise
            # 源站限流时降低并发重跑，并遵守 Retry-After；不换地址绕过限制。
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After", "60")
                if retry_after.isdigit():
                    delay = max(60, int(retry_after))
                else:
                    from email.utils import parsedate_to_datetime
                    delay = max(60, parsedate_to_datetime(retry_after).timestamp() - time.time())
                time.sleep(delay)
            else:
                time.sleep(2 * (attempt + 1))
    if len(response.content) != row["size"] or hashlib.md5(response.content).hexdigest() != row["md5"]:
        raise ValueError(f"长度/MD5不符：{row['fileName']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)


def audit_downloaded(rows):
    """每张已下载图验真，待确认许可范围/水印/原库重叠；不自动设 keep。"""
    report = []
    quality_path = TARGET / "quality-review.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    classes = defaultdict(list)
    for row in rows:
        path = TARGET / "raw" / row["author_label"] / row["fileName"]
        if not path.exists():
            continue
        result = audit_image(path)
        report.append({"decision": "", "status": "hold_source_review", "path": path.relative_to(ROOT).as_posix(),
            "source": SOURCE, "source_label": row["author_label"], "label": row["canonical_candidate"],
            "license": LICENSE, "region": "mixed/unknown per-image; domestic publisher is not capture location",
            "part": "leaf", "group": "unknown", "source_url": "https://doi.org/10.57760/sciencedb.agriculture.00226",
            "quality_note": quality.get("class_findings", {}).get(row["author_label"], "待复核"),
            "official_md5": row["md5"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **result})
        classes[row["author_label"]].append(path)
    if report:
        write_csv(ROOT / "data/maize/review/class-expansion-sciencedb.csv", report)
    samples = {}
    for label, paths in classes.items():
        samples[label] = contact_sheet(sorted(paths), TARGET / "samples" / (label + ".jpg"), label)
    save_json(TARGET / "audit.json", {"source": SOURCE, "version": VERSION, "license": LICENSE,
        "published_images": len(rows), "published_class_counts": dict(Counter(x["author_label"] for x in rows)),
        "downloaded_images": len(report), "downloaded_class_counts": dict(Counter(x["source_label"] for x in report)),
        "decode_failures": sum(bool(x["error"]) for x in report), "sampled_paths": samples,
        "visual_review": quality or "pending; contact sheets not yet interpreted", "prepared_changed": False,
        "restriction": "混合来源且含NC/ND限制；本轮只作私有数据审计，未加入当前训练或上线模型"})
    print("已下载/审计", len(report), "张", dict(Counter(x["source_label"] for x in report)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=0, help="每个新类按排序均匀抽取的原图数")
    parser.add_argument("--download-new", action="store_true", help="下载六个新类的全部作者原图，仍为hold")
    parser.add_argument("--label", action="append", choices=sorted(NEW_LABELS), help="只下载指定作者类别，可重复；默认选择六个新类")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=6, help="公开下载并发1到8；单图按源MD5复用")
    args = parser.parse_args()
    rows = index_source()
    by_class = defaultdict(list)
    for row in rows:
        if row["canonical_candidate"] and (not args.label or row["author_label"] in args.label):
            by_class[row["author_label"]].append(row)
    selected = []
    for label, items in by_class.items():
        if args.download_new:
            selected.extend(items)
        elif args.sample > 0:
            count = min(args.sample, len(items))
            selected.extend(items[round(i * (len(items) - 1) / max(count - 1, 1))] for i in range(count))
    print("官方索引", len(rows), "张；本次选择", len(selected), "张，原图未进入训练。", flush=True)
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, row): row for row in selected}
        for future in tqdm(as_completed(futures), total=len(futures), desc="下载校验原图", unit="image"):
            try:
                future.result()
            except Exception as exc:
                row = futures[future]
                errors.append({"file": row["fileName"], "id": row["id"], "error": str(exc)})
    save_json(TARGET / "download-errors.json", errors)
    audit_downloaded(rows)
    if errors:
        print("未完成", len(errors), "张；重跑相同命令只补失败文件。", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

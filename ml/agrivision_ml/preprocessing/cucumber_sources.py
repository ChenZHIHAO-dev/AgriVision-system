"""黄瓜来源适配：原包断点下载、来源审计与固定工作集准备。

数据只落在 data/cucumber；下载器不下载作者增强包，不将待核实病名自动改标。
图像解码、重复分组、工作图和划分复用既有 preprocessing 模块。
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import re

from .crop_review import REVIEW_FIELDS, merge_audit_row, select_with_basis
from .tables import read_rows, write_rows
from .wheat_review import build_dataset, print_report, print_selection

import httpx

from .source_collection import ROOT, audit_crop, extract_zip, get_json, mendeley_inventory, save_json, sha256


def download_ranges(url, destination, expected_sha256=None, block_size=4 * 1024 * 1024):
    """按 HTTP Range 续传同一个 .part；只有长度/官方摘要通过才成为原包。

    大文件直连在当前网络可能长期停住。每段完整收到并检查 Content-Range
    后才追加，所以断线不会把残缺段当成已完成，也不会另建编号下载副本。
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        probe = client.get(url, headers={"Range": "bytes=0-1023"})
        probe.raise_for_status()
        if probe.status_code != 206 or not probe.headers.get("content-range", "").startswith("bytes 0-"):
            raise ValueError("源站未返回可验证的分段下载响应")
        total = int(probe.headers["content-range"].rsplit("/", 1)[1])
        # 解析一次官方重定向，后续仍访问其公开对象；不保存临时签名 URL。
        target = str(probe.url)
        if destination.exists() and destination.stat().st_size == total:
            if not expected_sha256 or sha256(destination) == expected_sha256:
                return
            raise ValueError(f"已有原包摘要不符：{destination}")
        part = destination.with_suffix(destination.suffix + ".part")
        offset = part.stat().st_size if part.exists() else 0
        if offset > total:
            raise ValueError(f"未完成文件超过源站长度：{part}")
        print(f"续传 {destination.name}: {offset:,}/{total:,} bytes", flush=True)
        last_report = time.monotonic()
        with part.open("ab") as out:
            while offset < total:
                end = min(total - 1, offset + block_size - 1)
                for attempt in range(4):
                    try:
                        response = client.get(target, headers={"Range": f"bytes={offset}-{end}"})
                        response.raise_for_status()
                        required = f"bytes {offset}-{end}/{total}"
                        if response.status_code != 206 or response.headers.get("content-range") != required:
                            raise ValueError("分段边界不符，停止追加以免写坏原包")
                        if len(response.content) != end - offset + 1:
                            raise ValueError("分段长度不完整")
                        break
                    except (httpx.TransportError, httpx.HTTPStatusError):
                        if attempt == 3:
                            raise
                        time.sleep(attempt + 1)
                out.write(response.content)
                out.flush()
                offset = end + 1
                if time.monotonic() - last_report > 30 or offset == total:
                    print(f"{destination.name}: {offset / total:.1%} ({offset:,}/{total:,})", flush=True)
                    last_report = time.monotonic()
        actual_sha256 = sha256(part)
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise ValueError(f"原包 SHA-256 校验失败：{part}")
        part.replace(destination)
        save_json(destination.with_suffix(destination.suffix + ".download.json"), {
            "source_url": url, "bytes": total, "sha256": actual_sha256,
            "official_sha256": expected_sha256, "complete": True,
        })
        print(f"原包完成并校验：{destination.name}", flush=True)


def download_originals():
    """只选择作者明确命名的原图包；Kaggle 数据先作为待审核原始发布包。"""
    jobs = []
    for dataset_id, filename in [("y6d3z6f8z9", "Original Image.zip")]:
        root = ROOT / f"data/cucumber/sources/mendeley-{dataset_id}-v1"
        inventory_path = root / "inventory.json"
        if not inventory_path.exists():
            with httpx.Client(follow_redirects=True, timeout=90) as client:
                metadata, records, folders = mendeley_inventory(client, {"dataset_id": dataset_id, "version": 1})
            save_json(inventory_path, {"metadata": metadata, "files": records,
                                      "folders": {key: str(value) for key, value in folders.items()}})
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        record = next(item for item in inventory["files"] if item["filename"] == filename)
        info = record["content_details"]
        jobs.append((info["download_url"], root / "archives" / filename, info["sha256_hash"]))
    root = ROOT / "data/cucumber/sources/kaggle-kaushigihanml"
    if not (root / "metadata.json").exists():
        with httpx.Client(follow_redirects=True, timeout=90) as client:
            save_json(root / "metadata.json", get_json(client,
                "https://www.kaggle.com/api/v1/datasets/view/kaushigihanml/cucumber-leaf-disease-dataset"))
    jobs.append(("https://www.kaggle.com/api/v1/datasets/download/kaushigihanml/cucumber-leaf-disease-dataset?datasetVersionNumber=1",
                 root / "archives/cucumber-leaf-disease-dataset.zip", None))
    def fetch(job):
        url, path, checksum = job
        download_ranges(url, path, checksum)
        if path.suffix.lower() == ".zip":
            members = extract_zip(path, path.parent.parent / "raw")
            save_json(path.parent.parent / "archive-members.json", members)
    # 两个独立原包并行，单包只由一个写入者续传。
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(fetch, jobs))


def load_catalogs(root=ROOT):
    """黄瓜疾病、来源与部位映射独立配置；不改动其他作物的配置入口。"""
    sources = json.loads((root / "configs/datasets/cucumber.json").read_text(encoding="utf-8"))["sources"]
    catalog = json.loads((root / "configs/labels/cucumber.json").read_text(encoding="utf-8"))
    if catalog["crop"] != "cucumber" or any(item["crop"] != "cucumber" for item in sources):
        raise ValueError("黄瓜入口不能处理其他作物来源")
    return {item["id"]: item for item in sources}, catalog["labels"]


def filename_group(row):
    """保守把 iOS IMG_1234 与 IMG_E1234 放同组；这只是编辑副本关系，不是植株 ID。

    同一数字编号跨原作者 train/test 也合并，避免作者随机划分留下同帧不同编辑版本。
    其他文件没有可确认的采集关系，留空给通用近重复分组，不伪造采集身份。
    """
    if row["source"] != "kaggle-kaushigihanml":
        return ""
    match = re.fullmatch(r"IMG_E?(\d+)", Path(row["path"]).stem, re.IGNORECASE)
    return f"{row['source']}:frame-number:{match[1]}" if match else ""


def prepare_review(*, accept_source_labels=False, output=None, root=ROOT):
    """只适配来源表；审核保留规则、图像预处理、去重和分组划分均调用共享实现。"""
    sources, labels = load_catalogs(root)
    review = root / "data/cucumber/review/disease-review.csv"
    old_rows = read_rows(review, ("decision", "label", "path", "source")) if review.exists() else []
    previous = {(row["source"], row["path"]): row for row in old_rows}
    audit = read_rows(review.parent / "source-audit.csv", ("path", "source", "source_label", "group"))
    rows = []
    for row in audit:
        group = filename_group(row)
        if group:
            row = {**row, "group": group, "group_status": "conservative_filename_frame_group_not_plant_id"}
        rows.append(merge_audit_row(row, sources[row["source"]], labels, review, root, previous, accept_source_labels))
    # 消失的旧路径留记录但撤销 keep，避免重跑时误引用已撤回来源。
    current = {(row["source"], row["path"]) for row in rows}
    rows.extend({**old, "decision": "drop", "review_basis": "excluded_by_source_audit",
                 "exclusion_reason": "当前来源审计已无此图片"}
                for key, old in previous.items() if key not in current)
    write_rows(review, REVIEW_FIELDS, rows)
    selection = select_with_basis(review, labels, rows)
    print_selection(selection, labels, review)
    if output:
        report = build_dataset(selection, labels, Path(output), crop="cucumber")
        print_report(report, labels, Path(output))
    return selection


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="断点下载两份指定发布包，不下载增强包")
    parser.add_argument("--audit", action="store_true", help="完整解码与来源统计，并生成分病类抽样图")
    parser.add_argument("--check", action="store_true", help="更新筛选表与数量，不生成工作集")
    parser.add_argument("--accept-source-labels", action="store_true", help="内部实验接受作者标签，不代表逐图人工审核")
    parser.add_argument("--output", type=Path, help="固定路径 data/cucumber/prepared；已有目录不覆盖")
    args = parser.parse_args(argv)
    if not any((args.download, args.audit, args.check, args.output)):
        parser.error("请选择 --download、--audit、--check 或 --output")
    if args.download:
        download_originals()
    if args.audit:
        sources, _ = load_catalogs()
        audit_crop("cucumber", list(sources.values()))
    if args.check or args.output:
        prepare_review(accept_source_labels=args.accept_source_labels,
                       output=None if args.check else args.output)


if __name__ == "__main__":
    main()

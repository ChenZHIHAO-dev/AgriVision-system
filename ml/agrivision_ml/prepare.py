# 为已经按类存放的照片生成训练清单。它也被国内数据导入脚本调用，共用分组与划分规则。
"""Create grouped, deterministic manifests for existing image folders."""

import argparse
import json
from pathlib import Path

from .preprocessing.manifest import MANIFEST_FIELDS, build_manifest
from .preprocessing.tables import read_rows, write_rows


def prepare(data_root: Path, labels_path: Path, output: Path, seed=42, groups_path=None):
    config = json.loads(labels_path.read_text(encoding="utf-8"))
    # groups.csv 可以显式声明同一株、同一地块或同一拍摄批次的照片。路径统一用斜杠与扫描结果匹配。
    groups = {}
    if groups_path:
        groups = {
            row["path"].replace("\\", "/"): row["group"]
            for row in read_rows(Path(groups_path), ("path", "group"))
        }
    # 实际查重、处理类别冲突和划分数据由 build_manifest() 完成。seed 控制分组打乱的顺序。
    rows, report = build_manifest(data_root, config["labels"], seed, groups)

    # 写出训练程序读取的 CSV，并在同目录生成可人工核对的统计报告。
    output.parent.mkdir(parents=True, exist_ok=True)
    write_rows(output, MANIFEST_FIELDS, rows)
    output.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--groups", type=Path, help="CSV path,group for leaf/plot/batch/derived-image grouping")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(prepare(args.data_root, args.labels, args.output, args.seed, args.groups), ensure_ascii=False, indent=2))

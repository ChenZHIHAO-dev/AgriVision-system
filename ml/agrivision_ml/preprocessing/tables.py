"""CSV I/O shared by manifests and review tables."""

import csv


# utf-8-sig 同时兼容普通 UTF-8 和 Excel 保存的 BOM。先检查列名，再把每行读成字典。
def read_rows(path, required=()):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = set(required).difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name} 缺少列: {', '.join(sorted(missing))}")
        return list(reader)


# 统一 CSV 的列顺序。只输出调用者指定的列，多余字段可以保留在其他报告里。
def write_rows(path, fields, rows):
    # newline="" 让 csv 模块处理换行，避免在 Windows 上写出多余的空行。
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

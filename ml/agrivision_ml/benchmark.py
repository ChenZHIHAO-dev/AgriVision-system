"""测量常驻模型的单图推理耗时；与 HTTP 上传、数据库和聊天耗时分开记录。"""
import argparse
import csv
import json
from pathlib import Path
import platform
from time import perf_counter

import numpy as np
import torch

from .inference import Predictor


def benchmark(bundle, data_root, manifest, *, device="cpu", threads=4, repeats=80, warmup=8):
    """固定选图并重复测量，包含读图、预处理和网络前向，不包含首次加载权重。"""
    torch.set_num_threads(threads)
    started = perf_counter()
    predictor = Predictor(bundle, device)
    load_seconds = perf_counter() - started
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["split"] == "test"]
    # 每类取前两张，覆盖不同的原图比例。这里测性能，不用于估计识别准确率。
    selected = []
    for label in predictor.labels:
        selected.extend([row for row in rows if row["label"] == label][:2])
    if not selected:
        raise ValueError("清单中没有可测的测试照片")

    def predict(row):
        result = predictor.predict(data_root / row["path"])
        # CUDA 算子异步提交；计时结束前同步，避免只测到任务提交时间。
        if predictor.device.type == "cuda":
            torch.cuda.synchronize(predictor.device)
        return result

    for index in range(warmup):
        predict(selected[index % len(selected)])
    durations = []
    for index in range(repeats):
        started = perf_counter()
        predict(selected[index % len(selected)])
        durations.append((perf_counter() - started) * 1000)
    # 一次连续请求测量只能说明串行时延；不能由此推算并发容量。
    return {
        "architecture": predictor.metadata["architecture"],
        "input_size": predictor.metadata["input_size"],
        "model_version": predictor.metadata["version"],
        "parameters": sum(parameter.numel() for parameter in predictor.model.parameters()),
        "device": str(predictor.device), "threads": threads,
        "platform": platform.platform(), "processor": platform.processor(),
        "torch": torch.__version__, "load_seconds": load_seconds,
        "images": len(selected), "warmup": warmup, "repeats": repeats,
        "latency_ms": {
            "median": float(np.median(durations)),
            "p95": float(np.percentile(durations, 95)),
            "minimum": min(durations), "maximum": max(durations),
        },
        "samples_ms": durations,
        "scope": "warm serial single-image: decode + preprocessing + network; excludes HTTP and model loading",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=80)
    parser.add_argument("--warmup", type=int, default=8)
    args = parser.parse_args()
    if args.repeats < 1 or args.warmup < 0 or args.threads < 1:
        parser.error("repeats 和 threads 必须大于 0，warmup 不能小于 0")
    result = benchmark(**vars(args))
    output = args.bundle / f"benchmark-{args.device}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "samples_ms"}, ensure_ascii=False, indent=2))

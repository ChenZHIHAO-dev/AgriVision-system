"""Create grouped, deterministic manifests before applying augmentation."""
import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def prepare(data_root: Path, labels_path: Path, output: Path, seed=42, groups_path=None):
    config = json.loads(labels_path.read_text(encoding="utf-8"))
    labels = config["labels"]
    supplied = {}
    if groups_path:
        with open(groups_path, encoding="utf-8-sig", newline="") as stream:
            supplied = {r["path"].replace("\\", "/"): r["group"] for r in csv.DictReader(stream)}
    rows, invalid = [], []
    buckets = defaultdict(list)
    parents = []

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def union(a, b):
        parents[find(a)] = find(b)

    exact, named = {}, {}
    for label in labels:
        folder = data_root / label
        for path in sorted(folder.rglob("*")) if folder.exists() else []:
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            relative = path.relative_to(data_root).as_posix()
            try:
                content = path.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                with Image.open(path) as image:
                    if min(image.size) < 64:
                        raise ValueError("image is too small")
                    gray = np.asarray(ImageOps.exif_transpose(image).convert("L").resize((9, 8)))
                    bits = gray[:, 1:] > gray[:, :-1]
                    perceptual = int("".join("1" if x else "0" for x in bits.flat), 2)
            except (OSError, ValueError) as exc:
                invalid.append({"path": relative, "reason": str(exc)})
                continue
            index = len(rows)
            parents.append(index)
            rows.append({"path": relative, "label": label, "sha256": digest, "dhash": perceptual})
            if digest in exact:
                union(index, exact[digest])
            exact[digest] = index
            if relative in supplied:
                group = supplied[relative]
                if group in named:
                    union(index, named[group])
                named[group] = index
            candidates = set()
            for band in range(4):
                key = (band, (perceptual >> (16 * band)) & 65535)
                candidates.update(buckets[key])
                buckets[key].append(index)
            for other in candidates:
                if (rows[other]["dhash"] ^ perceptual).bit_count() <= 6:
                    union(index, other)
    clusters = defaultdict(list)
    for i, row in enumerate(rows):
        clusters[find(i)].append(row)
    clean = defaultdict(list)
    conflicts = []
    for cluster in clusters.values():
        if len({row["label"] for row in cluster}) > 1:
            conflicts.append([row["path"] for row in cluster])
        else:
            clean[cluster[0]["label"]].append(cluster)
    result = []
    for label in labels:
        groups = clean[label]
        if len(groups) < 3:
            raise ValueError(f"{label}: at least three independent groups are required; got {len(groups)}")
        random.Random(seed).shuffle(groups)
        n_val = max(1, round(len(groups) * .15))
        n_test = max(1, round(len(groups) * .15))
        for i, cluster in enumerate(groups):
            split = "val" if i < n_val else ("test" if i < n_val + n_test else "train")
            group_id = hashlib.sha256("|".join(sorted(r["sha256"] for r in cluster)).encode()).hexdigest()[:20]
            seen = set()
            for row in cluster:
                if row["sha256"] in seen:
                    continue
                seen.add(row["sha256"])
                result.append({"path": row["path"], "label": label, "group": group_id, "sha256": row["sha256"], "split": split})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "label", "group", "sha256", "split"])
        writer.writeheader()
        writer.writerows(result)
    report = {"input_files": len(rows), "manifest_images": len(result), "invalid": invalid, "conflicting_groups": conflicts, "groups": len(clusters), "seed": seed, "counts": {label: {split: sum(r["label"] == label and r["split"] == split for r in result) for split in ("train", "val", "test")} for label in labels}}
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

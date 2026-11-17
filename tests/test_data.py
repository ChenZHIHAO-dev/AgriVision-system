import csv
import json
from pathlib import Path
import numpy as np
from PIL import Image
from ml.agrivision_ml.prepare import prepare


def test_duplicate_images_stay_in_one_split_and_manifest_is_reproducible(tmp_path):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"crop":"wheat","labels":{"a":"A","b":"B"}}))
    root = tmp_path / "raw"
    for category in ("a","b"):
        folder = root / category
        folder.mkdir(parents=True)
        for i in range(12):
            image = Image.fromarray(np.random.default_rng(i + (100 if category == "b" else 0)).integers(0, 255, (180, 180, 3), dtype=np.uint8))
            image.save(folder / f"{i}.png")
        (folder / "duplicate.png").write_bytes((folder / "0.png").read_bytes())
    first = tmp_path / "one.csv"
    second = tmp_path / "two.csv"
    report = prepare(root, labels, first)
    prepare(root, labels, second)
    assert first.read_bytes() == second.read_bytes()
    assert report["input_files"] == 26 and report["manifest_images"] == 24
    with first.open() as stream:
        rows = list(csv.DictReader(stream))
    groups = {}
    for row in rows:
        assert groups.setdefault(row["group"], row["split"]) == row["split"]
    assert {r["split"] for r in rows} == {"train", "val", "test"}


def test_conflicting_labels_are_quarantined(tmp_path):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"crop":"wheat","labels":{"a":"A","b":"B"}}))
    for category in ("a", "b"):
        folder = tmp_path / "raw" / category
        folder.mkdir(parents=True)
        for i in range(8):
            Image.fromarray(np.random.default_rng(i+(30 if category == "b" else 0)).integers(0,255,(100,100,3),dtype=np.uint8)).save(folder / f'{i}.png')
    (tmp_path / 'raw/b/cross.png').write_bytes((tmp_path / 'raw/a/0.png').read_bytes())
    report = prepare(tmp_path / "raw", labels, tmp_path / "manifest.csv")
    assert report["conflicting_groups"] and report["manifest_images"] == 15

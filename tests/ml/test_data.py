import csv
import json
from pathlib import Path
import numpy as np
import pytest
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


def test_field_groups_keep_multiple_labels_and_filter_only_duplicate_conflicts(tmp_path):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"crop": "wheat", "labels": {"a": "A", "b": "B"}}))
    root = tmp_path / "raw"
    source_groups = {}
    for label_index, category in enumerate(("a", "b")):
        (root / category).mkdir(parents=True)
        for index in range(6):
            path = f"{category}/plot-{index}.png"
            pixels = np.random.default_rng(index + 20 * label_index).integers(
                0, 255, (100, 100, 3), dtype=np.uint8
            )
            Image.fromarray(pixels).save(root / path)
            source_groups[path] = f"plot-{index}"

    # This duplicate connects two fields even though only one file is retained.
    alias = "a/shared-photo.png"
    (root / alias).write_bytes((root / "a/plot-0.png").read_bytes())
    source_groups[alias] = "plot-1"

    # Different encodings of the same photo exercise the perceptual hash path.
    conflict_a, conflict_b = "a/conflict.png", "b/conflict.png"
    pixels = np.random.default_rng(50).integers(0, 255, (100, 100, 3), dtype=np.uint8)
    Image.fromarray(pixels).save(root / conflict_a)
    Image.fromarray(pixels).save(root / conflict_b, compress_level=0)
    assert (root / conflict_a).read_bytes() != (root / conflict_b).read_bytes()
    source_groups.update({conflict_a: "plot-1", conflict_b: "plot-2"})

    groups = tmp_path / "groups.csv"
    with groups.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "group"])
        writer.writerows(source_groups.items())
    output = tmp_path / "manifest.csv"
    report = prepare(root, labels, output, groups_path=groups)
    with output.open(newline="") as stream:
        rows = {row["path"]: row for row in csv.DictReader(stream)}
    repeat = tmp_path / "repeat.csv"
    prepare(root, labels, repeat, groups_path=groups)

    assert repeat.read_bytes() == output.read_bytes()
    assert report["manifest_images"] == 12 and report["groups"] == 5
    assert report["conflicting_groups"] == [[conflict_a, conflict_b]]
    assert set(rows) == {path for path in source_groups if "plot-" in path}
    for index in range(6):
        first, second = rows[f"a/plot-{index}.png"], rows[f"b/plot-{index}.png"]
        assert (first["group"], first["split"]) == (second["group"], second["split"])
    assert rows["a/plot-0.png"]["group"] == rows["a/plot-1.png"]["group"]
    assert rows["a/plot-1.png"]["group"] != rows["a/plot-2.png"]["group"]
    for category in ("a", "b"):
        assert {row["split"] for row in rows.values() if row["label"] == category} == {
            "train", "val", "test"
        }

    # Distinct files from only two fields cannot cover all three splits.
    with groups.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "group"])
        writer.writerows(
            (f"{category}/plot-{index}.png", f"field-{index % 2}")
            for category in ("a", "b") for index in range(6)
        )
    impossible = tmp_path / "impossible.csv"
    with pytest.raises(ValueError, match="three independent groups are required; got 2"):
        prepare(root, labels, impossible, groups_path=groups)
    assert not impossible.exists()

"""Regression checks for the review-table preparation workflow."""

import csv
import hashlib
import json

import numpy as np
import pytest
from PIL import Image

from ml.agrivision_ml.preprocessing.tables import read_rows, write_rows
from ml.agrivision_ml.preprocessing.wheat_review import main


@pytest.fixture
def review_inputs(tmp_path):
    review = tmp_path / "wheat-review"
    photos = review / "photos"
    photos.mkdir(parents=True)
    baseline = tmp_path / "reference"
    (baseline / "images").mkdir(parents=True)
    rows, baseline_manifest = [], []

    def add(path, label, seed, *, domestic=False, dimensions=(140, 96), orientation=1):
        width, height = dimensions
        pixels = np.random.default_rng(seed).integers(0, 255, (height, width, 3), dtype=np.uint8)
        image = Image.fromarray(pixels)
        exif = image.getexif()
        exif[274] = orientation
        image.save(path, exif=exif)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source = "domestic" if domestic else "kaggle-wheat-v6"
        relative = f"../reference/images/{path.name}" if domestic else f"photos/{path.name}"
        rows.append({"decision": "keep", "label": label, "path": relative, "source": source, "sha256": digest})
        if domestic:
            baseline_manifest.append({"path": path.name, "group": "shared-field", "sha256": digest})
        return rows[-1]

    for offset, label in enumerate(("a", "b")):
        add(baseline / "images" / f"{label}.jpg", label, offset + 1, domestic=True)
        for index in range(3):
            dimensions, orientation = ((1300, 650), 6) if label == "a" and index == 0 else ((140, 96), 1)
            add(photos / f"{label}{index}.jpg", label, offset * 20 + index + 3,
                dimensions=dimensions, orientation=orientation)

    publisher = tmp_path / "sources" / "publisher"
    publisher.mkdir(parents=True)
    (photos / "b2.jpg").rename(publisher / "leaf.jpg")
    publisher_photo = next(row for row in rows if row["path"] == "photos/b2.jpg")
    publisher_photo.update(path="../sources/publisher/leaf.jpg", source="publisher", part="叶片")

    duplicate_input = photos / "duplicate.jpg"
    duplicate_input.write_bytes((photos / "a0.jpg").read_bytes())
    rows.append({**rows[1], "path": "photos/duplicate.jpg"})
    add(photos / "rare.png", "rare", 51)
    bad_digest = add(photos / "changed.jpg", "a", 54)
    bad_digest["sha256"] = "0" * 64
    rows.extend([
        {"decision": "", "label": "pending", "path": "photos/pending.jpg"},
        {"decision": "drop", "label": "b", "path": "photos/dropped.jpg"},
        {"decision": "keep", "label": "", "path": "photos/unlabeled.jpg"},
    ])

    write_rows(baseline / "manifest.csv", ("path", "group", "sha256"), baseline_manifest)
    review_csv = review / "review.csv"
    write_rows(review_csv, ("decision", "label", "path", "source", "sha256", "part"), rows)
    config = tmp_path / "labels.json"
    names = {"a": "A", "b": "B", "rare": "Rare", "pending": "Pending", "unused": "Unused"}
    config.write_text(json.dumps({"crop": "wheat", "labels": names}), encoding="utf-8")
    return review_csv, config, baseline, rows


def test_review_preprocessing_preserves_provenance_and_reports_output_sizes(review_inputs, tmp_path, capsys):
    review, config, baseline, _ = review_inputs
    output = tmp_path / "prepared"
    main(["--review", str(review), "--labels", str(config), "--output", str(output), "--check"])
    assert not output.exists()
    check_output = capsys.readouterr().out
    assert "待筛 1" in check_output
    assert "待复核：Pending 1 张" in check_output
    assert "Unused" not in check_output

    main(["--review", str(review), "--labels", str(config), "--output", str(output)])
    stdout = capsys.readouterr().out
    assert "A：4 张" in stdout and "B：4 张" in stdout
    assert "512×1024 1 张" in stdout
    assert "独立组不足 3 个的已选类别：Rare（1 组）" in stdout
    assert "Unused" not in stdout
    manifest = read_rows(output / "manifest.csv")
    sources = read_rows(output / "sources.csv")
    report = json.loads((output / "manifest.report.json").read_text(encoding="utf-8"))
    labels = json.loads((output / "labels.json").read_text(encoding="utf-8"))

    assert report["manifest_images"] == len(manifest) == len(sources) == 8
    assert report["by_label_and_source"] == {
        "a": {"domestic": 1, "kaggle-wheat-v6": 3},
        "b": {"domestic": 1, "kaggle-wheat-v6": 2, "publisher": 1},
    }
    assert report["by_part"] == {"叶片": 1}
    publisher_photo = next(row for row in sources if row["source"] == "publisher")
    assert publisher_photo["source_path"] == "../sources/publisher/leaf.jpg"
    assert publisher_photo["part"] == "叶片"
    assert report["labels_with_fewer_than_three_groups"] == {"rare": 1}
    assert report["pending_by_label"] == {"pending": 1}
    assert labels["labels"] == {"a": "A", "b": "B"}
    assert report["review_decisions"] == {"keep": 12, "pending": 1, "drop": 1}
    assert len(report["review_skipped"]) == 1 and len(report["image_rejected"]) == 1
    assert report["resolution_counts"]["a"] == {"512x1024": 1, "140x96": 3}
    assert report["resolution_counts"]["b"] == {"140x96": 4}

    domestic = [row for row in sources if row["source"] == "domestic"]
    assert len({(row["group"], row["split"]) for row in domestic}) == 1
    for row in domestic:
        prepared = output / "images" / row["path"]
        assert prepared.read_bytes() == (baseline / "images" / f"{row['label']}.jpg").read_bytes()

    for row in manifest:
        prepared = output / "images" / row["path"]
        assert hashlib.sha256(prepared.read_bytes()).hexdigest() == row["sha256"]
        with Image.open(prepared) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
            assert image.getexif().get(274, 1) == 1

    previous = (output / "manifest.csv").read_bytes()
    with pytest.raises(SystemExit):
        main(["--review", str(review), "--labels", str(config), "--output", str(output)])
    assert (output / "manifest.csv").read_bytes() == previous


def test_insufficient_groups_leave_no_partial_dataset(review_inputs, tmp_path):
    review, config, _, rows = review_inputs
    with review.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows[:2])
    output = tmp_path / "prepared"

    with pytest.raises(SystemExit):
        main(["--review", str(review), "--labels", str(config), "--output", str(output)])

    assert not output.exists()
    assert not list(tmp_path.glob(".wheat-prep-*"))



def test_review_check_filters_sources_classes_and_folders(review_inputs, tmp_path, capsys):
    review, config, baseline, _ = review_inputs
    output = tmp_path / "prepared"
    main([
        "--review", str(review), "--labels", str(config), "--output", str(output), "--check",
        "--source", "kaggle-wheat-v6", "--source", "domestic", "--class", "b",
        "--folder", str(baseline / "images"),
    ])
    stdout = capsys.readouterr().out
    assert "本次选中 1 个数据集、1 个有图类别" in stdout
    assert "B (b): 1 张（domestic 1 张）" in stdout
    assert "A (a)" not in stdout
    assert not output.exists()

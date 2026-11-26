"""田间开发清单必须保留冻结基线、整日分组和独立最终测试的排除边界。"""
import csv
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from ml.agrivision_ml.preprocessing import field_manifest as field


def row(path, label, dhash, role="field", date="2020-01-01", split="train"):
    return {"path": path, "label": label, "dhash": dhash, "sha256": hashlib.sha256(path.encode()).hexdigest(),
            "role": role, "source": "author", "capture_date": date, "split": split, "group": path}


def test_date_groups_join_labels_without_reinterpreting_them_as_label_conflicts():
    rows = [row("a", "a", 0), row("b", "b", 2**64-1)]
    combined, blocked, conflicts = field.connect_field([], rows)
    assert not blocked and not conflicts
    assert len({r["group"] for r in combined}) == 1
    assert {r["label"] for r in combined} == {"a", "b"}


def test_field_near_duplicate_never_changes_frozen_baseline():
    baseline = row("base", "a", 0, role="baseline", split="test")
    duplicate = row("field", "a", 0)
    connected, blocked, _ = field.connect_field([baseline], [duplicate])
    assert connected == []
    assert blocked == [{"path": "field", "reason": "overlaps_frozen_baseline"}]
    assert baseline["split"] == "test" and baseline["group"] == "base"


def test_cross_label_duplicate_is_held_instead_of_relabelled():
    rows = [row("a", "a", 0), row("b", "b", 1)]
    connected, blocked, conflicts = field.connect_field([], rows)
    assert not connected and len(blocked) == 2 and len(conflicts) == 1
    assert rows[1]["label"] == "b"


def test_connected_dates_cannot_be_split_to_fill_validation():
    existing = [row("base-a", "a", 0, role="baseline"), row("base-b", "b", 0, role="baseline")]
    connected = [{**row("field", "a", 0), "connected_dates": ["2020-01-01", "2020-01-02"]}]
    with pytest.raises(ValueError, match="连接"):
        field.assign_development(existing, connected, ["2020-01-01"])


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_manifest_only_reuses_original_files_and_excludes_original_test(tmp_path):
    prepared = tmp_path / "prepared"
    images = prepared / "images"
    images.mkdir(parents=True)
    baseline = []
    for i in range(6):
        path = images / f"{i}.png"
        Image.fromarray(np.random.default_rng(i).integers(0, 256, (96, 120, 3), dtype=np.uint8)).save(path)
        baseline.append({"path": path.name, "label": "a" if i < 3 else "b",
                         "group": f"baseline-{i}", "sha256": field.file_digest(path),
                         "split": ("train", "val", "test")[i % 3]})
    write(prepared / "manifest.csv", baseline)
    write(prepared / "sources.csv", [{"path": r["path"], "source": "PV", "license": "CC BY-SA"} for r in baseline])
    external = []
    for i in range(4):
        path = tmp_path / f"field-{i}.png"
        Image.fromarray(np.random.default_rng(i + 99).integers(0, 256, (96, 120, 3), dtype=np.uint8)).save(path)
        external.append({"path": path.name, "label": ("a", "b")[i % 2], "review": "review",
                         "source": "field", "capture_datetime": f"2020:01:0{1 + i // 2} 12:00:00"})
    write(tmp_path / "field.csv", external)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.png")}
    original_manifest = (prepared / "manifest.csv").read_bytes()
    output = tmp_path / "experiment"
    report = field.build(tmp_path, prepared / "manifest.csv", tmp_path / "field.csv", output)
    assert report["excluded_baseline_original_test_images"] == 2
    assert not report["five_fold_field_feasible_by_block_count"]
    assert not (output / "manifest.csv").exists()
    field.build(tmp_path, prepared / "manifest.csv", tmp_path / "field.csv", output,
                validation_dates=["2020-01-02"])
    result = list(csv.DictReader((output / "manifest.csv").open(encoding="utf-8-sig")))
    assert len(result) == 8 and all(r["split"] != "test" for r in result)
    frozen = {f"prepared/images/{r['path']}": r for r in baseline if r["split"] != "test"}
    for r in result:
        if r["path"] in frozen:
            assert r["group"] == frozen[r["path"]]["group"] and r["split"] == frozen[r["path"]]["split"]
    assert (prepared / "manifest.csv").read_bytes() == original_manifest
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.png")} == before

def test_only_reviewed_edges_are_released_and_unreviewed_bridge_stays():
    left = row("base-1", "a", 0, role="baseline")
    other = row("base-2", "a", 1, role="baseline")
    target = row("field", "b", 2)
    one = {frozenset(("base-1", "field"))}
    connected, blocked, _ = field.connect_field([left, other], [target], one)
    assert not connected and len(blocked) == 1
    both = one | {frozenset(("base-2", "field"))}
    connected, blocked, conflicts = field.connect_field([left, other], [target], both)
    assert not blocked and not conflicts and len(connected) == 1
    assert left["group"] == "base-1" and other["group"] == "base-2"


def test_distinct_review_cannot_override_changed_bytes(tmp_path):
    left = row("base", "a", 0, role="baseline")
    right = row("field", "b", 1)
    review = tmp_path / "review.csv"
    record = {"left": "base", "right": "field", "left_sha256": left["sha256"],
              "right_sha256": right["sha256"], "decision": "different", "reason": "different visible leaf edge"}
    write(review, [record])
    assert field.reviewed_distinct_pairs(review, [left, right]) == {frozenset(("base", "field"))}
    right["sha256"] = "changed"
    with pytest.raises(ValueError, match="哈希"):
        field.reviewed_distinct_pairs(review, [left, right])

def test_existing_manifest_stops_before_overwriting_its_audit(tmp_path):
    output = tmp_path / "fixed"
    output.mkdir()
    (output / "manifest.csv").write_text("frozen")
    (output / "field-audit.json").write_text("keep-existing-audit")
    with pytest.raises(FileExistsError, match="冻结"):
        field.build(tmp_path, tmp_path / "not-read.csv", tmp_path / "not-read-either.csv", output)
    assert (output / "field-audit.json").read_text() == "keep-existing-audit"

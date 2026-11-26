"""物种筛选入口的小样本回归：不下载真实图，不训练，不生成全量工作集。"""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from ml.agrivision_ml.preprocessing import species_review
from ml.agrivision_ml.preprocessing.tables import read_rows, write_rows
from scripts.collect_crop_observations import FIELDS


@pytest.fixture
def species_inputs(tmp_path):
    root = tmp_path
    config = root / "configs/datasets/crop-identification.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({
        "task": "crop_identification",
        "targets": [
            {"id": "wheat", "name": "小麦", "scientific_name": "Triticum aestivum"},
            {"id": "maize", "name": "玉米", "scientific_name": "Zea mays"},
            {"id": "soybean", "name": "大豆", "scientific_name": "Glycine max",
             "excluded_taxa": ["Glycine max subsp. soja"]},
        ],
    }), encoding="utf-8")
    review = root / "data/crop-identification/review"
    review.mkdir(parents=True)
    rows = []
    for label_index, (label, scientific) in enumerate([
        ("wheat", "Triticum aestivum"), ("maize", "Zea mays"),
    ]):
        for index in range(6):
            photo_url = f"https://example.org/photos/{label}-{index}.jpg"
            identifier = hashlib.sha256(photo_url.encode()).hexdigest()[:20]
            path = f"data/crop-identification/sources/gbif-all/images/{label}/{identifier}.jpg"
            file = root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            pixels = np.random.default_rng(100 * label_index + index).integers(
                0, 255, (96, 128, 3), dtype=np.uint8,
            )
            Image.fromarray(pixels).save(file)
            # 每类前两张属于同次观察，剩余四张独立，共五个观察组。
            observation = f"https://example.org/observations/{label}-{max(0, index - 1)}"
            rows.append({
                "id": identifier, "label": label, "name": label, "scientific_name": scientific,
                "source_scientific_name": scientific + " L.", "path": path,
                "group": "ignored-source-group", "country": "CN", "region": "Henan",
                "organ": "待看图", "review": "review", "reason": "待人工核对",
                "license": "https://creativecommons.org/licenses/by/4.0/",
                "author": "Test Observer", "rights_holder": "Test Observer",
                "photo_url": photo_url, "photo_page": photo_url + "?page",
                "gbif_occurrence": f"https://www.gbif.org/occurrence/{label_index * 10 + index}",
                "dataset_key": "test-dataset", "observation_id": observation,
            })
    write_rows(review / "gbif-all.csv", FIELDS, rows)
    return root, rows


def test_check_creates_one_pending_review_and_no_images(species_inputs):
    root, raw = species_inputs
    path, labels, rows = species_review.sync_review(root)
    assert path == root / "data/crop-identification/review/species-review.csv"
    assert len(rows) == len(raw)
    assert {row["decision"] for row in rows} == {""}
    assert {row["review_basis"] for row in rows} == {"pending_manual_review"}
    assert {row["sha256"] for row in rows} == {""}
    assert all(row["path"].startswith("../sources/") for row in rows)
    assert len({row["group"] for row in rows}) == 10
    assert not species_review.select_photos(path, labels, rows).photos
    assert not (root / "data/crop-identification/prepared").exists()


def test_source_labels_require_explicit_permission_and_keep_manual_decisions(species_inputs):
    root, _ = species_inputs
    path, _, rows = species_review.sync_review(root)
    rows[0].update(decision="drop", note="人工发现拼图")
    rows[1].update(decision="keep", note="人工核对物种", part="leaf")
    write_rows(path, species_review.REVIEW_FIELDS, rows)
    path, labels, merged = species_review.sync_review(root, accept_source_labels=True)
    by_id = {row["id"]: row for row in merged}
    assert by_id[rows[0]["id"]]["decision"] == "drop"
    assert by_id[rows[0]["id"]]["note"] == "人工发现拼图"
    assert by_id[rows[1]["id"]]["review_basis"] == "manual_keep"
    assert by_id[rows[1]["id"]]["part"] == "leaf"
    assert len(species_review.select_photos(path, labels, merged).photos) == 1
    accepted = species_review.select_photos(path, labels, merged, accept_source_labels=True)
    assert len(accepted.photos) == 11
    assert sum(species_review.INTERNAL_BASIS in item.note for item in accepted.photos) == 10
    # 已接受来源标签不因普通刷新被冒充成人工审核。
    _, _, refreshed = species_review.sync_review(root)
    assert sum(row["review_basis"] == species_review.INTERNAL_BASIS for row in refreshed) == 10


def test_raw_manual_keep_is_preserved_but_license_taxon_and_path_errors_are_excluded(species_inputs):
    root, rows = species_inputs
    rows[0]["review"] = "keep"
    changes = [
        {"license": "https://creativecommons.org/licenses/by-nc/4.0/"},
        {"license": "https://creativecommons.org/licenses/by-nd/4.0/"},
        {"license": ""},
        {"label": "soybean", "scientific_name": "Glycine max",
         "source_scientific_name": "Glycine max (L.) Merr. subsp. soja"},
        {"label": "soybean", "source_scientific_name": "Glycine soja Siebold & Zucc."},
        {"path": "Z:/outside.jpg"},
        {"path": "data/crop-identification/sources/gbif-all/images/missing.jpg"},
        {"author": "", "rights_holder": ""},
        {"observation_id": ""},
        {"review": "drop", "reason": "人工发现水印"},
    ]
    for row, change in zip(rows[1:], changes):
        row.update(change)
    write_rows(root / "data/crop-identification/review/gbif-all.csv", FIELDS, rows)
    _, _, merged = species_review.sync_review(root, accept_source_labels=True)
    by_id = {row["id"]: row for row in merged}
    assert by_id[rows[0]["id"]]["review_basis"] == "manual_keep_source_table"
    for row in rows[1:11]:
        reviewed = by_id[row["id"]]
        assert reviewed["decision"] == "drop" and reviewed["exclusion_reason"]
    # 改表为 keep 也不能绕过来源许可和野生分类排除。
    path = root / "data/crop-identification/review/species-review.csv"
    for row in merged:
        row["decision"] = "keep"
    write_rows(path, species_review.REVIEW_FIELDS, merged)
    _, _, refreshed = species_review.sync_review(root, accept_source_labels=True)
    assert sum(row["decision"] == "drop" for row in refreshed) == 10


def test_cn_and_all_catalogs_merge_same_media_and_preserve_observation_identity(species_inputs):
    root, rows = species_inputs
    cn = dict(rows[0])
    cn["path"] = cn["path"].replace("gbif-all", "gbif-cn")
    target = root / cn["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes((root / rows[0]["path"]).read_bytes())
    # 同一观察的另一张照片仍归同组，不因它来自另一个区域列表而拆开。
    cn_second = dict(rows[1])
    write_rows(root / "data/crop-identification/review/gbif-cn.csv", FIELDS, [cn, cn_second])
    _, _, merged = species_review.sync_review(root)
    assert len(merged) == 12
    by_id = {row["id"]: row for row in merged}
    assert by_id[cn["id"]]["source"] == "gbif-cn"
    assert by_id[cn["id"]]["catalogs"] == "gbif-all.csv|gbif-cn.csv"
    assert by_id[cn["id"]]["group"] == by_id[cn_second["id"]]["group"]


def test_missing_source_rows_are_excluded_without_erasing_manual_note(species_inputs):
    root, raw = species_inputs
    path, _, rows = species_review.sync_review(root, accept_source_labels=True)
    removed = rows[0]
    removed.update(decision="keep", note="此前已核对")
    write_rows(path, species_review.REVIEW_FIELDS, rows)
    write_rows(root / "data/crop-identification/review/gbif-all.csv", FIELDS,
               [row for row in raw if row["id"] != removed["id"]])
    _, _, refreshed = species_review.sync_review(root)
    item = next(row for row in refreshed if row["id"] == removed["id"])
    assert item["decision"] == "drop" and item["note"] == "此前已核对"
    assert "已找不到" in item["exclusion_reason"]


def test_prepare_reuses_grouping_dedup_and_keeps_attribution(species_inputs, monkeypatch):
    root, raw = species_inputs
    # 同一标签增加一份真正的字节重复图，来自不同观察；公共流水线应查重。
    duplicate = {**raw[0], "id": "duplicate-media",
                 "path": "data/crop-identification/sources/gbif-all/images/wheat/duplicate.jpg",
                 "photo_url": "https://example.org/duplicate.jpg",
                 "observation_id": "https://example.org/observations/duplicate"}
    (root / duplicate["path"]).write_bytes((root / raw[0]["path"]).read_bytes())
    write_rows(root / "data/crop-identification/review/gbif-all.csv", FIELDS, [*raw, duplicate])
    monkeypatch.setattr(species_review, "ROOT", root)
    species_review.main(["--check", "--accept-source-labels"])
    output = root / "data/crop-identification/prepared"
    assert not output.exists()
    species_review.main(["--prepare", "--accept-source-labels"])
    labels = json.loads((output / "labels.json").read_text(encoding="utf-8"))
    assert labels == {"task": "crop_identification", "labels": {"wheat": "小麦", "maize": "玉米"}}
    sources = read_rows(output / "sources.csv")
    manifest = read_rows(output / "manifest.csv")
    assert len(sources) == len(manifest) == 12
    assert len({row["sha256"] for row in manifest}) == 12
    by_observation = {}
    for row in sources:
        by_observation.setdefault(row["observation_id"], set()).add(row["split"])
        assert row["author"] == "Test Observer"
        assert row["country"] == "CN" and row["region"] == "Henan"
        assert row["license"].endswith("/by/4.0/")
        assert row["review_basis"] == species_review.INTERNAL_BASIS
        assert row["photo_url"] and row["gbif_occurrence"] and row["source_path"]
    assert all(len(parts) == 1 for parts in by_observation.values())
    report = json.loads((output / "manifest.report.json").read_text(encoding="utf-8"))
    assert report["country_counts"] == {"CN": 12}
    before = (output / "manifest.csv").read_bytes()
    with pytest.raises(SystemExit):
        species_review.main(["--prepare", "--accept-source-labels"])
    assert (output / "manifest.csv").read_bytes() == before
    assert not list(output.parent.glob(".species-prep-*"))


def test_prepare_does_not_implicitly_use_previous_source_acceptance(species_inputs, monkeypatch):
    root, _ = species_inputs
    monkeypatch.setattr(species_review, "ROOT", root)
    species_review.main(["--check", "--accept-source-labels"])
    with pytest.raises(SystemExit):
        species_review.main(["--prepare"])
    assert not (root / "data/crop-identification/prepared").exists()


def test_inat_variants_merge_with_gbif_and_keep_previous_manual_drop(species_inputs):
    root, raw = species_inputs
    raw[0].update(
        photo_url="https://inaturalist-open-data.s3.amazonaws.com/photos/12345/original.jpeg",
        photo_page="https://www.inaturalist.org/photos/12345",
        observation_id="http://www.inaturalist.org/observations/54321",
    )
    raw[1]["observation_id"] = "https://inaturalist.org/observations/54321"
    catalog = root / "data/crop-identification/review/gbif-all.csv"
    write_rows(catalog, FIELDS, raw)
    review, _, previous = species_review.sync_review(root)
    prior = next(row for row in previous if row["id"] == "inat-photo:12345")
    # 模拟升级前使用 URL 哈希的筛选表，人工决定仍须跟随真实照片身份迁移。
    prior.update(id=raw[0]["id"], decision="drop", note="人工发现水印")
    write_rows(review, species_review.REVIEW_FIELDS, previous)

    variant = {**raw[0], "id": "different-url-hash",
               "photo_url": "https://static.inaturalist.org/photos/12345/square.jpg",
               "path": "data/crop-identification/sources/inat-cultivated/images/wheat/variant.jpg",
               "observation_id": "https://inaturalist.org/observations/54321",
               "quality_grade": "casual", "captive": "true"}
    file = root / variant["path"]
    file.parent.mkdir(parents=True)
    file.write_bytes((root / raw[0]["path"]).read_bytes())
    write_rows(review.parent / "inat-cultivated.csv", (*FIELDS, "quality_grade", "captive"), [variant])
    _, _, merged = species_review.sync_review(root, accept_source_labels=True)
    assert len(merged) == 12
    row = next(row for row in merged if row["id"] == "inat-photo:12345")
    assert row["decision"] == "drop" and row["note"] == "人工发现水印"
    assert row["quality_grade"] == "casual" and row["captive"] == "true"
    assert row["catalogs"] == "gbif-all.csv|inat-cultivated.csv"
    assert row["observation_id"] == "https://www.inaturalist.org/observations/54321"
    other = next(row for row in merged if row["id"] == raw[1]["id"])
    assert row["group"] == other["group"]


def test_casual_cultivated_sources_stay_explicit_internal_labels_and_keep_audit_fields(species_inputs):
    root, raw = species_inputs
    review_root = root / "data/crop-identification/review"
    (review_root / "gbif-all.csv").unlink()
    for row in raw:
        row.update(quality_grade="casual", captive="true")
    write_rows(review_root / "inat-cultivated.csv", (*FIELDS, "quality_grade", "captive"), raw)
    review, labels, pending = species_review.sync_review(root)
    assert all(row["decision"] == "" for row in pending)
    review, labels, rows = species_review.sync_review(root, accept_source_labels=True)
    assert {row["review_basis"] for row in rows} == {species_review.INTERNAL_BASIS}
    selected = species_review.select_photos(review, labels, rows, accept_source_labels=True)
    output = root / "data/crop-identification/prepared"
    species_review.prepare_dataset(selected, labels, rows, output)
    sources = read_rows(output / "sources.csv")
    assert {row["quality_grade"] for row in sources} == {"casual"}
    assert {row["captive"] for row in sources} == {"true"}
    assert all(row["original_observation_id"] for row in sources)
    assert all(row["source_media_id"] for row in sources)

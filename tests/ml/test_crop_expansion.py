"""扩类采集边界：保留共病标签，不覆盖人工审核，不触碰 prepared。"""
import csv
import json
from scripts import review_crop_expansion as review
from scripts import collect_maize_expansion as collect


def test_multi_disease_candidates_are_not_forced_into_single_label(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(review, "audit_image", lambda path: {"error": "", "width": 100, "height": 100})
    audit = tmp_path / "data/maize/review/source-audit.csv"
    audit.parent.mkdir(parents=True)
    audit.write_text("source,source_label\n", encoding="utf-8")
    metadata = tmp_path / "data/maize/sources/pretoria-field-20237613-v1/metadata/Database.csv"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("filePath,GLS,NCLB,PLS,CR,SR,NoFoliarSymptoms,Other,UnidentifiedDisease\n"
                        "single.jpg,0,0,1,0,0,0,0,0\n"
                        "mixed.jpg,0,0,0,1,1,0,0,0\n", encoding="utf-8")
    rows = review.maize_candidates()
    assert rows[0]["label"] == "maize_phaeosphaeria_leaf_spot"
    assert rows[1]["label"] == ""
    assert rows[1]["source_label"] == "CR|SR"
    assert rows[1]["CR"] == rows[1]["SR"] == "1"
    assert rows[1]["review"] == "hold"
    assert not (tmp_path / "data/maize/prepared").exists()


def test_union_csv_preserves_provider_fields_and_visual_review(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "ROOT", tmp_path)
    folder = tmp_path / "data/maize/review"
    folder.mkdir(parents=True)
    quality = {"findings": {"a": "watermark hold"}}
    (folder / "class-expansion-visual-review.json").write_text(json.dumps(quality), encoding="utf-8")
    rows = [{"path": "a.jpg", "source": "a", "label": "", "field_id": "N1", "review": "hold"},
            {"path": "b.jpg", "source": "b", "label": "", "CR": "1", "SR": "1", "review": "hold"}]
    review.write_candidates("maize", rows)
    with (folder / "class-expansion-existing.csv").open(encoding="utf-8-sig") as stream:
        result = list(csv.DictReader(stream))
    assert result[0]["field_id"] == "N1"
    assert result[1]["CR"] == result[1]["SR"] == "1"
    report = json.loads((folder / "class-expansion-existing.json").read_text(encoding="utf-8"))
    assert report["visual_review"] == quality
    assert report["prepared_changed"] is False


def test_verified_original_is_reused_without_network(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(collect, "TARGET", tmp_path)
    raw = tmp_path / "raw/小斑病/a.jpg"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"original")
    def no_network(*args, **kwargs):
        raise AssertionError("MD5匹配的原文件不应再下载")
    monkeypatch.setattr(collect.httpx, "Client", no_network)
    collect.download_one({"author_label": "小斑病", "fileName": "a.jpg", "md5": hashlib.md5(b"original").hexdigest()})

"""黄瓜来源适配的边界：标签/人工排除不能被实验开关覆盖，续传不能接受错误段。"""
import hashlib
import json

import httpx
import pytest
from PIL import Image

from ml.agrivision_ml.preprocessing import cucumber_sources as module
from ml.agrivision_ml.preprocessing.tables import write_rows, read_rows


def test_edited_filename_stays_in_same_group_without_inventing_plant_id():
    source = {"source": "kaggle-kaushigihanml"}
    assert module.filename_group({**source, "path": "train/Powdery/IMG_E0123.JPG"}) == module.filename_group(
        {**source, "path": "test/Powdery/IMG_0123.JPG"})
    assert module.filename_group({"source": "other", "path": "IMG_0123.JPG"}) == ""
    assert module.filename_group({**source, "path": "leaf.jpg"}) == ""


def test_review_acceptance_keeps_manual_drop_and_excludes_unmapped_fruit(tmp_path):
    source = {"id": "cucumber-source", "crop": "cucumber", "label_map": {"Downy": "downy"},
              "hold_labels": {"Fruit": "本轮仅叶片"}, "default_review": "review"}
    config = tmp_path / "configs/datasets"; config.mkdir(parents=True)
    (config / "cucumber.json").write_text(json.dumps({"sources": [source]}))
    labels = tmp_path / "configs/labels"; labels.mkdir(parents=True)
    (labels / "cucumber.json").write_text(json.dumps({"crop": "cucumber", "labels": {"downy": "霜霉", "healthy": "健康"}}))
    audit = []
    for name, label in [("kept", "Downy"), ("manual-drop", "Downy"), ("fruit", "Fruit")]:
        photo = tmp_path / f"data/cucumber/sources/cucumber-source/raw/{name}.png"
        photo.parent.mkdir(parents=True, exist_ok=True); Image.new("RGB", (10, 10), "green").save(photo)
        audit.append({"path": photo.relative_to(tmp_path).as_posix(), "source": source["id"],
                      "source_label": label, "group": "unknown", "review": "review"})
    review = tmp_path / "data/cucumber/review"; review.mkdir(parents=True)
    write_rows(review / "source-audit.csv", list(audit[0]), audit)
    write_rows(review / "disease-review.csv", module.REVIEW_FIELDS, [{"decision": "drop", "label": "downy",
        "path": "../sources/cucumber-source/raw/manual-drop.png", "source": source["id"], "review_basis": "manual_drop"}])
    selection = module.prepare_review(accept_source_labels=True, root=tmp_path)
    assert [photo.file.stem for photo in selection.photos] == ["kept"]
    rows = read_rows(review / "disease-review.csv", ("decision", "path"))
    assert sum(row["decision"] == "drop" for row in rows) == 2
    assert selection.photos[0].group == ""


@pytest.mark.parametrize("bad_range", [False, True])
def test_resumed_download_checks_segment_boundaries(tmp_path, monkeypatch, bad_range):
    content = b"a-real-original-image-archive"
    destination = tmp_path / "original.zip"
    part = destination.with_suffix(".zip.part"); part.write_bytes(content[:4])
    requested = []
    def handler(request):
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        end = min(end, len(content) - 1); requested.append((start, end))
        shown_start = start + 1 if bad_range and start else start
        return httpx.Response(206, headers={"Content-Range": f"bytes {shown_start}-{end}/{len(content)}"},
                              content=content[start:end + 1])
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(module.httpx, "Client", lambda **kwargs: client)
    if bad_range:
        with pytest.raises(ValueError, match="分段边界"):
            module.download_ranges("https://example.org/original.zip", destination, block_size=5)
        assert not destination.exists() and part.read_bytes() == content[:4]
    else:
        module.download_ranges("https://example.org/original.zip", destination,
                               hashlib.sha256(content).hexdigest(), block_size=5)
        assert destination.read_bytes() == content
        assert requested[1][0] == 4
        assert not part.exists()

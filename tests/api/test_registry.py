from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.knowledge import Knowledge
from app.models import ModelRegistry

ROOT = Path(__file__).resolve().parents[2]


def registry(tmp_path, **options):
    folder = tmp_path / 'wheat'
    folder.mkdir()
    metadata = {
        'crop': 'wheat', 'architecture': 'efficientnet_b0',
        'labels': ['wheat_stripe_rust', 'healthy', 'wheat_other'],
        'label_names': {'wheat_stripe_rust': '条锈病', 'healthy': '健康参考', 'wheat_other': '其他症状'},
        'version': 'test-bundle', 'input_size': 224, 'threshold': .85, 'margin': .25,
        'validated': False, 'development_ready': True, 'field_verified': False,
    }
    metadata.update(options)
    (folder / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    (folder / 'weights.pt').write_bytes(b'placeholder-never-loaded')
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path)
    return ModelRegistry(settings, Knowledge(ROOT))


def test_experimental_model_requires_explicit_development_setting(tmp_path):
    model = registry(tmp_path)
    assert model.metadata('wheat') is None
    model.settings = replace(model.settings, allow_experimental_models=True)
    assert model.metadata('wheat')['development_ready'] is True


def test_status_reads_each_crop_metadata_once(tmp_path, monkeypatch):
    model = registry(tmp_path)
    model.settings = replace(model.settings, allow_experimental_models=True)
    read_metadata = model.metadata
    crops_read = []

    def tracked_metadata(crop):
        crops_read.append(crop)
        return read_metadata(crop)

    monkeypatch.setattr(model, "metadata", tracked_metadata)
    states = {state["crop"]: state for state in model.status()}

    assert crops_read == ["wheat", "maize", "peanut", "cucumber", "tomato"]
    assert states["wheat"]["version"] == "test-bundle"
    assert states["wheat"]["classes"] == 3 and states["wheat"]["experimental"]
    assert states["wheat"]["labels"] == ["wheat_stripe_rust", "healthy", "wheat_other"]
    assert states["wheat"]["label_names"]["healthy"] == "健康参考"
    assert all(states[crop]["labels"] == [] and states[crop]["label_names"] == {}
               for crop in ("maize", "peanut", "cucumber", "tomato"))
    assert all(not states[crop]["ready"] for crop in ("maize", "peanut", "cucumber", "tomato"))


@pytest.mark.parametrize('allowed', [False, True])
def test_synthetic_smoke_bundle_is_never_servable(tmp_path, allowed):
    model = registry(tmp_path, development_only=True, validated=True)
    model.settings = replace(model.settings, allow_experimental_models=allowed)
    assert model.metadata('wheat') is None


def test_other_symptoms_are_rejected_even_with_high_probability(tmp_path, monkeypatch):
    pytest.importorskip('torch')
    from ml.agrivision_ml import inference

    class Predictor:
        def __init__(self, *_args):
            pass

        def predict(self, _path):
            return [{'id': 'wheat_other', 'name': '其他症状', 'score': .99},
                    {'id': 'healthy', 'name': '健康参考', 'score': .008},
                    {'id': 'wheat_stripe_rust', 'name': '条锈病', 'score': .002}]

    monkeypatch.setattr(inference, 'Predictor', Predictor)
    model = registry(tmp_path)
    model.settings = replace(model.settings, allow_experimental_models=True)
    result = model.predict('wheat', tmp_path / 'unused.jpg')
    assert result['status'] == 'uncertain' and result['disease_id'] is None
    assert result['experimental'] is True
    assert result['validation_scope'] == 'public-dataset-internal-test'


def test_model_labels_can_precede_reference_cards(tmp_path):
    model = registry(
        tmp_path, labels=["wheat_glume_blotch", "healthy"],
        label_names={"wheat_glume_blotch": "小麦颖枯病", "healthy": "健康参考"},
    )
    model.settings = replace(model.settings, allow_experimental_models=True)
    assert model.metadata("wheat")["labels"] == ["wheat_glume_blotch", "healthy"]
    assert model.knowledge.advice("wheat", "wheat_glume_blotch")["products"] == []


def test_model_labels_cannot_cross_crop(tmp_path):
    model = registry(
        tmp_path, labels=["maize_unknown_disease", "healthy"],
        label_names={"maize_unknown_disease": "玉米类别", "healthy": "健康参考"},
    )
    model.settings = replace(model.settings, allow_experimental_models=True)
    assert model.metadata("wheat") is None

@pytest.mark.parametrize(("environment", "expected"), [(None, False), ("0", False), ("1", True)])
def test_environment_requires_explicit_experimental_model_opt_in(monkeypatch, environment, expected):
    from app import config

    # 不读取开发者本机 .env；单独验证未配置、明确关闭、明确启用三种启动方式。
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("AGRIVISION_ALLOW_EXPERIMENTAL_MODELS", raising=False)
    if environment is not None:
        monkeypatch.setenv("AGRIVISION_ALLOW_EXPERIMENTAL_MODELS", environment)
    assert config.Settings.from_env().allow_experimental_models is expected

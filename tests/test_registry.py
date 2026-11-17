from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.knowledge import Knowledge
from app.models import ModelRegistry

ROOT = Path(__file__).resolve().parents[1]


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

"""未来候选启用的整体门槛不能被高置信子集或旧的80%门槛替代。"""
import hashlib
import json
import math
from types import SimpleNamespace

import pytest
import torch

from ml.agrivision_ml import evaluate


@pytest.fixture
def activation(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("fixed heldout manifest", encoding="utf-8")
    metadata_file = tmp_path / "metadata.json"
    metadata = {"labels": ["a", "b"], "input_size": 64, "version": "candidate",
                "threshold": .7, "margin": .12, "validated": False,
                "development_only": False, "development_ready": False,
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    truth = torch.arange(2).repeat_interleave(20)
    logits = torch.nn.functional.one_hot(truth).float() * 10
    class StaticPredictor:
        def __init__(self, bundle, device):
            self.metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            self.device = torch.device("cpu")
            self.model = torch.nn.Identity()
    monkeypatch.setattr(evaluate, "Predictor", StaticPredictor)
    monkeypatch.setattr(evaluate, "Images", lambda *args, **kwargs: torch.utils.data.TensorDataset(logits, truth))
    monkeypatch.setattr(evaluate, "read_manifest", lambda _: [{"split": "test"} for _ in truth])
    args = SimpleNamespace(bundle=tmp_path, data_root=tmp_path, manifest=manifest, device="cpu",
                           split="test", activate=False, activate_experimental=False, field_verified=False,
                           report_name="activation")
    report = {"accuracy": .90, "macro_f1": .90, "counts": [20, 20], "recall": [.90, .90]}
    monkeypatch.setattr(evaluate, "evaluate_loader", lambda *args: dict(report))
    return args, report, metadata_file


@pytest.mark.parametrize("mode", ["activate", "activate_experimental"])
@pytest.mark.parametrize("changes", [{"accuracy": .899, "macro_f1": .96},
                                      {"accuracy": .96, "macro_f1": .899},
                                      {"counts": [20, 19]}, {"recall": [.90, .59]},
                                      {"accuracy": float("nan")}, {"macro_f1": float("nan")}])
def test_activation_failure_keeps_metadata_unchanged(activation, mode, changes):
    args, report, metadata_file = activation
    setattr(args, mode, True)
    args.field_verified = mode == "activate"
    report.update(changes)
    before = metadata_file.read_bytes()
    with pytest.raises(ValueError, match="Activation requires overall"):
        evaluate.evaluate(args)
    assert metadata_file.read_bytes() == before
    # 失败的真实总体指标仍保留；即使被接受样本全对，也不能替代总体门槛。
    saved = json.loads((args.bundle / "evaluation-activation.json").read_text(encoding="utf-8"))
    if math.isnan(report["accuracy"]):
        assert math.isnan(saved["accuracy"])
    else:
        assert saved["accuracy"] == report["accuracy"]
    assert saved["selective"]["accuracy"] == 1.


@pytest.mark.parametrize("mode", ["activate", "activate_experimental"])
def test_exact_90_percent_boundary_activates_only_requested_stage(activation, mode):
    args, _, metadata_file = activation
    setattr(args, mode, True)
    args.field_verified = mode == "activate"
    evaluate.evaluate(args)
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["validated"] is (mode == "activate")
    assert metadata["field_verified"] is (mode == "activate")
    assert metadata["development_ready"] is (mode == "activate_experimental")


@pytest.mark.parametrize("mode", ["activate", "activate_experimental"])
def test_development_fold_stays_blocked_above_metric_gate(activation, mode):
    args, report, metadata_file = activation
    report.update(accuracy=1., macro_f1=1.)
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata["development_only"] = True
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    before = metadata_file.read_bytes()
    setattr(args, mode, True)
    args.field_verified = True
    with pytest.raises(ValueError):
        evaluate.evaluate(args)
    assert metadata_file.read_bytes() == before


def test_plain_evaluation_does_not_activate_candidate(activation):
    args, _, metadata_file = activation
    before = metadata_file.read_bytes()
    evaluate.evaluate(args)
    assert metadata_file.read_bytes() == before


def test_formal_activation_still_requires_field_confirmation(activation):
    args, _, metadata_file = activation
    args.activate = True
    before = metadata_file.read_bytes()
    with pytest.raises(ValueError, match="field verification"):
        evaluate.evaluate(args)
    assert metadata_file.read_bytes() == before


def test_experimental_activation_still_requires_original_manifest(activation):
    args, _, metadata_file = activation
    args.activate_experimental = True
    args.manifest.write_text("different manifest", encoding="utf-8")
    before = metadata_file.read_bytes()
    with pytest.raises(ValueError, match="held-out"):
        evaluate.evaluate(args)
    assert metadata_file.read_bytes() == before

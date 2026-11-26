"""缓存诊断必须使用同一清单与冻结骨干，并保留高置信错误。"""
import csv
import json

import numpy as np
import pytest
import torch
from torch import nn

from ml.agrivision_ml import probe_diagnostics as diagnostic
from ml.agrivision_ml.linear_probe import backbone_digest, digest


class TinyProbe(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = nn.Linear(2, 2)
        self.head = nn.Linear(2, 2)
        with torch.no_grad():
            self.head.weight.copy_(torch.eye(2))
            self.head.bias.zero_()


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    output = tmp_path / 'probe'
    bundle = output / 'bundle'
    bundle.mkdir(parents=True)
    manifest = tmp_path / 'manifest.csv'
    with manifest.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'group', 'sha256', 'label', 'split'])
        writer.writeheader()
        for split in ('val', 'test'):
            for index, label in enumerate(('a', 'b')):
                key = split + str(index)
                writer.writerow({'path': key + '.jpg', 'group': key, 'sha256': key,
                                 'label': label, 'split': split})
    model = TinyProbe()
    torch.save(model.state_dict(), bundle / 'weights.pt')
    model.head = nn.Identity()
    np.savez_compressed(output / 'features.npz', val_x=np.array([[5, -5], [5, -5]], dtype='float32'),
                        test_x=np.array([[5, -5], [-5, 5]], dtype='float32'),
                        val_y=np.array([0, 1]), test_y=np.array([0, 1]))
    identity = {'manifest': digest(manifest), 'cache_sha256': digest(output / 'features.npz'),
                'backbone_sha256': backbone_digest(model)}
    (output / 'features.json').write_text(json.dumps(identity), encoding='utf-8')
    metadata = {'architecture': 'swin_t', 'labels': ['a', 'b'], 'feature_cache': identity,
                'threshold': .7, 'margin': .12, 'temperature': 1}
    (bundle / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    monkeypatch.setattr(diagnostic, 'build_model', lambda *args, **kwargs: TinyProbe())
    return output, manifest


def test_cached_diagnostics_reconstructs_probabilities_and_keeps_confident_errors(experiment):
    output, manifest = experiment
    sources = manifest.with_name('sources.csv')
    sources.write_text('path,source\nval0.jpg,only-a\nval1.jpg,only-b\ntest0.jpg,only-a\ntest1.jpg,only-b\n', encoding='utf-8')
    result = diagnostic.diagnose(output, manifest, sources)
    assert result['splits']['val']['by_source']['only-a']['present_classes'] == ['a']
    assert result['splits']['val']['by_source']['only-a']['present_class_macro_f1'] == 1
    assert result['splits']['val']['accuracy'] == .5
    assert result['splits']['test']['accuracy'] == 1
    confidence = result['splits']['val']['confidence']
    assert confidence['calibrated'] is False
    assert confidence['wrong_at_least_90_percent'] == 1
    assert confidence['mean_wrong_confidence'] == pytest.approx(torch.tensor([5., -5.]).softmax(0)[0].item())
    with (output / 'predictions-val.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert [(row['true'], row['predicted']) for row in rows] == [('a', 'a'), ('b', 'a')]


@pytest.mark.parametrize('changed', ['manifest', 'cache', 'backbone'])
def test_changed_inputs_are_not_silently_used_for_diagnostics(experiment, changed):
    output, manifest = experiment
    if changed == 'manifest':
        with manifest.open('a') as stream:
            stream.write('\n')
    elif changed == 'cache':
        with (output / 'features.npz').open('ab') as stream:
            stream.write(b'changed')
    else:
        weights = output / 'bundle/weights.pt'
        state = torch.load(weights, weights_only=True)
        state['backbone.weight'] += 1
        torch.save(state, weights)
    with pytest.raises(ValueError):
        diagnostic.diagnose(output, manifest)
    assert not (output / 'probe-diagnostics.json').exists()

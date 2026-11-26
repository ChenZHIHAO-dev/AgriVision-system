"""以真实训练循环检查单张尾批，避免 LayerNorm 模型每轮悄悄少读一张图。"""
import csv
import hashlib
import json

from PIL import Image
import pytest
import torch
from torch import nn

from ml.agrivision_ml import train as training


@pytest.mark.parametrize('batch_norm,freeze_epochs,freeze_bn,seen,updates', [
    (False, 0, False, 3, 2),
    (True, 0, False, 2, 1),
    (True, 1, False, 3, 2),
    (True, 0, True, 3, 2),
])
def test_single_tail_batch_obeys_active_normalization(tmp_path, monkeypatch,
        batch_norm, freeze_epochs, freeze_bn, seen, updates):
    rows = []
    for index in range(5):
        path = tmp_path / f'{index}.png'
        Image.new('RGB', (64, 64), (30 + 40 * index, 90, 100 + index)).save(path)
        rows.append({'path': path.name, 'label': ['a', 'b'][index % 2],
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'group': str(index), 'split': 'train' if index < 3 else 'val'})
    manifest = tmp_path / 'manifest.csv'
    with manifest.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps({'crop': 'wheat', 'labels': {'a': 'A', 'b': 'B'}}))

    class TinyNetwork(nn.Module):
        def __init__(self):
            super().__init__()
            self.stem = nn.Sequential(nn.Conv2d(3, 4, 1), nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                                      nn.BatchNorm1d(4) if batch_norm else nn.LayerNorm(4))
            self.classifier = nn.Sequential(nn.Linear(4, 2))

        def forward(self, images):
            return self.classifier(self.stem(images))

    monkeypatch.setattr(training, 'build_model', lambda *args, **kwargs: TinyNetwork())
    output = tmp_path / 'bundle'
    args = training.parser().parse_args([
        '--data-root', str(tmp_path), '--manifest', str(manifest), '--labels', str(labels),
        '--output', str(output), '--architecture', 'convnext_tiny', '--no-pretrained',
        '--input-size', '64', '--batch-size', '2', '--epochs', '1',
        '--freeze-epochs', str(freeze_epochs), '--precision', 'fp32', '--device', 'cpu',
        *(['--freeze-bn'] if freeze_bn else []),
    ])
    metadata = training.train(args)
    history = json.loads((output / 'training.json').read_text())
    assert history[0]['train_images_seen'] == seen
    assert history[0]['optimizer_updates'] == updates
    assert metadata['validation']['epoch'] == 1
    assert (output / 'weights.pt').exists()

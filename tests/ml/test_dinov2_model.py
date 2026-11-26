"""DINO 接入测试：离线权重路径、输入约定及差分学习率不改变旧训练默认值。"""
import copy
import json
from pathlib import Path

import pytest
import torch
from torch import nn

from ml.agrivision_ml import model as networks
from ml.agrivision_ml import train as training
from ml.agrivision_ml.inference import Predictor


class TinyVision(nn.Module):
    """用轻量形状相关权重验证保存重载契约，不为单元测试下载或复制 346MB 骨干。"""
    def __init__(self, classes=3, input_size=224):
        super().__init__()
        self.input_size = input_size
        self.stem = nn.Linear(3, 4)
        self.pos_embed = nn.Parameter(torch.zeros(1, (input_size // 14) ** 2 + 1, 4))
        self.head = nn.Linear(4, classes)

    def forward(self, inputs):
        assert inputs.shape[-2:] == (self.input_size, self.input_size)
        return self.head(self.stem(inputs.mean((-1, -2))) + self.pos_embed.mean(1))


@pytest.fixture
def timm_calls(monkeypatch):
    import timm
    calls = []

    def create(name, **kwargs):
        calls.append((name, kwargs))
        return TinyVision(kwargs['num_classes'], kwargs['img_size'])

    monkeypatch.setattr(timm, 'create_model', create)
    return calls


def test_local_dino_weights_use_offline_adapter_and_head(tmp_path, timm_calls):
    checkpoint = tmp_path / 'public-dino.pth'
    checkpoint.write_bytes(b'fixture; adapter call only')
    model = networks.build_model('dinov2_vitb14_reg4', 14, pretrained=True,
                                 input_size=224, pretrained_weights=checkpoint)
    name, options = timm_calls[-1]
    assert name == 'vit_base_patch14_reg4_dinov2.lvd142m'
    assert options['pretrained'] is True and options['num_classes'] == 14
    assert options['pretrained_cfg_overlay'] == {'file': str(checkpoint.resolve()), 'hf_hub_id': None}
    assert networks.classification_head(model, 'dinov2_vitb14_reg4') is model.head
    assert model(torch.zeros(1, 3, 224, 224)).shape == (1, 14)


def test_dino_input_must_match_patch_grid_before_build(timm_calls):
    with pytest.raises(ValueError, match='14'):
        networks.build_model('dinov2_vitb14_reg4', 3, input_size=320)
    assert not timm_calls


def test_dino_bundle_reloads_metadata_size_without_original_pretraining_file(tmp_path, timm_calls):
    # 推理只使用本项目导出的权重。删去原始预训练文件也不应触发下载或改回224的位置编码。
    model = networks.build_model('dinov2_vitb14_reg4', 3, input_size=112).eval()
    torch.save(model.state_dict(), tmp_path / 'weights.pt')
    (tmp_path / 'metadata.json').write_text(json.dumps({
        'architecture': 'dinov2_vitb14_reg4', 'input_size': 112,
        'labels': ['a', 'b', 'c'], 'label_names': {'a': 'A', 'b': 'B', 'c': 'C'},
        'pretrained_weights': {'path': str(tmp_path / 'removed-original.pth'), 'sha256': 'historical'},
        'resize': 'letterbox',
    }))
    predictor = Predictor(tmp_path, 'cpu')
    sample = torch.rand(2, 3, 112, 112)
    with torch.inference_mode():
        torch.testing.assert_close(predictor.model(sample), model(sample))
    assert timm_calls[-1][1]['img_size'] == 112
    assert timm_calls[-1][1]['pretrained'] is False
    assert not timm_calls[-1][1].get('pretrained_cfg_overlay')


def test_default_optimizer_preserves_single_group_and_actual_update():
    torch.manual_seed(17)
    original = TinyVision(input_size=14)
    revised = copy.deepcopy(original)
    expected = torch.optim.AdamW(original.parameters(), lr=1e-4, weight_decay=.01)
    actual = training.make_optimizer(revised, 'dinov2_vitb14_reg4', 1e-4, 1.0)
    assert len(actual.param_groups) == 1
    inputs = torch.randn(4, 3, 14, 14)
    for model, optimizer in ((original, expected), (revised, actual)):
        model(inputs).square().mean().backward()
        optimizer.step()
    for before, after in zip(original.parameters(), revised.parameters()):
        torch.testing.assert_close(before, after, rtol=0, atol=0)


def test_differential_groups_have_every_parameter_once_and_freeze_head_warmup():
    model = TinyVision(input_size=14)
    optimizer = training.make_optimizer(model, 'dinov2_vitb14_reg4', 1e-5, 10)
    groups = optimizer.param_groups
    assert len(groups) == 2
    assert [g['lr'] for g in groups] == pytest.approx([1e-5, 1e-4])
    parameter_ids = [id(p) for group in groups for p in group['params']]
    assert len(parameter_ids) == len(set(parameter_ids))
    assert set(parameter_ids) == {id(p) for p in model.parameters()}
    assert {id(p) for p in groups[1]['params']} == {id(p) for p in model.head.parameters()}
    before_stem = model.stem.weight.detach().clone()
    before_head = model.head.weight.detach().clone()
    model.requires_grad_(False)
    model.head.requires_grad_(True)
    model(torch.randn(4, 3, 14, 14)).square().mean().backward()
    optimizer.step()
    assert torch.equal(model.stem.weight, before_stem)
    assert not torch.equal(model.head.weight, before_head)
    # 沿用原Cosine绝对下限：两组初始差10倍，调度末端不承诺恒定比例。
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=2, eta_min=5e-7)
    for _ in range(2):
        optimizer.step()
        scheduler.step()
    assert [g['lr'] for g in groups] == pytest.approx([5e-7, 5e-7])


@pytest.mark.parametrize('multiplier', [0, -1, float('nan'), float('inf')])
def test_invalid_head_multiplier_is_rejected(multiplier):
    with pytest.raises(ValueError, match='head'):
        training.make_optimizer(TinyVision(input_size=14), 'dinov2_vitb14_reg4', 1e-5, multiplier)


def test_optional_training_arguments_preserve_old_defaults():
    args = training.parser().parse_args(['--data-root', 'images', '--manifest', 'manifest.csv',
                                         '--labels', 'labels.json', '--output', 'bundle'])
    assert args.head_lr_multiplier == 1.0 and args.pretrained_weights is None

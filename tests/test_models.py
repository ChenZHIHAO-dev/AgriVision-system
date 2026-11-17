import json
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
from ml.agrivision_ml.model import build_model
from ml.agrivision_ml.train import Images, read_manifest


@pytest.mark.parametrize('architecture', ['efficientnet_b0', 'mobilenet_v3_small'])
def test_networks_support_configured_output_classes(architecture):
    torch.set_num_threads(4)
    network=build_model(architecture,4).eval()
    with torch.inference_mode():
        result=network(torch.rand(1,3,96,96))
    assert result.shape==(1,4) and torch.isfinite(result).all()


def test_manifest_refuses_a_group_in_multiple_splits(tmp_path):
    manifest=tmp_path/'bad.csv'
    manifest.write_text('path,label,group,sha256,split\na.png,a,same,a,train\nb.png,a,same,b,test\n')
    with pytest.raises(ValueError, match='multiple splits'):
        read_manifest(manifest)


def test_training_image_path_cannot_escape_root(tmp_path):
    data=Images(tmp_path,[{'path':'../outside.png','label':'a','sha256':'anything'}],['a'],96)
    with pytest.raises(ValueError, match='escapes'):
        data[0]

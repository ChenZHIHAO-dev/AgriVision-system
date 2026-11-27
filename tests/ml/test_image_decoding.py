"""训练、离线评估和单图推理必须把手机 EXIF 朝向解释为同一组像素。"""
import hashlib
from io import BytesIO

import numpy as np
from PIL import Image
import pytest
import torch

from ml.agrivision_ml.inference import Predictor
from ml.agrivision_ml.model import preprocessing
from ml.agrivision_ml.train import Images


def oriented_photo(tmp_path, orientation):
    # 六个不同色块避免旋转/镜像后仍因图案对称而碰巧通过。
    pixels = np.array([[[240, 20, 30], [30, 230, 40], [40, 50, 220]],
                       [[60, 70, 80], [180, 150, 40], [120, 30, 170]]], dtype=np.uint8)
    photo = Image.fromarray(pixels).resize((90, 60), Image.Resampling.NEAREST)
    pixels = np.asarray(photo)
    exif = photo.getexif()
    if orientation is not None:
        exif[274] = orientation
    path = tmp_path / 'orientation.png'
    photo.save(path, exif=exif)
    # 期望由几何定义计算，不再次调用被测的 EXIF 解码函数。
    expected = {
        None: pixels, 1: pixels, 2: np.fliplr(pixels), 3: np.rot90(pixels, 2),
        4: np.flipud(pixels), 5: pixels.transpose(1, 0, 2),
        6: np.rot90(pixels, 3), 7: np.rot90(pixels.transpose(1, 0, 2), 2),
        8: np.rot90(pixels, 1),
    }[orientation]
    return path, Image.fromarray(expected)


@pytest.mark.parametrize('orientation', [None, 1, 2, 3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize('verify_each_read', [True, False])
def test_training_and_prediction_share_upright_pixels(tmp_path, orientation, verify_each_read):
    path, expected_photo = oriented_photo(tmp_path, orientation)
    original = path.read_bytes()
    row = {'path': path.name, 'label': 'leaf', 'sha256': hashlib.sha256(original).hexdigest()}
    dataset = Images(tmp_path, [row], ['leaf', 'other'], 64, resize='letterbox')
    dataset.verify_each_read = verify_each_read
    actual, label = dataset[0]
    expected = preprocessing(64, resize='letterbox')(expected_photo)
    assert label == 0
    assert torch.equal(actual, expected)

    # 截获 Predictor 真正送入网络的张量，避免只测一个未被业务调用的工具函数。
    class Capture(torch.nn.Module):
        def forward(self, tensor):
            self.received = tensor.clone()
            return torch.tensor([[2., 0.]])

    predictor = Predictor.__new__(Predictor)
    predictor.model = Capture()
    predictor.device = torch.device('cpu')
    predictor.labels = ['leaf', 'other']
    predictor.metadata = {'label_names': {'leaf': '叶片', 'other': '其他'}}
    predictor.transform = preprocessing(64, resize='letterbox')
    scores = predictor.predict(path)
    assert scores[0]['id'] == 'leaf'
    assert torch.equal(predictor.model.received[0], actual)
    # HTTP 作物识别上传传 BytesIO，和文件路径必须得到相同朝向/张量/分数。
    stream = BytesIO(original)
    stream.seek(7)
    assert predictor.predict(stream) == scores
    assert torch.equal(predictor.model.received[0], actual)
    assert stream.tell() == 7 and not stream.closed
    assert path.read_bytes() == original

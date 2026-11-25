# 训练、校准、评估和推理共用的网络与输入变换。换骨干网络看 build_model()，改输入尺寸或增强方式看 preprocessing()。
"""Shared network and preprocessing definitions for training and inference."""
from torchvision import models, transforms
from torch import nn

from . import MOBILENET_V4
# ImageNet 的 RGB 通道均值和标准差。张量转成 0 到 1 的浮点数后，用这组参数归一化。
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


# 接入新架构时，输出列数应与本轮标签数一致，并提供 train.py 冻结骨干时要单独训练的 classifier。
def build_model(architecture, classes, pretrained=False):
    # MobileNetV4 来自 timm，构建时直接指定任务类别数。其余架构由 torchvision 提供。
    # pretrained 控制是否从公开的 ImageNet 权重开始。推理会另从模型包加载本项目训练出的权重。
    if architecture == MOBILENET_V4:
        from timm import create_model

        return create_model(
            "mobilenetv4_conv_small.e2400_r224_in1k", pretrained=pretrained, num_classes=classes
        )
    if architecture == "efficientnet_b0":
        model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT if pretrained else None)
    elif architecture == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None)
    elif architecture == "convnext_tiny":
        # 用 LayerNorm 的较大骨干，可在固定数据和输入尺寸下与 MobileNetV4 对照。
        model = models.convnext_tiny(
            weights=models.ConvNeXt_Tiny_Weights.DEFAULT if pretrained else None,
        )
    else:
        raise ValueError(f"Unsupported architecture: {architecture}")
    # 将 ImageNet 分类层换成当前任务的分类层。每张照片输出 classes 个 logits，顺序对应标签清单。
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, classes)
    return model


# preprocessing() 操作的是读进内存的图片。工作图的长边限制和等比缩放由 preprocessing/images.py 负责。
def preprocessing(size=224, training=False):
    # 模型输入统一成 size×size，当前做法会把非方形图拉伸。训练和推理都使用这个固定尺寸。
    steps = [transforms.Resize((size, size))]
    # 训练集额外执行随机水平翻转、±10° 旋转和轻微的亮度、对比度、饱和度调整。
    if training:
        steps += [transforms.RandomHorizontalFlip(), transforms.RandomRotation(10), transforms.ColorJitter(brightness=.12, contrast=.12, saturation=.1)]
    # 最后转为 C×H×W 的张量并按 RGB 通道归一化。所有图像变换都在读图时执行。
    return transforms.Compose([*steps, transforms.ToTensor(), transforms.Normalize(MEAN, STD)])

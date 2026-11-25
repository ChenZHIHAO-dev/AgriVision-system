# 训练、校准、评估和推理共用的网络与输入变换。换骨干网络看 build_model()，改输入尺寸或增强方式看 preprocessing()。
"""Shared network and preprocessing definitions for training and inference."""
from torchvision import models
from torch import nn

from . import MOBILENET_V4
# 保留公共导入，已有调用方可继续从 model 导入这些定义。
from .augmentation import MEAN, STD, preprocessing


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
    elif architecture == "efficientnet_v2_s":
        # ICML 2021 EfficientNetV2，Fused-MBConv 与 MBConv 相结合的中等规模 CNN。
        model = models.efficientnet_v2_s(
            weights=models.EfficientNet_V2_S_Weights.DEFAULT if pretrained else None,
        )
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



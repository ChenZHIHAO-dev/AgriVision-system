# 训练、校准、评估和推理共用的网络与输入变换。换骨干网络看 build_model()，改输入尺寸或增强方式看 preprocessing()。
"""Shared network and preprocessing definitions for training and inference."""
from pathlib import Path

from torchvision import models
from torch import nn

from . import DINOV2_VITB14_REG4, MOBILENET_V4
# 保留公共导入，已有调用方可继续从 model 导入这些定义。
from .augmentation import MEAN, STD, preprocessing


# 接入新架构时，输出列数应与本轮标签数一致，并提供 train.py 冻结骨干时要单独训练的 classifier。
def build_model(architecture, classes, pretrained=False, *, input_size=224, pretrained_weights=None):
    """按模型包的尺寸重建网络；本地预训练文件只用于初始化，推理不再依赖它。

    DINOv2 的位置编码随 patch 网格尺寸变化，训练和推理必须传入同一 input_size。
    既有卷积/Swin 调用保留原默认参数与权重行为。
    """
    if pretrained_weights is not None and architecture != DINOV2_VITB14_REG4:
        raise ValueError("Local pretrained_weights currently applies only to DINOv2")
    if architecture == DINOV2_VITB14_REG4:
        from timm import create_model

        if input_size < 14 or input_size % 14:
            raise ValueError("DINOv2 input_size must be a positive multiple of 14")
        options = {}
        if pretrained:
            # 复用已下载并核验的官方公开文件，禁止构建时隐式去 HF 拉取另一个权重版本。
            if pretrained_weights is None:
                raise ValueError("DINOv2 pretrained initialization requires --pretrained-weights")
            checkpoint = Path(pretrained_weights).resolve()
            if not checkpoint.is_file():
                raise FileNotFoundError(checkpoint)
            options["pretrained_cfg_overlay"] = {"file": str(checkpoint), "hf_hub_id": None}
        elif pretrained_weights is not None:
            raise ValueError("pretrained_weights requires pretrained=True")
        return create_model(
            "vit_base_patch14_reg4_dinov2.lvd142m", pretrained=pretrained,
            num_classes=classes, img_size=input_size, **options,
        )
    # MobileNetV4 来自 timm，构建时直接指定任务类别数。其余架构由 torchvision 提供。
    # pretrained 控制是否从公开的 ImageNet 权重开始。推理会另从模型包加载本项目训练出的权重。
    if architecture == MOBILENET_V4:
        from timm import create_model

        return create_model(
            "mobilenetv4_conv_small.e2400_r224_in1k", pretrained=pretrained, num_classes=classes
        )
    if architecture == "swin_t":
        # ICCV 2021 分层窗口注意力。分类头名为 head，保留官方权重键名便于加载。
        model = models.swin_t(weights=models.Swin_T_Weights.DEFAULT if pretrained else None)
        model.head = nn.Linear(model.head.in_features, classes)
        return model
    if architecture == "efficientnet_b0":
        model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT if pretrained else None)
    elif architecture == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None)
    elif architecture == "efficientnet_v2_s":
        # ICML 2021 EfficientNetV2，Fused-MBConv 与 MBConv 相结合的中等规模 CNN。
        model = models.efficientnet_v2_s(
            weights=models.EfficientNet_V2_S_Weights.DEFAULT if pretrained else None,
        )
    elif architecture == "convnext_small":
        # 更深的 ConvNeXt，对照增大网络容量是否改善当前难分样本。
        model = models.convnext_small(
            weights=models.ConvNeXt_Small_Weights.DEFAULT if pretrained else None,
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




def classification_head(model, architecture):
    """获取各官方模型的分类头。冻结骨干时只训练此模块，避免改动网络权重的键名。"""
    return model.head if architecture in {"swin_t", DINOV2_VITB14_REG4} else model.classifier

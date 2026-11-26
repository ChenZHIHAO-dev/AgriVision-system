"""Crop-specific model framework."""

from importlib.util import find_spec


# 这里登记对外使用的模型架构名。训练命令和模型包的 metadata.json 都使用这些名称。
MOBILENET_V4 = "mobilenetv4_conv_small"
DINOV2_VITB14_REG4 = "dinov2_vitb14_reg4"
ARCHITECTURES = frozenset({"efficientnet_b0", "mobilenet_v3_small", "convnext_tiny", "efficientnet_v2_s", "convnext_small", "swin_t", MOBILENET_V4, DINOV2_VITB14_REG4})


# MobileNetV4 和 DINOv2 依赖 timm。这里检查依赖，实际建模仍由 model.py 负责。
def architecture_available(name):
    return name in ARCHITECTURES and (name not in {MOBILENET_V4, DINOV2_VITB14_REG4} or find_spec("timm") is not None)

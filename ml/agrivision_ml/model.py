"""Shared network and preprocessing definitions for training and inference."""
from torchvision import models, transforms
from torch import nn

ARCHITECTURES = {"efficientnet_b0", "mobilenet_v3_small"}
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def build_model(architecture, classes, pretrained=False):
    if architecture == "efficientnet_b0":
        model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT if pretrained else None)
    elif architecture == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None)
    else:
        raise ValueError(f"Unsupported architecture: {architecture}")
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, classes)
    return model


def preprocessing(size=224, training=False):
    steps = [transforms.Resize((size, size))]
    if training:
        steps += [transforms.RandomHorizontalFlip(), transforms.RandomRotation(10), transforms.ColorJitter(brightness=.12, contrast=.12, saturation=.1)]
    return transforms.Compose([*steps, transforms.ToTensor(), transforms.Normalize(MEAN, STD)])

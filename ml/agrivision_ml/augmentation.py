"""模型输入与在线增强。只处理内存中的图像，磁盘工作图和采集组划分由 preprocessing 包管理。"""
from PIL import ImageOps
import torch
from torchvision import transforms
from torchvision.transforms import v2

MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


class Letterbox:
    """等比缩放后居中补边，保留整片叶或整穗，避免拉伸病斑和裁掉症状。"""

    def __init__(self, size):
        self.size = size

    def __call__(self, image):
        # 使用固定中性色补底。补边值接近 ImageNet 均值，归一化后接近零。
        return ImageOps.pad(image, (self.size, self.size), color=(124, 116, 104))


def preprocessing(size=224, training=False, *, resize="stretch", augmentation="light"):
    """训练、评估、推理共用尺寸约定；仅 training=True 开启随机变换。

    light 保留原有轻增强作为对照。field 在此基础上加入小幅平移缩放，
    每次有 15% 概率抽取一种成像退化，避免同时叠加多种强噪声。
    """
    geometry = Letterbox(size) if resize == "letterbox" else transforms.Resize((size, size))
    steps = [geometry]
    if training:
        steps.append(transforms.RandomHorizontalFlip())
        if augmentation == "field":
            steps.append(transforms.RandomAffine(
                degrees=10, translate=(0.03, 0.03), scale=(0.95, 1.05),
                interpolation=transforms.InterpolationMode.BILINEAR, fill=(124, 116, 104),
            ))
        else:
            steps.append(transforms.RandomRotation(10))
        steps.append(transforms.ColorJitter(brightness=.12, contrast=.12, saturation=.1))
        if augmentation == "field":
            # JPEG 在 uint8 图像上工作；高斯噪声在 0~1 张量上工作，3/255 约为 3 个像素灰度级。
            # 每次只抽一种。颜色不做色相翻转，以免改变病害本身的诊断特征。
            steps.append(transforms.RandomApply([transforms.RandomChoice([
                transforms.GaussianBlur(3, sigma=(.1, .7)),
                transforms.Compose([v2.ToImage(), v2.JPEG(quality=(75, 95)), v2.ToPILImage()]),
                transforms.Compose([
                    v2.ToImage(), v2.ToDtype(torch.float32, scale=True),
                    v2.GaussianNoise(sigma=3/255, clip=True), v2.ToPILImage(),
                ]),
            ])], p=.15))
    return transforms.Compose([*steps, transforms.ToTensor(), transforms.Normalize(MEAN, STD)])

"""Decode, normalize and fingerprint dataset photos with Pillow and NumPy."""

import hashlib
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps


# 这些常量控制离线工作图的质量与大小。模型读取时的尺寸由训练参数 input_size 决定。
MIN_SHORT_SIDE = 64
WORK_IMAGE_MAX_SIDE = 1024
WORK_IMAGE_JPEG_QUALITY = 92
REVIEW_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


# 由 Pillow 根据实际字节解码。应用 EXIF 方向后转成三通道 RGB，让后续处理读到正确朝向。
def decode_rgb(content, *, review_formats=False):
    with Image.open(BytesIO(content)) as image:
        # 筛选表入口只接收静态 JPEG、PNG 或 WebP，动画图不能作为单张症状照片处理。
        if review_formats and (image.format not in REVIEW_FORMATS or getattr(image, "is_animated", False)):
            raise ValueError(f"需要可读的静态 JPG、PNG 或 WebP，实际格式为 {image.format}")
        return ImageOps.exif_transpose(image).convert("RGB")


# thumbnail() 只在长边超出限制时等比缩小，且直接修改 image。返回值是输出图的实际宽高。
def write_work_jpeg(image, output):
    image.thumbnail((WORK_IMAGE_MAX_SIDE, WORK_IMAGE_MAX_SIDE))
    output.parent.mkdir(parents=True, exist_ok=True)
    # 用独占创建方式写入 JPEG，同名工作图已经存在时会报错。
    with output.open("xb") as stream:
        image.save(stream, "JPEG", quality=WORK_IMAGE_JPEG_QUALITY)
    return image.size


# 同时计算文件 SHA-256 和感知哈希。前者检查字节完全相同，后者为近重复照片分组提供依据。
def fingerprint(path):
    content = path.read_bytes()
    with Image.open(BytesIO(content)) as image:
        if min(image.size) < MIN_SHORT_SIDE:
            raise ValueError(f"image short side is below {MIN_SHORT_SIDE} pixels")
        # 为了生成 dHash，只对用于比较的临时图转灰度并缩到 9×8。实际工作图仍按原长宽比保存。
        gray = np.asarray(ImageOps.exif_transpose(image).convert("L").resize((9, 8)))
    # 逐行比较相邻像素的亮度高低，8 行各得到 8 位，再拼成 64 位整数。
    bits = gray[:, 1:] > gray[:, :-1]
    dhash = int("".join("1" if bit else "0" for bit in bits.flat), 2)
    return hashlib.sha256(content).hexdigest(), dhash

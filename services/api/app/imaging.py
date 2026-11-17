from io import BytesIO
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


def prepare_image(content: bytes):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("请选择 JPG、PNG 或 WebP 图片")
                if original.width * original.height > 24_000_000:
                    raise ValueError("图片分辨率过大，请压缩后上传")
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("图片无法读取，请重新选择清晰的作物照片") from exc
    width, height = image.size
    gray = np.asarray(image.convert("L").resize((256, 256)), dtype=np.float32)
    laplacian = -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    sharpness = float(laplacian.var())
    reasons = []
    if min(width, height) < 160:
        reasons.append("图片太小，请靠近作物重新拍摄")
    if float(gray.mean()) < 20 or float(gray.mean()) > 244:
        reasons.append("光线过暗或过亮，请在自然光下重新拍摄")
    if sharpness < 8:
        reasons.append("图像细节不足，请对焦后拍摄症状近照")
    image.thumbnail((2400, 2400))
    output = BytesIO()
    image.save(output, "JPEG", quality=90)
    return output.getvalue(), {"width": width, "height": height, "sharpness": round(sharpness, 2), "issues": reasons}

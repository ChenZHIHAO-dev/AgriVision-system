# 单张照片推理和模型包装载入口。服务端复用 Predictor，命令行用它查看模型候选。
import argparse
import json
from pathlib import Path
from PIL import Image
import torch

from .model import build_model, preprocessing


# 作物种类识别和某作物的病害分类使用不同的标签表。other、unknown 和 wheat_other 是对应任务的拒识标签。
CROP_IDENTIFICATION_TASK = "crop_identification"
CROP_REJECTION_LABELS = frozenset({"other", "unknown"})


# 把拒识标签换成当前模型输出中的下标，供评估、校准或服务判断明确结果。
def rejection_indices(metadata):
    excluded = (
        CROP_REJECTION_LABELS
        if metadata.get("task") == CROP_IDENTIFICATION_TASK
        else {"wheat_other"}
    )
    return [index for index, label in enumerate(metadata["labels"]) if label in excluded]


# auto 优先使用可用的 CUDA，否则使用 CPU。显式请求 CUDA 时会先确认环境支持。
def select_device(value="auto"):
    value = "cuda" if value == "auto" and torch.cuda.is_available() else ("cpu" if value == "auto" else value)
    if value.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in this environment")
    return torch.device(value)


# 模型包需要同一版本的 metadata.json 和 weights.pt。配置决定架构、输出类别顺序和输入大小。
class Predictor:
    def __init__(self, bundle: Path, device="auto"):
        self.metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
        self.device = select_device(device)
        self.labels = self.metadata["labels"]
        if len(self.labels) < 2:
            raise ValueError("At least two classes are required")
        # 按训练时的类别数重建网络。先在 CPU 读权重，再移到目标设备切换到评估模式。
        self.model = build_model(self.metadata["architecture"], len(self.labels))
        self.model.load_state_dict(torch.load(bundle / "weights.pt", map_location="cpu", weights_only=True))
        self.model.to(self.device).eval()
        self.transform = preprocessing(self.metadata["input_size"])

    # 单张图变成 1×C×H×W 的批次张量，按校准温度计算类别分数，最后返回前 3 个候选。
    @torch.inference_mode()
    def predict(self, path):
        with Image.open(path) as image:
            tensor = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        scores = (self.model(tensor)/float(self.metadata.get('temperature',1.0))).softmax(1)[0].cpu().tolist()
        names = self.metadata["label_names"]
        return sorted([{"id": label, "name": names[label], "score": round(scores[i], 6)} for i, label in enumerate(self.labels)], key=lambda row: row["score"], reverse=True)[:3]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect candidate scores from a local model bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    predictor = Predictor(args.bundle, args.device)
    metadata = predictor.metadata
    # 命令行输出候选和模型状态，方便核对标签及版本。是否接受为明确结果由上层流程判断。
    print(json.dumps({
        "mode": "candidate_preview",
        "model_version": metadata["version"],
        "architecture": metadata["architecture"],
        "device": str(predictor.device),
        "validated": metadata.get("validated", False),
        "development_only": metadata.get("development_only", False),
        "candidates": predictor.predict(args.image),
    }, ensure_ascii=False, indent=2))

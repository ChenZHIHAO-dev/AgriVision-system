import json
from pathlib import Path
from PIL import Image
import torch

from .model import build_model, preprocessing


def select_device(value="auto"):
    value = "cuda" if value == "auto" and torch.cuda.is_available() else ("cpu" if value == "auto" else value)
    if value.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in this environment")
    return torch.device(value)


class Predictor:
    def __init__(self, bundle: Path, device="auto"):
        self.metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
        self.device = select_device(device)
        self.labels = self.metadata["labels"]
        if len(self.labels) < 2:
            raise ValueError("At least two classes are required")
        self.model = build_model(self.metadata["architecture"], len(self.labels))
        self.model.load_state_dict(torch.load(bundle / "weights.pt", map_location="cpu", weights_only=True))
        self.model.to(self.device).eval()
        self.transform = preprocessing(self.metadata["input_size"])

    @torch.inference_mode()
    def predict(self, path):
        with Image.open(path) as image:
            tensor = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        scores = (self.model(tensor)/float(self.metadata.get('temperature',1.0))).softmax(1)[0].cpu().tolist()
        names = self.metadata["label_names"]
        return sorted([{"id": label, "name": names[label], "score": round(scores[i], 6)} for i, label in enumerate(self.labels)], key=lambda row: row["score"], reverse=True)[:3]

import importlib.util
import json
from pathlib import Path
import sys

from ml.agrivision_ml import architecture_available

from .knowledge import CROP_NAMES


class ModelRegistry:
    def __init__(self, settings, knowledge):
        self.settings = settings
        self.knowledge = knowledge
        self.cache = {}

    def metadata(self, crop):
        path = self.settings.models / crop / "metadata.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            labels = raw["labels"]
            valid = (
                (raw.get("validated") is True or (self.settings.allow_experimental_models and raw.get('development_ready') is True)) and not raw.get("development_only") and raw.get("crop") == crop
                and architecture_available(raw.get("architecture"))
                and len(labels) >= 2 and len(set(labels)) == len(labels)
                and isinstance(raw.get("version"), str) and bool(raw["version"])
                and isinstance(raw.get("input_size"), int) and 64 <= raw["input_size"] <= 1024
                and isinstance(raw.get("label_names"), dict) and set(labels) <= set(raw["label_names"])
                # 模型标签属于模型包，资料卡可随后补充；仍校验作物命名空间，避免跨作物装载。
                and all(
                    label == "healthy" or label.startswith(crop + "_")
                    or (self.knowledge.get(label) or {}).get("crop") == crop
                    for label in labels
                )
                and (path.parent / "weights.pt").is_file()
                and 0 < raw.get("threshold", 0) < 1
                and 0 <= raw.get("margin", -1) < 1
            )
            return raw if valid else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def status(self):
        torch_available = importlib.util.find_spec("torch") is not None
        statuses = []
        for crop, name in CROP_NAMES.items():
            metadata = self.metadata(crop) or {}
            statuses.append({
                "crop": crop,
                "name": name,
                "ready": bool(metadata) and torch_available,
                "classes": len(metadata.get("labels", [])),
                "version": metadata.get("version"),
                "experimental": bool(metadata.get("development_ready")) and not metadata.get("validated"),
            })
        return statuses

    def predict(self, crop, image_path: Path):
        metadata = self.metadata(crop)
        if metadata is None or importlib.util.find_spec("torch") is None:
            return {"status": "needs_model", "title": "图片已保存，识别模型准备中", "candidates": [], "disease_id": None, "model_version": None}
        try:
            if str(self.settings.root) not in sys.path:
                sys.path.insert(0, str(self.settings.root))
            from ml.agrivision_ml.inference import Predictor
            weights = self.settings.models / crop / "weights.pt"
            stamp = (weights.stat().st_mtime_ns, (weights.parent / "metadata.json").stat().st_mtime_ns)
            cached = self.cache.get(crop)
            if cached is None or cached[0] != stamp:
                cached = (stamp, Predictor(weights.parent, self.settings.device))
                self.cache[crop] = cached
            candidates = cached[1].predict(image_path)
            top = candidates[0]
            accepted = top["score"] >= metadata["threshold"] and top["score"] - candidates[1]["score"] >= metadata["margin"]
            disease_id = top["id"] if accepted and top["id"] not in {"healthy","wheat_other"} else None
            title = "未发现已支持病害的明显特征" if accepted and top["id"] == "healthy" else ("疑似" + top["name"] if accepted else "需要补充信息后再判断")
            if top['id']=='wheat_other':
                accepted=False
                title='可能属于本版未覆盖的症状，请补充资料复核'
            experimental = bool(metadata.get('development_ready')) and not metadata.get('validated',False)
            return {"status": "identified" if accepted else "uncertain", "title": title, "candidates": candidates, "disease_id": disease_id, "model_version": metadata["version"],'experimental':experimental,'validation_scope':'field-verified' if metadata.get('field_verified') is True else 'public-dataset-internal-test'}
        except (ImportError, RuntimeError, OSError, ValueError, KeyError) as exc:
            # The UI receives a stable state rather than a traceback or invented label.
            return {"status": "model_error", "title": "识别服务暂时不可用，图片已保存", "candidates": [], "disease_id": None, "model_version": metadata.get("version")}

"""Identify the crop independently of disease classifiers and case records."""

import importlib.util
import json
import math
import sys
from io import BytesIO
from threading import Lock

from ml.agrivision_ml import architecture_available

from .schemas import CropCandidate, CropRecognitionResponse


BUNDLE_NAME = "crop-identification"
UNRECOGNIZED_LABELS = {"other", "unknown"}


class CropRecognizer:
    def __init__(self, settings):
        self.settings = settings
        self.bundle = settings.models / BUNDLE_NAME
        self.weights = self.bundle / "weights.pt"
        self.metadata_path = self.bundle / "metadata.json"
        self._cache = None
        self._lock = Lock()

    def metadata(self):
        try:
            raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            labels = raw["labels"]
            names = raw["label_names"]
            temperature = raw.get("temperature", 1.0)
            valid = (
                raw.get("task") == "crop_identification"
                and raw.get("validated") is True
                and not raw.get("development_only")
                and architecture_available(raw.get("architecture"))
                and isinstance(labels, list)
                and 2 <= len(labels) == len(set(labels))
                and all(isinstance(label, str) and label and label == label.strip() for label in labels)
                and bool(set(labels) - UNRECOGNIZED_LABELS)
                and isinstance(names, dict)
                and all(isinstance(names.get(label), str) and names[label].strip() for label in labels)
                and isinstance(raw.get("version"), str)
                and bool(raw["version"].strip())
                and type(raw.get("input_size")) is int
                and 64 <= raw["input_size"] <= 1024
                and 0 < raw.get("threshold", 0) < 1
                and 0 <= raw.get("margin", -1) < 1
                and math.isfinite(temperature)
                and temperature > 0
                and self.weights.is_file()
                and importlib.util.find_spec("torch") is not None
                and importlib.util.find_spec("torchvision") is not None
            )
            return raw if valid else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def status(self):
        metadata = self.metadata()
        return {"ready": metadata is not None, "version": metadata["version"] if metadata else None}

    def predict(self, image: BytesIO) -> CropRecognitionResponse:
        metadata = self.metadata()
        if metadata is None:
            return CropRecognitionResponse(status="model_unavailable")
        try:
            if str(self.settings.root) not in sys.path:
                sys.path.insert(0, str(self.settings.root))
            from ml.agrivision_ml.inference import Predictor

            stamp = (self.weights.stat().st_mtime_ns, self.metadata_path.stat().st_mtime_ns)
            with self._lock:
                if self._cache is None or self._cache[0] != stamp:
                    self._cache = stamp, Predictor(self.bundle, self.settings.device)
                predictor = self._cache[1]
            if predictor.metadata != metadata:
                raise ValueError("Crop model metadata changed during load")
            candidates = [
                CropCandidate(
                    id=item["id"], name=metadata["label_names"][item["id"]], score=item["score"]
                )
                for item in predictor.predict(image)
            ]
            top, second = candidates[:2]
            accepted = (
                top.id not in UNRECOGNIZED_LABELS
                and top.score >= metadata["threshold"]
                and top.score - second.score >= metadata["margin"]
            )
            return CropRecognitionResponse(
                status="recognized" if accepted else "uncertain",
                crop_id=top.id if accepted else None,
                candidates=candidates,
                model_version=metadata["version"],
            )
        except (ImportError, RuntimeError, OSError, ValueError, KeyError, TypeError):
            return CropRecognitionResponse(status="service_error", model_version=metadata["version"])

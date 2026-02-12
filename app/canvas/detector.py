from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np
from PIL import Image

from app.config import settings


@dataclass(slots=True)
class Detection:
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


class AnimalDetector(Protocol):
    @property
    def available(self) -> bool:
        ...

    def detect_animals(self, image_bgr: np.ndarray) -> list[Detection]:
        ...


class NullAnimalDetector:
    """Fallback detector used when no model is wired yet."""

    @property
    def available(self) -> bool:
        return False

    def detect_animals(self, image_bgr: np.ndarray) -> list[Detection]:
        _ = image_bgr
        return []


class UltralyticsAnimalDetector:
    def __init__(self, model_name_or_path: str, confidence_threshold: float) -> None:
        from ultralytics import YOLO  # noqa: PLC0415 - optional dependency

        self._model = YOLO(model_name_or_path)
        self._confidence_threshold = confidence_threshold
        self._animal_labels = {
            "cat",
            "dog",
            "bird",
            "horse",
            "sheep",
            "cow",
            "elephant",
            "bear",
            "zebra",
            "giraffe",
        }

    @property
    def available(self) -> bool:
        return True

    def detect_animals(self, image_bgr: np.ndarray) -> list[Detection]:
        results = self._model.predict(
            source=image_bgr,
            conf=self._confidence_threshold,
            verbose=False,
        )
        detections: list[Detection] = []
        for res in results:
            if res.boxes is None:
                continue
            names = res.names or {}
            for box in res.boxes:
                cls_idx = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                label = str(names.get(cls_idx, str(cls_idx))).lower()
                if label not in self._animal_labels:
                    continue
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                detections.append(
                    Detection(
                        label=label,
                        confidence=conf,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                    )
                )
        return detections


class TransformersAnimalDetector:
    def __init__(self, model_name_or_path: str, confidence_threshold: float, device: str) -> None:
        from transformers import pipeline  # noqa: PLC0415 - optional dependency

        if device == "auto":
            try:
                import torch  # noqa: PLC0415 - optional dependency

                device_idx = 0 if torch.cuda.is_available() else -1
            except Exception:  # noqa: BLE001
                device_idx = -1
        elif device == "cuda":
            device_idx = 0
        else:
            device_idx = -1

        self._pipe = pipeline(
            "object-detection",
            model=model_name_or_path,
            device=device_idx,
        )
        self._confidence_threshold = confidence_threshold

    @property
    def available(self) -> bool:
        return True

    def detect_animals(self, image_bgr: np.ndarray) -> list[Detection]:
        image = Image.fromarray(image_bgr[:, :, ::-1], mode="RGB")
        outputs = self._pipe(image)

        detections: list[Detection] = []
        for item in outputs:
            label = str(item.get("label", "")).lower()
            score = float(item.get("score", 0.0))
            if score < self._confidence_threshold:
                continue
            if not any(token in label for token in ("cat", "dog", "bird", "horse", "sheep", "cow")):
                continue
            box = item.get("box", {})
            x1 = int(box.get("xmin", 0))
            y1 = int(box.get("ymin", 0))
            x2 = int(box.get("xmax", 0))
            y2 = int(box.get("ymax", 0))
            detections.append(
                Detection(
                    label=label,
                    confidence=score,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                )
            )
        return detections


@lru_cache(maxsize=1)
def create_default_detector() -> AnimalDetector:
    provider = settings.animal_detector_provider.lower().strip()
    model = settings.animal_detector_model
    confidence = settings.animal_detector_confidence_threshold
    device = settings.animal_detector_device.lower().strip()

    if provider == "null":
        return NullAnimalDetector()

    if provider in {"ultralytics", "auto"}:
        try:
            return UltralyticsAnimalDetector(model, confidence)
        except Exception:  # noqa: BLE001 - optional dependency/model load failure
            if provider == "ultralytics":
                raise

    if provider in {"transformers", "auto"}:
        try:
            # Default lightweight detector if user keeps yolov8n.pt in model field.
            model_id = model if "/" in model else "facebook/detr-resnet-50"
            return TransformersAnimalDetector(model_id, confidence, device)
        except Exception:  # noqa: BLE001 - optional dependency/model load failure
            if provider == "transformers":
                raise

    return NullAnimalDetector()

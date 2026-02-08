from dataclasses import dataclass
from io import BytesIO

import cv2
import numpy as np
from PIL import Image


@dataclass
class QualityResult:
    is_valid: bool
    reason_codes: list[str]
    metrics: dict[str, float]


def _load_image_bytes(image_bytes: bytes) -> np.ndarray:
    with Image.open(BytesIO(image_bytes)) as img:
        arr = np.array(img.convert("RGB"))
    return arr


def evaluate_quality(image_bytes: bytes) -> QualityResult:
    image = _load_image_bytes(image_bytes)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())

    dark_ratio = float((gray < 15).mean())
    bright_ratio = float((gray > 240).mean())
    edge_density = float((cv2.Canny(gray, 80, 180) > 0).mean())

    reason_codes: list[str] = []

    if blur_score < 50:
        reason_codes.append("BLUR_TOO_HIGH")
    if brightness < 40:
        reason_codes.append("TOO_DARK")
    if brightness > 215:
        reason_codes.append("TOO_BRIGHT")
    if dark_ratio > 0.35 or bright_ratio > 0.35:
        reason_codes.append("SATURATION_ARTIFACT")
    if edge_density < 0.02:
        reason_codes.append("LOW_TEXTURE_INFORMATION")

    metrics = {
        "blur_score": round(blur_score, 4),
        "brightness": round(brightness, 4),
        "dark_ratio": round(dark_ratio, 4),
        "bright_ratio": round(bright_ratio, 4),
        "edge_density": round(edge_density, 4),
    }

    return QualityResult(is_valid=not reason_codes, reason_codes=reason_codes, metrics=metrics)

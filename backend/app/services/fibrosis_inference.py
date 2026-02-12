from __future__ import annotations

import json
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

import boto3
import numpy as np
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image

from app.core.config import Settings
from app.core.enums import ConfidenceFlag, EscalationFlag, FibrosisStage

STAGES = [FibrosisStage.F0, FibrosisStage.F1, FibrosisStage.F2, FibrosisStage.F3, FibrosisStage.F4]

# Feature order for fallback classifier:
# [mean_intensity, p50, p75, std, dyn_range, iqr, lap_var, hf_energy, grad_mean,
#  grad_std, grad_tail, center_delta, depth_attenuation, high_echo_ratio, low_echo_ratio]
_HEURISTIC_FEATURE_MEAN = np.array(
    [
        0.12784807,
        0.0635637,
        0.18417127,
        0.1584802,
        0.35314798,
        0.16991515,
        0.00672685,
        0.01483944,
        0.02751697,
        0.04470874,
        0.26612425,
        0.11194175,
        0.10622714,
        0.01157674,
        0.84319466,
    ],
    dtype=np.float32,
)
_HEURISTIC_FEATURE_SCALE = np.array(
    [
        0.03711329,
        0.03592382,
        0.07425263,
        0.03991693,
        0.10389005,
        0.0694316,
        0.00523812,
        0.00699036,
        0.01124013,
        0.01839484,
        0.10339749,
        0.06291994,
        0.0809066,
        0.01426128,
        0.06972489,
    ],
    dtype=np.float32,
)
_HEURISTIC_COEF = np.array(
    [
        [
            0.7837249,
            0.93344754,
            0.42543802,
            0.7237358,
            -1.3780493,
            0.28977036,
            -1.526411,
            -0.8113013,
            0.7215441,
            -1.365598,
            0.92858386,
            0.4791555,
            0.39428368,
            -2.0814576,
            1.3257246,
        ],
        [
            -0.31925902,
            -0.35177892,
            0.088963084,
            0.76565367,
            1.5321877,
            -0.9406647,
            0.025522968,
            -2.4236236,
            0.99557066,
            0.39046565,
            -0.21323189,
            -0.45534167,
            -0.32375878,
            0.041175682,
            -0.052707475,
        ],
        [
            0.9824139,
            -0.5772055,
            0.2865326,
            0.46952158,
            -1.4895474,
            -1.0201513,
            -0.038081307,
            0.760871,
            -0.6594932,
            1.3681073,
            -0.12613784,
            0.0041183545,
            0.050960504,
            0.7673419,
            -0.5947984,
        ],
        [
            -3.035346,
            0.0016550738,
            -1.4410601,
            -0.9171607,
            0.7708494,
            2.113644,
            -0.51639634,
            1.608844,
            -0.5849754,
            0.9642903,
            0.89687914,
            0.01585337,
            0.078373015,
            1.4720455,
            -0.91611063,
        ],
        [
            1.5884662,
            -0.006118249,
            0.6401264,
            -1.0417503,
            0.5645596,
            -0.44259834,
            2.0553658,
            0.8652098,
            -0.47264612,
            -1.3572654,
            -1.4860933,
            -0.043785576,
            -0.19985843,
            -0.19910555,
            0.23789188,
        ],
    ],
    dtype=np.float32,
)
_HEURISTIC_INTERCEPT = np.array(
    [-2.361347, 1.3459122, -0.1603909, -0.11723393, 1.2930595],
    dtype=np.float32,
)


class Stage2ArtifactContractError(RuntimeError):
    pass


@dataclass
class FibrosisPredictionResult:
    softmax_vector: dict[FibrosisStage, float]
    top1: tuple[FibrosisStage, float]
    top2: list[tuple[FibrosisStage, float]]
    confidence_flag: ConfidenceFlag
    escalation_flag: EscalationFlag
    model_version: str
    inference_mode: Literal["ml", "heuristic"]


class FibrosisModelRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        model_artifact_path: Path | None = None,
        model_version: str | None = None,
    ):
        self.settings = settings
        self.model_artifact_path = model_artifact_path or settings.model_artifact_path
        self.temperature_artifact_path = settings.temperature_artifact_path
        self._model = None
        self._torch = None
        self.model_version = model_version or "fibrosis-efficientnet-b3:v1"
        self._strict_mode = not self.settings.is_local_dev and self.settings.stage2_require_model_non_dev
        self._allow_heuristic_fallback = not self._strict_mode
        self._temperature = self._load_temperature()

    @staticmethod
    def _parse_temperature_artifact(path: Path) -> float:
        try:
            payload = json.loads(path.read_text())
        except Exception as exc:
            raise Stage2ArtifactContractError(
                f"Stage 2 temperature artifact is invalid JSON: {path}"
            ) from exc

        if not isinstance(payload, dict):
            raise Stage2ArtifactContractError(
                f"Stage 2 temperature artifact payload must be an object: {path}"
            )

        raw_temperature = payload.get("temperature", 1.0)
        try:
            temperature = float(raw_temperature)
        except (TypeError, ValueError) as exc:
            raise Stage2ArtifactContractError(
                f"Stage 2 temperature artifact has non-numeric temperature: {path}"
            ) from exc

        if not math.isfinite(temperature) or temperature <= 0:
            raise Stage2ArtifactContractError(
                f"Stage 2 temperature artifact must provide temperature > 0: {path}"
            )

        return temperature

    def _load_temperature(self) -> float:
        if self.temperature_artifact_path.exists():
            try:
                return self._parse_temperature_artifact(self.temperature_artifact_path)
            except Stage2ArtifactContractError as exc:
                if self._strict_mode:
                    raise RuntimeError(str(exc)) from exc
                return 1.0
        return 1.0

    def _lazy_load_model(self):
        if self._model is not None:
            return
        artifact = self.model_artifact_path
        if not artifact.exists():
            if not self._allow_heuristic_fallback:
                raise RuntimeError(f"Stage 2 model artifact is missing: {artifact}")
            self._model = False
            return
        try:
            import torch
            import torch.nn as nn
            from torchvision.models import efficientnet_b3

            model = efficientnet_b3(weights=None)
            in_features = model.classifier[-1].in_features
            model.classifier[-1] = nn.Linear(in_features, len(STAGES))
            state = torch.load(artifact, map_location="cpu")
            model.load_state_dict(state)
            model.eval()
            self._model = model
            self._torch = torch
        except Exception as exc:
            if not self._allow_heuristic_fallback:
                raise RuntimeError(f"Failed to load Stage 2 model artifact: {artifact}") from exc
            self._model = False

    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        with Image.open(BytesIO(image_bytes)) as img:
            img = img.convert("RGB").resize((384, 384))
            arr = np.asarray(img).astype(np.float32) / 255.0

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
        arr = np.transpose(arr, (2, 0, 1))
        return arr

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        logits = logits - np.max(logits)
        exps = np.exp(logits)
        return exps / np.sum(exps)

    def _heuristic_logits(self, arr: np.ndarray) -> np.ndarray:
        # Fallback uses ROI-aware handcrafted radiomics features plus a calibrated
        # lightweight multiclass linear head, so probabilities don't collapse.
        feat = self._extract_heuristic_features(arr)

        # Guardrail: if scan is nearly textureless, keep distribution in low stages.
        if feat[3] < 0.025 and feat[4] < 0.08 and feat[7] < 0.0045:
            return np.array([2.6, 1.6, 0.3, -0.5, -1.2], dtype=np.float32)

        standardized = np.clip(
            (feat - _HEURISTIC_FEATURE_MEAN) / _HEURISTIC_FEATURE_SCALE,
            -4.0,
            4.0,
        )
        logits = (_HEURISTIC_COEF @ standardized) + _HEURISTIC_INTERCEPT

        # Extra separation for texture-heavy and very dark-noisy edge cases.
        if feat[7] > 0.018 and feat[6] > 0.006 and feat[12] > 0.08:
            logits += np.array([-0.7, -0.5, 0.2, 0.8, 1.0], dtype=np.float32)
        if feat[14] > 0.94 and feat[13] < 0.003:
            logits += np.array([0.9, 0.4, -0.2, -0.4, -0.7], dtype=np.float32)

        return logits.astype(np.float32)

    def _extract_heuristic_features(self, arr: np.ndarray) -> np.ndarray:
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        rgb = np.transpose(arr, (1, 2, 0))
        rgb = np.clip((rgb * std) + mean, 0.0, 1.0)
        gray = (
            (0.2989 * rgb[:, :, 0])
            + (0.5870 * rgb[:, :, 1])
            + (0.1140 * rgb[:, :, 2])
        )

        # Crop to tissue-like foreground to avoid black border dominance.
        fg = gray > 0.04
        if np.count_nonzero(fg) < (gray.size * 0.02):
            fg = gray > 0.01
        ys, xs = np.where(fg)
        if ys.size and xs.size:
            gray = gray[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]

        percentiles = np.percentile(gray, [5, 10, 25, 50, 75, 90, 95]).astype(np.float32)
        _, p10, p25, p50, p75, p90, _ = [float(v) for v in percentiles]

        dyn_range = p90 - p10
        iqr = p75 - p25
        mean_intensity = float(np.mean(gray))
        std_intensity = float(np.std(gray))

        lap = (
            (-4.0 * gray)
            + np.roll(gray, 1, axis=0)
            + np.roll(gray, -1, axis=0)
            + np.roll(gray, 1, axis=1)
            + np.roll(gray, -1, axis=1)
        )
        lap_var = float(np.var(lap))

        blur = (
            gray
            + np.roll(gray, 1, axis=0)
            + np.roll(gray, -1, axis=0)
            + np.roll(gray, 1, axis=1)
            + np.roll(gray, -1, axis=1)
        ) / 5.0
        hf_energy = float(np.std(gray - blur))

        grad_x = np.diff(gray, axis=1, append=gray[:, -1:])
        grad_y = np.diff(gray, axis=0, append=gray[-1:, :])
        grad_mag = np.sqrt((grad_x * grad_x) + (grad_y * grad_y))
        grad_mean = float(np.mean(grad_mag))
        grad_std = float(np.std(grad_mag))
        grad_tail = float(np.mean(grad_mag > 0.03))

        h, w = gray.shape
        radius = max(8, min(h, w) // 4)
        cy, cx = h // 2, w // 2
        center = float(np.mean(gray[cy - radius : cy + radius, cx - radius : cx + radius]))
        periphery_mask = np.ones_like(gray, dtype=bool)
        periphery_mask[cy - radius : cy + radius, cx - radius : cx + radius] = False
        periphery = float(np.mean(gray[periphery_mask])) if np.any(periphery_mask) else center
        center_delta = center - periphery

        band = max(1, h // 3)
        depth_attenuation = float(np.mean(gray[:band, :]) - np.mean(gray[-band:, :]))
        high_echo_ratio = float(np.mean(gray > 0.72))
        low_echo_ratio = float(np.mean(gray < 0.28))

        return np.array(
            [
                mean_intensity,
                p50,
                p75,
                std_intensity,
                dyn_range,
                iqr,
                lap_var,
                hf_energy,
                grad_mean,
                grad_std,
                grad_tail,
                center_delta,
                depth_attenuation,
                high_echo_ratio,
                low_echo_ratio,
            ],
            dtype=np.float32,
        )

    def predict(self, image_bytes: bytes) -> FibrosisPredictionResult:
        if self._strict_mode:
            validate_stage2_artifacts(
                self.settings,
                model_artifact_path=self.model_artifact_path,
                temperature_artifact_path=self.temperature_artifact_path,
            )

        self._lazy_load_model()
        arr = self._preprocess(image_bytes)

        if self._model:
            inference_mode: Literal["ml", "heuristic"] = "ml"
            tensor = self._torch.from_numpy(arr).unsqueeze(0)
            with self._torch.no_grad():
                logits = self._model(tensor).cpu().numpy()[0]
        else:
            if not self._allow_heuristic_fallback:
                raise RuntimeError("Stage 2 ML model is unavailable and heuristic fallback is disabled")
            inference_mode = "heuristic"
            logits = self._heuristic_logits(arr)

        logits = logits / max(self._temperature, 1e-3)
        probs = self._softmax(logits)

        probs_map = {stage: round(float(probs[idx]), 6) for idx, stage in enumerate(STAGES)}
        ordered = sorted(probs_map.items(), key=lambda kv: kv[1], reverse=True)
        top1 = ordered[0]
        top2 = ordered[:2]

        confidence_flag = (
            ConfidenceFlag.LOW_CONFIDENCE if top1[1] < 0.60 else ConfidenceFlag.NORMAL
        )
        if inference_mode == "heuristic":
            # Heuristic is a dev-only placeholder; always treat as low confidence.
            confidence_flag = ConfidenceFlag.LOW_CONFIDENCE
        escalation_flag = (
            EscalationFlag.SEVERE_STAGE_REVIEW
            if top1[0] in {FibrosisStage.F3, FibrosisStage.F4} and top1[1] >= 0.65
            else EscalationFlag.NONE
        )

        return FibrosisPredictionResult(
            softmax_vector=probs_map,
            top1=top1,
            top2=top2,
            confidence_flag=confidence_flag,
            escalation_flag=escalation_flag,
            model_version=self.model_version if inference_mode == "ml" else f"{self.model_version}::heuristic",
            inference_mode=inference_mode,
        )


def fetch_scan_bytes(*, object_key: str, settings: Settings) -> bytes:
    s3 = boto3.client("s3", region_name=settings.aws_region)
    try:
        obj = s3.get_object(Bucket=settings.s3_upload_bucket, Key=object_key)
        return obj["Body"].read()
    except (BotoCoreError, ClientError):
        pass

    maybe_local = Path(object_key)
    if maybe_local.exists():
        return maybe_local.read_bytes()

    filename = maybe_local.name
    if filename:
        matches = list(settings.local_image_root.glob(f"F*/{filename}"))
        if matches:
            return matches[0].read_bytes()

    raise FileNotFoundError(f"Unable to load scan bytes for key: {object_key}")


def validate_stage2_artifacts(
    settings: Settings,
    *,
    model_artifact_path: Path | None = None,
    temperature_artifact_path: Path | None = None,
) -> None:
    strict_mode = not settings.is_local_dev and settings.stage2_require_model_non_dev
    if not strict_mode:
        return

    model_path = model_artifact_path or settings.model_artifact_path
    temperature_path = temperature_artifact_path or settings.temperature_artifact_path
    errors = inspect_stage2_artifact_contract(
        model_artifact_path=model_path,
        temperature_artifact_path=temperature_path,
    )

    if errors:
        raise Stage2ArtifactContractError(
            "Stage 2 artifact contract check failed: " + "; ".join(errors)
        )


def inspect_stage2_artifact_contract(
    *,
    model_artifact_path: Path,
    temperature_artifact_path: Path,
) -> list[str]:
    errors: list[str] = []

    if not model_artifact_path.exists():
        errors.append(f"missing model artifact: {model_artifact_path}")
    elif not model_artifact_path.is_file():
        errors.append(f"model artifact path is not a file: {model_artifact_path}")

    if not temperature_artifact_path.exists():
        errors.append(f"missing temperature artifact: {temperature_artifact_path}")
    else:
        try:
            FibrosisModelRuntime._parse_temperature_artifact(temperature_artifact_path)
        except Stage2ArtifactContractError as exc:
            errors.append(str(exc))

    return errors

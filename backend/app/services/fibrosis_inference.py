from __future__ import annotations

import json
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import boto3
import numpy as np
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image

from app.core.config import Settings
from app.core.enums import ConfidenceFlag, EscalationFlag, FibrosisStage

STAGES = [FibrosisStage.F0, FibrosisStage.F1, FibrosisStage.F2, FibrosisStage.F3, FibrosisStage.F4]


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
        # Heuristic fallback keeps endpoint usable if model artifact is not yet available.
        rgb = np.transpose(arr, (1, 2, 0))
        brightness = float(rgb.mean())
        texture = float(np.var(rgb))

        base = np.array([
            1.2 - abs(brightness - 0.10) * 2.5,
            1.0 - abs(brightness - 0.05) * 2.0,
            0.9 + texture * 1.5,
            0.8 + texture * 1.8,
            0.7 + texture * 2.2,
        ])
        return base

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
            tensor = self._torch.from_numpy(arr).unsqueeze(0)
            with self._torch.no_grad():
                logits = self._model(tensor).cpu().numpy()[0]
        else:
            if not self._allow_heuristic_fallback:
                raise RuntimeError("Stage 2 ML model is unavailable and heuristic fallback is disabled")
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
            model_version=self.model_version,
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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register Stage 3 model artifacts in model_registry")
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("/Users/praty/hepatica-p/ml/artifacts/stage3"),
    )
    parser.add_argument("--activate", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:
        raise SystemExit("SQLAlchemy is required for registration.") from exc

    artifact_dir = args.artifact_dir
    metadata_path = artifact_dir / "stage3_run_metadata.json"
    val_metrics_path = artifact_dir / "stage3_metrics_val.json"
    test_metrics_path = artifact_dir / "stage3_metrics_test.json"
    thresholds_path = artifact_dir / "stage3_thresholds.json"

    required = [metadata_path, val_metrics_path, test_metrics_path, thresholds_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing Stage 3 artifacts: " + ", ".join(missing))

    metadata = json.loads(metadata_path.read_text())
    val_metrics = json.loads(val_metrics_path.read_text())
    test_metrics = json.loads(test_metrics_path.read_text())
    thresholds = json.loads(thresholds_path.read_text())

    model_name = str(metadata.get("model_name", "multimodal-stage3-risk"))
    model_version = str(metadata.get("model_version", "v1"))
    payload = {
        "run_metadata": metadata,
        "validation": val_metrics,
        "test": test_metrics,
        "thresholds": thresholds,
    }

    record = {
        "id": str(uuid.uuid4()),
        "name": model_name,
        "version": model_version,
        "artifact_uri": str(artifact_dir),
        "metrics": json.dumps(payload),
        "is_active": bool(args.activate),
        "created_at": datetime.now(timezone.utc),
    }

    engine = create_engine(args.database_url)
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            insert_sql = text(
                """
                INSERT INTO model_registry (id, name, version, artifact_uri, metrics, is_active, created_at)
                VALUES (:id, :name, :version, :artifact_uri, CAST(:metrics AS JSON), :is_active, :created_at)
                """
            )
        else:
            insert_sql = text(
                """
                INSERT INTO model_registry (id, name, version, artifact_uri, metrics, is_active, created_at)
                VALUES (:id, :name, :version, :artifact_uri, :metrics, :is_active, :created_at)
                """
            )
        conn.execute(insert_sql, record)

    print(
        json.dumps(
            {
                "registered": True,
                "name": model_name,
                "version": model_version,
                "artifact_uri": str(artifact_dir),
                "is_active": bool(args.activate),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

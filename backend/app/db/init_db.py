from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db.models import ModelRegistry
from app.db.session import engine


DEFAULT_MODELS = [
    {
        "name": "clinical-stage1-gbdt",
        "version": "v1",
        "artifact_uri": "file:///app/ml/artifacts/stage1",
        "metrics": {"type": "ml", "task": "risk_tier_and_probability"},
    },
    {
        "name": "clinical-rule-engine",
        "version": "v1",
        "artifact_uri": "builtin://clinical-rule-engine/v1",
        "metrics": {"type": "rules"},
    },
    {
        "name": "fibrosis-efficientnet-b3",
        "version": "v1",
        "artifact_uri": "file:///app/ml/artifacts/fibrosis_model.pt",
        "metrics": {"type": "ml", "task": "fibrosis_stage"},
    },
]


def init_db() -> None:
    try:
        with Session(engine) as db:
            for record in DEFAULT_MODELS:
                existing = db.scalar(
                    select(ModelRegistry).where(
                        ModelRegistry.name == record["name"],
                        ModelRegistry.version == record["version"],
                    )
                )
                if existing:
                    existing.artifact_uri = record["artifact_uri"]
                    existing.metrics = record["metrics"]
                    existing.is_active = True
                    continue
                db.add(ModelRegistry(**record))
            db.commit()
    except (OperationalError, ProgrammingError) as exc:
        raise RuntimeError(
            "Database schema is missing. Run `alembic upgrade head` before starting the API."
        ) from exc


if __name__ == "__main__":
    init_db()

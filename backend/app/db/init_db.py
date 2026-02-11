from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
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
    {
        "name": "multimodal-stage3-risk",
        "version": "v1",
        "artifact_uri": "file:///app/ml/artifacts/stage3",
        "metrics": {"type": "ml", "task": "multimodal_non_invasive_risk"},
    },
]


def _seed_defaults(db: Session) -> None:
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


def init_db() -> None:
    cfg = get_settings()
    try:
        with Session(engine) as db:
            _seed_defaults(db)
            db.commit()
    except (OperationalError, ProgrammingError) as exc:
        # Local demo mode: if the DB hasn't been migrated yet, create tables so the app can boot.
        # In non-dev, keep the stricter behavior to avoid silently running with an unintended schema.
        if cfg.is_local_dev and str(cfg.database_url).startswith("sqlite"):
            Base.metadata.create_all(bind=engine)
            with Session(engine) as db:
                _seed_defaults(db)
                db.commit()
            return
        raise RuntimeError(
            "Database schema is missing. Run `alembic upgrade head` before starting the API."
        ) from exc


if __name__ == "__main__":
    init_db()

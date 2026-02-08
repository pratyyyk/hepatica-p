from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db.models import ModelRegistry
from app.db.session import engine


DEFAULT_MODELS = [
    {
        "name": "clinical-rule-engine",
        "version": "v1",
        "artifact_uri": "builtin://clinical-rule-engine/v1",
        "metrics": {"type": "rules"},
    },
    {
        "name": "fibrosis-efficientnet-b3",
        "version": "v1",
        "artifact_uri": "s3://hepatica-models/fibrosis/v1/model.pt",
        "metrics": {},
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
                    continue
                db.add(ModelRegistry(**record))
            db.commit()
    except (OperationalError, ProgrammingError) as exc:
        raise RuntimeError(
            "Database schema is missing. Run `alembic upgrade head` before starting the API."
        ) from exc


if __name__ == "__main__":
    init_db()

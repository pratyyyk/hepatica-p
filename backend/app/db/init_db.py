from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
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
    Base.metadata.create_all(bind=engine)
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


if __name__ == "__main__":
    init_db()

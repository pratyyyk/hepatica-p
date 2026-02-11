from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ModelRegistry
from app.db.session import engine


def test_default_model_registry_rows_seeded(client):
    with Session(engine) as db:
        rows = db.scalars(select(ModelRegistry).where(ModelRegistry.is_active.is_(True))).all()

    indexed = {(row.name, row.version): row for row in rows}

    assert ("clinical-stage1-gbdt", "v1") in indexed
    assert (
        indexed[("clinical-stage1-gbdt", "v1")].artifact_uri
        == "file:///app/ml/artifacts/stage1"
    )

    assert ("fibrosis-efficientnet-b3", "v1") in indexed
    assert (
        indexed[("fibrosis-efficientnet-b3", "v1")].artifact_uri
        == "file:///app/ml/artifacts/fibrosis_model.pt"
    )

    assert ("multimodal-stage3-risk", "v1") in indexed
    assert (
        indexed[("multimodal-stage3-risk", "v1")].artifact_uri
        == "file:///app/ml/artifacts/stage3"
    )

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ModelRegistry
from app.db.session import engine
from app.services.model_registry_admin import (
    ModelPromotionError,
    activate_model_version,
    deactivate_model_version,
    list_models,
)


def _seed_model(name: str, version: str, active: bool) -> str:
    with Session(engine) as db:
        row = ModelRegistry(
            name=name,
            version=version,
            artifact_uri=f"file:///tmp/{name}/{version}",
            metrics={},
            is_active=active,
        )
        db.add(row)
        db.commit()
        return row.id


def test_activate_model_version_exclusive_deactivates_others():
    _seed_model("clinical-stage1-gbdt", "v1", True)
    _seed_model("clinical-stage1-gbdt", "v2", False)
    _seed_model("clinical-stage1-gbdt", "v3", True)

    with Session(engine) as db:
        result = activate_model_version(
            db,
            name="clinical-stage1-gbdt",
            version="v2",
            exclusive=True,
        )
        db.commit()
        rows = list_models(db, name="clinical-stage1-gbdt")

    assert result.changed is True
    assert set(result.deactivated_versions) == {"v1", "v3"}
    assert set(result.active_versions) == {"v2"}
    assert {row.version for row in rows if row.is_active} == {"v2"}


def test_activate_model_version_keep_others_active():
    _seed_model("fibrosis-efficientnet-b3", "v1", True)
    _seed_model("fibrosis-efficientnet-b3", "v2", False)

    with Session(engine) as db:
        result = activate_model_version(
            db,
            name="fibrosis-efficientnet-b3",
            version="v2",
            exclusive=False,
        )
        db.commit()
        rows = list_models(db, name="fibrosis-efficientnet-b3")

    assert result.changed is True
    assert result.deactivated_versions == []
    assert {row.version for row in rows if row.is_active} == {"v1", "v2"}


def test_deactivate_model_version_blocks_last_active():
    _seed_model("clinical-stage1-gbdt", "v1", True)

    with Session(engine) as db:
        with pytest.raises(ModelPromotionError, match="last active version"):
            deactivate_model_version(
                db,
                name="clinical-stage1-gbdt",
                version="v1",
                allow_zero_active=False,
            )


def test_deactivate_model_version_allow_zero_active():
    _seed_model("clinical-stage1-gbdt", "v1", True)

    with Session(engine) as db:
        result = deactivate_model_version(
            db,
            name="clinical-stage1-gbdt",
            version="v1",
            allow_zero_active=True,
        )
        db.commit()
        rows = list(
            db.scalars(
                select(ModelRegistry).where(
                    ModelRegistry.name == "clinical-stage1-gbdt",
                )
            ).all()
        )

    assert result.changed is True
    assert result.active_versions == []
    assert all(not row.is_active for row in rows)

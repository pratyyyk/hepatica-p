#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.model_registry_admin import (
    ModelPromotionError,
    activate_model_version,
    deactivate_model_version,
    list_models,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage model_registry activation safely.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL (defaults to backend settings).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List model_registry rows.")
    list_parser.add_argument("--name", default=None, help="Filter by model name.")

    activate_parser = subparsers.add_parser("activate", help="Activate a model version.")
    activate_parser.add_argument("--name", required=True)
    activate_parser.add_argument("--version", required=True)
    activate_parser.add_argument(
        "--keep-others-active",
        action="store_true",
        help="Do not deactivate other active versions for the same model name.",
    )

    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate a model version.")
    deactivate_parser.add_argument("--name", required=True)
    deactivate_parser.add_argument("--version", required=True)
    deactivate_parser.add_argument(
        "--allow-zero-active",
        action="store_true",
        help="Allow deactivating the last active version for a model name.",
    )

    return parser


def _render(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    print(json.dumps(data, indent=2))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    engine = create_engine(db_url, future=True)

    try:
        with Session(engine) as db:
            if args.command == "list":
                rows = list_models(db, name=args.name)
                payload = {
                    "count": len(rows),
                    "models": [
                        {
                            "id": row.id,
                            "name": row.name,
                            "version": row.version,
                            "artifact_uri": row.artifact_uri,
                            "is_active": bool(row.is_active),
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                        }
                        for row in rows
                    ],
                }
                _render(payload, args.json)
                return 0

            if args.command == "activate":
                result = activate_model_version(
                    db,
                    name=args.name,
                    version=args.version,
                    exclusive=not args.keep_others_active,
                )
                db.commit()
                payload = {
                    "ok": True,
                    "action": result.action,
                    "name": result.name,
                    "version": result.version,
                    "changed": result.changed,
                    "deactivated_versions": result.deactivated_versions,
                    "active_versions": result.active_versions,
                }
                _render(payload, args.json)
                return 0

            if args.command == "deactivate":
                result = deactivate_model_version(
                    db,
                    name=args.name,
                    version=args.version,
                    allow_zero_active=args.allow_zero_active,
                )
                db.commit()
                payload = {
                    "ok": True,
                    "action": result.action,
                    "name": result.name,
                    "version": result.version,
                    "changed": result.changed,
                    "active_versions": result.active_versions,
                }
                _render(payload, args.json)
                return 0
    except ModelPromotionError as exc:
        _render({"ok": False, "error": str(exc)}, True)
        return 2

    parser.error(f"Unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

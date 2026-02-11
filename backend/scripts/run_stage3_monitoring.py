#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.db.session import engine
from app.services.stage3_monitoring import run_scheduled_stage3_monitoring


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled Stage 3 monitoring batch.")
    parser.add_argument("--dry-run", action="store_true", help="Run and roll back DB changes.")
    parser.add_argument("--performed-by", default=None, help="Optional user id to attribute generated records.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = get_settings()

    with Session(engine) as db:
        payload = run_scheduled_stage3_monitoring(
            db=db,
            cfg=cfg,
            performed_by=args.performed_by,
        )
        if args.dry_run:
            db.rollback()
            payload["dry_run"] = True
        else:
            db.commit()

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

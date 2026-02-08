from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.knowledge import ingest_journals


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        stats = ingest_journals(db=db, settings=settings)
    print(f"Ingest complete: docs={stats['docs']} chunks={stats['chunks']}")


if __name__ == "__main__":
    main()

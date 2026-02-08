from sqlalchemy import JSON
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeDecorator


class EmbeddingVector(TypeDecorator):
    """Vector on Postgres (pgvector), JSON everywhere else."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = 1536, **kwargs):
        super().__init__(**kwargs)
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector

                return dialect.type_descriptor(Vector(self.dimensions))
            except Exception:
                return dialect.type_descriptor(postgresql.ARRAY(postgresql.DOUBLE_PRECISION))
        return dialect.type_descriptor(JSON())

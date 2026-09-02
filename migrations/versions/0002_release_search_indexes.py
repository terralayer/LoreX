from __future__ import annotations

from alembic import op

revision = "0002_release_search_indexes"
down_revision = "0001_postgres_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_releases_normalized_title_trgm "
        "ON releases USING gin (normalized_title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_releases_normalized_author_trgm "
        "ON releases USING gin (normalized_author gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_releases_narrator_trgm "
        "ON releases USING gin (narrator gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_releases_source_subject_trgm "
        "ON releases USING gin (source_subject gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_releases_source_subject_trgm", table_name="releases")
    op.drop_index("ix_releases_narrator_trgm", table_name="releases")
    op.drop_index("ix_releases_normalized_author_trgm", table_name="releases")
    op.drop_index("ix_releases_normalized_title_trgm", table_name="releases")
    # Leave pg_trgm installed: other database objects may legitimately depend on it.

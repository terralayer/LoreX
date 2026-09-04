from __future__ import annotations

from alembic import op

revision = "0005_library_read_indexes"
down_revision = "0004_import_pipeline_efficiency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deterministic keyset-friendly ordering for each public library sort.
    op.execute("CREATE INDEX ix_library_books_title_id ON library_books (title, id)")
    op.execute("CREATE INDEX ix_library_books_author_id ON library_books (author, id)")
    op.execute("CREATE INDEX ix_library_books_narrator_id ON library_books (narrator, id)")
    op.execute("CREATE INDEX ix_library_books_format_id ON library_books (format, id)")
    op.execute("CREATE INDEX ix_library_books_size_id ON library_books (size, id)")

    # pg_trgm is installed by migration 0002. These indexes support the
    # contains-style title/author/narrator filters exposed by the UI API.
    op.execute(
        "CREATE INDEX ix_library_books_title_trgm "
        "ON library_books USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_library_books_author_trgm "
        "ON library_books USING gin (author gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_library_books_narrator_trgm "
        "ON library_books USING gin (narrator gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_library_books_narrator_trgm", table_name="library_books")
    op.drop_index("ix_library_books_author_trgm", table_name="library_books")
    op.drop_index("ix_library_books_title_trgm", table_name="library_books")
    op.drop_index("ix_library_books_size_id", table_name="library_books")
    op.drop_index("ix_library_books_format_id", table_name="library_books")
    op.drop_index("ix_library_books_narrator_id", table_name="library_books")
    op.drop_index("ix_library_books_author_id", table_name="library_books")
    op.drop_index("ix_library_books_title_id", table_name="library_books")

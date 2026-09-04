from __future__ import annotations

from alembic import op

revision = "0005_library_read_efficiency"
down_revision = "0004_import_pipeline_efficiency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_library_books_author_title_id",
        "library_books",
        ["author", "title", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_library_books_author_title_id", table_name="library_books")

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_postgres_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "releases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("normalized_author", sa.Text(), nullable=False),
        sa.Column("narrator", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("completion", sa.Float(), nullable=False, server_default="1"),
        sa.Column("source_subject", sa.Text(), nullable=False),
        sa.Column("nzb", sa.Text(), nullable=False, server_default=""),
        sa.Column("isbn10", sa.String(length=10), nullable=True),
        sa.Column("isbn13", sa.String(length=13), nullable=True),
        sa.Column("asin", sa.String(length=16), nullable=True),
        sa.Column("series", sa.Text(), nullable=True),
        sa.Column("series_position", sa.Numeric(8, 3), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("wanted_key", sa.Text(), nullable=True),
        sa.Column("download_status", sa.String(length=32), nullable=True),
        sa.Column("import_status", sa.String(length=32), nullable=True),
        sa.UniqueConstraint("fingerprint", name="ux_releases_fingerprint"),
    )
    op.create_index("ix_releases_normalized_title", "releases", ["normalized_title"])
    op.create_index("ix_releases_normalized_author", "releases", ["normalized_author"])
    op.create_index("ix_releases_narrator", "releases", ["narrator"])
    op.create_index("ix_releases_isbn10", "releases", ["isbn10"])
    op.create_index("ix_releases_isbn13", "releases", ["isbn13"])
    op.create_index("ix_releases_asin", "releases", ["asin"])
    op.create_index("ix_releases_series_position", "releases", ["series", "series_position"])
    op.create_index("ix_releases_posted_at", "releases", ["posted_at"])
    op.create_index("ix_releases_wanted_match", "releases", ["wanted_key"])
    op.create_index("ix_releases_download_status", "releases", ["download_status"])
    op.create_index("ix_releases_import_status", "releases", ["import_status"])

    op.create_table(
        "release_articles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("release_id", sa.String(length=64), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("group", sa.Text(), nullable=False),
        sa.UniqueConstraint("message_id", name="ux_release_articles_message_id"),
    )
    op.create_index("ix_release_articles_release_id", "release_articles", ["release_id"])

    op.create_table(
        "indexer_checkpoints",
        sa.Column("source", sa.String(length=32), primary_key=True),
        sa.Column("group", sa.Text(), primary_key=True),
        sa.Column("article_number", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "library_books",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("release_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("narrator", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
    )

    op.create_table(
        "download_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("release_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("created_order", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_download_jobs_status", "download_jobs", ["status", "created_order"])

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("release_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_table("import_jobs")
    op.drop_index("ix_download_jobs_status", table_name="download_jobs")
    op.drop_table("download_jobs")
    op.drop_table("library_books")
    op.drop_table("indexer_checkpoints")
    op.drop_index("ix_release_articles_release_id", table_name="release_articles")
    op.drop_table("release_articles")
    op.drop_index("ix_releases_import_status", table_name="releases")
    op.drop_index("ix_releases_download_status", table_name="releases")
    op.drop_index("ix_releases_wanted_match", table_name="releases")
    op.drop_index("ix_releases_posted_at", table_name="releases")
    op.drop_index("ix_releases_series_position", table_name="releases")
    op.drop_index("ix_releases_asin", table_name="releases")
    op.drop_index("ix_releases_isbn13", table_name="releases")
    op.drop_index("ix_releases_isbn10", table_name="releases")
    op.drop_index("ix_releases_narrator", table_name="releases")
    op.drop_index("ix_releases_normalized_author", table_name="releases")
    op.drop_index("ix_releases_normalized_title", table_name="releases")
    op.drop_table("releases")

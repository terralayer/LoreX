from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_download_queue_efficiency"
down_revision = "0002_release_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("download_jobs", sa.Column("claimed_by", sa.String(length=128), nullable=True))
    op.add_column(
        "download_jobs",
        sa.Column("bytes_completed", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "download_jobs",
        sa.Column("articles_completed", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "download_jobs",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "download_articles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("download_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("bytes_completed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("provider", sa.String(length=128), nullable=True),
        sa.Column("attempts", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_order", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "message_id", name="ux_download_articles_job_message"),
    )
    op.create_index(
        "ix_download_articles_job_status",
        "download_articles",
        ["job_id", "status", "created_order"],
    )

    op.create_table(
        "provider_health",
        sa.Column("provider", sa.String(length=128), primary_key=True),
        sa.Column("attempts", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("successes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failures", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fallbacks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_delivered", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("elapsed_ms_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("provider_health")
    op.drop_index("ix_download_articles_job_status", table_name="download_articles")
    op.drop_table("download_articles")
    op.drop_column("download_jobs", "updated_at")
    op.drop_column("download_jobs", "articles_completed")
    op.drop_column("download_jobs", "bytes_completed")
    op.drop_column("download_jobs", "claimed_by")
    op.drop_column("download_jobs", "claimed_at")

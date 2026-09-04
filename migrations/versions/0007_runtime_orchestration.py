from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_runtime_orchestration"
down_revision = "0006_live_nntp_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scanner_group_state",
        sa.Column(
            "provider_id",
            sa.String(length=32),
            sa.ForeignKey("nntp_providers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("group_name", sa.Text(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_scanned_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_indexed_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scanner_group_state_status", "scanner_group_state", ["status", "updated_at"])

    op.create_table(
        "runtime_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "activity_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_activity_events_created_at", "activity_events", ["created_at"])

    op.add_column("download_jobs", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "download_jobs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("download_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("download_jobs", "completed_at")
    op.drop_column("download_jobs", "cancel_requested")
    op.drop_column("download_jobs", "error")

    op.drop_index("ix_activity_events_created_at", table_name="activity_events")
    op.drop_table("activity_events")
    op.drop_table("runtime_settings")
    op.drop_index("ix_scanner_group_state_status", table_name="scanner_group_state")
    op.drop_table("scanner_group_state")

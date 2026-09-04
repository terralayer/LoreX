from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_live_nntp_providers"
down_revision = "0005_library_read_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nntp_providers",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="563"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("fill_server", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_connections", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("username_encrypted", sa.Text(), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="ux_nntp_providers_name"),
    )
    op.create_table(
        "nntp_provider_groups",
        sa.Column(
            "provider_id",
            sa.String(length=32),
            sa.ForeignKey("nntp_providers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("group_name_normalized", sa.Text(), primary_key=True),
        sa.Column("group_name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scan_batch_size", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column("backfill_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_nntp_provider_groups_enabled", "nntp_provider_groups", ["provider_id", "enabled"])


def downgrade() -> None:
    op.drop_index("ix_nntp_provider_groups_enabled", table_name="nntp_provider_groups")
    op.drop_table("nntp_provider_groups")
    op.drop_table("nntp_providers")

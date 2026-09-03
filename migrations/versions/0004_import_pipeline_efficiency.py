from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_import_pipeline_efficiency"
down_revision = "0003_download_queue_efficiency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.add_column("import_jobs", sa.Column("source_path", sa.Text(), nullable=False, server_default=""))
    op.add_column("import_jobs", sa.Column("staging_path", sa.Text(), nullable=True))
    op.add_column("import_jobs", sa.Column("final_path", sa.Text(), nullable=True))
    op.add_column("import_jobs", sa.Column("stage", sa.String(length=32), nullable=False, server_default="verify"))
    op.add_column("import_jobs", sa.Column("created_order", sa.BigInteger(), sa.Identity(), nullable=False))
    op.add_column("import_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("import_jobs", sa.Column("claimed_by", sa.String(length=128), nullable=True))
    op.add_column("import_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("import_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("import_jobs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("import_jobs", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("import_jobs", sa.Column("wall_ms", sa.Float(), nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("cpu_ms", sa.Float(), nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("temp_bytes_peak", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("bytes_copied", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_index("ix_import_jobs_status_created", "import_jobs", ["status", "created_order"])


def downgrade() -> None:
    op.drop_index("ix_import_jobs_status_created", table_name="import_jobs")
    for column in [
        "bytes_copied", "temp_bytes_peak", "cpu_ms", "wall_ms", "error", "updated_at",
        "completed_at", "started_at", "claimed_by", "claimed_at", "created_order",
        "stage", "final_path", "staging_path", "source_path",
    ]:
        op.drop_column("import_jobs", column)
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])

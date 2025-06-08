"""Initial migration

Revision ID: 20240315_initial
Revises:
Create Date: 2024-03-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20240315_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tasks table
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB),
        sa.Column("execution_plan_id", sa.String(36)),
        sa.Column(
            "saga_state", sa.String(50), nullable=False, server_default="NOT_STARTED"
        ),
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("priority", sa.Integer(), server_default="1"),
    )

    # Create indexes for tasks
    op.create_index("idx_tasks_user_id", "tasks", ["user_id"])
    op.create_index("idx_tasks_status", "tasks", ["status"])
    op.create_index("idx_tasks_created_at", "tasks", ["created_at"])
    op.create_index("idx_tasks_priority", "tasks", ["priority"])

    # Create task history table
    op.create_table(
        "task_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id", sa.String(36), sa.ForeignKey("tasks.task_id"), nullable=False
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("details", postgresql.JSONB),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Create indexes for task history
    op.create_index("idx_task_history_task_id", "task_history", ["task_id"])
    op.create_index("idx_task_history_created_at", "task_history", ["created_at"])


def downgrade() -> None:
    # Drop task history table and its indexes
    op.drop_index("idx_task_history_created_at", table_name="task_history")
    op.drop_index("idx_task_history_task_id", table_name="task_history")
    op.drop_table("task_history")

    # Drop tasks table and its indexes
    op.drop_index("idx_tasks_priority", table_name="tasks")
    op.drop_index("idx_tasks_created_at", table_name="tasks")
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.drop_index("idx_tasks_user_id", table_name="tasks")
    op.drop_table("tasks")

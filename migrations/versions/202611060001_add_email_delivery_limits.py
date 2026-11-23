"""add email delivery status and rate limits

Revision ID: 202611060001
Revises: 518d48bc11de
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202611060001"
down_revision: Union[str, Sequence[str], None] = "518d48bc11de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column(
            "customer_email_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "notification_email_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.alter_column(
        "proposals",
        "customer_email_sent",
        existing_type=sa.Boolean(),
        server_default=sa.text("0"),
    )
    op.alter_column(
        "proposals",
        "notification_email_sent",
        existing_type=sa.Boolean(),
        server_default=sa.text("0"),
    )
    op.create_table(
        "email_rate_limits",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key_hash"),
    )


def downgrade() -> None:
    op.drop_table("email_rate_limits")
    op.drop_column("proposals", "notification_email_sent")
    op.drop_column("proposals", "customer_email_sent")

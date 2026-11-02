"""create proposals table

Revision ID: 518d48bc11de
Revises: 
Create Date: 2026-11-02 11:36:32.452262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '518d48bc11de'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'proposals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('proposal_id', sa.String(length=36), nullable=False),
        sa.Column('user_name', sa.String(length=150), nullable=False),
        sa.Column('user_email', sa.String(length=255), nullable=False),
        sa.Column('car_name', sa.String(length=150), nullable=False),
        sa.Column('offered_value', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('date_offer', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('proposal_id')
    )


def downgrade() -> None:
    op.drop_table('proposals')

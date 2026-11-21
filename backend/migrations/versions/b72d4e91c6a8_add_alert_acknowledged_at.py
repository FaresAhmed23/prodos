"""add alert acknowledged_at

Revision ID: b72d4e91c6a8
Revises: e4f1b7c92a03
Create Date: 2026-11-21 10:00:00.000000

F-22: the timestamp the response ratio needs. Nullable, no backfill — null
means "not acknowledged" and historical rows score as unacked by design.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b72d4e91c6a8'
down_revision = 'e4f1b7c92a03'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'alerts',
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # SQLite 3.35+ supports DROP COLUMN; Python 3.12 bundles a newer one.
    op.drop_column('alerts', 'acknowledged_at')

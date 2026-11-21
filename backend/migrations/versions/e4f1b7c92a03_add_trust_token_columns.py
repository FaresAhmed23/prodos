"""add trust token columns to site_profile

Revision ID: e4f1b7c92a03
Revises: c7e2a4d91b06
Create Date: 2026-11-21 09:00:00.000000

F-21 (spec §3): one nullable token per site plus its enroll/rotate stamps.
Nullable on purpose — an existing site is simply not enrolled. The unique
constraint is what makes token lookup unambiguous; NULLs stay unconstrained.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f1b7c92a03'
down_revision = 'c7e2a4d91b06'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('site_profile') as batch_op:
        batch_op.add_column(sa.Column('trust_token', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('trust_token_created_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('trust_token_rotated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint('uq_site_profile_trust_token', ['trust_token'])


def downgrade() -> None:
    with op.batch_alter_table('site_profile') as batch_op:
        batch_op.drop_constraint('uq_site_profile_trust_token', type_='unique')
        batch_op.drop_column('trust_token_rotated_at')
        batch_op.drop_column('trust_token_created_at')
        batch_op.drop_column('trust_token')

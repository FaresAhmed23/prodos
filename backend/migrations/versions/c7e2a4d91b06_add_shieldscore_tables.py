"""add shieldscore tables

Revision ID: c7e2a4d91b06
Revises: 9d3c1a7b4e20
Create Date: 2026-11-20 16:00:00.000000

F-19 foundation: `score_snapshots` and `checklist_answers` only. New tables, so
no existing row can be blocked by a non-null column. Do not edit earlier
revisions.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7e2a4d91b06'
down_revision = '9d3c1a7b4e20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'score_snapshots',
        sa.Column(
            'id',
            sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('score', sa.SmallInteger(), nullable=False),
        sa.Column('band', sa.String(length=32), nullable=False),
        sa.Column('components', sa.JSON(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('window_days', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id'], ['site_profile.site_id'],
            name='fk_score_snapshots_site_id_site_profile',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_score_snapshots_site_id_computed_at',
        'score_snapshots',
        ['site_id', 'computed_at'],
        unique=False,
    )
    op.create_table(
        'checklist_answers',
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('answers', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id'], ['site_profile.site_id'],
            name='fk_checklist_answers_site_id_site_profile',
        ),
        sa.PrimaryKeyConstraint('site_id'),
    )


def downgrade() -> None:
    op.drop_table('checklist_answers')
    op.drop_index(
        'ix_score_snapshots_site_id_computed_at',
        table_name='score_snapshots',
    )
    op.drop_table('score_snapshots')

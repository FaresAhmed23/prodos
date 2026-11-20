"""sync site, incident and AI metadata models

Revision ID: 9d3c1a7b4e20
Revises: bfd1100cc262
Create Date: 2026-11-20 12:00:00.000000

Hand-written to match the models exactly: `site_profile`, `incidents`, and the
nullable metadata columns added after F-9. Every added column is nullable, so a
metadata field can never fail an existing row (or an alert insert).

Do not edit bfd1100cc262. It is the base stamped by existing databases.
"""
from alembic import op
import sqlalchemy as sa


revision = '9d3c1a7b4e20'
down_revision = 'bfd1100cc262'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'site_profile',
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('business_name', sa.String(length=200), nullable=True),
        sa.Column('business_type', sa.String(length=64), nullable=True),
        sa.Column('wifi_ssids', sa.JSON(), nullable=False),
        sa.Column('known_access_points', sa.JSON(), nullable=False),
        sa.Column('router_model', sa.String(length=100), nullable=True),
        sa.Column('primary_language', sa.String(length=8), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('site_id'),
    )
    op.create_table(
        'incidents',
        sa.Column('incident_id', sa.String(length=36), nullable=False),
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('incident_key', sa.String(length=200), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_count', sa.Integer(), nullable=False),
        sa.Column('max_severity', sa.SmallInteger(), nullable=False),
        sa.Column('max_confidence', sa.Float(), nullable=False),
        sa.Column('sensor_ids', sa.JSON(), nullable=False),
        sa.Column('explained_alert_id', sa.String(length=36), nullable=True),
        sa.Column('explained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('explained_lang', sa.String(length=8), nullable=True),
        sa.Column('explained_severity', sa.SmallInteger(), nullable=True),
        sa.Column('explained_event_count', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['site_id'], ['site_profile.site_id'],
            name='fk_incidents_site_id_site_profile',
        ),
        sa.ForeignKeyConstraint(
            ['explained_alert_id'], ['alerts.alert_id'],
            name='fk_incidents_explained_alert_id_alerts',
        ),
        sa.PrimaryKeyConstraint('incident_id'),
    )
    op.create_index(
        'ix_incidents_site_key_last',
        'incidents',
        ['site_id', 'incident_key', 'last_seen_at'],
        unique=False,
    )

    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lang', sa.String(length=8), nullable=True))

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('incident_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_events_incident_id_incidents',
            'incidents', ['incident_id'], ['incident_id'],
        )

    with op.batch_alter_table('explanation_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lang', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('site_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('latency_ms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('fallback_reason', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('attempts', sa.SmallInteger(), nullable=True))
        batch_op.create_foreign_key(
            'fk_explanation_logs_site_id_site_profile',
            'site_profile', ['site_id'], ['site_id'],
        )

    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('site_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            'fk_sensors_site_id_site_profile',
            'site_profile', ['site_id'], ['site_id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sensors_site_id_site_profile', type_='foreignkey')
        batch_op.drop_column('site_id')

    with op.batch_alter_table('explanation_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_explanation_logs_site_id_site_profile', type_='foreignkey')
        batch_op.drop_column('attempts')
        batch_op.drop_column('fallback_reason')
        batch_op.drop_column('latency_ms')
        batch_op.drop_column('site_id')
        batch_op.drop_column('lang')

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_constraint('fk_events_incident_id_incidents', type_='foreignkey')
        batch_op.drop_column('incident_id')

    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_column('lang')

    op.drop_index('ix_incidents_site_key_last', table_name='incidents')
    op.drop_table('incidents')
    op.drop_table('site_profile')

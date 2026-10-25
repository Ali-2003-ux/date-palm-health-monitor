"""Create users, palm trees and inspection logs.

Revision ID: 11ceb747c89a
Revises:
Create Date: 2026-10-25 00:23:55.476691

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '11ceb747c89a'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.Enum('farmer', 'agronomist', 'admin', name='user_role'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('palm_trees',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('tree_code', sa.String(length=64), nullable=False),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('field_name', sa.String(length=120), nullable=True),
    sa.Column('variety', sa.String(length=80), nullable=True),
    sa.Column('location_metadata', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
    sa.Column('planted_on', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('latitude BETWEEN -90 AND 90', name=op.f('ck_palm_trees_latitude_range')),
    sa.CheckConstraint('longitude BETWEEN -180 AND 180', name=op.f('ck_palm_trees_longitude_range')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_palm_trees_users_owner_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_palm_trees'))
    )
    with op.batch_alter_table('palm_trees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_palm_trees_field_name'), ['field_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_palm_trees_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_palm_trees_tree_code'), ['tree_code'], unique=True)

    op.create_table('inspection_logs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('palm_tree_id', sa.Uuid(), nullable=False),
    sa.Column('inspected_by', sa.Uuid(), nullable=True),
    sa.Column('inspected_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('image_path', sa.String(length=512), nullable=False),
    sa.Column('detected_disease', sa.String(length=120), nullable=True),
    sa.Column('severity', sa.Enum('low', 'medium', 'high', name='inspection_severity'), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=False),
    sa.Column('status', sa.Enum('healthy', 'infected', 'critical', name='inspection_status'), nullable=False),
    sa.Column('treatment_recommendation', sa.Text(), nullable=True),
    sa.Column('detection_details', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('confidence BETWEEN 0 AND 1', name=op.f('ck_inspection_logs_confidence_range')),
    sa.ForeignKeyConstraint(['inspected_by'], ['users.id'], name=op.f('fk_inspection_logs_users_inspected_by'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['palm_tree_id'], ['palm_trees.id'], name=op.f('fk_inspection_logs_palm_trees_palm_tree_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inspection_logs'))
    )
    with op.batch_alter_table('inspection_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inspection_logs_inspected_at'), ['inspected_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_inspection_logs_palm_tree_id'), ['palm_tree_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('inspection_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inspection_logs_palm_tree_id'))
        batch_op.drop_index(batch_op.f('ix_inspection_logs_inspected_at'))

    op.drop_table('inspection_logs')
    with op.batch_alter_table('palm_trees', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_palm_trees_tree_code'))
        batch_op.drop_index(batch_op.f('ix_palm_trees_owner_id'))
        batch_op.drop_index(batch_op.f('ix_palm_trees_field_name'))

    op.drop_table('palm_trees')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')

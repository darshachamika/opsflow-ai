"""Add local web users and revocable browser sessions."""
from alembic import op
import sqlalchemy as sa
revision = 'f190a2bc710d'
down_revision = 'e84c71d329af'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('web_users',
        sa.Column('subject', sa.String(128), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(30), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('subject', name=op.f('pk_web_users')),
        sa.CheckConstraint("role IN ('OPERATOR','PROCUREMENT_MANAGER','ADMIN')", name=op.f('ck_web_users_valid_role')),
        sa.CheckConstraint('failed_attempts >= 0', name=op.f('ck_web_users_nonnegative_failed_attempts')))
    op.create_table('web_sessions',
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('subject', sa.String(128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('token_hash', name=op.f('pk_web_sessions')),
        sa.ForeignKeyConstraint(['subject'], ['web_users.subject'], ondelete='CASCADE', name=op.f('fk_web_sessions_subject_web_users')))
    op.create_index('ix_web_sessions_subject', 'web_sessions', ['subject'])
    op.create_index('ix_web_sessions_expires_at', 'web_sessions', ['expires_at'])

def downgrade():
    op.drop_index('ix_web_sessions_expires_at', table_name='web_sessions')
    op.drop_index('ix_web_sessions_subject', table_name='web_sessions')
    op.drop_table('web_sessions')
    op.drop_table('web_users')

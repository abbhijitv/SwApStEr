"""Create the existing record schema on an explicitly selected empty database.

Existing databases must be inspected before an operator chooses to stamp them.
No seed records, legacy-data upgrades, data copies, or destructive downgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_records'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(), nullable=True),
        sa.Column('data', sa.JSON(), nullable=True),
    )
    op.create_index('ix_records_kind', 'records', ['kind'])
    # Freeze the original JSON record layout rather than importing mutable app models.
    records = sa.table('records', sa.column('kind', sa.String()), sa.column('data', sa.JSON()))
    op.create_index(
        'unique_student_identity',
        'records',
        [records.c.data['identity'].as_string()],
        unique=True,
        sqlite_where=records.c.kind == 'student',
        postgresql_where=records.c.kind == 'student',
    )


def downgrade():
    raise RuntimeError('The records baseline cannot be downgraded: existing records must be preserved.')

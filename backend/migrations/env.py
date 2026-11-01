"""Explicit schema migrations. No application imports, seeds, or data upgrades."""
from alembic import context
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

from backend.models.database_config import create_database_engine, database_url
from backend.models.records import Base

load_dotenv()
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_database_engine(poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Synchronous database configuration with no connections or schema side effects."""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = 'sqlite:///./campusswap.db'


def database_url(value: str | URL | None = None) -> URL:
    """Normalize hosted PostgreSQL URLs without rendering credentials into logs."""
    if value is None:
        value = os.environ.get('DATABASE_URL', DEFAULT_DATABASE_URL)
    try:
        url = make_url(value.strip() if isinstance(value, str) else value)
        # Access port here too: malformed ports otherwise fail later in engine creation.
        _ = url.port
    except (ArgumentError, TypeError, ValueError):
        raise ValueError('Invalid DATABASE_URL; use a SQLite or PostgreSQL SQLAlchemy URL.') from None
    if url.drivername in ('postgres', 'postgresql', 'postgresql+psycopg'):
        return url.set(drivername='postgresql+psycopg')
    if url.drivername in ('sqlite', 'sqlite+pysqlite'):
        return url
    raise ValueError('Unsupported DATABASE_URL driver; use sqlite or postgresql+psycopg.')


def create_database_engine(value: str | URL | None = None, *, poolclass=None):
    """Engine creation is lazy: it never opens a connection or initializes tables."""
    url = database_url(value)
    options = {'pool_pre_ping': True, 'hide_parameters': True}
    if url.get_backend_name() == 'sqlite':
        options['connect_args'] = {'check_same_thread': False}
        # Keep one in-memory DB across FastAPI worker threads, just as file SQLite is shared.
        if not url.database or url.database == ':memory:':
            options['poolclass'] = StaticPool
    else:
        options['connect_args'] = {'connect_timeout': 10}
    if poolclass is not None:
        options['poolclass'] = poolclass
    return create_engine(url, **options)

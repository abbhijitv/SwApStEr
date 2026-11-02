"""Hosted tests are never selected by backend/tests and never load credentials from dotenv."""
import os
import time
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.models.database_config import create_database_engine, database_url
from backend.models.records import Record
from backend.commands.postgres_security import security_report


def pytest_collection_modifyitems(items):
    enabled = os.getenv('SWAPSTER_PG_INTEGRATION') == '1' and os.getenv('SWAPSTER_PG_WRITE_ACK') == 'isolated-records-and-sequence-use'
    if not enabled:
        for item in items:
            if Path(str(item.path)).is_relative_to(Path(__file__).parent):
                item.add_marker(pytest.mark.skip(reason='Hosted PostgreSQL integration requires explicit opt-in and write acknowledgement.'))


@contextmanager
def sanitized_failure(message):
    # Never let SQLAlchemy/Psycopg connection exceptions reach pytest output.
    try:
        yield
    except Exception:
        pytest.fail(message, pytrace=False)


@pytest.fixture
def pg_engine(request):
    engine = None
    with sanitized_failure('PostgreSQL preflight failed. Review private connection settings, grants/RLS, schema and trigger configuration.'):
        value = os.environ.get('SWAPSTER_TEST_POSTGRES_URL')
        if not value:
            raise ValueError('Dedicated test URL required; never fall back to DATABASE_URL.')
        url = database_url(value)
        if url.get_backend_name() != 'postgresql':
            raise ValueError('PostgreSQL required.')
        if url.query.get('sslmode') not in {'require','verify-ca','verify-full'}:
            raise ValueError('Encrypted test connection required.')
        if os.getenv('DATABASE_POOL_MODE','session') not in {'session','direct'}:
            raise ValueError('These tests require direct/session pooling.')
        engine = create_database_engine(url, poolclass=NullPool).execution_options(schema_translate_map={None:'public'})
        request.addfinalizer(engine.dispose)
        with engine.connect() as connection:
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
            report = security_report(connection)
            assert report.get('resolves_public') and report.get('current_role_crud_grants') and report.get('rls_enabled')
            assert report['bypass_rls'] or (report['owner'] and not report['rls_forced'])
            assert report['trigger_count'] == 0  # Custom business triggers need separate review before test writes.
            assert list(connection.scalars(text('SELECT version_num FROM public.alembic_version'))) == ['0001_records']
            for role in ('anon','authenticated'):
                access = report['privileges'][role]
                assert access['role_present']
                assert not any(access['table'].values()) and not any(access['any_column'].values()) and not any(access['sequence'].values())
    try:
        yield engine
    finally:
        if engine is not None:
            engine.dispose()


@pytest.fixture
def isolated(pg_engine, request):
    namespace = 'integration_4d_'+uuid4().hex
    request.node._pg_namespace = namespace
    try:
        with sanitized_failure('Isolated PostgreSQL integration assertion failed. No customer records were inspected; review private server diagnostics.'):
            yield pg_engine, namespace
    finally:
        # Independent connection/transaction; rollback of a failed test cannot undo cleanup.
        cleaned = False
        for attempt in range(3):
            try:
                with pg_engine.begin() as connection:
                    connection.exec_driver_sql("SET LOCAL lock_timeout='3s'")
                    connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
                    connection.execute(delete(Record).where(Record.kind == namespace))
                    remaining = connection.scalar(select(Record.id).where(Record.kind == namespace).limit(1))
                    if remaining is not None: raise RuntimeError('Cleanup incomplete')
                cleaned = True
                break
            except Exception:
                time.sleep(.2*(attempt+1))
        if not cleaned:
            pytest.fail('Cleanup could not be verified for test namespace '+namespace+'. Keep it for an operator-scoped cleanup; never delete other kinds.', pytrace=False)


@contextmanager
def scoped_session(engine):
    with Session(engine) as session:
        session.begin()
        session.connection().exec_driver_sql("SET LOCAL lock_timeout='3s'")
        session.connection().exec_driver_sql("SET LOCAL statement_timeout='5s'")
        yield session


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed and Path(str(item.path)).is_relative_to(Path(__file__).parent):
        namespace = getattr(item, '_pg_namespace', 'not-created')
        report.longrepr = ('PostgreSQL integration failed. Review private configuration/security and verify cleanup. '
                           'Synthetic namespace: '+namespace+'. Raw exceptions and captured logs are suppressed.')
        report.sections.clear()

"""Database readiness checks; PostgreSQL checks never contact a database server."""
import io
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, MagicMock

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.models import database_config
from backend.models.records import Base, Record, student_identity_index

ROOT = Path(__file__).resolve().parents[2]


def migration_config(output=None):
    return Config(str(ROOT / 'alembic.ini'), output_buffer=output)


def test_sqlite_is_default_only_when_database_url_is_unset(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    url = database_config.database_url()
    assert url.drivername == 'sqlite'
    assert url.database == './campusswap.db'
    monkeypatch.setenv('DATABASE_URL', '')
    with pytest.raises(ValueError, match='Invalid DATABASE_URL'):
        database_config.database_url()


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_postgresql_urls_preserve_credentials_and_connection_parameters(scheme):
    url = database_config.database_url(
        f'{scheme}://owner:p%40ss%3Aword%2F%25@db.example.invalid:5432/postgres'
        '?sslmode=require&application_name=swapster'
    )
    assert url.drivername == 'postgresql+psycopg'
    assert url.username == 'owner' and url.password == 'p@ss:word/%'
    assert url.host == 'db.example.invalid' and url.port == 5432
    assert url.database == 'postgres'
    assert dict(url.query) == {'sslmode': 'require', 'application_name': 'swapster'}
    assert 'p%40ss' not in str(url) and 'p@ss' not in str(url)


@pytest.mark.parametrize('value', [
    'bad-secret-value', '', 'postgresql://owner:SECRET@host:invalid/db',
    'mysql://owner:SECRET@host/db', 'postgresql+asyncpg://owner:SECRET@host/db',
    'postgresql+psycopg2://owner:SECRET@host/db', 'sqlite+aiosqlite:///:memory:',
])
def test_invalid_or_unsupported_urls_fail_without_echoing_credentials(value):
    with pytest.raises(ValueError) as error:
        database_config.database_url(value)
    assert 'SECRET' not in str(error.value) and 'bad-secret-value' not in str(error.value)


@pytest.mark.parametrize('value, expected_args', [
    ('sqlite:///local.db', {'check_same_thread': False}),
    ('postgres://owner:secret@db.example.invalid/postgres?sslmode=require', {'connect_timeout': 10}),
])
def test_only_sqlite_receives_check_same_thread(monkeypatch, value, expected_args):
    factory = Mock()
    monkeypatch.setattr(database_config, 'create_engine', factory)
    database_config.create_database_engine(value)
    args, kwargs = factory.call_args
    assert kwargs['connect_args'] == expected_args
    assert kwargs['pool_pre_ping'] and kwargs['hide_parameters']
    if args[0].get_backend_name() == 'postgresql':
        assert args[0].drivername == 'postgresql+psycopg'
        assert args[0].query['sslmode'] == 'require'


def test_real_psycopg_engine_initializes_without_connecting(monkeypatch):
    import psycopg
    connect = Mock(side_effect=AssertionError('Unexpected real connection'))
    monkeypatch.setattr(psycopg, 'connect', connect)
    engine = database_config.create_database_engine('postgresql://user:secret@db.example.invalid/postgres?sslmode=require')
    try:
        assert engine.dialect.name == 'postgresql' and engine.dialect.driver == 'psycopg'
        args, kwargs = engine.dialect.create_connect_args(engine.url)
        assert kwargs['sslmode'] == 'require'
        assert 'check_same_thread' not in kwargs
        connect.assert_not_called()
    finally:
        engine.dispose()


def test_postgresql_application_import_never_connects_seeds_or_creates_tables():
    env = dict(os.environ, DATABASE_URL='postgresql://user:secret@db.example.invalid/postgres')
    code = '''
from unittest.mock import patch
with patch('psycopg.connect', side_effect=AssertionError('Unexpected connection')), \\
     patch('sqlalchemy.engine.Engine.connect', side_effect=AssertionError('Unexpected connection')), \\
     patch('sqlalchemy.schema.MetaData.create_all', side_effect=AssertionError('Unexpected DDL')), \\
     patch('backend.services.store.seed', side_effect=AssertionError('Unexpected data seeding')):
    from backend.main import app
    from backend.models.database import engine, initialize_local_database
    assert engine.dialect.driver == 'psycopg'
    assert initialize_local_database() is False
'''
    subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT, check=True, capture_output=True, text=True)


def test_metadata_import_does_not_create_a_sqlite_file(tmp_path):
    path = tmp_path / 'not-created.db'
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(path))
    subprocess.run(
        [sys.executable, '-c', 'from backend.models.database import Base, Record, engine'],
        env=env, cwd=ROOT, check=True, capture_output=True, text=True,
    )
    assert not path.exists()


@pytest.mark.parametrize('dialect, extraction', [(sqlite.dialect(), 'JSON_EXTRACT'), (postgresql.dialect(), '->>')])
def test_portable_record_schema_and_partial_identity_index(dialect, extraction):
    table_sql = str(CreateTable(Record.__table__).compile(dialect=dialect))
    index_sql = str(CreateIndex(student_identity_index).compile(dialect=dialect))
    assert set(Record.__table__.columns.keys()) == {'id', 'kind', 'data'}
    assert 'data JSON' in table_sql and 'PRIMARY KEY (id)' in table_sql
    assert extraction in index_sql
    assert 'UNIQUE INDEX unique_student_identity' in index_sql
    assert "WHERE kind = 'student'" in index_sql
    if dialect.name == 'postgresql':
        assert 'SERIAL' in table_sql and 'json_extract' not in index_sql.lower()


def test_sqlite_json_records_uniqueness_and_cross_thread_memory_support():
    engine = database_config.create_database_engine('sqlite:///:memory:')
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            # Mirrors legacy initialization after create_all already made the index.
            connection.execute(CreateIndex(student_identity_index, if_not_exists=True))
            connection.execute(CreateIndex(student_identity_index, if_not_exists=True))
        with Session(engine) as db:
            db.add_all([
                Record(kind='student', data={'identity': 'keep-me'}),
                Record(kind='listing', data={'identity': 'keep-me', 'minimum': '23.50'}),
                Record(kind='student', data={'identity': 'second-person'}),
            ])
            db.commit()
        def read_from_worker():
            with Session(engine) as db:
                return db.scalars(select(Record).where(Record.kind == 'listing')).one().data
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(read_from_worker).result() == {'identity': 'keep-me', 'minimum': '23.50'}
        with Session(engine) as db:
            db.add(Record(kind='student', data={'identity': 'keep-me'}))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
            assert len(db.scalars(select(Record)).all()) == 3
    finally:
        engine.dispose()


@pytest.mark.parametrize('url', ['sqlite:///unused.db', 'postgresql://user:secret@db.example.invalid/postgres'])
def test_alembic_offline_baseline_never_connects_or_drops_records(monkeypatch, url):
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr('sqlalchemy.engine.Engine.connect', Mock(side_effect=AssertionError('Offline mode connected')))
    output = io.StringIO()
    command.upgrade(migration_config(output), 'head', sql=True)
    sql = output.getvalue()
    assert 'CREATE TABLE records' in sql and 'unique_student_identity' in sql
    assert 'DROP ' not in sql and 'DELETE ' not in sql and 'secret' not in sql
    assert 'INSERT INTO records' not in sql
    if url.startswith('postgresql'):
        assert '->>' in sql and 'json_extract' not in sql.lower()


def test_alembic_new_sqlite_database_and_repeated_upgrade_preserve_private_data(tmp_path, monkeypatch):
    path = tmp_path / 'baseline.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(path))
    config = migration_config()
    command.upgrade(config, 'head')
    engine = database_config.create_database_engine()
    snapshots = [
        (50, 'negotiation', {'preferences': {'maximum': '27'}, 'approvals': {'student-a': True, 'student-b': True}, 'messages': [], 'status': 'Confirmed'}),
        (51, 'session', {'student': 'student-a', 'token': 'synthetic-test-token'}),
        (52, 'listing', {'minimum': '23', 'seller_id': 'student-b'}),
    ]
    try:
        assert set(inspect(engine).get_table_names()) == {'records', 'alembic_version'}
        # SQLite reflection omits expression indexes; query its catalog explicitly.
        with engine.connect() as connection:
            indexes = set(connection.scalars(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='records'")))
        assert indexes == {'ix_records_kind', 'unique_student_identity'}
        with Session(engine) as db:
            assert db.scalars(select(Record)).all() == []  # Schema migration never seeds demo identities.
            db.add_all([Record(id=id, kind=kind, data=data) for id, kind, data in snapshots])
            db.commit()
        command.upgrade(config, 'head')
        with pytest.raises(RuntimeError, match='cannot be downgraded'):
            command.downgrade(config, 'base')
        with Session(engine) as db:
            assert [(r.id, r.kind, r.data) for r in db.scalars(select(Record).order_by(Record.id))] == snapshots
    finally:
        engine.dispose()


def test_existing_sqlite_database_requires_explicit_baseline_adoption(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'existing.db'))
    engine = database_config.create_database_engine()
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Record(id=100, kind='session', data={'student': 'student-a', 'token': 'keep-this-test-token'}))
            db.commit()
        # Upgrade refuses to overwrite an existing table. Stamping is a separate operator choice.
        with pytest.raises(OperationalError, match='already exists'):
            command.upgrade(migration_config(), 'head')
        command.stamp(migration_config(), '0001_records')
        command.upgrade(migration_config(), 'head')
        with Session(engine) as db:
            record = db.get(Record, 100)
            assert record.kind == 'session' and record.data == {'student': 'student-a', 'token': 'keep-this-test-token'}
            assert len(db.scalars(select(Record)).all()) == 1
    finally:
        engine.dispose()


def test_postgresql_never_uses_the_sqlite_backup_api(monkeypatch):
    from backend.services import students
    fake_engine = Mock()
    fake_engine.url.database = 'postgres'
    fake_engine.dialect.name = 'postgresql'
    monkeypatch.setattr(students, 'engine', fake_engine)
    connect = Mock(side_effect=AssertionError('SQLite backup must not run for PostgreSQL'))
    monkeypatch.setattr(students.sqlite3, 'connect', connect)
    assert students.backup_database() is None
    connect.assert_not_called()


@pytest.mark.parametrize('environment', ['production', 'staging', ''])
def test_non_development_sqlite_startup_never_creates_or_seeds(tmp_path, environment):
    path = tmp_path / 'must-not-exist.db'
    env = dict(os.environ, DATABASE_URL='sqlite:///'+str(path), APP_ENV=environment)
    code = '''
from unittest.mock import patch
with patch('sqlalchemy.schema.MetaData.create_all', side_effect=AssertionError('Unexpected DDL')), \\
     patch('backend.services.store.seed', side_effect=AssertionError('Unexpected demo seed')):
    import backend.main
'''
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, check=True, capture_output=True)
    assert not path.exists()


@pytest.mark.parametrize('mode', ['direct','session','transaction'])
def test_postgresql_pool_modes_and_isolation_are_explicit(monkeypatch, mode):
    monkeypatch.setenv('DATABASE_POOL_MODE', mode)
    factory = Mock()
    monkeypatch.setattr(database_config, 'create_engine', factory)
    database_config.create_database_engine('postgresql://user:synthetic@db.example.invalid/postgres')
    options = factory.call_args.kwargs
    assert options['isolation_level'] == 'READ COMMITTED'
    assert options['connect_args']['connect_timeout'] == 10
    if mode == 'transaction': assert options['connect_args']['prepare_threshold'] is None
    else: assert 'prepare_threshold' not in options['connect_args']


def test_invalid_postgresql_pool_mode_fails_before_connection(monkeypatch):
    monkeypatch.setenv('DATABASE_POOL_MODE', 'invalid')
    with pytest.raises(ValueError, match='DATABASE_POOL_MODE'):
        database_config.create_database_engine('postgresql://user:synthetic@db.example.invalid/postgres')


@pytest.mark.parametrize('sslmode', [None,'disable','allow','prefer'])
def test_supabase_urls_require_encryption_without_echoing_secrets(sslmode):
    value = 'postgresql://owner:DO_NOT_PRINT@aws-region.pooler.supabase.com:5432/postgres'
    if sslmode: value += '?sslmode='+sslmode
    with pytest.raises(ValueError) as error:
        database_config.create_database_engine(value)
    assert 'DO_NOT_PRINT' not in str(error.value)


def test_diagnostic_defaults_to_no_connection_or_initialization(tmp_path, monkeypatch):
    from backend.commands.database_check import check
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///'+str(tmp_path/'not-created.db'))
    monkeypatch.setattr('sqlalchemy.engine.Engine.connect', Mock(side_effect=AssertionError('Unexpected connection')))
    assert check()['connection'] == 'not tested'
    assert not (tmp_path/'not-created.db').exists()


def test_postgresql_diagnostic_defaults_to_no_remote_connection(monkeypatch):
    from backend.commands.database_check import check
    monkeypatch.setenv('DATABASE_URL', 'postgresql://owner:synthetic@db.example.invalid/postgres?sslmode=require')
    monkeypatch.setattr('psycopg.connect', Mock(side_effect=AssertionError('Remote connection forbidden')))
    assert check() == {'database':'postgresql','connection':'not tested','schema':'not tested'}


def test_read_only_diagnostic_preserves_temp_sqlite_and_detects_baseline(tmp_path, monkeypatch):
    import hashlib
    from backend.commands.database_check import check
    path = tmp_path/'diagnostic.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///'+str(path))
    command.upgrade(migration_config(), 'head')
    before = hashlib.sha256(path.read_bytes()).digest()
    result = check(connect=True)
    assert result['connection'] == 'ok' and result['schema'] == 'baseline observed'
    assert result['migration'] == '0001_records'
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_read_only_diagnostic_cannot_create_missing_sqlite(tmp_path, monkeypatch):
    from backend.commands.database_check import check
    path = tmp_path/'missing.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///'+str(path))
    with pytest.raises(OperationalError): check(connect=True)
    assert not path.exists()


def test_diagnostic_cli_failure_never_prints_exception_or_credentials(tmp_path):
    env = dict(os.environ, DATABASE_URL='postgresql://user:DO_NOT_PRINT@db.example.invalid:BAD/postgres')
    result = subprocess.run([sys.executable,'-m','backend.commands.database_check','--connect'],env=env,cwd=ROOT,capture_output=True,text=True)
    assert result.returncode == 1 and 'failed' in result.stdout
    assert 'DO_NOT_PRINT' not in result.stdout+result.stderr and 'Traceback' not in result.stdout+result.stderr


def test_postgresql_diagnostic_uses_read_only_transaction_and_rolls_back(monkeypatch):
    from backend.commands import database_check
    monkeypatch.setattr(database_check, 'database_url', lambda: database_config.database_url('postgresql://user:synthetic@db.example.invalid/postgres'))
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = 1
    inspector = Mock()
    inspector.get_table_names.return_value = []
    monkeypatch.setattr(database_check, 'create_database_engine', lambda *a, **kw: engine)
    monkeypatch.setattr(database_check, 'inspect', lambda c: inspector)
    result = database_check.check(connect=True)
    assert result['schema'] == 'review required'
    sql = [call.args[0] for call in connection.exec_driver_sql.call_args_list]
    assert sql == ['SET TRANSACTION READ ONLY', "SET LOCAL statement_timeout = '5s'"]
    connection.begin.return_value.rollback.assert_called_once()
    engine.dispose.assert_called_once()


def test_postgresql_marketplace_transaction_never_uses_begin_immediate(monkeypatch):
    from backend.services import account_marketplace
    factory = MagicMock()
    db = factory.return_value.__enter__.return_value
    db.bind.dialect.name = 'postgresql'
    monkeypatch.setattr(account_marketplace, 'Session', factory)
    with account_marketplace.writing() as current:
        assert current is db
    db.connection.assert_not_called()
    db.commit.assert_called_once()


def test_postgresql_marketplace_locking_and_json_queries_compile():
    from sqlalchemy import update, or_
    actor = '97e67eaa-7313-47cd-aae8-1294dd91a6f9'
    locked = select(Record).where(Record.kind == 'account_listing', Record.id == 10).with_for_update()
    public = select(Record).where(Record.data['deleted'].as_boolean().is_(False))
    cas = update(Record).where(Record.kind == 'account_negotiation', Record.data['version'].as_integer() == 4,
        or_(Record.data['buyer_id'].as_string() == actor, Record.data['seller_id'].as_string() == actor)).values(data={'version':5})
    dialect = postgresql.dialect()
    assert 'FOR UPDATE' in str(locked.compile(dialect=dialect))
    assert 'IS false' in str(public.compile(dialect=dialect))
    sql = str(cas.compile(dialect=dialect))
    assert '->>' in sql and 'CAST' in sql and 'UPDATE records' in sql and ' OR ' in sql

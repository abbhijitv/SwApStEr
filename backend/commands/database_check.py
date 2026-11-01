"""Credential-safe, opt-in connectivity and schema diagnostics.

Default: configuration only, no engine/connection or application startup.
--connect: explicit operator authorization to contact the configured database.
No business data is read. No migrations, writes, seeding or stamping occur.
"""
import argparse
import json
import logging
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.pool import NullPool

from backend.models.database_config import database_url, create_database_engine


def check(*, connect=False):
    url = database_url()
    dialect = url.get_backend_name()
    # Validate lazy engine options without importing application startup.
    if not connect:
        engine = create_database_engine(url, poolclass=NullPool)
        engine.dispose()
        return {'database': dialect, 'connection': 'not tested', 'schema': 'not tested'}
    if dialect == 'sqlite':
        if not url.database or url.database == ':memory:' or url.query:
            raise ValueError('Diagnostic requires an ordinary file-backed SQLite URL.')
        path = Path(url.database).resolve()
        # URI read-only mode prevents even an accidental new file on a missing path.
        url = url.set(database='file:'+quote(str(path)), query={'mode':'ro', 'uri':'true'})
    engine = create_database_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                if dialect == 'postgresql':
                    connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                    connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
                if connection.scalar(text('SELECT 1')) != 1:
                    raise ValueError('Unexpected connectivity result.')
                inspector = inspect(connection)
                tables = set(inspector.get_table_names())
                result = {'database':dialect, 'connection':'ok', 'records_table':'present' if 'records' in tables else 'missing', 'migration':'unmarked'}
                if 'records' in tables:
                    columns = {column['name'] for column in inspector.get_columns('records')}
                    result['record_columns'] = 'expected' if columns == {'id','kind','data'} else 'unexpected'
                if 'alembic_version' in tables:
                    revisions = list(connection.scalars(text('SELECT version_num FROM alembic_version')))
                    # Never echo arbitrary stored values or error text.
                    result['migration'] = '0001_records' if revisions == ['0001_records'] else 'unexpected'
                result['schema'] = 'baseline observed' if result.get('record_columns') == 'expected' and result['migration'] == '0001_records' else 'review required'
                return result
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connect', action='store_true', help='Explicitly contact DATABASE_URL using a read-only diagnostic transaction.')
    args = parser.parse_args(argv)
    # Driver/SQLAlchemy diagnostics can include connection identifiers. Emit only
    # this command's fixed JSON, including when a driver or configuration fails.
    logging.disable(logging.CRITICAL)
    try:
        load_dotenv()
        result = check(connect=args.connect)
        print(json.dumps(result))
        return 0
    except Exception:
        print(json.dumps({'status':'failed', 'detail':'Database configuration or diagnostic failed. Check private server configuration, connectivity and schema.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

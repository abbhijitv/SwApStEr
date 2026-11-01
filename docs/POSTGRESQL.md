# PostgreSQL preparation and a future Supabase connection

Prompt 2 adds database configuration and schema preparation only. SQLite remains
the default local database. No local PostgreSQL server, Supabase project, remote
connection, data import, authentication, or production deployment is required.

## Local SQLite behavior

Leave the root `.env` configured with:

```dotenv
DATABASE_URL=sqlite:///./campusswap.db
```

Paths remain relative to the working directory, so launch from the repository
root. Existing `.env` values are preserved; environment variables take precedence
over dotenv values. An unset `DATABASE_URL` defaults to the same SQLite path. An
explicitly empty, malformed, unsupported, or asynchronous URL fails clearly
instead of silently selecting a different database.

Importing database metadata or constructing an engine no longer creates tables.
Importing the FastAPI application still initializes **SQLite only**, then runs the
existing idempotent local demo/profile initialization. The existing legacy
student upgrade and SQLite backup behavior are retained; this change does not
introduce another automatic data migration. Standalone scripts that previously
relied on importing the database module to create SQLite tables must explicitly
call `initialize_local_database()` before accessing a fresh database.

`records(id INTEGER PRIMARY KEY, kind VARCHAR, data JSON)` remains the storage
format. All existing record IDs, JSON payloads, profile identities, session tokens,
negotiation transcripts, private preferences, and approval keys retain their
meaning. This work does not convert JSON to JSONB or normalize the record layout.

## Configuration and driver

Install the dependencies in the project virtual environment:

```sh
.venv/bin/python -m pip install -r backend/requirements.txt -c backend/requirements.lock.txt
```

The new dependencies are Psycopg 3 with its binary extra and Alembic. Psycopg
provides Python 3.13 support and binary distributions, avoiding a local PostgreSQL
server or compiler for this setup. See [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

Supported synchronous URL forms:

```text
sqlite:///./campusswap.db
postgresql+psycopg://USER:PERCENT_ENCODED_PASSWORD@HOST:5432/postgres?sslmode=require
postgresql://USER:PERCENT_ENCODED_PASSWORD@HOST:5432/postgres?sslmode=require
postgres://USER:PERCENT_ENCODED_PASSWORD@HOST:5432/postgres?sslmode=require
```

Both PostgreSQL aliases are normalized to SQLAlchemy's explicit
`postgresql+psycopg` dialect, preserving the username, password, host, port,
database, and query parameters. Percent-encode reserved password characters once
when assembling a URL; a literal percent sign is `%25`. The URL is passed as a
SQLAlchemy URL object, including in Alembic, so percent-encoded credentials never
pass through INI interpolation. Do not put credentials in `alembic.ini` or in a
`NEXT_PUBLIC_*` variable. [SQLAlchemy's Psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
is distinct from its older Psycopg 2 dialect.

SQLite alone receives `check_same_thread=False`. In-memory SQLite uses a shared
StaticPool so FastAPI threads see the same temporary database. PostgreSQL uses a
10-second connection timeout, SQLAlchemy's default connection pool, and
`pool_pre_ping=True`. Parameter values are hidden in SQLAlchemy statement logs and
errors; do not print the raw environment variable or connection exceptions to
public clients. Driver errors and arbitrary application logging still need care.

PostgreSQL engine construction is lazy. Importing the application with a
PostgreSQL URL neither connects nor creates tables, seeds demo profiles, runs the
legacy student upgrade, or copies SQLite data. A database-backed endpoint will
connect when queried and will fail if schema/access is not prepared. `/health`
is still a process-liveness response; it is **not** a database-connectivity probe.

## SQL compatibility improvements

- SQLAlchemy now compiles the student identity JSON expression and partial unique
  index for SQLite and PostgreSQL. SQLite uses `JSON_EXTRACT`; PostgreSQL uses
  text extraction with `->>`. The existing index name `unique_student_identity`
  and its `kind = 'student'` predicate are preserved.
- Existing profile initialization uses dialect-compiled `CREATE INDEX IF NOT
  EXISTS`, avoiding SQLite's incomplete reflection of expression indexes. It
  never replaces an existing index or rewrites a record to make it fit.
- Record enumeration orders by `records.id`, providing a stable order on both
  databases instead of depending on SQLite's incidental row order.
- SQLite's backup API remains guarded to run only on file-backed SQLite, not
  PostgreSQL or in-memory databases. PostgreSQL needs its own backup process.

## Alembic: explicit schema baseline

Alembic is included because metadata is now separate from engine/application
startup, allowing offline SQL generation without opening a database. The sole
revision, `0001_records`, creates the existing table and its kind/identity indexes
on an **empty** database. It inserts no application records, alters no existing
payloads, and contains no drop/delete operations. Its downgrade raises an error
rather than dropping the records table. [Alembic offline mode](https://alembic.sqlalchemy.org/en/latest/offline.html)
supports SQL review before any online action.

Preview PostgreSQL SQL without contacting a host (the URL below is a placeholder):

```sh
DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require' \
  .venv/bin/python -m alembic upgrade head --sql
```

No migration command is run by app startup or the launch script. For a future,
explicitly selected **empty development database**, first review the offline SQL,
then deliberately run:

```sh
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic current
```

These online commands use `DATABASE_URL` from the environment/root `.env` and a
NullPool migration engine. They create schema and an `alembic_version` marker;
they do not import campus listings or demo identities. Confirm the target before
running them. They have not been run against the existing `campusswap.db` or any
remote database during this work.

**Existing databases:** do not run the baseline upgrade against an existing
`records` table and do not delete the table to make the upgrade succeed. Upgrade
refuses to overwrite it. Local SQLite needs no Alembic adoption to keep working.
If a future operator wants to adopt an existing database, back it up, inspect its
columns, types, primary key, kind index, partial unique identity index and actual
duplicate/null identity behavior, and compare them with the baseline. Only after
confirming equivalence may the operator explicitly run `alembic stamp
0001_records` to record the baseline. Stamping does **not** validate or repair
schema, add missing indexes, or upgrade legacy profile data. Missing constraints
need a separately reviewed additive migration first. Never stamp an empty or
mismatched database as a shortcut. SQLite expression-index reflection is limited;
inspect `sqlite_master` as well as ordinary reflection. Review all future
autogenerated revisions manually, especially expression indexes and any proposed
drop operations.

## Future Supabase connection

No credentials or project are needed now. When a future non-production Supabase
database is authorized:

1. Copy its database connection string from the dashboard **Connect** dialog.
   Use the actual host and username shown there. A database URL is different from
   a Supabase HTTP project URL or API key.
2. Prefer a direct connection for a persistent backend and migration operations
   when the network supports it. On IPv4-only networks, the shared **session**
   pooler is an alternative. Supabase currently uses port 5432 for both modes,
   with different hosts/usernames. Copy the full string rather than guessing it.
   See [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).
3. Store the URL only in an ignored server-side `.env` or a future server secret.
   Explicitly include `sslmode=require` to require encryption. Configure
   `sslmode=verify-full` plus the appropriate CA for certificate/hostname
   validation where required. This code preserves SSL parameters; it does not
   silently change them or enable SSL for every possible local PostgreSQL server.
4. Use an empty development target to review/apply the schema baseline. If the
   target already has records or Alembic history, assess adoption rather than
   assuming it is empty. Switching `DATABASE_URL` never copies local data.
5. Perform a real connectivity and schema smoke test deliberately at that time.
   For example, in a Python process configured with the future URL:

   ```python
   from sqlalchemy import text
   from backend.models.database import engine

   with engine.connect() as connection:
       assert connection.scalar(text('SELECT 1')) == 1
   ```

   Do not treat importing the engine or `/health` as evidence of connectivity.

Transaction poolers (commonly port 6543) have different prepared-statement and
session-state behavior. This prompt targets direct/session connections and does
not claim transaction-pooler support. Changing only the port is insufficient;
driver preparation/pipeline settings and deployment pool sizes need separate
verification. Follow [Supabase's mode-specific limitations](https://supabase.com/docs/guides/database/connecting-to-postgres#transaction-mode-limitations).

## Remaining migration and production risks

- No SQLite-to-PostgreSQL data-transfer tool was implemented or run. A future
  transfer must preserve every numeric record ID and every JSON reference,
  including private constraints and session tokens, validate row counts/content,
  preserve the legacy migration marker, and advance the PostgreSQL ID sequence
  past the maximum imported ID before allowing inserts. PostgreSQL does not
  automatically advance its sequence when inserting explicit IDs.
- Missing/duplicate profile identities and JSON values must be checked before
  applying a uniqueness constraint. Existing nullability and JSON semantics were
  retained, not strengthened silently. A fresh empty PostgreSQL database contains
  no profiles/listings; explicit approved provisioning or a reviewed import is a
  separate task. The legacy profile upgrader remains available to callers but
  never runs automatically for PostgreSQL.
- Existing approval/advance locks are process-local. PostgreSQL support does not
  make multi-worker negotiations safe; cross-process concurrency and transaction
  design still require work. No authorization or negotiation logic was changed.
- `records.data` contains private budgets and session tokens. Before putting
  private data in a hosted database, separately configure access/role permissions
  and prevent direct browser/Data API exposure of this storage table. Supabase
  public-schema exposure and RLS must be reviewed; no policies, roles, or
  authentication were provisioned by this prompt.
- Connection limits, deployment credentials, TLS certificate verification,
  backups/restore, network reachability and real PostgreSQL behavior remain to be
  validated on an authorized development instance. Configuration/SQL compilation
  and mocks do not establish that a remote PostgreSQL server works.

## Verification

```sh
.venv/bin/python -m pytest backend/tests/test_database.py -q
.venv/bin/python -m pytest backend/tests -q
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

The new tests cover default/invalid URLs, aliases and encoded credentials,
dialect-specific engine options, real Psycopg driver loading without connection,
PostgreSQL application imports with connection/DDL/seeding forbidden, portable
DDL, temporary SQLite JSON/uniqueness behavior, offline migrations, explicit
baseline adoption, non-destructive downgrade refusal, and preservation of private
record data during repeated upgrades. Existing backend tests still cover the
legacy SQLite backup, data migration, and independent approvals.

No real PostgreSQL/Supabase connectivity has been tested in this preparation step.

Recorded local results: **150 backend tests passed** (including **24 database
configuration/migration tests**, which also passed separately), with no failures
or skips. TypeScript, the Next.js production build, and `pip check` passed. The
existing `campusswap.db` SHA-256 checksum was identical before and after testing.
All online migration tests used newly created temporary SQLite files; PostgreSQL
coverage used driver loading, SQL compilation, offline Alembic, and mocks only.

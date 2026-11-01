# Step 4A: safe Supabase PostgreSQL integration readiness

This step prepares configuration and diagnostics. No remote database was contacted,
no remote migrations were executed, and no SQLite records were copied or changed.
Supabase Auth settings remain independent from the database connection string.

## Architecture and inspection

The single configured SQLAlchemy engine/session factory in `backend/models/database.py`
serves both record namespaces. `records(id INTEGER PRIMARY KEY, kind VARCHAR,
data JSON)` contains demo students/listings/sessions/negotiations and separate
`account_listing` / `account_negotiation` records. Account approval decisions,
private preferences, listing references, conversation, timestamps and versions
are embedded in JSON. There is no separate approval table. At inspection the
local SQLite file held 2 account listings, 1 account negotiation, 7 demo listings,
3 students, 12 sessions and 1 legacy migration marker; only aggregate counts
were read, not private payloads or identities.

Every account storage operation uses that configured Session. SQLite-specific
`BEGIN IMMEDIATE` is dialect-guarded. PostgreSQL mutations lock the listing first,
then use owner/participant-and-version conditional updates. Inference runs outside
the write transaction. PostgreSQL now explicitly uses READ COMMITTED isolation so
subsequent statements see a competing transaction's committed version after a
listing lock is acquired. Existing authorization and human approval rules are
unchanged. PostgreSQL locking/CAS execution is still unverified against a server.

SQLAlchemy compiles JSON text/integer/boolean extraction, row locks, SERIAL IDs,
and the partial unique demo-student identity index for PostgreSQL. UUID subjects
and approval keys remain verified canonical strings in JSON; no native UUID cast
or new FK to Supabase Auth is required. Money remains decimal strings and dates
are validated/handled by application code. Timestamps remain ISO strings, not
TIMESTAMPTZ columns. No JSON-to-JSONB conversion, table normalization, type change,
new constraint, or record rewrite occurs. JSON references have no database foreign
keys, and account ownership/versions have no dedicated JSON expression indexes;
performance, orphan checks and direct database write access need operational review.

Automatic `create_all()` and demo initialization now run only for development
SQLite. Any other APP_ENV, including production SQLite, skips them. PostgreSQL
always skips them regardless of environment. Application startup never runs
Alembic. `/health` stays process liveness; it does not establish database health.

## Required configuration

| Setting | Meaning |
| --- | --- |
| `DATABASE_URL` | Required to select PostgreSQL; unset retains local SQLite. Server-only SQLAlchemy URL, never `NEXT_PUBLIC_*`. Use a percent-encoded password and `sslmode=require` at minimum. |
| `DATABASE_POOL_MODE` | New optional PostgreSQL setting: `direct` (default), `session`, or `transaction`. Match the actual dashboard connection mode; this flag does not change host or port. Ignored for SQLite. |
| `APP_ENV` | Defaults to `development` for the existing local demo. Set explicitly to `production` in a future production process; this prevents local schema/demo bootstrapping. |
| `ENABLE_ACCOUNT_MARKETPLACE` | Default false; keep false throughout this readiness step and in production configuration. No rollout is enabled. |

Existing `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` authenticate accounts and
are unchanged. They are not database credentials. No service-role key is needed
for SQLAlchemy. URL aliases `postgres://` / `postgresql://` select the installed
Psycopg 3 driver (`postgresql+psycopg`); asynchronous/other drivers are rejected.

Known Supabase hostnames require `sslmode=require`, `verify-ca` or `verify-full`;
missing, opportunistic or disabled SSL fails before connection. For hostnames
outside those suffixes, operators must explicitly enforce TLS themselves. For
certificate/hostname verification prefer `sslmode=verify-full` and the dashboard
CA via `sslrootcert=/absolute/private/path/to/ca.crt`. `require` encrypts traffic
but is not equivalent to full hostname verification. Never print URLs or raw
connection exceptions. Parameter hiding does not sanitize arbitrary driver errors.

## Choose a connection mode

For this long-running FastAPI process, prefer direct connections when IPv6 is
available (or a direct IPv4 add-on), otherwise the Supavisor session pooler.
Use the exact dashboard Connect string; don't construct pooler hosts or usernames.
Typical direct/session port is 5432; the shared transaction pooler typically uses
6543. [Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
explains the endpoint and network choices.

Direct and session modes retain Psycopg's normal prepared-statement behavior.
Transaction mode sets the Python connection argument `prepare_threshold=None`;
this disables automatic preparation. Do not put `prepare_threshold=None` in the
URL: it is a driver option, not a libpq connection-string parameter, and zero is
not equivalent to disabling preparation. [Psycopg's preparation documentation](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html)
describes this setting. This configuration is not a claim that Supavisor
transaction mode was live-tested. Session state and pipeline limitations still
require integration tests; prefer direct/session for this application and a
direct connection for migrations (session if direct is unreachable and separately
validated). Don't use transaction mode for this step's schema initialization.

The application retains SQLAlchemy QueuePool defaults (up to 5 retained plus 10
overflow connections per worker). Multiply by workers/instances and account for
migrations and dashboard activity before selecting a hosted connection budget.
Pool pre-ping and the 10-second connection timeout remain enabled. This step does
not tune deployment pool sizes or bypass provider connection limits. Alembic and
the diagnostic use NullPool and dispose their connections.

## Credential-safe diagnostic

```sh
# Configuration validation only: no database connection, file creation or app import.
.venv/bin/python -m backend.commands.database_check

# ONLY after explicit authorization to contact the selected target:
.venv/bin/python -m backend.commands.database_check --connect
```

The command emits fixed JSON with database family, connection result, expected
column presence and a recognized migration marker. It prints no host, username,
URL, password, payloads, arbitrary stored marker or exception text. Its default
never connects. With `--connect`, PostgreSQL uses a read-only transaction,
transaction-local 5-second statement timeout, SELECT 1, catalog inspection and
an Alembic version SELECT, then rolls back. SQLite uses a read-only URI and
cannot create a missing database file. No seed, migration, stamp or business
record access occurs. Failed checks exit 1 with a generic message. Successful
connectivity exits 0 even when schema says `review required`: `baseline observed`
is not a full schema/permissions certificate; inspect indexes/types/grants too.

## Safe manual setup of a new development target

These are future operator steps, not actions executed in Step 4A. Obtain explicit
approval before connecting or migrating any remote target.

1. Keep `campusswap.db` and its backup intact. Use a new non-production Supabase
   project/application namespace. Existing Supabase system schemas are expected;
   `records` and `alembic_version` must be absent for fresh application baseline
   initialization. Never assume an existing table belongs to this app.
2. In the dashboard Connect dialog select direct (IPv6 available) or session
   (IPv4-only). Choose the actual database credentials, not Auth API keys, and
   percent-encode reserved password characters exactly once. Copy the full host,
   username, port and database. Add required SSL/CA options.
3. Configure only an isolated local backend terminal; do not edit the actual root
   `.env` or frontend `.env.local`. For zsh, prompt silently rather than putting
   a password in shell history:

   ```sh
   read -rs 'DATABASE_URL?Paste the development PostgreSQL SQLAlchemy URL: '
   export DATABASE_URL
   export DATABASE_POOL_MODE=session  # use direct for a direct URL
   export APP_ENV=production
   export ENABLE_ACCOUNT_MARKETPLACE=false
   ```

   Do not echo the variable or paste it into reports. Exported variables override
   dotenv. Protect the terminal environment like a secret. Closing that terminal
   restores the usual SQLite setup for future processes.
4. Run the diagnostic without `--connect`. Review `alembic heads` and offline DDL:

   ```sh
   .venv/bin/python -m backend.commands.database_check
   .venv/bin/python -m alembic heads
   .venv/bin/python -m alembic upgrade head --sql
   ```

   These do not contact PostgreSQL. Expected sole head: `0001_records`.
5. After remote-connect approval, run the read-only diagnostic with `--connect`.
   Expect connection ok and application schema missing on a fresh target. Inspect
   the target and grants in the dashboard. Use a separate migration operator and
   a restricted backend role as appropriate; restrict Data API/browser access to
   the records table before inserting any business records. Supabase's default
   public-schema privileges must not expose private JSON. RLS with no client
   policies and/or revoked anon/authenticated grants, plus deliberate backend
   role permissions, require explicit review. This step creates no roles/policies.
6. Only after separate migration approval and confirming an empty application
   target, deliberately run through direct/session mode:

   ```sh
   .venv/bin/python -m alembic upgrade head
   .venv/bin/python -m alembic current
   .venv/bin/python -m backend.commands.database_check --connect
   ```

   Validate `records` columns/types/nullability, primary key/sequence,
   `ix_records_kind`, and `unique_student_identity` (unique JSON identity
   expression restricted to `kind='student'`) in the dashboard. The marker must
   be `0001_records`. Check `SELECT count(*) FROM public.records` is zero before
   any authorized testing; don't select JSON payloads. Confirm backend role table
   and sequence privileges, schema visibility and denied browser/Data API access.
7. Start a local backend only after schema and permissions checks. Keep the
   marketplace flag false. `/health` alone does not validate storage. Any later
   real-account write test, flag enablement, import or production rollout needs
   its own authorized step; no automatic demo initialization occurs on PostgreSQL.
8. Stop the test process and close the isolated terminal, or `unset DATABASE_URL
   DATABASE_POOL_MODE APP_ENV ENABLE_ACCOUNT_MARKETPLACE`. Start the usual local
   backend from the repository root to use the unchanged SQLite environment.

## Alembic and remaining risks

The sole revision `0001_records` creates `records` and its two indexes, plus
Alembic's version marker. Offline PostgreSQL compilation produces SERIAL/JSON and
the PostgreSQL JSON-expression partial unique index. It inserts no business data,
drops nothing and refuses destructive downgrade. Empty temporary SQLite online
migration tests pass; an actual empty PostgreSQL upgrade is **unverified**.
Existing SQLite requires neither automatic upgrade nor stamp. Never stamp an
empty or mismatched target, delete tables to rerun the baseline, or repurpose the
legacy JSON `migration` marker as an Alembic revision.

No data-transfer tool is added. Switching DATABASE_URL selects a different store;
it does not copy SQLite. A future explicitly reviewed import must preserve IDs,
UUID strings, JSON references, approval state and private constraints, verify
counts/content, and advance the PostgreSQL SERIAL sequence beyond imported IDs.
Backups/restore, live locking and serialization behavior, TLS/reachability,
pool capacity, runtime role access and Supabase Data API/RLS remain unverified.
Account JSON queries may need additive indexes at scale. Legacy demo negotiation
locks remain process-local; account negotiations use database serialization/CAS.
Inventory reservation across distinct negotiations remains outside this step.

## Files and verification

Changed `backend/models/database.py`, `backend/models/database_config.py`,
`backend/tests/test_database.py`, `.env.example`, `docs/POSTGRESQL.md`, and README.
Added `backend/commands/__init__.py`, `backend/commands/database_check.py`, and this
runbook. Existing migration files, account authorization, Auth and frontend
implementation are unchanged. PostgreSQL coverage consists of compilation,
offline Alembic, driver loading and mocks, not a live server.

Actual Step 4A results: **309 backend tests passed**, including **43 database
configuration/migration/diagnostic tests** (also passed separately); **75 relevant
frontend tests passed**. TypeScript, production build and `git diff --check`
passed. `alembic heads` reports `0001_records (head)`. The default diagnostic
reported connection/schema not tested. SQLite, actual environment files and all
existing migrations retained identical checksums. Live PostgreSQL connectivity,
DDL execution and runtime concurrency remain unverified.

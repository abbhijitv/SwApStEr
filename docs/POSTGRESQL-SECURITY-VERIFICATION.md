# Step 4D: opt-in PostgreSQL integration and security verification

No hosted test, diagnostic connection, migration or privilege change was executed
by this implementation. The operator reports successful Session-pooler connectivity,
revision `0001_records`, expected `public.records`, RLS enabled and table-level
SELECT/INSERT/UPDATE/DELETE/TRUNCATE denied to anon/authenticated. These remote
facts are user-reported, not independently rechecked here. SQLite remains default.

## Read-only diagnostics

Existing configuration-only usage still makes no connection:

```sh
.venv/bin/python -m backend.commands.database_check
```

After a separately authorized remote read-only check, with the intended application
role's URL in the isolated terminal's DATABASE_URL:

```sh
.venv/bin/python -m backend.commands.database_check --connect --security
```

Both flags are required for security inspection. No URL, username, sequence name,
policy text, business payload, exception details or customer records are printed.
The report contains only booleans, counts, recognized migration status, fixed
privilege names and anonymized default-ACL creators. It checks:

- `public.records` RLS enabled/forced flags, owner/BYPASSRLS status, policy count,
  and count of user-defined table triggers.
- Current schema/name resolution to public.records, public schema USAGE/CREATE,
  and effective table privileges for current_user, anon and authenticated.
- Effective column grants, which can permit access even when table-wide SELECT,
  INSERT or UPDATE is absent; privileges inherited from PUBLIC/roles are included
  by PostgreSQL's `has_*_privilege` checks.
- Owned ID-sequence presence and effective USAGE/SELECT/UPDATE. INSERT via the
  sequence normally needs USAGE or UPDATE, not sequence ownership or SELECT.
- Global and public-schema default ACLs for future tables and sequences, across
  creators, including PUBLIC and roles whose privileges API roles inherit.
- Enabled event-trigger count, since DDL automation can apply grants independently
  of default ACLs. Trigger/function definitions are not read or printed.

The transaction is read-only, statement-limited and rolled back. No nextval(),
DDL, grants or policy changes occur. Catalog privileges do not establish whether
RLS permits an actual row operation. Owners/BYPASSRLS may bypass row policies;
FORCE RLS affects owners but not superusers/BYPASSRLS. The report exposes that
condition without treating it as evidence that client policies are safe.
`review_required=false` is not a public-launch certificate: RPC/security-definer
functions, role switching, Data API exposure, event-trigger behavior, additional
schemas and later creating roles need separate review. Missing schema or unknown
migration status still require attention in the outer diagnostic report.

## Separately authorized integration run

The suite lives in `backend/integration_tests`, outside the default SQLite suite.
It needs all three dedicated variables below. It never falls back to DATABASE_URL
for its write target and never loads a test URL from dotenv. A normal run skips
all five hosted tests, even if a test URL happens to exist. The ordinary
`backend/tests` suite still forces temporary SQLite and runs independently.

Prefer a disposable development database with the same schema/security setup.
Running against a shared hosted application store requires explicit approval of
synthetic INSERT/UPDATE/DELETE, sequence consumption, locking and cleanup. Use the
actual intended backend role to test its access; an administrator success does
not prove a different restricted application's access. Do not use production
credentials or print the environment. In a new zsh terminal, after authorization:

```sh
read -rs 'SWAPSTER_TEST_POSTGRES_URL?Paste the approved PostgreSQL test URL: '
export SWAPSTER_TEST_POSTGRES_URL
export DATABASE_POOL_MODE=session  # direct if using the approved direct URL
export SWAPSTER_PG_INTEGRATION=1
export SWAPSTER_PG_WRITE_ACK=isolated-records-and-sequence-use
.venv/bin/python -m pytest backend/integration_tests -q --tb=no
unset SWAPSTER_TEST_POSTGRES_URL SWAPSTER_PG_INTEGRATION SWAPSTER_PG_WRITE_ACK DATABASE_POOL_MODE
```

Require an SSL URL (require/verify-ca/verify-full); prefer verify-full plus the
appropriate CA. No URL should appear in command history. Never use pytest
`--showlocals`, `--pdb`, `-s`, SQL echo or live SQL logging with credentials.
Raw failure tracebacks and captured logs are suppressed by this suite's report
hook; failure output retains only the synthetic namespace needed for cleanup.
Do not export opt-in flags globally or add them to CI/secrets without a separate
review. Direct/session pooling is required, not transaction pooling.

Before any write, the suite checks the public schema resolution, baseline marker,
RLS, table/sequence access and absence of API table/column/sequence grants.
The verification role also needs read access to public.alembic_version for its
preflight; this is a diagnostic prerequisite, not a new runtime CRUD requirement. It
refuses custom record triggers. For verifiable cleanup of every test row it also
requires the testing role to bypass RLS, either explicitly or as a non-forced
owner. It does not grant bypass or disable RLS. A policy-restricted backend role
needs a separately reviewed policy-aware cleanup/test design; report that blocker
instead of running as an unrelated administrator and claiming success for it.

The five tests exercise:

1. Committed insert/read/update/delete across independent SQLAlchemy sessions and
   distinct PostgreSQL backend connections; insertion exercises the real sequence.
2. Flushed update rollback followed by an independent read of the original state.
3. Simultaneous application `compare_and_swap` calls against one version: exactly
   one commit and one conflict, no lost update.
4. The application's FOR UPDATE read waiting behind another transaction, confirmed
   by a pending lock for the synthetic worker PID; after commit the waiting
   READ COMMITTED session must see the new version.
5. Current role security and future-grant review, failing when public defaults or
   unsafe effective permissions remain.

The suite does not call public marketplace APIs or import application startup.
Its synthetic kind `integration_4d_<random UUID>` is never enumerated by marketplace
routes. Test ORM statements explicitly map to the public schema. Every data
query/update/delete is scoped to the random kind, and specific
row operations also use the generated ID. It never reads customer JSON, resets
SQLite, runs migrations, sets roles, changes RLS, truncates tables or resets IDs.

## Cleanup guarantees and limits

Each test uses a fresh namespace and finally-based cleanup in an independent
transaction. It retries scoped DELETE and verifies no matching test ID remains,
including after assertion failures or rollback. Backend connections use NullPool;
lock/statement timeouts bound operations and sessions close on all paths.

No distributed client can guarantee cleanup after SIGKILL, machine loss, revoked
permissions or a sustained network outage. If cleanup cannot be verified, the run
fails and reports its exact synthetic namespace. After restoring access and
separate operator review, remove only that exact namespace with a parameterized
DELETE and verify its absence. Never use a broad `integration_%` cleanup, touch
account/demo kinds, reset the sequence or truncate records. Successful committed
tests permanently consume a few sequence values; gaps are expected and harmless.
The tests deliberately refuse role/trigger configurations where their cleanup
assumptions cannot be established.

## Review future grants without changing Supabase Auth

Current-table revocations do not change future-object grants. Default privileges
belong to the role that actually creates an object, not automatically to its role
members. Schema defaults add to global defaults; a schema-only REVOKE cannot undo
a global grant. See [PostgreSQL default privilege semantics](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html).

Safe review process (documentation only; no SQL here is automatically executed):

1. Inventory the actual application migration creator(s), global/public defaults,
   inherited grantees, and enabled event-trigger automation. Review the diagnostic
   privately; anonymized creator labels require an operator to map them to their
   known migration role configuration. Do not assume current_user created every
   future table or rely on a single role's defaults.
2. Prefer a dedicated application-only migration role. Consider an unexposed,
   app-owned schema through a separately approved migration; do not relocate
   existing public.records automatically. Runtime backend privileges should be
   deliberate and separate from DDL ownership where practical.
3. Prepare a role/schema-specific SQL proposal, diff it and review its effect on
   future application objects only. For example, substitute an approved dedicated
   role in this template; **do not run it as-is or apply it to managed roles**:

   ```sql
   BEGIN;
   ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public
     REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
   ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public
     REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
   -- If that dedicated app-only creator has GLOBAL grants, also propose:
   ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator
     REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
   ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator
     REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
   ROLLBACK; -- Review template only. No privileges have been applied here.
   ```

   Global changes affect all schemas for that creator. Never apply a global
   postgres/supabase_admin default change simply to secure this app; it may affect
   future managed objects. Do not modify auth/storage schemas, managed roles,
   Supabase Auth grants/functions or broadly revoke schema access. The template
   neither creates the dedicated role nor changes current object privileges.
4. Explicitly deny unintended client grants for each future application table
   and sequence and enable RLS in its reviewed migration, in the same transaction
   as creation before sensitive writes. Supply only necessary backend grants.
   Don't assume raw SQL-created tables receive dashboard RLS defaults. Validate
   post-DDL catalogs, because automation/default changes can reintroduce grants.
5. In a separately authorized disposable target, create a throwaway application
   table/sequence using each intended migration role, inspect effective grants,
   RLS and backend access, then clean up the probe. No such DDL probe is run here.
6. Rerun read-only diagnostics and the authorized suite. Separately review Data
   API exposure, RPC paths and privileged keys. Supabase's guidance discusses
   [grants and RLS together](https://supabase.com/docs/guides/api/securing-your-api).

Existing migration `0001_records`, remote grants, Auth, marketplace permissions,
startup configuration and default local SQLite selection are unchanged.

## Changed files

Added `backend/commands/postgres_security.py`,
`backend/integration_tests/__init__.py`, `backend/integration_tests/conftest.py`,
`backend/integration_tests/test_postgresql.py`,
`backend/tests/test_postgres_security.py`, and this document. Modified
`backend/commands/database_check.py` and `docs/SUPABASE-POSTGRESQL.md`.
No migrations, environment values, marketplace authorization, frontend
implementation or deployment configuration changed.

Actual local verification: **317 backend tests passed**, **49 relevant frontend
tests passed**, TypeScript and `git diff --check` passed. The hosted suite reported
**5 skipped**, not 5 passed. No PostgreSQL test or security diagnostic was run
against the hosted database. Existing SQLite, environment files and migrations
retained identical checksums. No frontend source changed, so no production build
was needed for Step 4D.

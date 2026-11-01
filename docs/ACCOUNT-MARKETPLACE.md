# Account marketplace backend — Prompt 3C-1

This is a staged backend implementation. Prompt 3C-2 adds a separate
[real account frontend](ACCOUNT-MARKETPLACE-UI.md); the existing demo remains separate.
Signup/login alone does not change demo ownership. No
deployment, database conversion, or existing record migration is performed.

## Development configuration

Keep the existing Supabase authentication settings from AUTH-FOUNDATION.md.
Set `ENABLE_ACCOUNT_MARKETPLACE=true` only in a controlled development backend
environment when testing this API. The default is false: every `/marketplace`
route returns 404. No production environment is changed. A file-backed SQLite
database or PostgreSQL is required; shared in-memory SQLite is rejected.

Protected requests require `Authorization: Bearer <Supabase user access token>`.
The existing verifier checks the signature, issuer, expiry, audience, authenticated
role and UUID subject. Neither a publishable key, a demo cookie, nor a supplied
buyer/seller/user ID authenticates a request. Missing or invalid authentication
configuration fails closed. There is no fallback to a demo identity.

[Purchase/rental and automatic progression corrections](NEGOTIATION-PROGRESSION.md)
add duration-free purchase terms, explicit rental-duration validation and a public
turn limit. The endpoint paths and ownership checks below remain unchanged.

## Endpoints

| Method and path | Access and behavior |
| --- | --- |
| GET `/marketplace/listings` | Public account listings only; `after` ID and `limit` (1–100) pagination |
| GET `/marketplace/listings/{id}` | Public projection of an available account listing |
| POST `/marketplace/listings` | Authenticated creation, ownership from verified token |
| GET `/marketplace/listings/mine` | Own listings, optional `include_deleted=true`, same pagination |
| GET `/marketplace/listings/{id}/manage` | Owner-only projection including own minimum |
| PUT `/marketplace/listings/{id}` | Owner-only replacement of listing terms with current `version` |
| DELETE `/marketplace/listings/{id}?version=N` | Owner-only archival; atomically cancels unfinished negotiations |
| POST `/marketplace/negotiations` | Authenticated buyer; seller derived from the account listing |
| GET `/marketplace/negotiations` | Only the caller's negotiations, same pagination |
| GET `/marketplace/negotiations/{id}` | Only the verified buyer or seller |
| POST `/marketplace/negotiations/{id}/advance` | Participant-only server-generated AI offer turn, body `{"version": N}` |
| POST `/marketplace/negotiations/{id}/approve` | Participant-only human decision, body `{"version": N, "decision": "approve"}` or `"reject"` |
| POST `/marketplace/negotiations/{id}/cancel` | Participant-only closure of an unfinished negotiation, body `{"version": N}` |

Creation uses the existing listing fields (including the owner's private
`minimum`), without a seller identity. Negotiation creation uses the existing
preferences fields: `listing_id`, private `maximum`, deadline/rental or housing
preferences, pickup location for items, and optional `provider` (`mock` default
or `ollama`). No demo profile is resolved. Self-negotiation is forbidden.
Unknown top-level identity, approvals, status or offer fields are rejected.
Raw browser-supplied offers are not supported; `/advance` uses the existing
independent buyer and seller agents and server validation.

Versions are nonnegative integers, initially zero. Clients must refresh after
409 and explicitly retry with the current version; never blindly replay an
approval. Listing updates require the full listing body plus its version.
All route responses use private/no-store caching directives.

## Ownership, privacy and human decisions

Public listing projections omit seller UUID, private minimum, email and internal
state. Only owner management responses include that owner's minimum and UUID.
Negotiation responses contain public offers/messages and participant IDs, but
exclude buyer preferences/maximum, seller minimum, internal audits and raw
provider errors. Display names are generic until account profile/UI work.
History is participant-filtered; outsiders receive 404 for negotiation IDs.
No account profile or email database is introduced; `/auth/me` remains the
verified account identity endpoint.

Agents receive their own private constraints and public counterpart information.
Only validated public terms and controlled narration enter the conversation.
Agent execution cannot change participant identities, stored private preferences,
listing snapshots, human approvals or terminal human decisions. The approval
boundary revalidates the proposal, constraints, transcript and pickup/move-in
date. Two different authenticated humans must each approve as themselves;
rejection/cancellation is terminal, duplicates and stale versions are rejected.

## Transactions and preservation

New records use `account_listing` and `account_negotiation` kinds in the existing
`records` table. All reads and writes are namespace-scoped, including legacy
store writes. Demo IDs cannot address account data and vice versa. There is no
schema change, Alembic revision, stamping, automatic ownership mapping, deletion
or rewrite of existing SQLite records. Existing migrations remain unchanged.
For a fresh PostgreSQL database follow the existing baseline migration procedure
in POSTGRESQL.md before enabling the API. Back up before any future data migration.

SQLite writes use short `BEGIN IMMEDIATE` transactions. PostgreSQL mutations lock
the listing row first. Both use version-and-owner/participant conditional updates.
Inference runs outside the write transaction, then checks the current version
before committing. Concurrent approval requests cannot overwrite each other's
decision; a stale request must refresh and retry. Finalization is recorded once.
Tests include simultaneous requests from separate Python processes against a
temporary SQLite file. PostgreSQL SQL compilation is tested, but no live
PostgreSQL connection or runtime concurrency has been tested.

Active negotiations freeze listing term edits. Either participant may cancel to
close a negotiation. A seller can always withdraw their own listing: one atomic
transaction archives it and cancels unfinished negotiations. Completed agreements,
private state, history and audit records are retained. A withdrawal racing the
last approval is serialized; an agreement already confirmed remains recorded.

## Demo boundary and launch limitations

Legacy listing, profile, negotiation, approval, session and judge endpoints keep
their existing demo behavior and only access demo record kinds. Demo identity
switching cannot select a Supabase UUID or authorize this API. Account Bearer
headers are rejected by demo identity/session switching flows. No account data
is copied into demo identities. Existing demo initialization remains unchanged.

Before public deployment, remove or restrict legacy demo endpoints at the
application/network boundary; do not expose development/demo identity switching.
Keep the existing non-development Supabase/demo safeguards and do not rely on
`PUBLIC_DEMO_MODE` as account authorization. The new feature flag does not make
legacy endpoints safe for public account traffic.

Prompt 3C-2 now connects separate account listing management, preferences, participant
history and human approval screens to this API, attaching real user access tokens
and handling versions/409s. The account UI has no demo identity selector.
Public launch also requires abuse/rate controls, real PostgreSQL transaction and
permissions/TLS testing, database/Data API access policies, and explicit inventory
reservation rules. Atomicity is per negotiation: this prompt does not prevent
multiple distinct negotiations for one listing from independently confirming,
reserve stock, process payments or guarantee a housing reservation. Existing demo
records need an explicit reviewed mapping if ownership migration is ever desired.

The backend tests use independent signed test-user tokens with mocked JWKS,
temporary databases and local HTTP requests; no real Supabase credentials or
hosted database are required. Run `pytest backend/tests/test_account_marketplace.py`
with the project's virtualenv, followed by the full backend suite.

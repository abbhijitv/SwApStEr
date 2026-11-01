# Real account marketplace UI — Prompt 3C-2

Open `/marketplace/account` using **Real marketplace** in account navigation or
**Open real marketplace** on `/account`. This extends the existing white/blue
marketplace style. `/marketplace` remains the separate demo, including its demo
profile selector. `/b2b` is unchanged. Failures never fall back to demo records.

## Local testing configuration

The exact existing backend flag is `ENABLE_ACCOUNT_MARKETPLACE`. It remains
false by default. Without it the UI displays an unavailable message. No new
browser feature flag or credentials are needed. Do not change production settings.

Use a local development process with the existing private `.env` authentication
settings (never paste keys into commands, documentation or commits):

```sh
ENABLE_ACCOUNT_MARKETPLACE=true .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
npm run dev --prefix frontend
```

Run these in separate terminals. Stop an existing backend yourself before starting
another on the same port; do not reset its database. Use `http://localhost:3000`
for the frontend and its existing `NEXT_PUBLIC_API_URL` pointing to the local API.
Supabase URL/publishable-key configuration must match the backend project. The
existing backend CORS permits localhost:3000. The account transport permits local
HTTP only in development; a production build requires an HTTPS account API.
Changing the flag only for that backend process leaves its default disabled.

See [purchase/rental contracts and automatic progression](NEGOTIATION-PROGRESSION.md)
for the subsequent correction, limits, pause/resume behavior and test scenarios.

## Screens and contracts

- **Browse listings:** public account data, details, empty/loading/error states,
  and pagination. Public reads send neither access tokens nor demo cookies.
- **My listings:** token-authenticated own listings, including withdrawn records;
  create, full term edit, owner minimum management, and confirmed withdrawal.
  Withdrawal archives the listing and cancels unfinished negotiations atomically.
- **My negotiations:** participant-filtered history, offers and transcript,
  buyer/seller approval states, bounded automatic agent progression, independent human
  approve/reject buttons, cancellation and refresh. Open negotiations poll every
  three seconds while visible; hidden pages pause polling.
- **Forms:** item rental/sale and housing fields use the actual backend schema.
  Owner editing preserves all existing pickup windows. Item buyer preferences
  currently submit one pickup window. Housing includes lease dates, preferences
  and the landlord-approval disclaimer. Provider selection is explicit: mock is
  deterministic, Ollama requires the existing local inference setup.

The typed client connects to the listing browse/detail/mine/manage/create/update/
withdraw and negotiation start/history/detail/advance/approve/cancel endpoints
listed in [the backend contract](ACCOUNT-MARKETPLACE.md). No backend endpoint,
constraint, authentication rule or database schema is changed by this prompt.

The shared account transport asks the Supabase SDK for the current session token
for each protected request and sends it as a Bearer header. FastAPI remains the
identity and authorization authority. No browser-supplied actor, buyer or seller
ID is sent as authorization. Requests omit cookies, prohibit redirects, use
no-store caching and never automatically retry mutations. Public listing reads
never attach a token. The demo transport remains unchanged.

Errors distinguish 401, 403, 409, validation, missing records, disabled API,
network and service failures. Raw upstream errors/private validation inputs are
not rendered. A 409 disables actions until the user refreshes and reviews current
state; refresh never replays approval. Pending operations use an immediate ref
lock plus disabled controls to prevent double submission. Finalization appears
only when the backend returns `Confirmed`, never from counting clicks locally.

Private inputs and owner-only listing state stay in React memory. They are not
written to browser storage, URLs, logs or shared transcripts. The negotiation UI
renders only the backend's authorized public offer/message fields, never a raw
JSON debug view. Changing account or signing out unmounts the account workspace;
401 clears private forms, listings and participant history. SDK-managed auth
cookies remain the existing session mechanism. Identity comparisons control UI
labels only; the backend enforces every permission independently.

## Automated verification

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python frontend/tests/support/run-account-marketplace.py
npm run typecheck --prefix frontend
npm run build --prefix frontend
git diff --check
```

The integration runner copies frontend source into temporary configured and
unconfigured projects, uses a synthetic local Auth test double and a temporary
SQLite database, and launches spare ports 3101/3102/8101/55421. It refuses occupied
ports and cleans up only its own processes/files. It never reads real frontend
`.env.local` into the copies or contacts a Supabase project. Chrome must be at the
path configured in Playwright. A test-only route bridge supplies CORS for the
spare frontend origin; production CORS is unchanged. Tests exercise independent
browser sessions and real FastAPI marketplace routes, as well as mocked error
responses. They do not prove live Supabase or PostgreSQL connectivity.

Verification for this implementation: 271 backend tests and 56 relevant frontend
tests passed; TypeScript, the production build and `git diff --check` passed.
The frontend run includes two independent synthetic accounts using the real
FastAPI routes and a temporary SQLite database. Live Supabase, live PostgreSQL
and live Ollama inference were not tested in this prompt.

## Manual test with two Supabase accounts

1. Enable the flag only on the local backend process as above. Confirm `/health`
   and the existing `/account` secure API check work. Use a development Supabase
   project with its existing localhost callback allowlist. Do not deploy.
2. Use a regular browser profile for seller A and a separate private/browser
   profile for buyer B. Sign up, confirm email and log in independently. Ordinary
   tabs share cookies; do not use a demo profile switch to represent B.
3. As A open **Real marketplace → Create listing**. Create an item with asking
   price 35, private minimum 20, rental duration 3, a future pickup window, and
   availability extending at least three days beyond pickup. Publish it.
4. In **My listings**, edit A's listing and save. Verify B's **My listings** does
   not offer management controls for it. Anonymous browsing should show the item
   without the private minimum or seller UUID. Demo listings should be absent.
5. As B browse the real item, open its details and start negotiation. Set target
   15, private maximum 27, duration 3, overlapping future pickup window, a later
   completion deadline, and a public pickup location. Choose mock for a repeatable
   workflow or Ollama only if configured locally.
6. Agents advance automatically until **Prepare human review**. Prepare review. A
   opens the same item through **My negotiations**. Each sees their own role and
   only public offers/history, without the other person's price limits.
7. B approves as buyer. Verify the deal remains awaiting approvals and A remains
   unapproved. Refresh A's view (or wait for polling) and approve as seller. Both
   views should show **Confirmed — both people approved** only after that response.
8. In another negotiation, reject or cancel and verify further approval controls
   disappear. Verify seller withdrawal cancels unfinished negotiations and retains
   their history. A confirmed record must remain recorded after withdrawal.
9. Open one proposal in two seller tabs. Act in one, then act from the stale view
   before polling updates it. On 409, verify explicit refresh/review is required;
   no automatic duplicate approval is sent. Expired sessions should prompt login.
10. Log out; private account state must disappear. Check `/marketplace` demo profile
    switching and `/b2b` remain separate. Stop the flagged backend and restart it
    without the flag; the real marketplace should display unavailable.

Live two-account Supabase testing is still required; automated tests use synthetic
identities. No real two-account Supabase or live PostgreSQL test is claimed.

## Remaining limitations before public launch

Backend launch restrictions still apply: restrict/remove legacy demo access,
validate hosted PostgreSQL concurrency and access policies, and add abuse/rate
controls. Multiple distinct negotiations can confirm for the same listing; no
inventory reservation, stock enforcement, payment or guaranteed housing booking
is implemented. Participant display names remain generic. No automatic migration
of demo ownership is provided. Existing active negotiations freeze listing term
edits; cancellation or withdrawal is required to release them. This prompt does
not authorize deployment.

## Files

Created `frontend/app/marketplace/account/page.tsx`, its `marketplace.css`,
`frontend/lib/api/marketplace.ts`, `frontend/tests/account-marketplace-api.spec.ts`,
`frontend/tests/account-marketplace.spec.ts`, the isolated runner
`frontend/tests/support/run-account-marketplace.py`, and this document.
Modified `frontend/lib/api/authenticated.ts`,
`frontend/app/components/account-nav.tsx`,
`frontend/app/components/auth-screen.tsx`, `frontend/tests/auth-ui.spec.ts`,
`frontend/tests/supabase-foundation.spec.ts`, `README.md`,
`docs/ACCOUNT-MARKETPLACE.md`, `docs/AUTH-FOUNDATION.md` and `docs/AUTH-UI.md`.
No backend implementation or migration was modified.

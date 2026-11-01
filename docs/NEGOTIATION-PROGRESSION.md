# Account purchase/rental negotiations and automatic progression

This correction applies to `/marketplace/account`. It does not deploy anything,
change credentials, migrate records or enable the account API by default.
`ENABLE_ACCOUNT_MARKETPLACE=true` is still a local backend process opt-in.

## Root causes and contract changes

The account buyer form rendered rental duration for every item, and the shared
structured item terms required it. New account purchase negotiations now omit
`rental_days` in the request and stored buyer preferences. The backend derives
purchase mode from the authenticated listing, not a caller-supplied transaction
flag. Purchase terms use `transaction: "purchase"`, require pickup/location and
price, and prohibit rental duration and lease dates. Public purchase offers,
agreements and history omit rental duration and return dates. The UI also uses
the listing type to hide these facts for legacy purchase history.

Rental negotiations explicitly require `rental_days` (integer 1–90), with the
existing matching-duration and availability checks. Pickup windows, deadline and
location remain required for both item purchases and rentals. Housing keeps its
existing lease contract. Negotiation responses add public `turn_limit`, capped at
8 and honoring a lower backend `MAX_NEGOTIATION_TURNS`.

Legacy `transaction: "item"` terms and stored durations remain readable and
validatable. Existing records are not rewritten. The demo keeps its legacy
request contracts and mock strategy; no database schema change or migration is
needed. Previously terminal negotiations remain terminal; starting a new
negotiation requires the normal authorized API operation on an available listing.

The Ollama structured-output schema now supports duration-free purchase terms.
Its pricing strategy is unchanged. Legacy demo purchase contexts keep the old
compatibility schema. No real Ollama inference was tested for this correction;
its purchase schema is tested with mocked generation and narration.

## Exact automatic behavior

Previously the account screen invoked only a single turn per button click. It now
runs a bounded foreground loop when a participant opens or starts a negotiation
whose server status is `Negotiating`. After a short display delay it:

1. Reads authoritative server state using the existing participant-protected GET.
2. Stops if status is not `Negotiating`, the provider reports an error, or the
   server turn limit has been reached.
3. Submits one existing `/advance` request with the fetched version and displays
   the actual returned messages/status. It never manufactures messages or terms.
4. Stops immediately at `Agreement proposed`, `No agreement`, or any other
   non-negotiating status. Otherwise it waits roughly 650 ms between turns.
5. On 409, reloads state before considering another turn, never reusing a stale
   version. Each run permits at most eight advance attempts, including conflicts.
   Network/auth/provider errors pause for explicit user action; no blind retries.

A shared UI request lock prevents concurrent local progression actions. Independent
browser tabs can still race, but the unchanged backend versioned transactions
permit one state transition per version. Cross-tab duplicate inference can occur;
committed turns and approvals cannot overwrite each other.

The loop never advances from a proposal into human review and never calls the
approval endpoint. **Prepare human review** performs the existing explicit
transition to `Awaiting approvals`; then each independently authenticated person
can approve only their own side. Only backend `Confirmed` finalizes the UI.

**Pause automatic negotiation** stops scheduling more turns. An already submitted
request can finish and commit; pause does not roll it back or abort server-side
inference. Wait for the current request before cancelling through **Cancel
negotiation**. Cancellation remains an authorized, versioned backend operation.
Hidden pages pause scheduling; reopening requires Resume. Leaving the workspace
or logging out stops scheduling. No background server job or new run endpoint is
introduced. A currently running turn may still complete after leaving the page.

The URL retains only `?negotiation=<record ID>`. Reloading fetches that authorized
record and resumes from the latest version; it stores no limits, transcripts or
tokens in browser storage or URLs. If a request committed before a lost network
response, the next GET observes its newer version. Pausing is page-local; another
participant/tab may continue advancing, and a refresh starts a fresh bounded run.

## Mock convergence and privacy

The old mock increased item offers by only $5 and decreased counters by $10,
regardless of asking price. This exhausted eight turns on expensive items.
Account mock contexts now include only a public round budget. Each agent makes
proportional concessions within its own bounds and can accept a compatible public
offer. Normal eight-turn runs can reach a mutually valid proposal even for large
prices or a narrow overlap. Non-overlapping bounds cannot produce an agreement:
all offers and acceptances still pass the coordinator's original role-specific
and joint validation, including dates, duration and availability.

Private bounds are never sent to the other agent or exposed as response fields,
limit labels or raw provider errors. An authorized public offer may naturally
coincide with a participant's bound; its status as a private bound is not exposed.
User-entered constraints are not changed. Deterministic mock is always labeled
as mock and is not represented as live AI. Existing live-provider concession
strategy is unchanged, so convergence is not guaranteed for every provider,
turn budget or combination of non-price constraints.

## Verification and manual testing

Run the full backend suite and the isolated frontend integration runner described
in [account marketplace UI setup](ACCOUNT-MARKETPLACE-UI.md), followed by
TypeScript, production build and `git diff --check`. The runner includes pure
orchestration tests, real FastAPI requests against temporary SQLite, synthetic
independent accounts, and mocked provider/schema/error tests. No real Supabase
accounts or PostgreSQL connectivity are claimed.

Latest verification: **290 backend tests passed**, **75 relevant frontend tests
passed**, TypeScript checks and the production frontend build passed, and
`git diff --check` passed. The browser suite uses synthetic Auth and temporary
SQLite, including independent buyer/seller sessions and reload recovery.

To test manually, enable the flag only for the local backend, run the frontend
in development at localhost:3000, and use separate browser profiles:

1. Seller A logs in and publishes **For sale**: asking $1,000, private minimum
   $900, future pickup window, future availability. No rental days are needed.
2. Buyer B logs in, opens the item, selects **Buy / Negotiate purchase**, and sets
   target $500, private maximum $950, an overlapping future pickup window, pickup
   location and valid deadline. Select deterministic mock.
3. Start once. Observe authentic agent offers progress without Advance clicks.
   Pause/resume, then refresh; the record should recover from server state.
   Purchase screens/history must show no rental duration or return date.
4. At **Agreement proposed**, choose **Prepare human review**. B approves as buyer.
   A opens My negotiations and independently approves as seller. Confirmation
   must appear only after both approvals.
5. Repeat with buyer maximum $800. Expect **No agreement**, no fabricated proposal
   and no human approval controls. Starting again requires new explicit inputs.
6. For a rental, A lists asking $35/minimum $20, rental duration 3 days and pickup
   availability covering the return date. B chooses target $15/maximum $27 and
   matching 3 days. Verify required duration, automatic progression, pickup/return
   summaries, separate approvals, rejection and cancellation.

Public launch limitations from the account backend still apply, including legacy
demo restrictions, abuse controls, PostgreSQL runtime validation and inventory
reservation across distinct negotiations. This correction does not authorize a
public rollout or alter the existing live database.

## Files changed for this correction

- `backend/models/schemas.py`, `backend/models/marketplace_schemas.py`
- `backend/agents/negotiation_coordinator.py`, `backend/agents/mock_provider.py`,
  `backend/agents/ollama_provider.py`
- `backend/services/account_marketplace.py`, `backend/tests/test_account_marketplace.py`
- `frontend/app/marketplace/account/page.tsx`, `frontend/lib/api/marketplace.ts`
- New `frontend/lib/api/negotiation-runner.ts` and `frontend/tests/negotiation-runner.spec.ts`
- `frontend/tests/account-marketplace.spec.ts`, `frontend/tests/support/run-account-marketplace.py`
- This document, `docs/ACCOUNT-MARKETPLACE.md`, and `docs/ACCOUNT-MARKETPLACE-UI.md`

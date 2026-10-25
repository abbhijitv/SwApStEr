# Submission hardening — privacy-safe audit and approval integrity

Inspected clean repository at `0ac7f05`. This change is backend-only: no provider, strategy, frontend, dependency, route name, table name, secret, or deployment configuration was changed. No commit, push, or deployment was performed.

## Existing safeguards retained

- Independent buyer/seller contexts contain only each principal's private limits and shared offers.
- Decimal price constraints, seller asking-price ceiling, pickup overlap/deadline, rental duration/availability, and exact acceptance checks are enforced server-side.
- Negotiation length and repeated-offer limits remain unchanged.
- Sessions resolve an opaque HttpOnly cookie server-side; submitted approval names/roles do not authorize actions.
- Only the two actual participants may inspect or approve their negotiation. Self-negotiation is blocked.
- Both approval flags are required; rejection closes the proposal; duplicate and closed-state decisions return HTTP 409.
- A per-negotiation process lock serializes advance/approval mutations. Ollama inference remains sequential. Mock and Ollama implementations are unchanged.

## Changes

### Internal structured audit

`backend/services/audit.py` creates allowlisted events stored in `audit_events` inside the existing negotiation JSON record. Events and state changes are saved in the same SQLite row commit. There is no new table, schema migration, public audit endpoint, or dependency. Existing records acquire audit history only when new relevant events occur; prior records are not backfilled or rewritten.

Each event records category, negotiation ID, turn (when valid/applicable), role, action type, validated public price when appropriate, validation result, safe rejection code, and UTC timestamp. Supported categories are `offer_proposed`, `offer_accepted`, `offer_rejected`, `constraint_violation`, `approval_recorded`, and `agreement_finalized`.

No free-form reasoning, prompts, message text, private preferences, student tokens, keys, or private limit fields enter events. Invalid proposals omit their attempted price entirely. Rejection reasons and roles are allowlisted; malformed turn metadata is omitted. Public session/history projections exclude the entire audit field as well as private preferences. Duplicate/stale/unauthorized denials are audited without advancing the negotiation version.

Operators can inspect `get('negotiation', id).get('audit_events', [])` on the backend. Only print that selected audit field, not the complete private negotiation record. Old records without events return an empty list. This is internal diagnostic history, not an immutable or tamper-proof external log.

### Approval state boundary

Before accepting a human decision, the backend now rechecks:

- A valid agreement exists and remains compatible with the actual listing and private constraints.
- Buyer/seller are distinct, the seller owns the listing, and exactly those two IDs have Boolean approval slots.
- A real outstanding offer and opposite-role ACCEPT exist in the saved transcript and match the agreement using typed price/datetime comparisons.
- Rental return time matches pickup plus the agreed duration; purchases have no return deadline.
- Rejected, missing, malformed, inconsistent, or failed proposals cannot finalize.

Existing successful flows and both approval orders continue to work. An ordinary invalid request still returns 403/409 as appropriate. New denial audit entries do not change status, approval flags, terms, or version.

### Hosted demo privacy

`PUBLIC_DEMO_MODE=true` continues to permit the existing hosted demo sessions/profiles. Judge Mode now independently requires `APP_ENV=development`, so enabling public demos cannot expose the private debug view in production—even with its debug flag set and a loopback/proxy client.

## Verification

Commands actually run:

```bash
.venv/bin/python -m pytest -q
git diff --check
```

- Baseline: **67 passed**.
- Updated complete suite: **98 passed** (31 new cases).
- Diff whitespace check: passed.
- SQLite integrity_check: `ok`.
- All **477** existing database records are identical to the pre-change backup. Tests use isolated temporary SQLite databases; no live records were deleted or reset.
- Frontend TypeScript/build were not rerun because no frontend files or API response shapes changed.
- No new genuine Ollama inference run was needed for these audit/state changes. Existing provider/decision/narration regression tests passed, including the Ollama boundary tests; the model and strategy code were not modified.

New coverage exercises public response/context privacy with distinct private-value sentinels; price-bypass attempts; incompatible schedules; 12 malformed proposal variants; invalid lifecycle states; role spoofing and third-party approval; duplicate and stale requests; audit persistence/field whitelisting; stall logging; public-demo/Judge isolation; and concurrent approval behavior.

Threaded API tests verified: independent buyer/seller approvals finalize once, concurrent duplicate buyer requests cannot fill the seller slot, and simultaneous seller approve/reject after buyer approval have exactly one successful terminal winner. State and audit match the winner.

## Files changed

- `backend/services/audit.py` — new allowlisted internal event builder.
- `backend/agents/negotiation_coordinator.py` — audit hooks, hidden audit projection, and approval-boundary validation helper; no strategy change.
- `backend/routes/negotiations.py` — validated/audited approval decisions and stale-version denials; production Judge guard.
- `backend/tests/test_security_audit.py` — 31 API/privacy/audit/state/concurrency cases.
- `docs/SECURITY-AUDIT.md` — this report.

## Deployment and limitations

This is a backwards-compatible backend change suitable for review and the existing **single-worker** demo deployment. No migration or frontend redeploy is required. Remote Render/Vercel integration was not tested or deployed during this task; hosting and cookie settings remain unchanged.

Run one backend worker. The process-local lock does not provide cross-worker or cross-instance serialization; SQLite's atomic row commit alone is not a replacement for that coordination. A larger transactional locking/CAS refactor was deliberately skipped under the hackathon deadline. SQLite/audit durability still depends on the existing persistent-disk setup. Audit retention, rate limiting, and tamper-proof external logging are not included.

Demo identities are not production authentication: anyone permitted to use the demo switcher can select a profile. Tests prove participant enforcement for the selected server-managed identity, not real-world identity verification. Production authentication was not added or claimed.

## Hackathon pitch

“Two student agents share public offers while keeping their private limits separate. The backend checks every deal and both independent approvals, and records a privacy-safe decision trail—even when requests are duplicated or arrive concurrently.”

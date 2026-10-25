# Two-student deal approval

The existing backend approval endpoint remains the single source of truth. It already resolved the acting student from an opaque HttpOnly cookie, restricted access to the actual buyer/seller, rejected duplicate decisions, persisted approvals, and required both students before confirmation. The agent providers and negotiation engine are unchanged.

## What's added

- Approve Deal / Reject Deal controls for the selected participant, with the active student's name shown above them.
- Named Approved/Pending indicators, derived from the stored approval map, and buyer-approved/seller-approved statuses in history.
- After approving: “You approved this deal.” and “Waiting for [other student] to approve.” The proposal stays pending.
- After both approve: “Deal confirmed! Both students approved.”
- Rejections now also store `rejected_by` and `rejected_at`. Legacy rejected records remain readable without these optional fields. Rejection closes the proposal permanently.
- Approval/rejection increments the existing negotiation version. Polling ignores older responses so a stale GET cannot undo a freshly displayed decision.
- Open proposals poll GET /negotiations/{id} every 2.5 seconds after the previous request completes. Hidden tabs pause; returning to the tab refreshes immediately. Requests/timers are cleaned up on navigation, student switch, or terminal status. Temporary failures display a retry notice without discarding the proposal.
- Copy negotiation link and a selectable fallback URL. The link contains only the existing negotiation ID; no student ID, role, session token, or private preference. Sharing it never authenticates a student.
- History shows the deal number to distinguish repeated negotiations for the same item.

The SQLite record structure is retained. No database reset or schema migration is needed; optional rejection metadata is written only for new rejection decisions. Existing records remain unchanged. A pre-change backup was created under ignored backups/.

## Two-browser demonstration

1. Start the app with `./scripts/start.sh` and visit http://localhost:3000 in regular Chrome. Select Abbhijit.
2. Open a separate Incognito session and visit the same URL. Select Shorya Moses. Regular Chrome tabs share cookies and therefore the active demo profile; independent browser profiles/Incognito contexts isolate them.
3. In the buyer window, select the seeded TI-84 calculator owned by Shorya. Submit compatible target/budget, pickup, rental duration, and deadline. Select Ollama for real local inference or mock for the reliable backup.
4. Wait for the agents' proposal. Review the item, price, rental duration, pickup/location, buyer, seller, and their pending decisions.
5. In Abbhijit's window click Approve Deal. It shows his approval and the waiting message; the deal is not confirmed.
6. In Shorya's window open My negotiations and select the same deal number. It displays identical terms, the buyer's approval, and Shorya's own controls. Alternatively, copy the negotiation link from the proposal and paste it into the independently selected seller session.
7. Approve as Shorya. Both visible windows update to the confirmed state within the polling interval, without a manual refresh. If the buyer window is hidden/minimized, restore it to trigger refresh.
8. Select Oumar in a separate session. The link does not grant access, the proposal is not displayed to him, and approval requests return HTTP 403.

Seller-first approval works identically. Either participant may reject before making their own decision; both views then show rejection and no further approval is permitted. There is no automatic renegotiation.

The optional single-window “Switch student to review” control is preserved for demos, alongside the independent-session flow. Demo profile selection intentionally allows anyone at the local machine to choose a profile; this is not production authentication. Run one backend worker because mutation locks are process-local.

## Verification

See docs/VERIFICATION.md for the completed test results. Backend tests cover both approval orders using independent session cookies, duplicate prevention, unrelated-student rejection, persisted state, private response filtering, and rejection after the other party approves. Browser coverage exercises two isolated contexts, seller history access, copied-link authorization, live confirmation/rejection, terminal polling cleanup, and temporary polling failure recovery. The optional real Ollama browser test uses the seeded TI-84 and separate buyer/seller contexts.

## Completed verification — October 25, 2026

- All backend tests: **30 passed** (26 existing plus four approval-order/rejection cases).
- TypeScript check and production build passed.
- All **10 distinct Chrome regression cases passed across the suite and targeted reruns**: four new approval cases, three original marketplace/mock cases, hydration, real Ollama, and dynamic profiles.
- The first combined browser run passed eight cases, then was interrupted after the real model proposed invalid terms and the existing validator paused the negotiation. This was not an approval bypass: no deal was confirmed. The remaining two cases were subsequently run and passed individually.
- The real seeded TI-84 test used a compatible $20 target and $25 maximum and completed four independent Ollama actions in session 169. Final price $20; pickup October 28, 2026 at 5 PM Arizona time, Hayden Library; return October 31 at 5 PM. Buyer approval alone remained pending; the separate seller session approved; both pages updated to Confirmed. Oumar received HTTP 403. No mock switch or model/engine change was used.
- Two separate mock-browser tests verify both approval orders. Another verifies that seller rejection after buyer approval updates both pages and stops polling. A temporary-503 test verifies automatic polling recovery.
- Copy-link authorization, participant history access, approval persistence after reload, and terminal polling cleanup passed.
- All 106 records from the pre-change backup remain identical on disk after verification. SQLite integrity_check is ok. Test-created records were retained.

The existing local CampusSwap servers were restarted to load the backend change and verified production build; the app is available at http://localhost:3000, with the API on port 8000. No Git commit, history change, or push was performed.

Files changed: backend/routes/negotiations.py, backend/tests/test_approvals.py, frontend/app/page.tsx, frontend/app/globals.css, frontend/tests/approvals.spec.ts, frontend/tests/ollama.spec.ts, frontend/tests/demo.spec.ts, frontend/tests/profiles.spec.ts, README.md, docs/VERIFICATION.md, and this file. The agent/model implementation was not changed.

Known limits remain local demo identity, process-local mutation locks (one backend worker), shared cookies across regular tabs, and potentially invalid real-model proposals that must be blocked rather than forced into a deal. Explicit retry/mock controls remain available. These do not relax dual approval or participant authorization.

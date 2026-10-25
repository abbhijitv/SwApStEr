# Housing & Subleases demo

Start the existing stack from the repository root:

```sh
ollama serve # only if Ollama is not already running
./scripts/start.sh
```

Open http://localhost:3000. Existing dependencies and `qwen2.5:3b` are reused. No new dependencies or paid services are required. Use separate browser profiles or an incognito window for independent student sessions.

## Successful arrangement

1. Select **Shorya Moses** (or any student). Click **List an item**, then select **Housing & Subleases**.
2. Enter a title and description; choose **Private room sublease**. Set monthly asking rent **900**, private minimum **750**, neighborhood **Tempe campus**, lease start **2027-05-15**, lease end **2027-08-15**, furnished **yes**, utilities included **yes**, one bedroom and one bathroom. Publish.
3. Select **Abbhijit** (or another student). Use the **Housing & Subleases** filter, open the listing, and click **Let My AI Negotiate**.
4. Enter private maximum monthly rent **850**, move-in **2027-06-01**, move-out **2027-08-01**, flexibility **0**. Leave preferences at Any and choose **Deterministic mock**.
5. Start negotiation. Mock offers **$765/month** and the owner’s agent accepts because it satisfies the owner’s minimum. The proposal covers the complete requested stay, June 1 through August 1. The exact price follows the provider’s strategy; it is not a hardcoded example agreement.
6. Approve as the interested student. The arrangement remains pending. Open its copied negotiation link in the other student’s session and approve separately. The UI now says **Housing terms mutually accepted**. Both approvals and the housing disclaimer remain visible.
7. Repeat with **Real local AI · Ollama / Qwen 2.5 3B** to use the existing local model. Inference can be slow. Model failures remain explicit; switching to mock requires a deliberate action. Unsafe narration may use a labeled safe wording fallback without replacing the validated model decision.

## Failed arrangement

Repeat with maximum monthly rent **700** against the same listing. No price can satisfy both students; mock stops within eight turns with **No agreement**, and approval is blocked.

Alternatively, request **2027-05-01** through **2027-08-01**, with zero flexibility. The available property starts May 15, so the full required stay cannot be provided. The backend fails immediately rather than substituting a partial overlap. Requests ending after August 15 also fail.

For a flexibility demo, request May 13 through August 1 with **2** days of move-in flexibility. May 15 is permitted; the move-out date remains August 1.

## Data and security

Housing is an optional nested `housing` object inside existing JSON listing and negotiation records. Asking rent uses existing `price`; private minimum uses existing server-only `minimum`. No SQL table migration, bulk rewrite, or database reset occurs. Old records without housing fields retain their item behavior. The pre-change SQLite backup is `backups/swapster-before-housing-20261025-093207.db`.

Monthly rent, full lease dates, furnished/utilities requirements, location, and optional move-in flexibility are checked deterministically. Approval rechecks the complete proposal and actual listing ownership. Both participants must approve; unrelated and duplicate approvals remain blocked. Private preferences and audit events are omitted from public negotiation responses; the narrator sees only already validated public facts.

Optional special requirements remain private notes to the interested student’s agent, not automatically guaranteed contract terms. Optional roommate information is public listing information. Existing image infrastructure has no photo uploads, so housing uses a distinct house illustration. There are no payments, lease signatures, legal documents, or landlord approval integrations. The existing demo profile/session system is unchanged.

> This agreement records the students' proposed terms only. Any sublease remains subject to landlord or property-manager approval, applicable lease restrictions, and required documentation.

## Checks

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
npm run typecheck --prefix frontend
npm run build --prefix frontend
# With backend and frontend running:
npm run test:e2e --prefix frontend
```

The existing real item-inference browser test is opt-in (`RUN_OLLAMA_E2E=1`) because it needs a running model. Housing provider decision schemas, private context separation, invalid model actions, public narration, date/rent constraints, and approval validation have automated backend coverage. The housing browser test exercises creation, browsing, monthly displays, independent approvals, failure, and mobile layout.

## Changed files

- `backend/models/schemas.py`: optional housing listing/preferences models and transaction-aware terms.
- `backend/agents/housing.py`: deterministic full-stay, location, preference, and monthly-rent validation.
- `backend/agents/negotiation_coordinator.py`: housing routing and proposal/approval compatibility.
- `backend/agents/mock_provider.py`: monthly-rent bargaining and housing messages.
- `backend/agents/ollama_provider.py`: housing-specific decision schema and public narration instructions; original item schema retained.
- `backend/agents/seller_agent.py`: owner's housing details in its own agent context.
- `backend/agents/narration.py`: date fact tokens, monthly units, false-acceptance and repetition guards.
- `backend/routes/negotiations.py`: require preferences matching the actual transaction type.
- `frontend/app/housing.tsx`: conditional forms, metadata, date formatting, and disclaimer.
- `frontend/app/page.tsx`: housing browsing, creation, negotiation, history, and approval summaries.
- `frontend/app/globals.css`: housing illustration and metadata styles.
- `backend/tests/test_housing.py`: housing, privacy, security, provider, and compatibility coverage.
- `frontend/tests/housing.spec.ts`: complete mock housing browser flow and mobile layout.
- `README.md`, `HOUSING_DEMO.md`: feature overview and demo instructions.
- `frontend/next-env.d.ts`: regenerated by the production build to reference production type files.

## Verification on October 25, 2026

- Complete backend suite: **126 passed** (98 existing and 28 housing checks).
- TypeScript and production build: passed.
- Full Chrome suite with `RUN_OLLAMA_E2E=1`: **13 passed**, including real item negotiation and independent approvals.
- Real housing inference: Ollama proposed **$780/month, June 1–August 1, 2027** and the other agent accepted. Both students approved successfully in an isolated temporary database. Public wording failed the strict narration checks and used the explicit safe narration fallback; the decisions remained Ollama-generated.
- SQLite integrity: **ok**. All **492** records from the backup remain identical, including **30 listings** and **103 negotiations**. Browser verification adds demo records; it does not remove or rewrite old ones.
- Clean Chrome with extensions disabled reported no hydration warnings. Housing mobile layout has no horizontal overflow.
- During development, one audit assertion accidentally matched timestamp digits, and one new browser selector used the wrong exact label. Both were corrected and the affected tests passed on rerun. The real model’s false opening acceptance and repeated housing wording were caught and guarded by regression tests.
- After the final housing summary/thumbnail cleanup, production rebuild passed again and the focused housing + hydration browser recheck passed **2/2**.

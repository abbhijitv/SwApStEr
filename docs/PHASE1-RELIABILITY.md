# Phase 1 — Ollama reliability

Phase 1 only. No frontend/UI files were modified under the new phase checkpoint. The previously committed UI was preserved. No Git reset, clean, commit, or push was performed. Initial Git status was clean at eb915e8.

## Root cause

The old implementation coupled valid structured decisions to a fragile public-wording pass. Narration ran before the coordinator completed action validation and raised ProviderError after two wording failures, pausing negotiations at turn zero or one. Observed public responses quoted the incoming price instead of the new counter, omitted the current price, invented earlier-offer context, and used generic phrases such as “rental days” that the numeric checker incorrectly rejected. Purchase prompts could also produce rental or listed-price language. These were actual observed model/validator interactions, not an assumption that price/schedule enforcement was too strict.

## Implemented boundary

1. Genuine Ollama generates only the structured action using its principal’s private context. Decision inference remains sequential and bounded to two attempts. Invalid decisions still produce a safe error; they never use mock strategy or a forced agreement.
2. The coordinator validates price, seller asking-price ceiling, scheduling, duration, location, outstanding-offer acceptance, and allowed offer/counter transitions before narration.
3. A separate public-only narration method sees the validated terms, public item type, recent public offers, and up to four public messages. Purchase prompts omit the internal rental_days compatibility field. It receives no private limits.
4. Narration receives at most two attempts with sanitized fixed-reason logging and a concise repair instruction. Equivalent public facts are normalized; conflicting figures and invalid transaction/first-turn wording are rejected.
5. If narration still fails, neutral wording is rendered from the already validated action. It does not change strategy, provider, price, scheduling, or acceptance. Each saved message records narration_source as ollama, safe_fallback, or mock.
6. Role-prefix cleanup and duplicate-message/listed-price guards improve wording without weakening financial or approval validation. Buyer bids are capped at the public asking price as well as their private maximum. Mock purchase prose no longer mentions rental duration.

## Verification

- Full backend pytest suite: **64 passed**.
- git diff --check passed.
- A bounded genuine qwen2.5:3b smoke run used a disposable SQLite database and two independently authenticated TestClient sessions. No inference response was supplied or replaced by the test.
- Rental reached a proposal, buyer approval alone stayed pending, and seller approval confirmed it.
- One genuine textbook purchase opening was generated. Its narration was separately rechecked after tightening listed-price and duplicate-wording guards.
- The smoke run made 11 genuine inference calls: 4 decisions and 7 narration attempts. The focused purchase narration recheck used at most two more calls. No additional full negotiation loop was run.
- All 292 records from the Phase 1 pre-change backup remained identical. SQLite integrity_check was ok. No database migration/reset was performed.
- No new UI/browser redesign or later-phase testing was undertaken. Full real purchase end-to-end/browser scenario remains for the approved later testing phase.

## Actual rental transcript from the smoke run

- **buyer — OFFER — safe_fallback:** Would $16 work for 3 days?
- **seller — COUNTER — ollama:** REPLY: $25 for 3 days works for me. Looking forward to reviewing the details with you.
- **buyer — ACCEPT — ollama:** REPLY: $25 for 3 days works for me. Looking forward to reviewing the details with you.

Result: **Confirmed**, price **$25**, pickup 2026-10-28T17:00:00-07:00, return 2026-10-31T17:00:00-07:00. Both approval flags were true.

The original live transcript above is preserved verbatim. That run exposed the REPLY prefix and copied acceptance wording; subsequent narrow normalization/duplicate guards were verified by tests rather than another long inference loop.

## Purchase wording recheck

- Validated real decision: OFFER at $20.
- Public wording: Would you consider $20 for this item?
- Wording source: **safe_fallback**.

Presentation fallback was used for the rental opening and the focused purchase recheck. The rental counter and acceptance in the original live run used model narration. All negotiation decisions remained genuine Ollama decisions. Raw evidence is saved in ignored artifacts/phase1-ollama.json and artifacts/phase1-purchase-narration-check.json.

## Files changed in Phase 1

- backend/agents/ollama_provider.py
- backend/agents/narration.py
- backend/agents/negotiation_coordinator.py
- backend/agents/mock_provider.py
- backend/tests/test_negotiation.py
- backend/tests/test_natural_negotiation.py
- backend/tests/test_phase1_reliability.py
- scripts/phase1_ollama_smoke.py
- docs/PHASE1-RELIABILITY.md

## Manual review

1. From the repository root run ./scripts/start.sh, then open http://localhost:3000. Use the existing Ollama service at localhost:11434 with qwen2.5:3b.
2. Select Abbhijit, open the TI-84 owned by Shorya Moses, enter target $15 / maximum $25 / three-day rental / compatible Wednesday pickup at Hayden Library, and select Ollama.
3. Watch validated offers progress. A narration repair/fallback must not pause a valid decision. The provider remains ollama. Inspect the authenticated GET /negotiations/{id} message narration_source fields to distinguish model wording from safe fallback.
4. Approve as the buyer. The proposal must remain pending until Shorya independently approves in a separate Incognito session or through the explicit local demo switch.
5. For a textbook purchase, use a compatible buyer budget, and check that opening text proposes a purchase, never acknowledges a nonexistent offer, never describes renting, and never invents a return deadline.
6. Optional bounded reproducible verification: .venv/bin/python scripts/phase1_ollama_smoke.py. It uses a temporary DB and caps genuine inference requests at 18.

## Remaining limits

Qwen 2.5 3B still produces inconsistent prose on some generations. Safe presentation fallback is therefore an intentional reliability mechanism, not evidence that every sentence came from the model. It never repairs or invents a decision. Purchase records retain the existing internal rental_days field for API compatibility; it is omitted from purchase narration and does not create a return deadline. Full real purchase/browser testing and further UI work require approval for the later phases. Demo identity and single-backend-worker limitations remain unchanged.

**PHASE 1 COMPLETE — Ollama reliability. Please review and approve before I begin Phase 2.**

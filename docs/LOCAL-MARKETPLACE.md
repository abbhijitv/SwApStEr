# General local marketplace — Prompt 1

The frontend at `/marketplace` supports general buying, selling, renting, and AI-assisted negotiation. The platform homepage `/` and B2B placeholder `/b2b` are unchanged.

## Presentation and compatibility

- General categories: Electronics, Furniture, Clothing, Home & Living, Books, Sports, and Other.
- Legacy categories remain available with their exact values: Calculators, Textbooks, Lab kits, Drafting, and Housing & Subleases. Any additional category returned in listings appears in both filtering and the listing form. Categories are not silently remapped, so existing listings remain discoverable.
- Search covers titles, descriptions, categories, and existing course codes. Price sorting uses the listing's numeric asking price; card prices preserve cents. Empty results offer a filter reset.
- Listing forms leave the already-optional `course` field blank unless entered. Existing course data remains visible in listing details and searchable. Pickup location must be supplied by the buyer rather than defaulting to a campus landmark.
- New listing pickup times default to tomorrow in the browser's local time, with an availability horizon of one week. These editable defaults do not copy another seller's schedule. Dates still serialize as timezone-aware ISO timestamps.
- API keys, category values, `Buy`/`Rent` values, student IDs, cookies, and approval endpoints remain unchanged. Sale negotiation forms retain the required `rental_days` value as a hidden field, while rentals show the editable duration.
- Shared negotiation URLs use `/marketplace?negotiation=<id>`. They select neither an identity nor a role and do not grant access. The existing server checks participant authorization.
- The identity selector is explicitly labeled Demo. Profile creation and independent buyer/seller switching remain demo mechanisms, not production authentication.
- Existing illustrative photos remain labeled as illustrative. Categories without suitable photos use the existing honest placeholder; no listings or uploaded photos are fabricated.

## Backend limitations for a later phase

1. Profiles and endpoint names still use the student model (`/students`, `student`, `university`, `course_or_major`). Optional academic metadata is labeled accurately rather than repurposed into unrelated fields. Authentication and a general account model remain future work.
2. Item listings require pickup windows and timezone-aware availability. Negotiations require a target, maximum, pickup window, deadline, location, and duration, including a duration value for purchases. The UI labels the deadline “Preferred completion deadline”; it remains a backend constraint. A future API could separate purchase and rental schemas more clearly.
3. Listing records do not provide a general seller meetup location, coordinates, radius search, shipping, or distance. The interface says “Local pickup” without inventing a location or distance. Buyers enter a proposed location; both people review the terms. Location verification and proximity search need backend support.
4. Existing seeded products, descriptions, profiles, and backend-generated narration or validation messages may still contain campus wording. Data and negotiation logic were preserved. Do not rewrite user data to generalize the UI.
5. Category choices are derived from returned listings plus the supported general and legacy choices. There is no dedicated category taxonomy endpoint. A future taxonomy should preserve compatibility with stored categories.
6. Categories are general, but there are no category-specific attributes, uploaded listing photos, payments, shipping, inventory reservation, or secure accounts. Housing retains its existing lease requirements and landlord-approval disclaimer.
7. Mock negotiations are explicitly labeled deterministic mock. Ollama requires a separately configured local model; the UI does not assume a particular model name.

## Verification

Run the required checks from the repository root:

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
npm run typecheck --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m pytest backend/tests -q
```

Browser tests use `/marketplace` for marketplace workflows and retain checks for participant authorization, independent approvals, rejection, history, housing, hydration, photos, and mobile focus/layout. General-marketplace coverage adds optional course codes, a furniture sale listing, description search, cents, sorting, dynamic backend categories, and platform/B2B navigation. Run write-capable browser tests against a separate temporary SQLite database rather than a developer's existing database. Real Ollama testing remains opt-in through `RUN_OLLAMA_E2E=1`.

Verified locally on October 31, 2026: backend **126 passed, 0 failed, 0 skipped**; TypeScript and the Next.js production build passed; Chrome/Playwright **17 passed, 0 failed, 1 skipped** (the opt-in real Ollama test). HTTP checks returned 200 for `/`, `/marketplace`, `/b2b`, and the backend health/docs/listings endpoints. Browser tests used an isolated temporary database and the mock provider; temporary servers and that database were cleaned up.

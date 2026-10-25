# CampusSwap AI

**Your campus deals, negotiated by AI.** A local academic marketplace built for Cubbie Hackathon Track 2: Agent-to-Agent Coordination. Independent buyer and seller agents exchange structured offers with separate private contexts, negotiate conflicting student constraints, and ask both humans to approve.

## What works

- Responsive Next.js marketplace with seeded academic listings, search, categories, price sorting, item details, listing creation, and My listings.
- Dynamic SQLite student profiles, optional university/major, profile creation and switching, and persistent server-managed demo sessions. Abbhijit, Shorya Moses, and Oumar are the initial profiles; anyone can be a buyer or seller.
- Buyer preferences, persisted SQLite sessions, live incremental agent turns, current offer, pickup/return details, thinking states, restart, and saved history.
- Independent buyer/seller agent modules, deterministic dynamic mock negotiation, interchangeable Ollama structured-JSON provider, explicit fallback control.
- Decimal price enforcement, timezone-aware pickup checks, rental and availability checks, eight-turn cap, rejection, and independent dual approval.
- Opaque server-side demo identity sessions; private limits omitted from ordinary API responses; disabled-by-default, local-only Judge Mode.
- Generated device/book illustrations use CSS/SVG and need no external assets or API keys.

## Prerequisites and installation

Verified host: macOS 14.3, Apple Silicon arm64, Python 3.9.6, Node 24.14.1, npm 11.11.0. Homebrew, Git, Chrome, and Ollama were already installed. Python 3.9 works; newer supported Python is recommended for future development.

From this repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm ci --prefix frontend
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Backend exact installed versions are recorded in `backend/requirements.lock.txt`; use that file instead of requirements.txt to reproduce this Python 3.9 environment. No global Python package installation, paid APIs, Docker, Redis, or cloud database is needed. SQLite is seeded once automatically. Dates use the next Wednesday in America/Phoenix when the database is first seeded. Do not delete a populated database to refresh demo dates; create a fresh DATABASE_URL if needed.

## Run

In terminal 1, from the root:

```bash
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In terminal 2:

```bash
npm run dev --prefix frontend
```

Or run `./scripts/start.sh` to start both. Open **http://localhost:3000** (use localhost consistently for cookie/CORS behavior). API health: http://localhost:8000/health. Interactive request/response schemas: http://localhost:8000/docs; machine-readable schema: `/openapi.json`.

Production frontend verification/start:

```bash
npm run build --prefix frontend
npm run start --prefix frontend
```

Build/dev scripts use Webpack because Turbopack's CSS subprocess port binding failed in this execution environment. This still runs standard Next.js App Router.

## Environment

Backend loads `.env` from the working directory. Always run from the repository root.

| Variable | Default/example | Purpose |
| --- | --- | --- |
| AI_PROVIDER | ollama | Default for API requests that omit provider; UI explicitly selects its displayed provider |
| OLLAMA_BASE_URL | http://localhost:11434 | Local model API |
| OLLAMA_MODEL | qwen2.5:3b | Single shared model |
| DATABASE_URL | sqlite:///./campusswap.db | SQLite database location |
| MAX_NEGOTIATION_TURNS | 8 | Total agent turns, hard capped at 8 |
| APP_ENV | development | Demo identities are disabled outside development |
| ENABLE_JUDGE_MODE | false | Explicit opt-in to private demo inspector |
| NEXT_PUBLIC_API_URL | http://localhost:8000 | Frontend `.env.local`; rebuild after changing |

The installed local `.env` selects mock for reliable demos. The UI provider picker labels each session. Failed Ollama requests stay in Ollama mode and show retry / explicit switch-to-mock buttons.

## Ollama

If missing on your Mac, install with `brew install ollama`. Do not run a second server if the Ollama desktop app is already serving port 11434.

```bash
OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

In another terminal:

```bash
ollama pull qwen2.5:3b
curl http://localhost:11434/api/tags
curl http://localhost:11434/api/generate -d '{"model":"qwen2.5:3b","prompt":"Reply with hello","stream":false,"options":{"num_predict":20}}'
```

Then select **Real local AI · Ollama / Qwen 2.5 3B** in the buyer form. Agent calls are sequential and use the same loaded model. Keep memory-heavy applications closed on an 8 GB Mac. See `docs/VERIFICATION.md` for the actual installed model and inference verification status.

## Successful demo

1. Select **Abbhijit** in the navbar, then open **TI-84 Plus CE Graphing Calculator** (owned by Shorya Moses) → **Let My AI Negotiate**.
2. Keep target $15, private maximum $25, three days, the seeded Wednesday pickup window, Friday deadline, Hayden Library, and mock provider.
3. Start. Buyer offers $15; seller computes a counter from its own asking price; buyer concedes; seller accepts compatible terms. The normal seed currently reaches $20 through four independent turns. The outcome is calculated, not a hardcoded deal.
4. Observe Wednesday 5 PM Arizona pickup and Saturday return. With this initial seed: October 28 and October 31, 2026.
5. Approve as Abbhijit. The deal remains pending. Switch to Shorya Moses with the button or top-right student selector, then approve as Shorya Moses. Only now does it show **Confirmed**.
6. Open **My negotiations** or reload the session URL to inspect persisted public messages and status.

A student's maximum/minimum never appears in the normal session GET response. The buyer's own submitted form data is naturally visible to that buyer's browser; it is never sent to the seller agent. The demo identity selector is intentionally open to hackathon participants and is not real authentication.

## Dynamic student profiles and safe upgrade

Choose a student in the navbar, or choose **+ Create student profile** to create and immediately select a new one. Names, initials, listing ownership, agent labels, histories, and approval controls come from persisted profile IDs. Refresh preserves the selected profile via a 30-day HttpOnly demo cookie. **My listings** filters to the active student. All profiles can both buy and sell; initial role hints do not restrict actions.

When buying, the active student is the buyer and the listing owner is the seller. Self-negotiation is blocked by the backend. Only those two IDs may inspect, advance, or approve their negotiation. Switching to Oumar or another unrelated student clears the conversation and refreshes history; spoofed names/roles do not authorize approvals. To approve as the other participant, use the review switch button or select their profile.

The additive `dynamic_students_v1` migration runs once at backend startup. It backs up an existing database into ignored `backups/`, preserves legacy `student-a` / `student-b` IDs and all associated records/approval keys, renames only the known original demo display names, and adds Oumar. User-created names and data are retained. A unique student-ID index and a migration marker make subsequent starts idempotent. Existing listing/negotiation display names resolve from profiles without rewriting their historical records. See `docs/MIGRATION.md` for the preservation audit.

To reproduce the requested multi-user demo: select Shorya Moses → list a calculator for $35 with a private $20 minimum → select Abbhijit → open it and submit $15/$25 preferences with Ollama → review and approve → switch to Shorya and approve. Oumar cannot approve that deal, but can start an independent one. A fourth profile can create listings and negotiate immediately with no code changes.

## Two-student approval demo

Agents propose the terms; each student independently chooses **Approve Deal** or **Reject Deal**. One approval stays pending and shows who is still required. Both approvals confirm the deal. Either rejection closes the proposal permanently.

For the two-window demo, use regular Chrome as Abbhijit and a separate Incognito session as Shorya Moses. Regular tabs share the active-profile cookie. The seller finds the proposal through **My negotiations**, identified by its deal number, or opens the buyer's copied negotiation link after selecting their own profile. A link grants no access and never changes identity. Both visible proposal views refresh approval state every 2.5 seconds; hidden tabs pause and refresh when restored.

See [the complete two-student demo instructions](docs/TWO-STUDENT-APPROVALS.md). Existing profiles, negotiations, and private constraints are preserved.

## Failed demo

Select **TI-Nspire CX II · premium rental**. Keep target $15 and maximum $25. Its seller minimum is $50. Agents exchange up to eight price offers within their respective boundaries and finish **No agreement — incompatible price constraints.** No agreement or approval controls are created. You can also test non-overlapping pickup windows or an incompatible rental duration.

## Judge Mode

Set `ENABLE_JUDGE_MODE=true` in `.env`, keep `APP_ENV=development`, restart the backend, and click **Inspect Judge Mode**. It shows both private contexts, public decisions, terms, and approvals. The route checks loopback access and environment. Set it back to false for ordinary student demonstrations. `APP_ENV=production` disables demo authentication and Judge Mode; this project needs real campus authentication before deployment.

## API

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | /health | Readiness |
| GET | /listings, /listings/{id} | Public listings without private minimum |
| POST | /listings | Seller session required; validated listing including private minimum |
| GET | /students, /students/{id} | Public demo profile metadata; stable student IDs |
| POST | /students | Create profile: display_name, optional university, optional course_or_major |
| POST | /demo/session | Select any existing student by stable ID; sets opaque HttpOnly cookie |
| GET | /demo/session | Current server-resolved demo student |
| POST | /negotiations | Buyer preferences; returns public session, HTTP 201 |
| GET | /negotiations | Current participant's saved history |
| GET | /negotiations/{id} | Public transcript, terms, status, approvals |
| POST | /negotiations/{id}/advance | `{ "version": 0 }`; one independent turn, stale versions return 409 |
| POST | /negotiations/{id}/approve | `{ "decision": "approve" }` or `reject`; actor derives from cookie |
| POST | /negotiations/{id}/mock | Explicit switch for a still-open session |
| GET | /demo/judge/{id} | Opt-in, local development-only private inspector |

Datetime values must include a timezone. Prices accept exact decimal strings, with at most two fractional digits. Common statuses are Negotiating, Agreement proposed, Awaiting approvals, Confirmed, Rejected, and No agreement. Unknown resources return 404, missing sessions 401, wrong identities 403, stale/closed actions 409, invalid inputs 422. Full body schemas are generated in FastAPI docs.

## Tests

Latest approval-flow verification: 30 backend tests and all 10 distinct Chrome regression cases passed across the suite and targeted reruns, including real seeded TI-84 negotiation with independent buyer/seller sessions. TypeScript and production build passed. See `docs/TWO-STUDENT-APPROVALS.md` for exact results, the blocked initial model trial, and preservation checks. Earlier verification is retained in `docs/RESUME-VERIFICATION.md`.

```bash
.venv/bin/python -m pytest -q
npm run build --prefix frontend
npm run typecheck --prefix frontend
```

Browser tests require both servers running, the initial seed listings, and Google Chrome installed at the standard macOS path:

```bash
npm run test:e2e --prefix frontend
```

To run the optional full real-model browser test:

```bash
RUN_OLLAMA_E2E=1 npm run test:e2e --prefix frontend -- ollama.spec.ts
.venv/bin/python scripts/verify_live.py --provider ollama
```

Playwright uses existing Chrome with extensions disabled; no additional browser download is needed. The hydration test monitors hydration-related console messages and browser page errors while selecting and reloading profiles. It checks marketplace filtering/search, a complete dual-approval negotiation, persisted history/reload, incompatible prices, mobile overflow, and seller listing persistence. The seller test creates a uniquely named listing. Use a fresh disposable DATABASE_URL when you want a clean demo database. Configure `frontend/playwright.config.ts` for another browser/OS. Pytest always uses a separate temporary SQLite database.

## Architecture and folder structure

```text
campus-swap-ai/
├── .env.example
├── .gitignore
├── README.md
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── requirements.txt
│   ├── requirements.lock.txt
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── provider.py
│   │   ├── buyer_agent.py
│   │   ├── seller_agent.py
│   │   ├── mock_provider.py
│   │   ├── ollama_provider.py
│   │   └── negotiation_coordinator.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── schemas.py
│   ├── routes/
│   │   ├── __init__.py
│   │   └── negotiations.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── store.py
│   │   └── students.py
│   └── tests/
│       ├── conftest.py
│       ├── test_basic.py
│       ├── test_negotiation.py
│       ├── test_students.py
│       └── test_approvals.py
├── frontend/
│   ├── .env.example
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── tests/demo.spec.ts
│   ├── tests/ollama.spec.ts
│   ├── tests/profiles.spec.ts
│   ├── tests/profile-helpers.ts
│   ├── tests/hydration.spec.ts
│   ├── tests/approvals.spec.ts
│   ├── playwright.config.ts
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.mjs
│   ├── tsconfig.json
│   └── next-env.d.ts
├── docs/
│   ├── ARCHITECTURE.md
│   ├── VERIFICATION.md
│   ├── MIGRATION.md
│   ├── RESUME-VERIFICATION.md
│   └── TWO-STUDENT-APPROVALS.md
└── scripts/
    ├── start.sh
    └── verify_live.py
```

Generated local `.venv`, `.env`, `frontend/.env.local`, database, dependencies, build output, model data, and test artifacts are ignored. See `docs/ARCHITECTURE.md` for context isolation, state transitions, provider contracts, and storage decisions.

## Troubleshooting and limitations

- Connection refused: start backend/frontend from the root; check ports 8000 and 3000.
- CORS/cookies: visit `http://localhost:3000`, and keep API URL `http://localhost:8000`; switching between 127.0.0.1 and localhost creates different cookie hosts.
- Ollama connection failure: start Ollama, inspect `/api/tags`, then retry. Mock mode is an explicit user choice.
- Agent invalid terms: the server blocks the action. Retry, explicitly switch provider, or restart. Two invalid actions close the negotiation safely.
- Demo dates grow stale in a long-lived database. Use a fresh database or list a new item with current dates.
- Run one backend worker. In-process locks do not coordinate multiple processes. Normalized tables, transactions across workers, real authentication, moderation, and reservation/inventory locking are future production work.
- No payment, chat between humans, image uploads, notifications, or campus SSO. Seeded listings belong to Shorya Moses; new listings belong to the active student. Profiles have no fixed role restrictions. Dates and exact rental durations are negotiated; restrictions are displayed text, while enforceable rules are represented by structured fields.
- Prices/terms come from provider actions; public text is safely rendered from those structured decisions. This prevents accidental private-prompt disclosure and keeps both providers consistent.
- The frontend uses one App Router page with working views/dialogs and persisted negotiation URLs rather than seven separate route files.

## Three-developer collaboration

Stable boundaries: `Provider.decide(context) -> Action`; agent context builders; validated API schemas; public session response. Keep those contracts stable while working independently.

1. Developer 1: `backend/agents/` — model prompt quality, negotiation strategies, provider tests.
2. Developer 2: `frontend/` — accessibility, component extraction, more browser coverage and polish.
3. Developer 3: `backend/routes/`, `models/`, `services/` — authentication, normalized persistence, transactional locking and API tests.

This workspace initially had no Git repository. To commit the verified foundation yourself:

```bash
git init
git add .gitignore .env.example README.md backend frontend docs scripts
git status --short
git commit -m "Build CampusSwap AI end-to-end demo"
git branch feature/agents
git branch feature/website
git branch feature/api
```

Each teammate should use a separate clone/worktree and `git switch` to their assigned branch. Review `git status` before committing; ignored env files, SQLite data and dependencies must stay out of Git. Add a GitHub remote and push only when the team authorizes it. No GitHub push was performed.

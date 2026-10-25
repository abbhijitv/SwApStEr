# Verification record — October 25, 2026

Latest human approval verification: **30 backend tests**, **10 distinct Chrome cases passed across runs**, TypeScript and production build passed. See [TWO-STUDENT-APPROVALS.md](TWO-STUDENT-APPROVALS.md) for separate-session live updates, real Ollama approval, the safely blocked initial model trial, and data-preservation results.

Current multi-student verification: see [RESUME-VERIFICATION.md](RESUME-VERIFICATION.md) — 26 backend tests, 6 production Chrome tests including real Ollama, and a separate development hydration check passed. The checkpoint history below records the original MVP.

All checks below ran on this local macOS arm64 workspace. No hosted deployment, GitHub push, paid API, or global Python package installation was performed.

## Installed and reused

Reused macOS 14.3, Apple Silicon arm64, Python 3.9.6, Node 24.14.1, npm 11.11.0, Homebrew 7.0.10, Git 2.39.3, Google Chrome, and Ollama client 0.40.11. Backend packages were installed into `.venv`; exact versions are in `backend/requirements.lock.txt`. Frontend versions are locked in `frontend/package-lock.json` (Next 16.4.3, React 19.3.1, TypeScript 5.9.3, Tailwind 4.3.3, Lucide, and Playwright).

The requested `qwen2.5:3b` model downloaded successfully (about 1.9 GB) into the existing Ollama installation. The existing `qwen3:4b` model was preserved. The attempted dedicated local Ollama server found port 11434 occupied, so the existing server was reused. `ollama ps` during inference showed only qwen2.5:3b, about 2.1 GB, GPU inference, 2,048-token context.

## Checkpoint 1: backend

- FastAPI/Uvicorn started on 127.0.0.1:8000.
- Live `GET /health` returned HTTP 200 with `{"status":"ok"}`.
- SQLite initialized and six realistic listings seeded without duplication.
- Initial health and public listing tests passed before negotiation work.

## Checkpoint 2: negotiation

Original MVP pytest suite: **21 passed**. Tests use an isolated temporary SQLite database.

Coverage includes health/listings, authenticated listing creation, the full listing → negotiate → proposal → independent approvals → confirmation integration, incompatible prices, private context and public response isolation, pickup overlap, rental duration, buyer ceiling, seller floor, matching accepted terms, turn cap, stale advances, rejection, duplicate approval, unauthorized/invalid input, cookie-derived approval roles, malformed Ollama JSON, bounded own-price correction, explicit mock switching, Judge Mode opt-in, production restrictions, browser UTC timestamps, and the distinct proposed/pending approval transition.

## Checkpoint 3: website

- Next.js production build and TypeScript checks passed.
- `npm audit` reported **0 vulnerabilities**.
- Live homepage returned HTTP 200.
- Final combined Chrome suite: **4 passed in approximately one minute**, including the real-model flow. Acceptance tests passed for marketplace category/search, backend-driven incremental messages, mock negotiation, independent approvals, confirmed reload/history, impossible-price failure, mobile overflow, and persistent seller listing creation.
- Checked desktop confirmation and mobile marketplace screenshots under ignored `artifacts/`.

## Checkpoint 4: real Ollama

- `/api/tags` reached successfully.
- Direct qwen2.5:3b inference returned `Hello! How can I assist you today?`.
- Full real-Ollama Chrome flow passed, including provider selection, model-generated structured decisions, proposal, buyer approval, student switch, seller approval, and confirmed agreement.
- Observed separate buyer/seller actions: buyer OFFER $15 → seller COUNTER $25 → buyer COUNTER $20 → seller ACCEPT $20. No mock provider was used in this flow.
- Wednesday October 28, 2026 at 5 PM Arizona pickup; Saturday October 31 at 5 PM return; three-day rental.
- Earlier real-model trials proposed an invalid below-floor price or rejected prematurely. The server safely blocked the invalid action and no deal was finalized. Prompt/schema adjustments improved negotiation, with the same independent server validation retained.

## Checkpoint 5: final polish

- All requested statuses are implemented: Negotiating, Agreement proposed, Awaiting approvals, Confirmed, Rejected, No agreement.
- Browser UTC `Z` timestamp regression fixed for Python 3.9; scheduling normalized to America/Phoenix.
- Mobile decorative overflow fixed; mobile history navigation added.
- Backend concurrency uses per-session locks and expected versions; model inference remains serialized globally.
- README includes setup, architecture, API schemas, both demos, Ollama, tests, limitations, complete source tree, and the three-developer branch plan.

## Environment issues resolved

Initial sandbox network requests could not resolve package hosts; authorized dependency downloads succeeded. Turbopack's CSS subprocess failed to bind its internal port even on retry; the standard Webpack build succeeded. Browser execution and server binds used authorized local execution. No administrator installation was needed.

## Limits

This is a local hackathon demo. Identity switching deliberately grants either demo student; production authentication is not implemented. Judge Mode is disabled by default and restricted to development/loopback. Run one backend worker. SQLite uses JSON records rather than a normalized migration-managed schema. Model outcomes can vary, and invalid outputs fail safely; mock mode remains available explicitly. Public message text is rendered from validated model decisions to prevent private prompt disclosure. No payment or inventory reservation exists. Initial seed dates are persisted and eventually need a fresh demo database or new listings.

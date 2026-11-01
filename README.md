# SwApStEr

**Your campus. Your deals. Your AI negotiator.**

SwApStEr is an AI-powered campus marketplace where students have personal AI agents that negotiate purchases and rentals on their behalf.

Built for **Cubbie Hackathon — Track 2: Agent-to-Agent Coordination**.

**GitHub:** https://github.com/abbhijitv/SwApStEr

## The Problem

College students frequently need calculators, textbooks, and other academic essentials, but buying everything new is expensive.

Campus marketplaces help, but negotiating prices, coordinating schedules, and arranging pickups can involve awkward conversations and unnecessary back-and-forth.

**What if your AI agent could handle the negotiation while you kept the final say?**

## Our Solution

SwApStEr gives each student an independent AI agent.

- **Buyer AI:** Negotiates for the best acceptable price while respecting the buyer's private maximum budget.
- **Seller AI:** Negotiates favorable terms while respecting the seller's private minimum price.
- **Agent-to-agent coordination:** Both agents exchange structured offers containing prices, pickup times, locations, and rental durations.
- **Constraint validation:** The backend checks whether proposed terms satisfy student preferences and item availability.
- **Human approval:** Both students must independently approve the final proposal.

**AI negotiates. Students decide.**

## How It Works

1. A student lists an item for sale or rent.
2. Another student selects the item and enters private preferences.
3. The buyer's AI agent initiates negotiation with the seller's AI agent.
4. Agents exchange offers without revealing private budget limits.
5. The backend validates the proposed terms.
6. When an agreement is reached, both students receive a proposal.
7. The deal is confirmed only after both students approve.

If the students' constraints are incompatible, SwApStEr refuses to create an invalid agreement.

## Real Demo — Successful Negotiation

**Campus scenario:** A student needs a TI-84 Plus CE graphing calculator for MAT 265 at Arizona State University.

| Detail | Value |
|---|---|
| Item | TI-84 Plus CE Graphing Calculator |
| Seller | Shorya Moses |
| Buyer | Oumar |
| Asking price | $35 |
| Rental duration | 3 days |
| Pickup location | Hayden Library |
| AI provider | Ollama — Qwen 2.5 3B |

### Agent Conversation

**Buyer AI:** Offers $16.

**Seller AI:** Counters at $20.

**Buyer AI:** Accepts $20.

The final proposed price is **$20 for three days**, saving the buyer $15 compared with the asking price.

The buyer approves the proposal, but it remains pending until the seller independently approves.

**Final result: Confirmed — both students approved.**

This negotiation was demonstrated using the real local Ollama model, not just a scripted mock conversation.

## Conflict Demonstration — Incompatible Schedules

SwApStEr also handles situations where students cannot agree.

For the same calculator:

- **Seller availability:** October 28, 2026, 4:00–8:00 PM.
- **Buyer availability:** October 28, 2026, 9:00–10:00 AM.

Because there is no overlapping pickup window, the system returns:

**No agreement — incompatible pickup schedules or academic deadline.**

No deal is created, and neither student's availability constraints are violated.

This conflict is detected by deterministic backend validation before AI negotiation begins.

## Why This Fits Track 2

SwApStEr demonstrates:

- Independent personal AI agents representing different students.
- Agent-to-agent exchange of relevant public deal information.
- Different private goals and constraints.
- Negotiation toward a mutually acceptable outcome.
- Conflict detection and safe rejection of incompatible terms.
- Independent human approval before confirmation.
- A practical campus scenario involving academic equipment.

Unlike a traditional marketplace, SwApStEr lets agents coordinate on behalf of their students instead of requiring students to negotiate manually.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript |
| Backend | Python, FastAPI |
| Database | SQLite |
| AI inference | Ollama |
| Model | Qwen 2.5 3B |
| Testing | Pytest, Playwright |
| Deployment | Local prototype |

The project runs locally without paid AI APIs.

SQLite remains the default local database. PostgreSQL configuration and an explicit,
non-destructive Alembic baseline are available for future use; no existing data is
copied automatically. See [PostgreSQL and future Supabase setup](docs/POSTGRESQL.md)
before selecting a hosted database or running migrations.
[Step 4A Supabase readiness and safe manual setup](docs/SUPABASE-POSTGRESQL.md)
adds an opt-in read-only diagnostic and current pooling guidance.

Supabase account authentication now has a separate session/token foundation and
`/auth/me`; the original marketplace retains separate demo identities. See
[authentication setup and rollout boundaries](docs/AUTH-FOUNDATION.md). Real
account ownership now has a separate, staged backend API; demo endpoints are not account APIs.

Prompt 3B adds `/signup`, `/login`, password recovery/reset, `/account`, and
secure confirmation callbacks. See [account UI setup and manual email testing](docs/AUTH-UI.md).
Supabase accounts remain separate from local demo profiles. Prompt 3C-1 adds
[account marketplace ownership and authorization](docs/ACCOUNT-MARKETPLACE.md),
disabled by default. Prompt 3C-2 connects the separate `/marketplace/account` UI;
see [local setup and two-account testing](docs/ACCOUNT-MARKETPLACE-UI.md).

## Getting Started

### Prerequisites

- Python 3.10 or newer (local setup verified with Python 3.13)
- Node.js and npm
- Git
- Ollama
- Google Chrome for browser testing

### Installation

Clone the repository:

```bash
git clone https://github.com/abbhijitv/SwApStEr.git
cd SwApStEr
```

Set up the Python environment and frontend:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm ci --prefix frontend
```

Create the environment configuration:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

### Set Up Ollama

Install Ollama if needed, then download the model:

```bash
ollama pull qwen2.5:3b
```

Make sure Ollama is running on:

```text
http://localhost:11434
```

### Start SwApStEr

From the repository root:

```bash
./scripts/start.sh
```

Alternatively, run the backend and frontend separately:

```bash
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
npm run dev --prefix frontend
```

Open:

**http://localhost:3000**

Backend API documentation:

**http://localhost:8000/docs**

## How to Try the Demo

### Successful Negotiation

1. Select a student profile.
2. Open the TI-84 calculator listing.
3. Click **Let My AI Negotiate**.
4. Enter a target price of $15 and a maximum budget of $25.
5. Select a three-day rental and a pickup window overlapping the seller's availability.
6. Choose **Real local AI — Ollama / Qwen 2.5 3B**.
7. Start the negotiation and watch the agents exchange offers.
8. Review the proposed deal.
9. Approve as the buyer.
10. Switch to the seller's profile and approve independently.

The deal is confirmed only after both approvals.

### Conflicting Schedule

Repeat the process with the buyer's pickup window set to:

- October 28, 2026, 9:00 AM
- October 28, 2026, 10:00 AM

The seller's existing availability is 4:00–8:00 PM.

The system should display a no-agreement result because the schedules do not overlap.

*Note: Seeded listing dates depend on when the database was first initialized. Use the dates shown on the listing if they differ from this example.*

## Privacy and Safety

SwApStEr separates private preferences from shared negotiation terms.

- Buyer maximum budgets are not disclosed to the seller agent.
- Seller minimum prices are not disclosed to the buyer agent.
- Only public offers and relevant terms are exchanged.
- Invalid prices and incompatible pickup schedules are blocked.
- Rental duration and item availability are validated.
- Negotiations are capped at eight turns.
- Both students must approve before confirmation.
- No payments are processed.

Demo student switching is intended for local hackathon testing and is not production authentication.

## AI Architecture

The application uses separate buyer and seller agent modules.

Each agent receives its own private context, the public listing details, and relevant shared negotiation history.

Ollama generates structured negotiation decisions. The backend validates these decisions before they are accepted into the conversation.

Natural-language messages are generated from the validated public terms, with safeguards against misleading or unsupported claims.

A deterministic mock provider is also available as an explicitly selected demonstration fallback.

The negotiation engine and the safety-validation layer serve different purposes: **AI proposes and negotiates; backend rules enforce boundaries.**

## Testing and Verification

Verified during development:

- **67 backend tests passed.**
- TypeScript type checking passed.
- Real Ollama Playwright end-to-end test passed.
- Successful real-AI negotiation manually demonstrated.
- Independent buyer and seller approvals verified.
- Incompatible pickup schedules manually tested and correctly rejected.

Run backend tests:

```bash
.venv/bin/python -m pytest backend/tests -q
```

Run TypeScript checking:

```bash
cd frontend
npx tsc --noEmit
```

Run browser tests:

```bash
npm run test:e2e --prefix frontend
```

Run the optional real-Ollama browser test from the frontend directory:

```bash
RUN_OLLAMA_E2E=1 npx playwright test tests/ollama.spec.ts --workers=1
```

The real-model test requires Ollama and the application servers to be running.

## Key Features

- Student marketplace for buying, selling, and renting.
- Searchable academic listings.
- Dynamic student profiles.
- Private buyer and seller preferences.
- Independent AI negotiation agents.
- Real-time negotiation progress.
- Structured offer validation.
- Scheduling conflict detection.
- Rental return-date calculation.
- Independent two-student approvals.
- Persistent negotiation history.
- Real local Ollama inference.
- Optional deterministic mock mode.
- Local development Judge Mode.

## Current Limitations

SwApStEr is a working hackathon prototype, not a production marketplace.

It does not currently include real university single sign-on, payment processing, inventory reservation locking, or production-grade account authentication.

Future improvements could include verified university identities, notifications, campus calendar integration, and secure transaction processing.

## Our Vision

We want students to spend less time negotiating and coordinating logistics and more time focusing on campus life.

SwApStEr demonstrates how personal AI agents can work together while protecting individual preferences and keeping humans in control.

**Two students. Two AI agents. One better deal.**

Built for **Cubbie Hackathon — Track 2: Agent-to-Agent Coordination**.

## Campus housing and subleases

The existing marketplace also supports apartment subleases, private room subleases, and room rentals. Housing listings use monthly rent, complete lease dates, optional move-in flexibility, and the same independent agents and two-student approval flow. [Housing demo instructions](HOUSING_DEMO.md) include successful and failed scenarios, data compatibility, and limitations. Mutually accepted student terms remain subject to landlord/property-manager approval and applicable lease restrictions.

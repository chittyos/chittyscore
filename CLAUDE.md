# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ecosystem Position

ChittyScore is a **Tier 4 (Domain) service** in the ChittyOS ecosystem, deployed at `score.chitty.cc`. It is the behavioral trust scoring engine that converts entity activity into quantified trust levels.

**Upstream dependencies:**
- **ChittyID** (Tier 0) - Entity identifiers being scored
- **ChittyTrust** (Tier 0) - Cryptographic root authority; ChittyScore consumes cert data for the Source dimension
- **ChittyAuth** (Tier 1) - Authentication for API access

**Downstream consumers:**
- **ChittyRegister** (Tier 1) - Uses trust levels during onboarding decisions
- **ChittyCases** (Tier 5) - Displays trust profiles in case management
- **ChittyPortal** (Tier 5) - Surfaces trust scores in user dashboards

**Relationship to ChittyTrust:** ChittyScore is *analytical* (behavioral scoring). ChittyTrust is *governance* (cryptographic root authority). They are complementary, not overlapping. See `CHITTYTRUST_ROOT_CA_ARCHITECTURE.md` for the distinction.

## Repository Structure

Multi-project monorepo. The root is the **ChittyScore 6D Trust Scoring Engine** (Python/Flask). Sub-projects are independent applications with their own stacks:

- **Root (chittyscore)** - Python Flask trust scoring API (`app.py`, `src/chitty_score/`)
- **chittyfinance/** - Financial tracking (TypeScript/Node/Express/React, Drizzle ORM, Neon DB)
- **chittyassets/** - Asset management (TypeScript/Node full-stack app)
- **chittypm/** - Project management tools (contains nested sub-projects like `chittycan/`, `chittybeacon/`)
- **chitty-frontend/** - React/Vite frontend (minimal scaffold)

Each sub-project is standalone. Check its `package.json` and `CLAUDE.md` (if present) before working on it.

## Development Commands

### ChittyScore Engine (Root)

```bash
# Run dev server
python main.py                                                # Port 5000
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app  # With auto-reload

# Dependencies
pip install -r requirements.txt   # Flask, Pydantic, numpy, psycopg2, gunicorn

# Database
psql $DATABASE_URL < schema.sql   # Initialize PostgreSQL schema
```

### TypeScript Sub-Projects (chittyfinance, chittyassets, chittypm/*)

```bash
cd <sub-project>/
npm install
npm run dev     # Development server
npm run build   # Production build
npm test        # Tests (if configured)
```

### Deployment

```bash
# Cloudflare Workers (edge)
npm run deploy                    # Uses wrangler.toml

# Docker
docker build -t chittyscore-api .
docker run -p 8000:8000 -e DATABASE_URL=$DATABASE_URL chittyscore-api
```

**Note:** The Dockerfile references `real_trust_api:app` and `gunicorn.conf.py` which don't exist. For Docker, update the CMD to use `main:app` or create the missing files.

## Core Architecture

### 6D Trust Scoring Engine

The engine in `src/chitty_score/` calculates trust across **6 weighted dimensions** producing **4 output scores**:

**Flow:** `TrustEntity` + `TrustEvent[]` -> `TrustEngine.calculate_trust()` (in `app.py`) -> dimension calculations -> weighted composite -> output scores + insights

**Dimensions** (defined in `src/chitty_score/dimensions.py`, each is an async `TrustDimension` subclass):
| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Source | 15% | Identity verification, credentials |
| Temporal | 10% | Account age, consistency, recency |
| Channel | 15% | Channel reliability (verified_api=95, blockchain=90, email=60, etc.) |
| Outcome | 20% | Positive/negative outcome ratio with recency weighting |
| Network | 15% | Connection quality, endorsements |
| Justice | 25% | Community impact, transparency, dispute resolution |

**Output scores** (derived from dimensions with different weight blends):
- People Score (outcome 40%, network 35%, source 25%)
- Legal Score (justice 50%, outcome 30%, temporal 20%)
- State Score (source 40%, justice 35%, temporal 25%)
- ChittyScore (full weighted composite)

**Trust levels:** L0 (0+) -> L1 (25+) -> L2 (50+) -> L3 (75+) -> L4 (90+), mapping to ChittyID lifecycle.

### Key Files

| File | Role |
|------|------|
| `app.py` | Flask app, routes, `TrustEngine` class, demo personas |
| `main.py` | Entry point, imports and runs `app` |
| `src/chitty_score/models.py` | Pydantic models: `TrustEntity`, `TrustEvent`, `Credential`, `Connection` |
| `src/chitty_score/dimensions.py` | 6 dimension calculators (all async, use numpy) |
| `src/chitty_score/analytics.py` | `TrustAnalytics` - insight generation, pattern detection |
| `schema.sql` | PostgreSQL schema (trust_scores, evidence_records, trust_events, etc.) |
| `packages/chitty-score/` | Mirror of `src/chitty_score/` modules (packaging/distribution copy) |

### API Endpoints

- `GET /` - Service info
- `GET /api/health` - Health check
- `POST /api/trust/calculate` - Calculate trust score (body: `{entity: TrustEntity, events: TrustEvent[]}`)
- `GET /api/trust/demo/<persona_id>` - Demo personas: `alice`, `bob`, `charlie`

### Async Pattern

All dimension calculations are async. Flask routes bridge sync/async with:
```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(engine.calculate_trust(entity, events))
loop.close()
```

### Database

- **PostgreSQL** via `DATABASE_URL` env var (Neon in production)
- **Cloudflare D1** for Workers deployment (wrangler.toml binds `TRUST_DB`)
- Schema has mixed SQL dialects: `trust_scores` and `trust_events` use PostgreSQL syntax (UUID, JSONB); `evidence_records`, `verification_requests`, `ai_insights`, `api_usage` use SQLite syntax (AUTOINCREMENT, DATETIME). Be aware of this when writing queries.

### Cloudflare Workers Bindings (wrangler.toml)

- `AI` - Cloudflare AI
- `TRUST_CACHE` (KV) - Score caching
- `TRUST_DB` (D1) - Trust database
- `EVIDENCE_STORE` (R2) - Evidence file storage
- `chittytrack` tail consumer for observability

## Gotchas

- `requirements.txt` has duplicate entries - deduplicate if editing
- `packages/chitty-score/` is a copy of `src/chitty_score/` - keep them in sync or consolidate
- `chittyfinance/` is named "claudefo" in its package.json (Replit origin) - don't be confused by the mismatch
- Demo persona data is hardcoded in `app.py:get_demo_persona_data()` AND seeded in `schema.sql` - two sources of truth
- The `schema.sql` INSERT statements use `INSERT OR IGNORE` (SQLite syntax) but the table definitions for `trust_scores`/`trust_events` use PostgreSQL syntax - this file won't run cleanly against either database as-is

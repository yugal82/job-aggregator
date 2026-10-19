# Server Roadmap — Job Aggregator Backend

A phase-by-phase build guide for the FastAPI + PostgreSQL backend. Each phase produces something runnable and testable before moving on.

**Stack:** Python 3.11+, FastAPI, PostgreSQL + pgvector, SQLAlchemy, Alembic, Pydantic, httpx, Redis, APScheduler, Playwright (fallback), Pytest.

---

## Phase 0 — Project Skeleton

**Goal:** A FastAPI app that starts, connects to Postgres, and responds to `GET /health`.

### Tasks
- Initialize Python project (`pyproject.toml` with Poetry or `uv`).
- Create the module layout:
  ```
  server/
  ├── app/
  │   ├── api/            # FastAPI routers
  │   ├── adapters/       # Source adapters
  │   ├── ingestion/      # Fetch → normalize → dedupe → classify
  │   ├── models/         # SQLAlchemy models
  │   ├── schemas/        # Pydantic schemas
  │   ├── repositories/   # DB access
  │   ├── services/       # Business logic
  │   ├── workers/        # Background jobs
  │   ├── config/         # Settings, env
  │   ├── db.py           # Engine/session
  │   └── main.py         # FastAPI entry
  ├── migrations/         # Alembic
  ├── tests/
  ├── docker-compose.yml  # Postgres + Redis
  └── .env.example
  ```
- Add `docker-compose.yml` for Postgres 16 (with `pgvector`) and Redis 7.
- Wire settings via Pydantic `BaseSettings` — load `DATABASE_URL`, `REDIS_URL`, `LLM_API_KEY`, etc.
- Configure Alembic against the SQLAlchemy metadata.
- Add `GET /health` returning DB + Redis status.
- Set up structured JSON logging.
- Add `pytest` with a session-scoped test DB fixture (use a separate database, run migrations at start).

### Exit criteria
- `docker compose up` boots Postgres + Redis.
- `uvicorn app.main:app` serves `/health` returning 200.
- `pytest` runs cleanly (even with no real tests yet).

---

## Phase 1 — Core Data Model

**Goal:** Persist companies, sources, and jobs with full provenance.

### Tables (Alembic migration)
- `companies` — id, name, slug, website, careers_url, logo_url, active, timestamps.
- `sources` — id, name, type (`official` | `ats` | `board`), provider (`greenhouse`, `lever`, etc.), base_url, active.
- `company_sources` — links a company to one or more sources. Columns: company_id, source_id, adapter, configuration (JSONB — e.g. `board_token`), enabled, last_successful_sync, last_attempted_sync.
- `jobs` — canonical job. id (UUID), company_id, canonical_title, description, employment_type, workplace_type, posted_at, first_seen_at, last_seen_at, closed_at, salary_min/max/currency, department, team, application_url, canonical_url, content_hash, status (`DISCOVERED`/`ACTIVE`/`UPDATED`/`CLOSED`), timestamps.
- `job_sources` — one row per (job, source) pair. Columns: job_id, source_id, source_job_id, source_url, source_application_url, source_title, source_location, source_posted_at, raw_payload JSONB, first_seen_at, last_seen_at, is_active. **Unique constraint** on `(source_id, source_job_id)`.
- `job_locations` — job_id, city, state, country, postal_code, remote_allowed, hybrid_allowed, location_text.
- `raw_source_documents` — id, source_id, company_id, fetched_at, content, content_type, http_status, response_headers, content_hash. Used for reprocessing.

### Tasks
- Write SQLAlchemy models mirroring the schema.
- Add repositories: `CompanyRepo`, `SourceRepo`, `JobRepo`, `JobSourceRepo`.
- Seed script: insert the first ~10 companies (Google, Amazon, Apple, Meta, etc.) plus baseline sources (`greenhouse`, `lever`, `ashby`).
- Add read-only API endpoints:
  - `GET /api/companies`
  - `GET /api/companies/{id}`
  - `GET /api/sources`
  - `GET /api/jobs` (basic pagination, no filters yet)
  - `GET /api/jobs/{id}`

### Exit criteria
- `alembic upgrade head` builds the schema from scratch.
- Seed script populates companies + sources.
- API returns seeded data.
- Repository unit tests hit a real test DB (no mocks).

---

## Phase 2 — Adapter Framework

**Goal:** A pluggable adapter interface with the first ATS integration.

### Tasks
- Define `RawJob` and `CanonicalJob` Pydantic models mirroring §9 of the design doc.
- Define the abstract adapter:
  ```python
  class JobSourceAdapter(ABC):
      async def discover(self) -> list[RawJob]: ...
      async def get_job(self, job_id: str) -> RawJob: ...
      def normalize(self, raw: RawJob) -> CanonicalJob: ...
  ```
- Build a registry that resolves adapter name + configuration → adapter instance.
- Add HTTP client wrapper (`httpx.AsyncClient`) with:
  - Per-adapter rate limiter (requests/sec + concurrency).
  - Retry with exponential backoff on 429/5xx, honoring `Retry-After`.
  - Timeout handling.
- Implement **GreenhouseAdapter** first (easiest — public JSON API, no auth):
  - `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
  - Parse into `RawJob`s, then `normalize()` into `CanonicalJob`s.
- Store fetched payloads to `raw_source_documents` before parsing.

### Testing
- Unit tests: given a fixture JSON payload, `normalize()` produces the expected `CanonicalJob`.
- Integration test (opt-in, tagged `@pytest.mark.integration`): hits a real Greenhouse board.

### Exit criteria
- Running `python -m app.cli sync --company stripe` fetches, normalizes, and prints Stripe jobs (Stripe is on Greenhouse).
- Raw payloads are persisted.

---

## Phase 3 — Ingestion Pipeline

**Goal:** End-to-end flow that persists canonical jobs and job_sources idempotently.

### Pipeline stages
1. **Fetcher** — invokes the adapter, stores raw payload.
2. **Normalizer** — raw → `CanonicalJob`.
3. **Deduplicator** (basic for now — Levels 1–3 from §28):
   - L1: match on `(company_id, source_id, source_job_id)` — if found, update.
   - L2: if requisition_id present, match on `(company_id, requisition_id)`.
   - L3: normalize URL (strip `utm_*`, `ref`, `source`) → match.
4. **Persister** — upsert `jobs`, insert/update `job_sources`, update `job_locations`.
5. **Lifecycle updater** — for jobs not seen in this sync, increment `consecutive_missed_syncs`; mark `CLOSED` after 2–3 consecutive misses.

### Tasks
- Implement each stage as a small module in `app/ingestion/`.
- Add DB uniqueness constraint `(source_id, source_job_id)` as the final idempotency guard.
- Track sync runs in a `sync_runs` table: adapter, started_at, completed_at, jobs_found, jobs_new, jobs_updated, jobs_closed, status, error.
- Add `POST /api/sync/{company_id}` to trigger a sync manually.

### Testing
- Fixture-based tests for each stage in isolation.
- End-to-end test: seed a company, run the pipeline twice, assert no duplicates and correct `last_seen_at` bumps.
- Lifecycle test: simulate 3 consecutive syncs where a job disappears → assert `status = CLOSED`.

### Exit criteria
- Running sync twice creates jobs once.
- Disappearing jobs are correctly closed after grace period.
- Sync runs are logged.

---

## Phase 4 — Add More ATS Adapters + Custom Company Adapters

**Goal:** Cover ~15 companies across 3+ adapter types.

### Tasks
- Implement **LeverAdapter** (`GET https://api.lever.co/v0/postings/{site}?mode=json`).
- Implement **AshbyAdapter** (`POST https://api.ashbyhq.com/posting-api/job-board/{org}`).
- For companies not on a known ATS, add custom adapters (e.g. `GoogleAdapter`, `AmazonAdapter`). Prefer:
  1. Discovered JSON endpoints (check `Network` tab on the careers page).
  2. Sitemap parsing.
  3. Server-rendered HTML with BeautifulSoup.
  4. Playwright only if nothing else works — isolate in `app/adapters/browser/`.
- Move company + adapter config to `config/companies.yaml`:
  ```yaml
  companies:
    - id: stripe
      name: Stripe
      official: { adapter: greenhouse, board_token: stripe }
      enabled: true
      priority: high
  ```
- Loader syncs YAML into `companies` + `company_sources` on startup.

### Exit criteria
- 10–15 companies actively syncing.
- Failing adapters are isolated (one broken adapter doesn't crash the pipeline).
- Adding a new company means editing YAML, not code (when the adapter already exists).

---

## Phase 5 — Scheduling & Background Workers

**Goal:** Continuous, tiered ingestion without manual triggering.

### Tasks
- Wire **APScheduler** with an AsyncIOScheduler running in-process (fine for MVP).
- Define tier-based cron schedules from `company_sources.priority`:
  - High-value: every 2–4 hours.
  - Medium: every 6–12 hours.
  - Low: daily.
- Use Redis as a distributed lock (`SET NX EX`) to prevent overlapping syncs of the same company.
- Add a worker CLI: `python -m app.workers.scheduler` — separate process from the API.
- Emit metrics per sync run (jobs_fetched_total, source_failures_total, sync_duration_seconds).

### Exit criteria
- Workers run independently of the API process.
- Overlapping syncs are prevented.
- `docker-compose up` starts API + worker + Postgres + Redis and jobs start populating on their own.

---

## Phase 6 — Advanced Deduplication + Change Detection

**Goal:** Recognize the same job across sources; detect updates over time.

### Tasks
- Add Level 4 dedup: content fingerprint (normalize title + company + location + description → SHA256).
- Add `job_versions` table: job_id, version, content_hash, description, requirements, captured_at.
- On update, if `content_hash` differs from the latest version, insert a new version row and set `status = UPDATED`.
- Add diff helper that reports which fields changed (title, salary, requirements).
- Implement canonical-URL selection: prefer official → ATS → board.

### Exit criteria
- Same job appearing on Greenhouse and (later) a job board resolves to one canonical row with two `job_sources`.
- Job edits produce a new `job_versions` row with a computed diff.

---

## Phase 7 — AI Classification

**Goal:** Enrich jobs with role, seniority, skills, new-grad flag, sponsorship, etc.

### Tasks
- Build the LLM provider abstraction:
  ```python
  class LLMProvider(ABC):
      async def classify(self, job: CanonicalJob) -> Classification: ...
  ```
  Implement `AnthropicProvider` (Claude) first. Keep the interface clean so `OpenAIProvider` slots in later.
- **Do deterministic classification first** (§23):
  - Regex for `"0–2 years"`, `"new graduate"`, `"2026 graduates"`.
  - Keyword-based skill extraction (Python, Java, AWS, etc.).
  - Employment type + workplace type from structured fields.
- Feed LLM only when deterministic rules can't answer.
- Add a `classifications` table or JSONB column on `jobs`: role, specialization[], seniority, new_grad (bool), skills[], visa_sponsorship (`YES`/`NO`/`UNKNOWN`/`UNCLEAR`), confidence.
- Add classification queue (Redis list or Postgres `SKIP LOCKED`) — jobs are inserted immediately, then classified asynchronously.
- Cache LLM responses by `content_hash` to avoid reclassifying unchanged descriptions.

### Cost controls
- Tier prompts: cheap model for routing, expensive model only for ambiguous cases.
- Batch where the provider supports it.
- Track spend per day.

### Exit criteria
- New jobs appear in the API immediately with `classification_status = pending`.
- A worker picks them up and enriches them.
- LLM cost per 1000 jobs is measured and logged.

---

## Phase 8 — Embeddings + Semantic Search

**Goal:** Vector similarity for matching and dedup Level 5.

### Tasks
- Enable `pgvector` extension (already in Phase 0's Docker image).
- Add `job_embedding vector(1536)` column on `jobs`.
- Generate embeddings on the job description (or a distilled version — title + key requirements).
- Batch-generate embeddings for existing jobs; enqueue new jobs after classification.
- Add HNSW or IVFFlat index on the embedding column.
- Use embedding similarity as **Level 5 dedup**: candidate pairs with cosine similarity > threshold get flagged for merge review.
- Expose a `POST /api/jobs/search` endpoint that accepts a query embedding and returns nearest neighbors combined with structured filters.

### Exit criteria
- Queries like "entry-level backend Python" return semantically ranked jobs.
- Suspected duplicates are flagged in an `dedup_candidates` table.

---

## Phase 9 — User Profile + Matching

**Goal:** Personalized ranking and match explanations.

### Tasks
- Add `user_profiles` table (initially single-user): resume_text, resume_embedding, years_experience, education, target_roles, target_companies, target_locations, visa_requirements.
- Add `POST /api/profile` to update from a config file or upload.
- Implement hybrid matching (§25):
  - **Structured pass**: role, location, seniority, visa, remote — hard filters or soft weights.
  - **Semantic pass**: cosine similarity between resume + job embeddings.
- Return **facets, not a single score** (§26): strong matches, potential gaps, location, education.
- `GET /api/recommendations` returns matched jobs with explanation.

### Exit criteria
- Recommendations feel personalized when resume changes.
- Match explanations map to actual profile fields.

---

## Phase 10 — Search API + Filters

**Goal:** A rich filtering API the frontend can build on.

### Tasks
- Extend `GET /api/jobs` with query params:
  - `company=stripe,openai`
  - `role=software-engineer`
  - `level=new-grad`
  - `location=us` or `location=remote`
  - `posted_after=2026-09-01`
  - `remote=true`
  - `visa=yes`
  - `q=` (full-text query via Postgres tsvector)
- Add GIN indexes on skills[] and tsvector columns.
- Add `POST /api/jobs/{id}/save`, `/apply`, `/dismiss` endpoints and a `job_user_states` table (`NOT_VIEWED`/`VIEWED`/`SAVED`/`APPLIED`/`INTERVIEW`/`REJECTED`/`OFFER`/`WITHDRAWN`).
- Add `GET /api/jobs/new` (jobs where `first_seen_at > last_digest_time`).

### Exit criteria
- Frontend can request filtered lists efficiently (single query per view).
- Save/apply/dismiss actions persist.

---

## Phase 11 — Notifications

**Goal:** Daily digest + instant alerts for high-confidence matches.

### Tasks
- Add `notifications` table with unique constraint `(user_id, job_id, notification_type)`.
- Email transport (SES if AWS, otherwise SMTP or Resend).
- Digest worker (runs daily): find new matched jobs since last digest → format email → send.
- Instant worker: on high-confidence match (score > threshold + target company), send immediately.
- Optional: Slack/Discord webhook transport behind the same interface.

### Exit criteria
- Digest email received with correct new-job list.
- No duplicate notifications for the same job.

---

## Phase 12 — Observability + Health

**Goal:** Silent breakage becomes visible.

### Tasks
- Structured JSON logs on every ingestion step.
- Prometheus metrics endpoint (`/metrics`) or push to CloudWatch/Datadog.
- Adapter health dashboard endpoint: `GET /api/admin/sources/health` returning last_success, last_failure, error_rate, jobs_found per adapter.
- Sentry integration for exceptions.
- Alerting rule: if an adapter fails 3 consecutive syncs, page.

### Exit criteria
- A silently broken parser triggers a visible alert within one sync cycle.
- Metrics show ingestion latency and volume per source.

---

## Phase 13 — Testing + CI

**Goal:** Regression safety, especially for parsers.

### Tasks
- Store fixture payloads under `tests/fixtures/adapters/{adapter}/`.
- Regression tests: every fixture must produce the expected `CanonicalJob`.
- Contract tests: run against real endpoints on a schedule (weekly) — separate from PR CI.
- GitHub Actions:
  - Lint (ruff), typecheck (mypy or pyright), test on PR.
  - Nightly contract tests.
- Coverage floor for `adapters/`, `ingestion/`, `services/`.

### Exit criteria
- Green CI on every PR.
- Broken parser caught by fixture test before merge.

---

## Phase 14 — Security + Deployment (single-user, $0/mo)

**Goal:** Deployed URL at zero cost, matching the single-user scope: one
person uses the portal to track applications. No high-availability, no
multi-user auth, no observability stack.

### Architecture (Option 1 — Vercel + Neon + GitHub Actions)

```
┌──────────────────────────┐      ┌──────────────────────────┐
│ GitHub Actions (cron)    │      │ Vercel (hobby, $0)       │
│                          │      │                          │
│ sync workflow:           │      │ FastAPI as Python        │
│   "0 */6 * * *"          │─────▶│ serverless functions     │
│                          │      │ (/api/*)                 │
│ runs `python -m          │      │                          │
│ app.cli sync --company   │      │ 10s timeout per route    │
│ all` and pokes the API   │      │ 100 GB bandwidth free    │
│ for cache invalidation.  │      └─────────────┬────────────┘
└──────────────────────────┘                    │
                                                ▼
                                   ┌──────────────────────────┐
                                   │ Neon (free tier, $0)     │
                                   │                          │
                                   │ Postgres 16              │
                                   │ 0.5 GB storage           │
                                   │ auto-suspend when idle   │
                                   │ pooled connections       │
                                   └──────────────────────────┘
```

**Pieces that go away:**
- **Redis** — single user can't race on itself. Drop the service entirely;
  replace the sync-overlap guard with a Postgres advisory lock
  (`pg_try_advisory_lock(hash)`).
- **Always-on worker** — long syncs run as scheduled GitHub Actions
  (same pattern as the Microsoft scraper repo). The APScheduler worker
  stays in-code for local dev but isn't deployed.

**Why Vercel over Fly.io/Render:**
- Fly.io: minimum ~$2/mo for an always-on machine; permanently free is harder.
- Render: free Web Service sleeps after 15 min idle (OK), but Postgres is
  only free for 90 days then $7/mo.
- Vercel + Neon are permanently free at this scale, at the cost of a
  10-second request timeout (fine for interactive routes, forces long
  syncs onto Actions anyway — which we want).

### Tasks

#### 14.1 — Code changes to make the stack deployable
- **Drop Redis** from `docker-compose.yml` and `app/workers/job_runner.py`;
  swap the Redis-based lock for `pg_try_advisory_lock`. Keep the
  interface in `app/workers/job_runner.py` so local-dev + Actions paths
  stay identical.
- **Bearer-token auth middleware** — one `API_TOKEN` env var checked on
  every `/api/*` request (except `/health`). Reject 401 otherwise.
  ~30 lines in `app/main.py`. The `user_id` query param stays
  single-user default `1`.
- **Vercel entry point** — `api/index.py` that mounts the existing
  `app.main:app`. Vercel's Python runtime treats it as a function.
- **CORS** — allow the frontend origin only (one env var).
- **DB connection pooling** — Neon's pooler URL (not direct URL) in prod
  so serverless cold starts don't exhaust connections.

#### 14.2 — Deploy configuration
- **`vercel.json`** — rewrites all `/api/*` to the Python function;
  frontend (`client/`) builds and serves from Vercel's static layer.
- **`.github/workflows/sync.yml`** — cron workflow:
  ```yaml
  on:
    schedule:
      - cron: "0 */6 * * *"
    workflow_dispatch:
  jobs:
    sync:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
        - run: pip install -e .
        - run: python -m app.cli sync --company all
          env:
            DATABASE_URL: ${{ secrets.NEON_POOLED_URL }}
  ```
  Runs 4×/day. Replaces the APScheduler worker in production.
- **`.github/workflows/ci.yml`** — PR tests (lint + full pytest suite)
  on every push. Uses GitHub-hosted Postgres service for integration tests.
- **`.github/workflows/deploy.yml`** — on `main` push, run Alembic
  migrations against Neon, then trigger a Vercel deploy via their API.
  Migration step uses direct (non-pooled) Neon URL.

#### 14.3 — Secrets
Three env vars total, stored twice (Vercel for runtime, GitHub for
Actions):
- `DATABASE_URL` — Neon direct URL for migrations
- `DATABASE_POOLED_URL` — Neon pooler URL for runtime queries
- `API_TOKEN` — shared bearer token (set once, hard-coded in the
  user's bookmark / frontend)

No AWS Secrets Manager, no Vault — Vercel and GitHub secrets panels
are enough for one person.

#### 14.4 — Database setup on Neon
- Create project + branch (`main`).
- Enable connection pooling. Note both direct + pooled URLs.
- Run `alembic upgrade head` once from local to establish schema.
- Export seed data from the existing local docker DB (optional) via
  `pg_dump` → `psql` restore.
- Enable Neon's point-in-time restore (free tier includes 7 days).

#### 14.5 — Health + migration-on-deploy
- `/health` already exists. Add `/ready` that confirms DB connectivity.
- Deploy workflow runs Alembic as its first step; aborts deploy on
  migration failure.

### Exit criteria
- Push to `main` → migrations apply → Vercel redeploys → new URL live.
- Cron workflow syncs all enabled companies 4×/day; next-run visible
  in the Actions tab.
- `/api/jobs` responds in < 2s cold, < 500ms warm.
- Monthly spend: **$0** across all providers for the first 6+ months
  (until data outgrows Neon's 0.5 GB free tier, estimated 2–3 years
  of accumulated job history for this roster).

### Deferred — out of scope for single-user deploy
- Multi-user auth (OAuth / Clerk / Cognito) — bearer token is enough.
- AWS / Terraform / Fargate — overkill at this scale.
- Database TLS cert pinning — Neon handles TLS termination.
- Rate limiting / WAF — bearer-token gating is sufficient for one user.
- Phase 11 (notifications) and Phase 12 (observability) explicitly
  skipped per user requirement.

---

## Phase 15 — Expanded adapter coverage (target: 30-company roster)

**Goal:** Ship adapters that cover the user's stated roster below without
scraping aggregator sites (LinkedIn/Indeed) — both for legal/TOS reasons and
to avoid an anti-bot arms race.

### Target companies (30)

Apple, Google, Amazon, Netflix, Microsoft, Meta, Adobe, Intel, Nvidia, Oracle,
Qualcomm, OpenAI, Anthropic, Salesforce, Bloomberg, Atlassian, Intuit,
ServiceNow, Databricks, Stripe, Coinbase, Airbnb, Ripple, DoorDash, Discord,
Notion, Pinterest, Robinhood, Uber, Spotify.

### Status by tier (as of 2026-10-05)

**Tier A — covered today (14)**
Amazon, Netflix, Microsoft (own-portal adapters);
Stripe, Coinbase, Airbnb, DoorDash, Discord, Pinterest, Robinhood,
Databricks (Greenhouse); Spotify (Lever); Ripple (Greenhouse — probed OK).
*Note: add `ripple` to `config/companies.yaml`.*

**Tier B — unlocked by one `WorkdayAdapter` (likely 7+)**
Nvidia (confirmed: 2000 roles on `nvidia.wd5.myworkdayjobs.com`,
site `NVIDIAExternalCareerSite`). Likely Workday-hosted but need per-tenant
site-slug discovery: Adobe, Intel, Qualcomm, Salesforce, Intuit, ServiceNow.
Possibly on Workday under different site names: Uber, Oracle, Atlassian, Meta
(all four 422 on the common site-slug guesses — need to inspect their
careers-page frontend `fetch` calls to find the right slug).

**Tier C — needs its own custom adapter**
- Google: previous `/api/v3/search/` is retired. Options: schema.org
  extraction from each listing page, or reverse the current frontend's API.
- Apple: `jobs.apple.com/api/v1/search` returns 401. Options: schema.org
  from the public page, or figure out the required session token.
- Meta: `metacareers.com` is a GraphQL mesh. One-off reverse engineering.
- Bloomberg: `careers.bloomberg.com` is a custom portal, not Workday.
- Oracle: custom portal (`careers.oracle.com`, likely Taleo-based).
- Notion: previous Greenhouse board gone. Current platform unknown — probe.

**Tier D — blocked by platform-wide auth (watch, don't build yet)**
OpenAI, Anthropic — both on Ashby, which closed its public posting API
(401 for every board). Yaml entries sit `enabled: false`. Re-enable when
Ashby reopens the endpoint OR when we add an HTML-scrape fallback.

### Build order (highest coverage per unit of work)

1. **`WorkdayAdapter`** — one generic adapter unlocks Tier B. Minimum useful
   output: Nvidia (confirmed). Then add Adobe/Intel/Qualcomm/Salesforce/
   Intuit/ServiceNow by discovering each tenant's site-slug (open their
   careers page, inspect the XHR to `/wday/cxs/{tenant}/{site}/jobs`).

2. **`SchemaOrgAdapter`** — generic `<script type="application/ld+json">`
   extractor from career pages. The one adapter unlocks Google, Apple, Meta
   assuming their public listings embed JSON-LD (verify first). Config per
   company: listing-page URL + optional sitemap for crawl discovery.

3. **Per-company custom adapters** — Bloomberg, Oracle, Notion, Uber (if
   Workday discovery fails for Uber). Each is a one-off reverse-engineering
   exercise; estimate ~half-day each.

4. **Ashby fallback** — switch `AshbyAdapter` to scrape
   `https://jobs.ashbyhq.com/{org}` (public HTML + their Next.js data script)
   when the posting API 401s. Unlocks OpenAI, Anthropic, Vercel, Linear.

### Workday adapter shape

```
POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Content-Type: application/json
Body: { "appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "" }
```

Response contains `total` + `jobPostings[]` (title, externalPath,
locationsText, postedOn, bulletFields). Description requires a second call
to `/wday/cxs/{tenant}/{site}/job/{externalPath}` — same two-phase pattern as
the MicrosoftAdapter.

Per-company config:
```yaml
sources:
  - source_name: Workday
    adapter: workday
    configuration:
      host: nvidia.wd5.myworkdayjobs.com
      tenant: nvidia
      site: NVIDIAExternalCareerSite
```

### Explicitly NOT in scope
- LinkedIn / Indeed scraping. Both prohibit it in their TOS, both run
  aggressive anti-bot infra, and the maintenance cost of a scraping pipeline
  (residential proxies, fingerprint rotation, CAPTCHA solvers) is dispro-
  portionate to the value. If we ever need their coverage, pay a vendor
  (SerpApi, Bright Data, TheirStack) and expose it as a `provider` like any
  other source rather than rolling our own.

### Exit criteria
- `WorkdayAdapter` ships + Nvidia + at least 4 more Tier-B companies syncing.
- `SchemaOrgAdapter` ships + Google OR Apple OR Meta producing jobs.
- Tier A gaps closed: Ripple yaml entry added.
- Target roster coverage ≥ 22 of 30 companies actively syncing.

---

## Cross-cutting principles (revisit every phase)

- **Adapter isolation**: one broken source cannot break the pipeline.
- **Raw + normalized**: always keep the raw payload — reprocessable.
- **Idempotent ingestion**: syncing twice = one row.
- **Official URL wins**: canonical application URL points to the company page when available.
- **Deterministic before LLM**: use rules where possible; LLM only for ambiguity.
- **Provenance everywhere**: every enriched field should be traceable to its source.
- **Modular monolith, not microservices** — until measured pain justifies splitting.

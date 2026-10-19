# Deploy — Vercel + Neon + GitHub Actions (single-user, $0/mo)

Everything the code side needs is already in place. The remaining steps
are account setup you have to do once.

## Prereqs
- A GitHub account (you already have one).
- A **Neon** account (free tier is enough): https://neon.tech
- A **Vercel** account connected to GitHub: https://vercel.com

## One-time setup

### 1. Create the Neon project
1. Create a new project. Pick the region closest to you.
2. Open the project → **Connection details**. You need two URLs:
   - **Direct** URL (used by Alembic migrations)
   - **Pooled** URL (used by the API at runtime — PgBouncer-fronted)
3. In the URLs, replace the `postgresql://` scheme with
   `postgresql+asyncpg://` so SQLAlchemy's async driver picks them up.

### 2. Load the schema
From your laptop (one-shot bootstrap — later deploys do this automatically):
```bash
cd server
export DATABASE_URL="<Neon direct URL with postgresql+asyncpg:// prefix>"
alembic upgrade head
python -m app.seed            # seed companies / sources from config/companies.yaml
```

### 3. GitHub repository secrets
In **GitHub → Settings → Secrets and variables → Actions**:

| Secret name          | Value                                 |
|----------------------|---------------------------------------|
| `NEON_DATABASE_URL`  | Neon **direct** URL (`+asyncpg`)      |

Both `sync.yml` and `deploy.yml` read this.

### 4. Vercel project
1. **New Project** → Import your GitHub repo.
2. Vercel autodetects `vercel.json` in `server/` — make sure the
   **Root Directory** is set to `server`.
3. Add the following **Environment Variables** in Vercel's project settings:

   | Key                     | Value                                               |
   |-------------------------|-----------------------------------------------------|
   | `DATABASE_URL`          | Neon **direct** URL (`+asyncpg`)                    |
   | `DATABASE_POOLED_URL`   | Neon **pooled** URL (`+asyncpg`)                    |
   | `CORS_ORIGINS`          | your frontend origin, e.g. `https://your-app.vercel.app` |
   | `ENV`                   | `production`                                         |
   | `LOG_LEVEL`             | `INFO`                                               |

4. Deploy. Vercel auto-triggers on every push to `main` after this.

### 5. First sync
Go to **GitHub → Actions → sync-jobs → Run workflow** to kick off the
first ingest manually. After that it fires on cron every 6 hours.

## Day-to-day

- **Add a new company**: edit `server/config/companies.yaml`, push to
  `main`. The next sync run picks it up; migrations only run if
  `migrations/**` changed.
- **Monitor syncs**: GitHub Actions tab shows every run. A failed sync
  emits a line in the job log — no paging / Sentry wired up (Phase 12
  deferred).
- **Backup**: Neon's free tier has 7-day point-in-time restore built-in.
  Nothing else to do.

## When free runs out

Signals:
- Neon storage approaches 0.5 GB (current DB is ~50 MB; this is years
  away at current growth).
- Vercel bandwidth > 100 GB/mo (single-user hobby traffic won't hit this).

Mitigations:
- Prune closed jobs older than N days.
- Switch to Neon Launch ($19/mo) for 10 GB.
- Switch Vercel to Pro ($20/mo) for 1 TB bandwidth.

## Reverting to local docker-compose

The `docker-compose.yml` in this repo is unchanged for local dev:

```bash
cd server
docker compose up -d postgres
docker compose up -d api worker
```

Prod and local use the same code; the only difference is the env vars.

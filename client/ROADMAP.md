# Client Roadmap — Job Aggregator Frontend

A phase-by-phase build guide for the Next.js dashboard. Each phase produces something you can open in a browser and click through.

**Stack:** Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zod, React Hook Form.

**Design principle:** the backend can outrun the UI. Keep the UI thin — most logic lives in the API. The client's job is to make discovered/filtered/matched jobs easy to browse and act on.

---

## Phase 0 — Project Skeleton

**Goal:** A Next.js app that loads, styled with Tailwind and shadcn/ui, and can talk to the backend.

### Tasks
- `pnpm create next-app@latest` — TypeScript, App Router, Tailwind, ESLint, `src/` directory.
- Install and initialize `shadcn/ui`. Add starter primitives: `button`, `input`, `card`, `badge`, `dropdown-menu`, `dialog`, `sheet`, `select`, `checkbox`, `separator`, `skeleton`, `tabs`, `sonner` (toasts).
- Install TanStack Query + devtools. Wrap the app in `QueryClientProvider`.
- Install Zod + React Hook Form.
- Create the directory layout:
  ```
  client/
  ├── src/
  │   ├── app/                    # Next.js routes
  │   │   ├── layout.tsx
  │   │   ├── page.tsx            # Dashboard
  │   │   └── jobs/[id]/page.tsx  # Job detail
  │   ├── components/
  │   │   ├── ui/                 # shadcn primitives
  │   │   ├── jobs/               # JobCard, JobList, JobFilters
  │   │   └── layout/             # Header, Sidebar
  │   ├── lib/
  │   │   ├── api/                # Typed API client
  │   │   ├── hooks/              # useJobs, useCompanies, etc.
  │   │   ├── types/              # Shared TS types
  │   │   └── utils.ts
  │   └── styles/
  ├── .env.local.example          # NEXT_PUBLIC_API_URL, etc.
  └── next.config.ts
  ```
- Environment: `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- Add a typed API client (`fetch` wrapper + Zod parsing at the boundary).
- Add a simple health page (`/system`) that pings `GET /health` on the backend and shows status.

### Exit criteria
- `pnpm dev` opens the app at `localhost:3000`.
- The system page shows backend connectivity.
- Tailwind + shadcn styles render correctly.

---

## Phase 1 — Job List (Read-Only)

**Goal:** Render jobs from the API in a scannable list.

### Tasks
- Define shared TypeScript types matching backend schemas (`Job`, `Company`, `JobSource`). Consider generating them from FastAPI's OpenAPI spec via `openapi-typescript`.
- Build `useJobs()` hook using TanStack Query.
- Build `<JobCard>` component:
  - Company logo + name.
  - Job title.
  - Location(s) (comma-separated, truncated).
  - "Posted 3h ago" (relative time).
  - Employment type + workplace type badges.
  - "View" button linking to job detail.
- Build `<JobList>` with infinite scroll or pagination.
- Add loading skeletons and empty states.
- Add error boundary + toast on API failure.

### Exit criteria
- Dashboard shows a paginated job list from the seeded backend data.
- Cards are clean, dense, and readable.
- Loading and error states behave gracefully.

---

## Phase 2 — Job Detail Page

**Goal:** Deep-dive view for a single job.

### Tasks
- Route: `/jobs/[id]`.
- `useJob(id)` hook.
- Layout:
  - Header: company logo, name, title, location, posted date.
  - "Apply" primary CTA — opens `application_url` (official URL) in a new tab.
  - Metadata badges (employment type, workplace, seniority, salary if present).
  - Full description (render as sanitized HTML or markdown — the backend should already sanitize).
  - "Sources" panel — every `job_source` shown with logo + link ("Also on LinkedIn", "Also on Indeed").
  - "Version history" panel (Phase 6 backend feature — hide until then).
- Handle missing fields gracefully (no salary, no team, etc.).

### Exit criteria
- Clicking a job opens the detail page.
- The Apply CTA sends the user to the official URL.
- All source links open the correct external page.

---

## Phase 3 — Filters + Search

**Goal:** Narrow the list by the dimensions users actually care about.

### Tasks
- Build a `<JobFilters>` panel (sheet on mobile, sidebar on desktop) with:
  - Company multi-select (async search).
  - Role (Software Engineer, ML Engineer, etc. — comes from role taxonomy).
  - Seniority (New Grad / Entry / Mid / Senior / Staff / Principal).
  - Location + Remote toggle.
  - Posted-after date picker (default: last 7 days).
  - Visa sponsorship (Yes / Unknown — hide No by default).
- Filter state lives in URL query params (shareable, back-button safe).
- Debounced full-text search box in the header.
- Show active filter count + a "Clear all" button.
- "New today" quick chip → `posted_after=today`.

### Exit criteria
- Filters reflect in the URL and persist across reload.
- Combining filters returns expected results.
- Search is snappy (debounced 250ms).

---

## Phase 4 — User Actions (Save / Apply / Dismiss)

**Goal:** Personal state so the dashboard becomes a workflow tool.

### Tasks
- Add save/apply/dismiss buttons to `<JobCard>` and detail page (requires backend Phase 10).
- Optimistic updates via TanStack Query mutations.
- Filter tabs at the top of the dashboard: **All / New / Saved / Applied / Dismissed**.
- Dismissed jobs are hidden from the default view but reachable via the tab.
- "Applied" state visible on the job card (subtle badge, not shouty).
- Undo toast after dismiss ("Undo" for 5s before commit).

### Exit criteria
- Save/apply/dismiss round-trips through the API.
- UI updates instantly (optimistic) and reconciles on server response.
- No jarring flicker when switching tabs.

---

## Phase 5 — Company Pages

**Goal:** Per-company view for browsing everything from one employer.

### Tasks
- Route: `/companies/[slug]`.
- Header: logo, name, careers URL, active job count, last-synced timestamp.
- Job list scoped to that company with the same filters.
- Companies index page: `/companies` — grid of cards, sorted by open job count or alphabetically.

### Exit criteria
- Landing on a company page shows their jobs and adapter health at a glance.

---

## Phase 6 — Match Explanations

**Goal:** Show *why* a job matches — actionable facets, not a black-box score.

### Tasks
- Once backend Phase 9 is live, add a `<MatchExplanation>` component with grouped facets:
  - **Strong matches** (green check): role, skills, location.
  - **Potential gaps** (yellow triangle): "3+ years requested".
  - **Neutral**: education, visa.
- Add a "Recommended" tab that surfaces `GET /api/recommendations`.
- Sort options: newest, best match, salary.

### Exit criteria
- Recommendations tab feels distinct from the raw list.
- Explanations map cleanly to profile fields.

---

## Phase 7 — Profile Editor

**Goal:** Let the user shape their matches without editing YAML.

### Tasks
- Route: `/profile`.
- Sections:
  - Resume: upload PDF/paste text. Show extracted structured fields (years, education, skills) with edit controls.
  - Target roles (multi-select).
  - Target companies (multi-select, autocomplete).
  - Target locations + remote preference.
  - Visa requirements (needs sponsorship? yes/no).
- Show a preview: "Based on this profile, N of the last 100 jobs would match."

### Exit criteria
- Profile changes update matches immediately.
- Uploads succeed and structured extraction is visible.

---

## Phase 8 — Notifications Preferences

**Goal:** Control the daily digest and instant alerts.

### Tasks
- Route: `/settings/notifications`.
- Email digest: on/off, delivery time.
- Instant alerts: on/off, "high-confidence match" threshold slider.
- Optional Slack/Discord webhook fields.
- History table: last 30 days of notifications sent.

### Exit criteria
- Preferences persist and take effect on the next digest run.

---

## Phase 9 — Source Health Dashboard

**Goal:** Operator visibility (initially for the single user; later for admin).

### Tasks
- Route: `/admin/sources` (gated behind role once auth is real).
- Table:
  - Adapter name.
  - Last successful sync (green ✓ / yellow ⚠ / red ✗ badge).
  - Jobs found last run.
  - Error rate over 7 days.
  - "Sync now" button.
- Ties to backend Phase 12 endpoints.

### Exit criteria
- A silently broken adapter is visible on this page.
- Manual sync trigger works and shows progress.

---

## Phase 10 — Polish + Performance

**Goal:** Production feel.

### Tasks
- Empty states with helpful CTAs (no jobs? → "Add a company" or "Check source health").
- Keyboard shortcuts: `/` to focus search, `j/k` to move through list, `s` to save, `d` to dismiss.
- Dark mode toggle (shadcn theme provider).
- Lighthouse pass: image optimization for company logos, code-splitting, prefetch on hover.
- Responsive audit: filters as a bottom sheet on mobile, single-column list.
- Error tracking (Sentry) + basic analytics (only if user opts in).

### Exit criteria
- Lighthouse performance score ≥ 90 on the dashboard.
- Keyboard-only navigation works.
- Mobile is usable, not just viewable.

---

## Phase 11 — Auth (When Multi-User)

**Goal:** Transition from single-user to multi-tenant.

### Tasks
- Wire Auth.js (or Clerk / Cognito to match backend Phase 14).
- Add sign-in page, protected route middleware.
- Session token attached to API calls via a fetch interceptor.
- Sign-out and session-expired handling.
- Profile becomes per-user; scoped queries throughout.

### Exit criteria
- Two accounts see independent job lists, saved state, and profiles.

---

## Phase 12 — Deployment

**Goal:** Ship it.

### Tasks
- Dockerfile for the Next.js app (or deploy to Vercel).
- Environment separation: `.env.local`, `.env.production`.
- CI: lint, typecheck, build on every PR (GitHub Actions).
- Preview deployments per PR.
- Configure CDN caching for static assets and company logos.

### Exit criteria
- A merged PR produces a live production build automatically.

---

## Cross-cutting principles (revisit every phase)

- **URL is the source of truth for filter state.** Every filter view should be shareable.
- **Optimistic UI where cheap; loading states where not.** Save/dismiss = optimistic. Filter change = skeleton.
- **Match explanations, not scores.** Never surface "92% match" alone (per §26 of the design doc).
- **Sanitize backend HTML.** Job descriptions come from third parties — treat as untrusted.
- **Skeleton over spinner** — feels faster and preserves layout.
- **No client-side scraping, ever.** All data comes from the backend API.
- **Types at the boundary.** Zod-parse API responses so runtime errors surface where they originate, not deep in a component tree.

---

## Build order rationale

The vertical slice from the design doc's §72 is:
```
Google → Career Adapter → Canonical Job → Postgres → FastAPI → Next.js Dashboard
```

That means Phase 0–2 of the client should be built **in parallel with backend Phases 0–3**. Everything after Phase 2 on the client waits on the corresponding backend phase to be usable. Don't build filters (client Phase 3) before the backend supports them (server Phase 10) — you'll throw away work.

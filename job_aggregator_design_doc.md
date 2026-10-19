# Design Document: Multi-Source Job Aggregation & Tracking Platform

**Status:** Proposed  
**Target:** Personal job-search platform, extensible to a multi-user product  
**Primary use case:** Aggregate Software Engineering, ML/AI, and related openings from a curated list of companies' official career sites plus general job boards, normalize and deduplicate them, identify newly posted jobs, and provide highly targeted filtering/matching.

---

## 1. Executive Summary

The system will continuously collect job postings from two fundamentally different source categories:

1. **Official company career sites**
   - Google
   - Amazon
   - Microsoft
   - Apple
   - Meta
   - NVIDIA
   - Netflix
   - Adobe
   - Stripe
   - OpenAI
   - Anthropic
   - etc.

2. **General job boards / aggregators**
   - LinkedIn
   - Indeed
   - ZipRecruiter
   - Built In
   - Wellfound
   - Dice
   - other legally/API-accessible sources

The important architectural decision is to **treat every source as an adapter**, rather than building one giant scraper.

```text
                        ┌──────────────────────────┐
                        │       User Profile       │
                        │                          │
                        │ Target companies         │
                        │ Target roles             │
                        │ Locations                │
                        │ Experience level         │
                        │ Skills                   │
                        └────────────┬─────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                        SOURCE MANAGER                             │
│                                                                  │
│  Official Careers                     Job Boards                 │
│  ┌───────────────┐                    ┌────────────────┐          │
│  │ Google        │                    │ LinkedIn       │          │
│  │ Amazon        │                    │ Indeed         │          │
│  │ Microsoft     │                    │ ZipRecruiter   │          │
│  │ Apple         │                    │ Built In       │          │
│  │ Meta          │                    │ Wellfound      │          │
│  │ NVIDIA        │                    │ ...            │          │
│  └───────┬───────┘                    └───────┬────────┘          │
│          │                                    │                   │
│          └───────────────┬────────────────────┘                   │
└──────────────────────────┼───────────────────────────────────────┘
                           ▼
                 ┌─────────────────────┐
                 │ Acquisition Layer   │
                 │ API / HTML / Browser│
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ Raw Job Store       │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ Normalization       │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ Deduplication       │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ AI Classification   │
                 │ + Matching          │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ PostgreSQL          │
                 └──────────┬──────────┘
                            ▼
             ┌──────────────┴──────────────┐
             ▼                             ▼
       Web Dashboard                  Notifications
                                      Email / Slack
```

---

## 2. Goals

### Primary goals

The system should:

- Track a configurable list of companies.
- Check their official career sites.
- Check supported external job boards.
- Discover newly posted jobs.
- Detect jobs that have disappeared/closed.
- Normalize inconsistent job data.
- Deduplicate the same job appearing on multiple sources.
- Preserve the official application URL.
- Search/filter jobs efficiently.
- Match jobs against a user's profile.
- Track jobs already viewed/applied to.
- Notify the user about relevant new jobs.
- Maintain historical data.
- Be easy to add new companies to.

### Secondary goals

Eventually:

- Resume-aware matching.
- Cover-letter generation.
- Application tracking.
- Job posting change detection.
- Salary/compensation extraction.
- Visa sponsorship classification.
- New-grad/entry-level classification.
- Company-specific hiring trends.
- Job-search analytics.

---

## 3. Non-Goals for V1

I would explicitly **not** build these initially:

- Automatic job applications.
- Automatic LinkedIn interactions.
- CAPTCHA bypassing.
- Aggressive browser automation.
- Scraping private/authenticated job data.
- Automatically contacting recruiters.
- Automatically submitting resumes.

The aggregator should primarily **discover and organize opportunities**, while sending the user to the legitimate application page.

---

# 4. Core Architectural Principle

## Source adapters, not site-specific business logic

The biggest mistake would be:

```text
Google scraper
Amazon scraper
Microsoft scraper
Apple scraper
...
```

with all of them directly writing to PostgreSQL.

Instead:

```text
                 SourceAdapter
                     │
          ┌──────────┼───────────┐
          ▼          ▼           ▼
       Greenhouse   Lever       Workday
          │          │           │
          └──────────┼───────────┘
                     ▼
               Canonical Job
```

Each source is responsible only for:

> "How do I retrieve jobs from this source?"

Everything afterward is source-independent.

---

# 5. Source Strategy

This is probably the most important component of the entire system.

## Tier 1: Public ATS APIs

Use structured APIs wherever possible.

### Greenhouse

Greenhouse's public Job Board API exposes published jobs, locations, departments, descriptions, URLs, IDs and other fields without authentication for GET endpoints.

This makes it an excellent source adapter.

```text
GreenhouseAdapter
       │
       ▼
GET /v1/boards/{board_token}/jobs
       │
       ▼
Canonical Job
```

### Lever

Lever provides a public postings API capable of retrieving published postings, including paginated listings and individual postings.

```text
LeverAdapter
       │
       ▼
GET /v0/postings/{site}
       │
       ▼
Canonical Job
```

### Ashby

Ashby provides a public Job Postings API for currently published postings, including optional compensation information.

```text
AshbyAdapter
       │
       ▼
Job Posting API
       │
       ▼
Canonical Job
```

### Why this matters

Instead of scraping:

```text
HTML
JavaScript
DOM
pagination
buttons
```

we get structured records such as:

```json
{
  "title": "...",
  "location": "...",
  "description": "...",
  "job_id": "...",
  "url": "..."
}
```

This should be the preferred acquisition mechanism.

---

# 6. Tier 2: Official Company APIs / Feeds

Some large companies expose structured career data or use identifiable ATS infrastructure.

For each company maintain:

```yaml
company:
  id: google
  name: Google
  careers_url: ...
  adapter: google
  source_type: official
  country: US
  enabled: true
```

The adapter could use:

- public API
- JSON endpoint
- structured feed
- server-rendered HTML
- embedded JSON
- sitemap
- browser automation as a last resort

---

# 7. Tier 3: Browser-Based Extraction

Some career sites will inevitably require browser automation.

For those:

```text
Playwright
   │
   ├── Navigate
   ├── Wait
   ├── Extract
   └── Return normalized raw data
```

But this should be the **fallback**, not the default.

Reasons:

- slower
- more expensive
- more fragile
- bot detection
- UI changes
- JavaScript complexity
- higher operational burden

I'd isolate these adapters so failures don't affect the rest of the pipeline.

---

# 8. General Job Boards

The external-board architecture should be identical:

```text
LinkedInAdapter
IndeedAdapter
ZipRecruiterAdapter
BuiltInAdapter
WellfoundAdapter
...
```

However, there's an important architectural distinction:

### Official sources

```text
Source of truth
```

### Aggregators

```text
Discovery source
```

If a job appears on both:

```text
Google Careers
LinkedIn
Indeed
```

the official posting should generally become the canonical application destination.

---

# 9. Canonical Job Model

Every source gets transformed into a common schema.

Example:

```python
class CanonicalJob:
    company_id: UUID

    source_id: UUID
    source_job_id: str

    title: str
    description: str

    locations: list[Location]

    employment_type: EmploymentType
    workplace_type: WorkplaceType

    department: str | None
    team: str | None

    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None

    posted_at: datetime | None
    updated_at: datetime | None

    application_url: str

    source_url: str

    requisition_id: str | None

    raw_data: dict

    content_hash: str
```

---

# 10. Database Design

Use **PostgreSQL** as the primary database.

Why?

- relational data
- strong consistency
- excellent indexing
- JSONB support
- full-text search
- vector extensions if needed
- mature ecosystem
- easy AWS deployment

## Core tables

### companies

```sql
companies
---------
id
name
slug
website
careers_url
logo_url
active
created_at
updated_at
```

### sources

```sql
sources
-------
id
name
type
provider
base_url
active
created_at
```

### company_sources

This maps a company to one or more sources.

```sql
company_sources
---------------
id
company_id
source_id
adapter
configuration
enabled
last_successful_sync
last_attempted_sync
```

This is extremely useful.

For example:

```text
Stripe
 ├── Official Stripe Careers
 └── LinkedIn

Company X
 └── Greenhouse

Company Y
 └── Lever
```

---

# 11. Jobs Table

```sql
jobs
----
id UUID PRIMARY KEY

company_id
canonical_title

description

employment_type
workplace_type

posted_at
first_seen_at
last_seen_at
closed_at

salary_min
salary_max
salary_currency

department
team

application_url

canonical_url

content_hash

status

created_at
updated_at
```

---

# 12. Job Sources

This is critical for deduplication and provenance.

```sql
job_sources
-----------
id

job_id
source_id

source_job_id
source_url

source_application_url

source_title
source_location

source_posted_at

raw_payload JSONB

first_seen_at
last_seen_at

is_active
```

Now:

```text
Canonical Job #123

Sources:
 ├── Google Careers
 ├── LinkedIn
 └── Indeed
```

rather than storing three independent jobs.

---

# 13. Job Locations

A job can have multiple locations.

```sql
job_locations
-------------
job_id
city
state
country
postal_code
remote_allowed
hybrid_allowed
location_text
```

Example:

```text
Job:
Software Engineer

Locations:
- Mountain View, CA
- New York, NY
- Seattle, WA
```

---

# 14. User Profile

Eventually:

```sql
user_profiles
-------------
id

resume_text
resume_embedding

years_experience
education

target_roles
target_companies
target_locations

visa_requirements

created_at
updated_at
```

For a personal version, this could initially just be a JSON configuration.

---

# 15. Job Status

Use a lifecycle:

```text
DISCOVERED
    ↓
ACTIVE
    ↓
UPDATED
    ↓
CLOSED
```

But don't immediately mark a job closed because one scraper request failed.

Instead track:

```text
last_seen_at
consecutive_missed_syncs
```

Example policy:

```text
1 failed fetch → don't change status

1 successful fetch where job absent
→ suspicious

2–3 consecutive successful fetches where job absent
→ CLOSED
```

This prevents transient source failures from incorrectly removing jobs.

---

# 16. Acquisition Pipeline

The ingestion pipeline should be asynchronous.

```text
Scheduler
    │
    ▼
Create Sync Job
    │
    ▼
Queue
    │
    ▼
Worker
    │
    ▼
Source Adapter
    │
    ▼
Raw Job
    │
    ▼
Normalization
    │
    ▼
Deduplication
    │
    ▼
Classification
    │
    ▼
Database
```

---

# 17. Scheduling

Different sources need different frequencies.

### High-value sources

Every 2–4 hours.

### Medium-value sources

Every 6–12 hours.

### Lower-priority sources

Daily.

Avoid unnecessarily polling every source every few minutes.

---

# 18. Job Scheduler

For V1:

### APScheduler

Simple and perfectly adequate for a single deployment.

For a larger system:

### Celery + Redis

```text
Celery Beat
     │
     ▼
Redis
     │
     ▼
Celery Workers
```

Or:

### AWS EventBridge + SQS

For AWS-native deployment:

```text
EventBridge
     │
     ▼
SQS
     │
     ▼
ECS/Fargate Workers
```

I'd start with APScheduler and migrate only when necessary.

---

# 19. Raw Data Layer

Don't immediately throw away the source response.

Store it.

```sql
raw_source_documents
--------------------
id
source_id
company_id

fetched_at

content
content_type

http_status
response_headers

content_hash
```

Why?

Because when the parser breaks, you can reproduce the issue.

It also lets you reprocess old jobs without hitting the company's site again.

---

# 20. Normalization

Different sources might say:

```text
Software Engineer
Software Engineer I
Software Engineer, Backend
SWE I
Software Development Engineer I
```

The raw title must remain untouched.

But we can create:

```text
canonical_role = SOFTWARE_ENGINEER
level = ENTRY
specialization = BACKEND
```

This gives us powerful filtering.

---

# 21. Role Taxonomy

Define a controlled vocabulary.

```text
Engineering
├── Software Engineer
│   ├── Backend
│   ├── Frontend
│   ├── Full Stack
│   ├── Mobile
│   ├── Infrastructure
│   ├── Distributed Systems
│   └── Platform
│
├── Machine Learning Engineer
├── AI Engineer
├── Data Engineer
├── Data Scientist
├── Research Engineer
├── Applied Scientist
└── Security Engineer
```

And seniority:

```text
Intern
New Grad
Entry
Mid
Senior
Staff
Principal
Manager
Director
```

---

# 22. AI Classification Pipeline

For every new job:

```text
Job Description
       │
       ▼
LLM Classifier
       │
       ├── Role
       ├── Seniority
       ├── Skills
       ├── Domain
       ├── Location
       ├── New Grad?
       ├── Sponsorship?
       ├── Salary
       └── Requirements
```

Example output:

```json
{
  "role": "software_engineer",
  "specialization": ["backend", "distributed_systems"],
  "seniority": "entry",
  "new_grad": true,
  "skills": [
    "Python",
    "Java",
    "AWS",
    "Distributed Systems"
  ],
  "visa_sponsorship": "unknown"
}
```

---

# 23. Don't Use an LLM for Everything

Use deterministic code where possible.

### Regex / rules

For example:

```text
"0-2 years"
"1+ years"
"new graduate"
"2026 graduates"
```

can often be classified without an LLM.

### LLM

Use it for ambiguous semantic interpretation:

> "Currently pursuing or recently completed a Bachelor's degree..."

or:

> "Experience building large-scale ML infrastructure."

This reduces:

- cost
- latency
- hallucinations
- unnecessary complexity

---

# 24. LLM Classification Should Be Asynchronous

Don't make users wait for classification.

```text
Job discovered
      │
      ▼
Store immediately
      │
      ├───────────────► Dashboard
      │
      ▼
Classification Queue
      │
      ▼
LLM
      │
      ▼
Update job
```

The job should appear quickly, then become progressively enriched.

---

# 25. User Matching

Use a hybrid matching system.

Not:

```text
LLM → "87% match"
```

by itself.

Instead:

```text
                Job
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
Structured matching     Semantic matching
       │                    │
       │                    │
Role                   Resume embedding
Location               Job embedding
Seniority              Skill similarity
Visa                   Description similarity
       │                    │
       └─────────┬──────────┘
                 ▼
          Match explanation
```

---

# 26. Avoid a Single "Match Score"

Instead of:

> 92% match

show:

```text
Strong role match
✓ Software Engineering
✓ Backend
✓ Python
✓ AWS

Potential gap
△ 3+ years experience requested

Location
✓ Phoenix / Remote compatible

Education
✓ Master's / Bachelor's accepted
```

This is more actionable and easier to audit.

---

# 27. Embeddings

PostgreSQL + pgvector is sufficient initially.

Store:

```text
job_embedding
resume_embedding
```

Then:

```sql
SELECT *
FROM jobs
ORDER BY embedding <=> :resume_embedding
LIMIT 50;
```

No need for Pinecone/Weaviate/etc. in V1.

---

# 28. Deduplication

This is one of the hardest parts.

A job can have:

```text
Google:
Software Engineer III
```

and LinkedIn:

```text
Software Engineer III - Google
```

and Indeed:

```text
Software Engineer, Google
```

We need to recognize them as one job.

## Deduplication hierarchy

### Level 1 — Exact source ID

Best:

```text
company + source + source_job_id
```

### Level 2 — Requisition ID

If available:

```text
company + requisition_id
```

### Level 3 — Application URL

Normalize:

```text
tracking parameters
utm_*
ref
source
```

### Level 4 — Content fingerprint

Normalize:

```text
title
company
location
description
```

Then hash.

### Level 5 — Semantic similarity

For difficult cases:

```text
embedding similarity > threshold
```

Potential duplicate candidates can then be reviewed/merged algorithmically.

---

# 29. Canonical Source Priority

When multiple sources disagree:

```text
Official company source
       ↓
ATS source
       ↓
Major job board
       ↓
Other aggregator
```

For example, if salary differs across sources, don't blindly merge them.

Store both values and assign provenance.

```json
{
  "salary": {
    "value": "$X-$Y",
    "source": "official",
    "confidence": "high"
  }
}
```

---

# 30. Change Detection

Suppose:

```text
Monday:
Software Engineer
2+ years experience
```

Tuesday:

```text
Software Engineer
1+ years experience
```

The system should detect:

```text
Job updated

Changed:
Experience requirement
2+ years → 1+ years
```

Store:

```text
job_versions
------------
job_id
version
content_hash
description
requirements
captured_at
```

---

# 31. Search Architecture

For V1, PostgreSQL is enough.

Use:

- B-tree indexes
- GIN indexes
- PostgreSQL full-text search
- pgvector

Example:

```text
Query:
"entry level machine learning engineer Python"

        ↓

Full text search
        +
Structured filters
        +
Vector similarity
```

No Elasticsearch required initially.

---

# 32. Backend

### Recommendation

**Python + FastAPI**

Why it fits:

- excellent HTTP ecosystem
- async support
- easy integration with scrapers
- ML/LLM ecosystem
- Pydantic
- easy testing
- clean OpenAPI generation

Suggested structure:

```text
backend/
├── api/
│   ├── jobs.py
│   ├── companies.py
│   ├── sources.py
│   └── users.py
│
├── adapters/
│   ├── base.py
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── google.py
│   └── ...
│
├── ingestion/
│   ├── fetcher.py
│   ├── normalizer.py
│   ├── deduplicator.py
│   └── classifier.py
│
├── models/
├── repositories/
├── services/
├── workers/
└── config/
```

---

# 33. Frontend

### Next.js + TypeScript

Recommended:

- Next.js
- TypeScript
- Tailwind
- shadcn/ui
- TanStack Query

Example dashboard:

```text
┌──────────────────────────────────────────────────────────────┐
│ Job Tracker                                      🔔  Profile │
├──────────────────────────────────────────────────────────────┤
│ Search jobs...                                               │
│                                                              │
│ Companies     Role          Level       Location             │
│ [50 selected] [SWE]         [New Grad]  [US]                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  NEW TODAY                                                   │
│                                                              │
│  Google                                                       │
│  Software Engineer                                            │
│  Mountain View, CA                                            │
│                                                              │
│  ✓ New Grad   ✓ Backend   ✓ Python                           │
│                                                              │
│  [View Job] [Save]                                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

# 34. API Design

Example endpoints:

```text
GET /api/jobs
GET /api/jobs/{id}

GET /api/companies
GET /api/companies/{id}

GET /api/sources

POST /api/jobs/{id}/save
POST /api/jobs/{id}/apply
POST /api/jobs/{id}/dismiss

GET /api/recommendations
GET /api/jobs/new

POST /api/sync/{company_id}
```

Example filters:

```text
/api/jobs?
company=google,apple
role=software-engineer
level=new-grad
location=us
posted_after=2026-09-22
remote=true
```

---

# 35. Application Tracking

Each job can eventually have:

```text
NOT_VIEWED
VIEWED
SAVED
APPLIED
INTERVIEW
REJECTED
OFFER
WITHDRAWN
```

This transforms the aggregator into a lightweight ATS for the applicant.

---

# 36. Notifications

### Email

```text
Daily Job Digest

12 new jobs matching your profile

Google
- Software Engineer

Apple
- Software Engineer, Cloud

NVIDIA
- Machine Learning Engineer
```

### Immediate notification

Only for high-confidence matches:

```text
New Google job

Software Engineer
Mountain View, CA

Matches your target role and experience.
```

### Slack/Discord

Could be added later.

---

# 37. Notification Deduplication

Never notify repeatedly about the same job.

Store:

```sql
notifications
-------------
user_id
job_id
type
sent_at
```

Unique constraint:

```text
(user_id, job_id, notification_type)
```

---

# 38. Company Configuration

This should be data-driven rather than hardcoded.

Example:

```yaml
companies:

  - id: google
    name: Google
    official:
      adapter: google
      url: https://careers.google.com
    enabled: true
    priority: high

  - id: stripe
    name: Stripe
    official:
      adapter: ashby
      board: stripe
    enabled: true
    priority: high

  - id: example
    name: Example Corp
    official:
      adapter: greenhouse
      board_token: example
    enabled: true
```

Adding a company should ideally require:

```text
Add config
→ test
→ enable
```

rather than modifying application code.

---

# 39. Adapter Interface

Something like:

```python
class JobSourceAdapter(ABC):

    @abstractmethod
    async def discover(self) -> list[RawJob]:
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> RawJob:
        ...

    @abstractmethod
    def normalize(self, raw: RawJob) -> CanonicalJob:
        ...
```

Then:

```python
class GreenhouseAdapter(JobSourceAdapter):
    ...

class LeverAdapter(JobSourceAdapter):
    ...

class AshbyAdapter(JobSourceAdapter):
    ...

class GoogleAdapter(JobSourceAdapter):
    ...
```

---

# 40. Adapter Health Monitoring

Every adapter should expose:

```text
last_success
last_failure
jobs_found
jobs_added
jobs_updated
jobs_removed
latency
error_rate
```

Dashboard:

```text
SOURCE HEALTH

Google         ✓ 12 min ago
Amazon         ✓ 17 min ago
Microsoft      ✓ 22 min ago
Apple          ⚠ 2 hrs ago
NVIDIA         ✓ 14 min ago
Greenhouse     ✓ 5 min ago
```

This is important because web scrapers silently break.

---

# 41. Observability

Use structured JSON logging:

```json
{
  "source": "google",
  "event": "sync_completed",
  "jobs_found": 1243,
  "jobs_new": 17,
  "duration_ms": 1240
}
```

Useful metrics:

```text
jobs_fetched_total
jobs_created_total
jobs_updated_total
source_failures_total
sync_duration_seconds
llm_classification_latency
```

Sentry would be useful for error tracking.

---

# 42. Testing

Every adapter gets:

### Unit tests

```text
HTML/JSON fixture
      ↓
Parser
      ↓
Expected CanonicalJob
```

### Integration tests

Run against the actual public endpoint periodically.

### Regression fixtures

Store previously encountered payloads.

If a company changes its page:

```text
Parser test fails
→ CI catches it
```

---

# 43. Rate Limiting

Each adapter should have its own limits.

```python
rate_limit = {
    "requests_per_second": 0.5,
    "concurrency": 2
}
```

Support:

```text
Retry-After
429
5xx
timeouts
```

with exponential backoff.

Always respect applicable site terms, robots policies, API limits, and access restrictions.

---

# 44. Caching

Use Redis for:

- rate limiting
- short-lived API cache
- distributed locks
- job queue
- duplicate sync prevention

But don't make Redis the source of truth.

PostgreSQL remains authoritative.

---

# 45. Security

Even for a personal application:

### Authentication

Use one of:

- Auth.js
- Clerk
- Supabase Auth
- Cognito

### Secrets

Never put:

```text
API keys
database passwords
LLM keys
```

in Git.

Use AWS Secrets Manager or environment secrets.

### Database

- private subnet
- encryption at rest
- TLS
- least-privilege DB users

---

# 46. Privacy

If the system stores:

- resume
- profile
- application history
- personal information

treat it as sensitive.

Don't send the entire resume to an LLM for every job.

Instead:

```text
Resume
 ↓
Extract structured profile
 ↓
Store profile
 ↓
Generate embedding
```

Then use the structured profile for most matching.

---

# 47. LLM Cost Optimization

Suppose:

```text
50 companies
× 500 jobs
= 25,000 jobs
```

You don't want to send 25,000 descriptions to an expensive model every day.

Instead:

### Stage 1

Cheap deterministic filtering:

```text
title
location
level
employment type
```

### Stage 2

Cheap embedding:

```text
semantic similarity
```

### Stage 3

LLM only for:

```text
top candidates
ambiguous classifications
new/changed jobs
```

This can reduce LLM calls dramatically.

---

# 48. AI Model Strategy

Keep the model provider abstract:

```python
class LLMProvider:
    async def classify(self, job):
        ...
```

Implement:

```text
OpenAIProvider
AnthropicProvider
LocalModelProvider
```

That prevents vendor lock-in.

For a personal deployment, a hosted model is likely easiest initially.

---

# 49. Data Retention

Don't delete closed jobs immediately.

Keep historical records.

Potential policy:

```text
Active jobs:
indefinite

Closed jobs:
12–24 months

Raw HTML/API responses:
30–90 days
```

Historical data enables:

- hiring trend analysis
- posting duration
- company hiring volume
- job reopening detection

---

# 50. Job Reopening Detection

Company:

```text
Software Engineer
Req #1234
```

Job closes.

Three months later:

```text
same requisition / similar job
```

The system should distinguish:

```text
same posting reopened
```

from:

```text
new requisition
```

Store historical IDs and content fingerprints.

---

# 51. Salary Handling

Salary data is inconsistent.

Store:

```text
salary_min
salary_max
currency
period
location
source
confidence
```

Example:

```json
{
  "min": 140000,
  "max": 190000,
  "currency": "USD",
  "period": "annual",
  "source": "official",
  "confidence": "high"
}
```

Never interpret missing salary as "$0".

---

# 52. Visa Sponsorship

For a US-focused job search, this could become a valuable field.

Use multiple states:

```text
YES
NO
UNKNOWN
UNCLEAR
```

Don't have an LLM infer:

> "This company usually sponsors."

from unrelated evidence.

Instead distinguish:

```text
Explicitly stated
Explicitly prohibited
Not mentioned
Ambiguous
```

This prevents misleading results.

---

# 53. Location Normalization

Normalize:

```text
Mountain View
Mountain View, California
Mountain View, CA
```

to:

```text
city = Mountain View
state = CA
country = US
```

Potentially use a geocoding API, but cache normalized locations so you don't repeatedly geocode the same city.

---

# 54. Remote Classification

Don't rely only on a checkbox.

Classify:

```text
REMOTE
HYBRID
ONSITE
FLEXIBLE
UNKNOWN
```

Preserve the original text.

Example:

> "Employees must be located within 50 miles of one of our offices."

This is not equivalent to unrestricted remote.

---

# 55. Freshness

Every job should expose:

```text
Posted:
3 hours ago

Last verified:
17 minutes ago
```

Those are different concepts.

A job might have been posted 40 days ago but verified as still active 10 minutes ago.

---

# 56. "New Job" Definition

Define it precisely.

A job is **new to the system** if:

```text
first_seen_at > last_user_digest_time
```

Not necessarily:

```text
posted_at > yesterday
```

because many sources don't reliably provide original posting dates.

Maintain both timestamps.

---

# 57. Job Board vs Official Source Conflicts

Example:

```text
Official:
Software Engineer
Req 12345
$150K–$200K

LinkedIn:
Software Engineer
Req 12345
$140K–$180K
```

Don't overwrite.

Store:

```text
Official source:
$150K–$200K

LinkedIn:
$140K–$180K
```

and show the official value as the preferred source when appropriate.

---

# 58. Recommended Tech Stack

| Component | Technology |
|---|---|
| Frontend | Next.js + TypeScript |
| Backend | FastAPI + Python |
| Database | PostgreSQL |
| Vector search | pgvector |
| Queue | Redis |
| Scheduler | APScheduler |
| Scraping | httpx + BeautifulSoup |
| Browser automation | Playwright |
| Validation | Pydantic |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| AI | LLM API + embeddings |
| Auth | Auth.js / Clerk |
| UI | Tailwind + shadcn/ui |
| Testing | Pytest + Playwright |
| Monitoring | Sentry |
| Deployment | Docker |
| Cloud | AWS |

---

# 59. AWS Architecture

For a serious deployment:

```text
                         CloudFront
                             │
                             ▼
                        Next.js App
                             │
                             ▼
                          ALB
                             │
                             ▼
                         FastAPI
                             │
                 ┌───────────┴────────────┐
                 ▼                        ▼
             PostgreSQL                 Redis
                 │                        │
                 │                     SQS
                 │                        │
                 │                        ▼
                 │                   ECS Workers
                 │                        │
                 │             ┌──────────┼──────────┐
                 │             ▼          ▼          ▼
                 │          Google     Greenhouse   Lever
                 │
                 ▼
              pgvector
```

AWS services:

- ECS/Fargate
- RDS PostgreSQL
- ElastiCache Redis
- S3
- SQS
- EventBridge
- CloudFront
- Secrets Manager
- CloudWatch

---

# 60. But Don't Start With This

For the MVP:

```text
Docker Compose

Next.js
FastAPI
PostgreSQL
Redis
Worker
```

That's enough.

Don't start with:

```text
Kubernetes
Kafka
Elasticsearch
20 microservices
```

You don't need them.

---

# 61. Monolith vs Microservices

Choose a **modular monolith** initially.

```text
One backend
├── API
├── ingestion
├── adapters
├── classification
├── matching
└── notifications
```

with workers running separately.

Why?

The domain is still evolving.

You'll discover that:

- some sources need browser automation
- some APIs return different fields
- deduplication rules change
- classification changes
- UI requirements change

A modular monolith keeps iteration fast.

Split services later only when there is a demonstrated need.

---

# 62. MVP Scope

Build the first version around **10–15 companies**.

Example:

```text
Google
Amazon
Microsoft
Apple
Meta
NVIDIA
Netflix
Adobe
Stripe
OpenAI
Anthropic
Databricks
Uber
Airbnb
Salesforce
```

Then support:

```text
Greenhouse
Lever
Ashby
```

plus a few official custom adapters.

The MVP should produce:

```text
Company
Title
Location
Posted date
Description
Official URL
Source
Status
```

That's enough to validate the concept.

---

# 63. Phase 2

Add:

- 50–100 companies
- more ATS adapters
- external job boards
- deduplication
- saved jobs
- application tracking
- notifications
- advanced filters

---

# 64. Phase 3

Add:

- resume ingestion
- AI job matching
- skill extraction
- sponsorship classification
- semantic search
- job-change detection
- personalized daily digest

---

# 65. Phase 4

Potentially:

```text
Resume
   ↓
Job
   ↓
Gap analysis
   ↓
Recommended resume version
   ↓
Cover letter
   ↓
Application tracking
```

At that point the product becomes more than a job aggregator.

It becomes a **job-search operating system**.

---

# 66. Example End-to-End Flow

Suppose Apple posts:

> Software Engineer, Cloud Infrastructure

### Step 1

Apple adapter discovers it.

```text
source_job_id = 200636744
```

### Step 2

Raw response gets stored.

### Step 3

Normalizer creates:

```text
company = Apple
role = Software Engineer
specialization = Cloud Infrastructure
location = Cupertino, CA
```

### Step 4

Deduplication checks existing jobs.

No match.

### Step 5

Job gets inserted.

```text
status = ACTIVE
first_seen_at = 08:14
```

### Step 6

Rule engine:

```text
SWE?        YES
US?         YES
Entry?      YES
```

### Step 7

Semantic matching:

```text
Resume ↔ Job
```

### Step 8

Classification:

```text
New Grad: likely
Backend: yes
Cloud: yes
Python: yes
C++: yes
```

### Step 9

Notification:

```text
New Apple job matching your profile
```

### Step 10

User clicks Apply and is sent to Apple's official application page.

---

# 67. Important Architectural Decision: Preserve Provenance

Every important field should ideally have provenance.

Instead of simply:

```json
{
  "salary": 180000
}
```

store:

```json
{
  "salary": {
    "value": 180000,
    "source": "official",
    "retrieved_at": "2026-09-29T..."
  }
}
```

This becomes extremely valuable when sources disagree.

---

# 68. Important Architectural Decision: Raw + Normalized Data

Never make normalized data your only data.

Use:

```text
Raw source
    ↓
Normalized representation
    ↓
Enriched representation
```

So if your normalization algorithm changes, you can reprocess historical raw data.

This is a core design principle.

---

# 69. Important Architectural Decision: Idempotent Ingestion

Running:

```text
sync_google()
```

twice should not create duplicate jobs.

Everything should be idempotent around:

```text
company_id
+
source_id
+
source_job_id
```

Use database uniqueness constraints as the final protection.

---

# 70. Important Architectural Decision: Official URLs Win

When multiple sources identify the same job:

```text
canonical_application_url
```

should generally point to the company's official application destination.

External sources remain useful for:

- discovery
- alternate metadata
- confirmation
- provenance

but not as the preferred application destination when an official URL is available.

---

# 71. Development Roadmap

### Milestone 1 — Foundation

Build:

- PostgreSQL
- FastAPI
- Next.js
- company table
- source table
- job table
- adapter interface

### Milestone 2 — ATS ingestion

Implement:

```text
Greenhouse
Lever
Ashby
```

### Milestone 3 — Official company adapters

Implement:

```text
Google
Amazon
Microsoft
Apple
Meta
NVIDIA
```

### Milestone 4 — Dashboard

Build:

- search
- filters
- company pages
- job detail
- save
- application status

### Milestone 5 — Deduplication

Add:

- URL normalization
- requisition matching
- content fingerprints
- semantic duplicate detection

### Milestone 6 — AI

Add:

- role classification
- seniority
- skills
- new-grad classification
- semantic matching

### Milestone 7 — Notifications

Add:

- daily digest
- instant high-confidence alerts

### Milestone 8 — Job boards

Add external sources progressively, subject to their available APIs and access terms.

---

# 72. What I Would Build First

Do not start by trying to support every company.

Build this vertical slice:

```text
              Google
                │
           Career Adapter
                │
                ▼
          Canonical Job
                │
                ▼
            PostgreSQL
                │
                ▼
           FastAPI API
                │
                ▼
          Next.js Dashboard
```

Then add:

```text
Amazon
Microsoft
Apple
```

Then:

```text
Greenhouse
Lever
Ashby
```

Then deduplication.

Then AI.

Then notifications.

That gives you a working system very early rather than spending weeks building infrastructure before seeing a job on the screen.

---

# 73. Final Proposed Architecture

```text
                         ┌─────────────────────┐
                         │      USER PROFILE   │
                         │ Resume / Preferences│
                         └──────────┬──────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       JOB DISCOVERY                             │
│                                                                 │
│ Official Companies                 External Sources             │
│ ┌───────────────────────┐         ┌────────────────────────┐    │
│ │ Google                │         │ LinkedIn               │    │
│ │ Amazon                │         │ Indeed                 │    │
│ │ Microsoft             │         │ ZipRecruiter           │    │
│ │ Apple                 │         │ Built In               │    │
│ │ Meta                  │         │ Wellfound              │    │
│ │ NVIDIA                │         │ ...                    │    │
│ └───────────┬───────────┘         └────────────┬───────────┘    │
│             │                                  │                │
│             └───────────────┬──────────────────┘                │
└─────────────────────────────┼───────────────────────────────────┘
                              ▼
                     ┌──────────────────┐
                     │ Source Adapters  │
                     │ API / HTML /     │
                     │ Browser          │
                     └────────┬─────────┘
                              ▼
                     ┌──────────────────┐
                     │ Raw Data Store   │
                     └────────┬─────────┘
                              ▼
                     ┌──────────────────┐
                     │ Normalization    │
                     └────────┬─────────┘
                              ▼
                     ┌──────────────────┐
                     │ Deduplication    │
                     └────────┬─────────┘
                              ▼
                     ┌──────────────────┐
                     │ Canonical Jobs   │
                     └────────┬─────────┘
                              │
                 ┌────────────┼─────────────┐
                 ▼            ▼             ▼
          Classification  Embeddings   Change Detection
                 │            │             │
                 └────────────┼─────────────┘
                              ▼
                     ┌──────────────────┐
                     │   PostgreSQL     │
                     │ + pgvector       │
                     └────────┬─────────┘
                              │
                ┌─────────────┼──────────────┐
                ▼             ▼              ▼
             Search       Matching       Analytics
                │             │              │
                └─────────────┼──────────────┘
                              ▼
                     ┌──────────────────┐
                     │ Next.js Web App  │
                     └────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              Job Dashboard       Notifications
                                  Email / Slack
```

---

# 74. Final Architectural Decisions

The most important decisions are:

1. **Official career sites are first-class sources**, not an afterthought.
2. **Use public ATS APIs wherever available** rather than scraping HTML.
3. **Use source adapters** so adding a company doesn't require rewriting the system.
4. **Keep raw source data separately from normalized jobs.**
5. **Represent one canonical job with multiple source records.**
6. **Prefer the official company application URL.**
7. **Use PostgreSQL + pgvector initially; don't over-engineer the data layer.**
8. **Use deterministic extraction before LLM-based extraction.**
9. **Make ingestion asynchronous and idempotent.**
10. **Treat source health as a first-class operational concern.**
11. **Build a modular monolith first, not microservices.**
12. **Start with ~10–15 companies and 3 major ATS platforms, prove the pipeline, then expand.**

The resulting product can start as a **personal job tracker** and later evolve into a much more sophisticated system that answers:

> **"What relevant jobs were newly posted today across all the companies I care about?"**

without requiring you to manually visit dozens of career sites.

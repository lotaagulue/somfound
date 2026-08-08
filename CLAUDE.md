# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Somfound is a demo web app for a **real, already-operating Nigerian community-development
nonprofit** (see "Real-world context" below), not a from-scratch hypothetical. It lets villagers
in South-East Nigeria report crime/safety issues, infrastructure problems, community needs
(water, medical help), and positive local news — via a web form or plain SMS — onto a
public, moderator-reviewed map. Full product spec (user flows, taxonomy, data model,
risks, roadmap): [README.md](README.md).

## Commands

```bash
uv sync                                       # install deps (incl. dev/test)
uv run uvicorn somfound.main:app --reload     # run the app — http://localhost:8000
uv run pytest                                 # run the full test suite
uv run pytest tests/test_sms_parser.py -q     # run one test file
uv run pytest tests/test_reports.py::test_sms_rate_limit_stops_after_threshold  # single test
```

There's no separate lint/format command configured yet. The SQLite DB file (`somfound.db`,
gitignored) is created and seeded automatically on first run/import — delete it to reset.

## Architecture

FastAPI + SQLModel (SQLite by default), server-rendered Jinja2 + Leaflet (via CDN, no JS
build step). One process serves everything — public pages, the JSON API, and the SMS
webhook — under `src/somfound/`:

- **`models.py`** — SQLModel tables (`Report`, `Village`, `SmsInbound`) and the enums/label
  dicts (`Category`, `Urgency`, `Status`, `SourceChannel`). `CATEGORY_LABELS`/`CATEGORY_ICONS`
  and `URGENCY_LABELS`/`URGENCY_COLORS` are the single source of truth for how those enums
  render — routers and templates pull from these rather than hardcoding labels/colors.
- **`sms_parser.py`** — pure function, no I/O: turns freeform SMS text into
  `(category, urgency, description, village)` via a leading-keyword map, escalation words,
  and village-name matching. Covered directly by `tests/test_sms_parser.py` with no DB/app
  needed.
- **`sms_service.py`** — `process_inbound_sms()`: the shared pipeline (parse → per-phone
  rate limit → create `Report` → log `SmsInbound`) used by both `POST /sms/inbound` (a real
  webhook, shaped for a future SMS gateway) and `/sms/simulate` (the in-app demo UI). Keep
  new inbound-SMS behavior here, not duplicated across the two callers.
- **`crud.py`** — the only place that touches the DB for reads/writes report data; hashes
  reporter phone numbers (`hash_reporter_contact`) so raw numbers are never persisted.
- **`routers/`** — `pages.py` (public map + report form), `moderation.py` (queue, HTTP Basic
  auth via `auth.py`), `api.py` (JSON feed the map's JS polls), `sms.py` (both the real
  webhook and `/sms/simulate`, both backed by `sms_service.py`).
- **`main.py`** — assembles the FastAPI app. Notably calls `init_db()` + seeding **at import
  time**, not inside an ASGI lifespan hook — this was deliberate so cold starts on
  serverless hosts (Vercel) that don't reliably run lifespan events still initialize
  correctly. Both are idempotent, so this is also safe under `uvicorn --reload`.
- **`paths.py`** — absolute `STATIC_DIR`/`TEMPLATES_DIR` computed from `__file__`, not cwd,
  since cwd isn't reliable on Vercel.
- **`db.py`** — picks the SQLite path based on environment: `/tmp` on Vercel (read-only FS
  elsewhere), a local file otherwise. `DATABASE_URL` overrides this — Supabase Postgres is the
  documented path (README §12); `normalize_database_url()` rewrites the bare `postgres://`
  scheme Supabase/Heroku hand out to `postgresql://`, which SQLAlchemy requires, and non-SQLite
  engines get `execution_options={"compiled_cache": None}` because Supabase's Supavisor
  transaction-mode pooler (the right choice for serverless — see README) doesn't support
  server-side prepared statements.
- **`sms_client.py`** — optional outbound confirmation SMS via Africa's Talking. Their free
  sandbox is deprecated, so this is dormant by default (`AT_API_KEY` unset) and unused by
  the demo; it's there for whenever a real pilot wires up production SMS credentials.
- **`GET /api/health`** — cheap liveness/config check (DB reachable, which backend, village
  seed count) with no secrets in the response. First thing to hit when a deploy misbehaves,
  before assuming routing is broken.
- **`vercel_compat.py`** — works around a real, empirically-confirmed Vercel Python-runtime bug:
  requests forwarded through `vercel.json`'s catch-all rewrite arrive with `scope["path"]`
  hardcoded to the function's own address (`/api/index`) for *every* request, not the original
  URL, so plain FastAPI routing can't distinguish `/` from `/report` from `/api/reports`. Fixed
  by having the rewrite append the real path as a `__path` query param (`destination:
  "/api/index?__path=/$1"`), then `RestoreOriginalPathMiddleware` restores it before the app's
  router sees the request. Only wired into `api/index.py`, not `main.py` — local dev and Render
  never go through this rewrite at all, so they'd be unaffected either way, but keeping it out
  of `main.py` keeps the workaround visibly scoped to the platform that needs it. If Vercel's
  Python runtime is rearchitected and this workaround is no longer needed, `tests/test_vercel_compat.py`
  documents exactly what it does — recheck against a real deploy before removing it, not just
  the tests, since the tests exercise the middleware in isolation and can't reproduce the
  original bug's actual trigger (Vercel's edge behavior itself).

### Deployment targets

Three hosts are supported from one codebase, picked via env vars — no code branching needed
beyond what's in `db.py`:

- **Local dev** — `uv run uvicorn ...`
- **Render** (`render.yaml`) — persistent-ish disk per instance (resets on redeploy).
- **Vercel** (`vercel.json` + `api/index.py`) — single serverless function, all routes
  rewritten to it; SQLite lives in `/tmp` so it persists only within a warm instance.

Both platforms' free tiers reset SQLite demo data on cold start/redeploy — expected, not a bug,
documented in README §12. Fix by pointing `DATABASE_URL` at Supabase's free Postgres (via the
Supavisor **transaction pooler**, port 6543 — not the direct connection, which serverless can
exhaust) — see README §12 "Using Supabase for storage" for the exact steps.

### Design system

Urgency colors are **not** an arbitrary red/orange/yellow/blue ramp — they're the `dataviz`
skill's validated *status* palette (good/warning/serious/critical), chosen because a plain
categorical ramp failed the skill's colorblind/contrast checks for this exact use case
(adjacent severities need to be reliably distinguishable in a crime/safety context). Because
"warning"/"serious" sit under 3:1 contrast on a light surface by design, urgency is always
paired with a label or icon in the UI (map legend, popups, moderation cards) — never color
alone. If you touch `URGENCY_COLORS` in `models.py`, re-validate with
`node scripts/validate_palette.js "<hex,hex,...>"` from the `dataviz` skill before shipping.

Brand colors (deep blue `#2638c4` / `#1b2999` on warm cream `#faf6f0`, in
`static/style.css`) come from the org's own pitch deck, not a generic default.

## Real-world context

Somfound is an existing nonprofit (operating since 2020, partnered with a CAC-registered
Nigerian company for project execution) focused on community development across Nigeria's
South-East geopolitical zone — 5 states (Abia, Anambra, Ebonyi, Enugu, Imo), 95 LGAs. Its
2025 priorities include: emergency health preparedness (first-aid kits in community halls
across all 95 LGAs), an anonymous crime-tip/reward hotline, and primary-research
needs-assessment surveys — this app is effectively a digital platform prototyping the
anonymous-reporting and needs-assessment pieces of that plan (their own roadmap separately
describes wanting to launch a standalone `SomFound.ng` platform).

The org's founder supplied a business-plan PDF with this context; it's intentionally
**gitignored** (not committed) because it contains her personal contact details and photos
of community members/children — treat that file as reference-only, never as something to
publish, quote verbatim into commits, or include in generated docs.

Given the org's actual scope is 5 states / 95 LGAs, treat the README's Anambra-only pilot
and its seeded Idemili North villages as a deliberately small **placeholder** to build and
demo against — not a claim about where the real pilot will happen. That's still an open
decision (see README §10).

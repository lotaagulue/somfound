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

- **`static/style.css`** — one stylesheet, mobile-first-ish with a `max-width: 640px` breakpoint
  (nav collapses to a CSS-only checkbox-hack hamburger, forms/legend/moderation cards restack,
  tap targets sized to 44px). `static/manifest.json` + `static/icons/` make it installable to a
  phone home screen. `static/sw.js` (served at `/sw.js`, not `/static/sw.js`, so its scope
  covers the whole origin — see the route in `main.py`) adds a deliberately minimal service
  worker: cache-first for map tiles + the CDN Leaflet assets (the expensive part of loading the
  map on a slow connection), cache-first for our own static assets, and a friendly offline
  fallback page for navigations instead of the browser's dead-connection screen. It does **not**
  cache dynamic content (reports, API responses) or queue failed POSTs — that's real
  background-sync territory, out of scope for this MVP. The report form's own draft-autosave
  (plain `localStorage`, see `report_form.html`) is what actually protects against losing a
  typed report mid-fill on a dropped connection, independent of the service worker. Icons were
  generated locally with Pillow as a one-off (`uv run --with pillow ...`,
  not a project dependency) — regenerate the same way if the brand mark changes.
- **`models.py`** — SQLModel tables (`Report`, `LGA`, `SmsInbound`, plus Phase C's
  `Resource`, `ReportConfirmation`, `Wallet`, `RewardOption`, `RedemptionRequest`) and the
  enums/label dicts (`Category`, `Urgency`, `Status`, `SourceChannel`, `ResourceType`,
  `ResourceStatus`, `RedemptionStatus`). `CATEGORY_LABELS`/`CATEGORY_ICONS` and
  `URGENCY_LABELS`/`URGENCY_COLORS` (and their `RESOURCE_*` equivalents) are the single source
  of truth for how those enums render — routers and templates pull from these rather than
  hardcoding labels/colors. The location model is LGA-level (Local Government Area —
  Nigeria's admin unit below state), not individual villages; `LGA.state` is one of the 5
  South-East states.
- **`sms_parser.py`** — pure functions, no I/O. `parse_sms()` turns freeform SMS text into
  `(category, urgency, description, lga)` via a *leading*-keyword map, escalation words, and
  LGA-name matching (longest name first, to avoid a shorter name winning a substring
  collision). `guess_category_urgency()` shares the same `KEYWORD_MAP`/`ESCALATE_WORDS` but
  scans the *whole* text (earliest match wins, whole-word regex so e.g. `ROAD` doesn't
  false-positive inside `BROADBAND`) instead of only the first token — used by the web report
  form (`routers/pages.py::submit_report`), where people write a normal sentence rather than
  SMS's lead-with-a-keyword convention. Category/urgency are optional form fields; a blank one
  is auto-detected, an explicit one overrides the guess for that field only. Both functions are
  covered directly by `tests/test_sms_parser.py` with no DB/app needed.
- **`llm_classifier.py`** — optional LLM fallback for the *same* auto-detection, used only when
  `guess_category_urgency()` finds no keyword at all *and* the reporter left both fields blank
  (not a second opinion on cases keywords already handle — keeps it limited to where it adds
  value and keeps free-tier quota usage low). Two providers tried **in order**, Gemini then
  Mistral — Mistral only runs if Gemini itself didn't produce a usable answer (unset, error,
  timeout, bad response), a resilience fallback against one provider's outage/quota, never a
  parallel second opinion. Each stage is independently dormant unless its own API key
  (`GEMINI_API_KEY` / `MISTRAL_API_KEY`) is set, same pattern as `sms_client.py`: any failure
  at any stage is caught and logged, falling through to the next stage or, if both are
  exhausted, to the caller's existing `OTHER`/`MODERATE` default — neither provider's outage
  can break report submission. Both use their SDK's structured-output mode
  (`Category`/`Urgency` enum values baked into the JSON schema) rather than parsing freeform
  text, with `_parse()` still validating defensively regardless. `_run_with_timeout()` enforces
  its own hard wall-clock budget via `ThreadPoolExecutor` for both providers rather than
  trusting either SDK's own timeout handling — verified necessary for Gemini specifically
  (`http_options.timeout` has documented reliability issues upstream,
  googleapis/python-genai#911 and #1330, and also a server-side *minimum* of 10s, too slow to
  gate a request path on); Mistral's `timeout_ms` looked more trustworthy in testing but gets
  the same treatment for consistency. `_call_gemini()`/`_call_mistral()` are split out
  specifically so tests can monkeypatch just those functions (see `tests/test_llm_classifier.py`)
  without a real API key or network access — the CI environment never has either. Model names
  (`GEMINI_MODEL`/`MISTRAL_MODEL`) are configurable env vars rather than hardcoded, since
  availability shifts over time and that shouldn't need a code change.
- **`sms_service.py`** — `process_inbound_sms()`: the shared pipeline (parse → per-phone
  rate limit → create `Report` → log `SmsInbound`) used by both `POST /sms/inbound` (a real
  webhook, shaped for a future SMS gateway) and `/sms/simulate` (the in-app demo UI). Keep
  new inbound-SMS behavior here, not duplicated across the two callers.
- **`crud.py`** — the only place that touches the DB for reads/writes report data; hashes
  reporter phone numbers (`hash_reporter_contact`) so raw numbers are never persisted.
  `list_published_reports()` excludes `RESOLVED` by default (`include_resolved=True` to opt
  in) — this used to silently include resolved reports alongside published ones with no visual
  distinction, defeating the entire point of "Resolved," until a user caught it in production.
  `MAX_PENDING_PER_REPORTER` + `count_pending_reports()` are the shared spam/abuse guard behind
  both inbound channels: SMS always has a phone number to key on; the web form's phone field is
  optional, so `routers/pages.py::submit_report` falls back to hashing the submitter's IP
  (`hash_reporter_contact` doubles as a generic string hasher, not phone-specific) when none is
  given. `create_report()`'s `reporter_ref` param lets a caller pass that pre-computed key
  directly instead of re-deriving it from `reporter_contact` — needed for the IP-hash case, since
  `reporter_contact` is passed separately to `resolve_wallet_for_report()` and stays phone-only
  there.

- **`routers/`** — `pages.py` (public map + report form), `moderation.py` (queue, HTTP Basic
  auth via `auth.py`), `api.py` (JSON feed the map's JS polls), `sms.py` (both the real
  webhook and `/sms/simulate`, both backed by `sms_service.py`), `resources.py` (Phase C: kit
  locations — public read, moderator-auth write, no public submission), `wallet.py` (Phase C:
  reward wallets — public `/wallet` lookup/redeem, moderator-auth `/redemptions` fulfillment
  queue).
- **`session.py`** — the anonymous cookie behind Phase C's community confirmations: hashed
  before storage, deliberately *not* tied to anything identifying (unlike `reporter_ref`,
  which hashes something the reporter typed) — this hashes a random token the server handed
  out, so it can't be linked back to a person even in principle.
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
  server-side prepared statements. `_run_additive_migrations()` handles the gap `create_all()`
  leaves — it only creates *missing* tables, never alters existing ones — by hand-adding any
  columns current models need that an existing (e.g. live Supabase) table doesn't have yet. No
  Alembic yet; additive-only by design (add columns, never drop), since this runs
  unconditionally on every startup against a real production DB. Five columns handled this way
  so far (`Report.lga_id`, `.confirmations_count`, `.wallet_id`, `.points_awarded`,
  `.submission_token` — each added when its feature shipped, each verified by rebuilding a DB
  with the actual prior code before touching production, not just reasoned about). That's the
  pattern to follow for the next one too — revisit reaching for a real migration framework once
  this list gets much longer, but
  it's not there yet.
- **`sms_client.py`** — optional outbound confirmation SMS via Africa's Talking. Their free
  sandbox is deprecated, so this is dormant by default (`AT_API_KEY` unset) and unused by
  the demo; it's there for whenever a real pilot wires up production SMS credentials.
- **`GET /api/health`** — cheap liveness/config check (DB reachable, which backend, LGA seed
  count) with no secrets in the response. First thing to hit when a deploy misbehaves, before
  assuming routing is broken.
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

### Phase C (reward wallets, kit locations, confirmations)

Full user-facing description: README §13. The one thing worth internalizing before touching
`crud.resolve_wallet_for_report()`: **every** report gets a wallet, resolved in priority order
(explicit wallet code the reporter already has → phone-linked wallet, found-or-created →
brand-new anonymous wallet). The anonymous case's code is shown exactly once, at submission —
there's no recovery path if it's lost, by design (same tradeoff as a call-in tip line's
reference number). Encouraging a phone number instead (report_form.html's phone field and the
post-submission "Tip:" banner) is the actual answer for "I don't want to have to save a code" —
`find_wallet()` already looks a wallet up by phone, no code needed, which an IP- or
device-fingerprint-based scheme was explicitly considered and rejected for: Nigerian mobile
carriers share IPs across many customers via CGNAT, so an IP-keyed wallet would leak one
person's points to everyone else behind the same IP, and fingerprinting is the opposite of this
app's whole hash-only-what-was-explicitly-given identity model.

That's also why `POST /report` renders the confirmation directly instead of redirect-after-post
(`routers/pages.py`) — putting a reusable, sensitive code in a redirect's query string would
leave it sitting in browser history. The real cost of that choice: a browser can resubmit that
POST (hitting "back" past the page's `no-store` header, or a double-tap), and without a guard
that would silently mint a *second*, orphaned anonymous wallet with a different code — a real
bug a user actually hit. Fixed with `Report.submission_token`: a random value minted on every
`GET /report` and echoed back as a hidden field; `POST /report` checks for an existing report
with that exact token *before* doing anything else (before rate-limiting, before validation) and
if found, just replays that report's original confirmation instead of creating anything new.

`RedemptionRequest.contact_phone` is the one deliberate exception to "never store a raw phone
number" (see `Report.reporter_ref` elsewhere) — delivering a real reward needs a real contact,
which is fundamentally impossible from a one-way hash. Scoped as narrowly as possible: only on
that one table, only for the moment someone's actively redeeming, never on `Report` or
`Wallet` itself. If you're touching the wallet/redemption code, keep that scope narrow rather
than let plaintext contact info creep into the report/wallet models.

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

The app's location model matches the org's actual scope directly — `seed.py` carries all 95
real LGAs across the 5 states (see README §11 for the data source and its corrections), not a
placeholder subset. What's still a placeholder: the handful of demo *reports* (synthetic
example content, one per state), and which specific LGA(s) get real moderation/outreach focus
first — that's still an open decision (see README §10), distinct from the geographic data.

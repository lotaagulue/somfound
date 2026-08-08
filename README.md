# Somfound

**Somfound** turns word-of-mouth into a shared, visual picture of what's happening on the ground in a community — across South-East Nigeria's 5 states (Anambra, Abia, Ebonyi, Enugu, Imo) and their 95 LGAs. Anyone can report crime/safety concerns, infrastructure issues, community needs (water, medical help, etc.), or positive local news (a new school, a new borehole) — from a smartphone browser or by plain SMS. Reports show up as color-coded points on a live map so residents, local leaders, and outside partners (NGOs, government, diaspora) get a real-time, place-based view instead of relying on rumor.

> This repo is a demo build for an already-operating South-East Nigeria community-development nonprofit — not a from-scratch hypothetical. See [CLAUDE.md](CLAUDE.md) for that context and the technical architecture.

## 1. Problem

In many Nigerian villages, information about local events — a robbery, a burst water line, a new clinic opening — spreads by word of mouth, unevenly and often too slowly to act on. There's no shared, place-anchored record that a whole village (or the people who left it) can check. Meanwhile most residents have basic phones, not smartphones, so any solution that only works through an app or WhatsApp excludes the people closest to the ground.

## 2. Core user flows

### A. Report via web app (smartphone/desktop)

1. Open Somfound in a browser (no login required for MVP — optional phone number for follow-up).
2. Drop a pin (GPS location) or pick a **state, then LGA** from a list — the location model is LGA-level (Local Government Area), not individual villages, matching how the org's own plans already describe its coverage area.
3. Choose a category, write a short description, optionally attach a photo.
4. Submit → goes to moderator queue → published to the map once approved.

### B. Report via SMS (any phone)

1. Text a short, freeform message to a shortcode, e.g.:
   `WATER Nsukka borehole broken 3 days no fix`
   `HELP Aba North road robbery near market 9pm armed men`
2. A keyword parser extracts category + an LGA match from the message.
3. Sender gets an SMS confirmation ("Got it, thanks — under review").
4. Goes to the same moderator queue as web reports.

### C. View the map

1. Anyone (no login) sees a map of the 5-state region, default-centered on the whole area.
2. Points are colored by **urgency** and shaped/icon'd by **category** (see §3).
3. Filter by category, urgency, or time range ("last 7 days").
4. Tap a point for the report detail: description, photo (if any), time, status (published/resolved).

## 3. Report taxonomy

### Category (icon on the map)

| Category | Examples |
| --- | --- |
| 🛑 Crime & Safety | robbery, kidnapping, violence, suspicious activity |
| 🔧 Infrastructure | road damage, power outage, water line broken |
| 💧 Needs & Resources | "we need water," medical help, food shortage |
| 🏗️ Community & Development | new school, new borehole, market day, positive updates |
| ❓ Other | anything that doesn't fit cleanly |

### Urgency (color on the map)

| Color | Level | Meaning |
| --- | --- | --- |
| 🔴 Red (`#d03b3b`) | Critical | active danger, needs immediate attention |
| 🟠 Coral (`#ec835a`) | High | urgent unmet need, not immediately life-threatening |
| 🟡 Amber (`#fab219`) | Moderate | ongoing issue, worth knowing, not urgent |
| 🟢 Green (`#0ca30c`) | Informational | neutral/positive news, FYI |
| ⚪ Grey | Pending | submitted, not yet moderator-reviewed |

These are the `dataviz` skill's validated status palette (good/warning/serious/critical), not
an arbitrary red/orange/yellow/blue pick — a plain categorical ramp failed colorblind and
normal-vision separation checks between adjacent severities, which matters when the map is
showing crime/safety data. Because two of these steps sit under 3:1 contrast on a light
background by design, the app always pairs urgency with a label/icon on screen (map legend,
popups, moderation queue) rather than relying on the color dot alone.

Keeping category (icon) and urgency (color) as two separate dimensions means a "water shortage" and a "burst pipe" both show as the 💧 icon, but can carry different color/urgency depending on severity.

## 4. Trust & moderation model (MVP)

All reports land in a **moderator review queue** before they're public — nothing auto-publishes at launch. A moderator (local volunteer, community leader, or small internal team) can:

- Approve as-is
- Edit (fix location, tone down unverified claims, correct category)
- Reject (spam, duplicate, unverifiable)
- Mark **Resolved** later (e.g., water line fixed) so old issues stop looking live

This is slower than auto-publish, but it matters here specifically because reports can include unverified crime allegations about real places and real people — false positives have real consequences. Two features worth planning for from day one even if not built in MVP:

- **Rate limiting per phone number/session** to blunt spam or coordinated abuse.
- **Confirmation/upvote counts** from other nearby reporters, as an input moderators can see (not auto-publish trigger) — sets up a future move toward community verification once an LGA has enough active users.

## 5. Data model (draft)

```text
Report
  id
  category            enum: crime_safety | infrastructure | needs_resources | community_dev | other
  urgency              enum: critical | high | moderate | informational
  status                enum: pending | published | rejected | resolved
  title                 short auto/derived summary
  description           free text
  location              lat, lon, lga_id (nullable)
  source_channel        enum: web | sms
  reporter_ref           hashed phone or anonymous session id (never raw phone in plaintext)
  media[]                photo URLs (web only, MVP)
  confirmations_count    int, default 0
  created_at, published_at, resolved_at
  moderator_id, moderation_notes

LGA (Local Government Area — the reporting unit, not individual villages)
  id, name, state, lat, lon

SmsInbound (raw audit log)
  id, from_phone_hash, raw_text, parsed_category, parsed_urgency, linked_report_id, received_at

ModerationAction
  id, report_id, moderator_id, action, notes, created_at
```

## 6. Architecture (as built)

One stack, kept deliberately small so the demo runs on **entirely free infrastructure**:

- **Backend:** FastAPI (Python) — REST API + server-rendered pages for report submission, map queries, moderator actions.
- **Database:** SQLite via SQLModel — zero-cost, zero-setup, no separate DB service to pay for or manage. `DATABASE_URL` can point at Postgres later with no code changes when this needs a real pilot deployment (PostGIS was the original proposal for real geospatial queries at scale — SQLite is a deliberate demo-stage simplification, fine at this data volume).
- **Frontend:** Server-rendered Jinja2 pages + Leaflet.js (via CDN) for the map. No JS build step, no Node toolchain, one deployable app.
- **SMS pipeline:** a keyword parser (`sms_parser.py`) assigns category/urgency and creates a `pending` Report, driven through `sms_service.py` by either a real inbound webhook (`POST /sms/inbound`, shaped for [Africa's Talking](https://africastalking.com/)'s callback format) or the in-app **`/sms/simulate`** page. The demo uses the latter — Africa's Talking's free sandbox has been deprecated, so wiring up a real SMS gateway is deliberately deferred to actual pilot deployment (needs a paid shortcode anyway), not required to demo the pipeline today.
- **Moderator dashboard:** `/moderate`, HTTP Basic auth, same app — no separate admin tool.
- **Hosting:** [Render](https://render.com)'s free web service tier — see §12.

## 7. MVP scope (all 5 South-East states / 95 LGAs — real geographic scope from day one)

- ✅ Web report form (no login, GPS or state→LGA picker) — `/report`
- ✅ SMS report via free-text keyword parsing — `POST /sms/inbound` (real gateway, future) and `/sms/simulate` (in-app demo, no gateway needed)
- ✅ Public map with the 5 categories / 4 urgency colors, filterable by category/urgency/date — `/`
- ✅ Moderator queue (approve/reject/resolve) — `/moderate`
- ✅ Real LGA list (all 95, across Anambra/Abia/Ebonyi/Enugu/Imo) to anchor locations — see §11 for the data source

Note the distinction from earlier versions of this doc: the *geographic reference data* (which LGAs exist, roughly where) is now real, not a placeholder — what's still undecided is which specific LGA(s) actually get real moderation attention/outreach first (§10).

Explicitly **out of scope for MVP**: USSD, community upvote/confirmation, multi-language (Igbo) UI, native mobile app, analytics dashboard for government/NGO partners, monetization, photo uploads.

## 8. Key risks & mitigations

| Risk | Mitigation |
| --- | --- |
| False/malicious crime reports | Moderator queue, per-phone rate limiting, ability to retract/correct |
| Reporter safety (retaliation risk for crime reports) | Never show reporter identity publicly, hash/secure phone numbers, keep reporting anonymous by default |
| Data privacy (NDPR compliance) | Minimize stored PII, hash phone numbers, define a retention policy before launch — worth a dedicated pass later |
| Low connectivity / feature phones | SMS is the fallback by design; keep SMS parsing lenient (freeform, not rigid syntax) |
| Moderator bottleneck / who moderates? | Needs a real answer before pilot launch — local volunteer(s), community leader, or a small rotating team |
| Sustainability of SMS shortcode cost | Look at NGO, diaspora, or local government partnership to cover ongoing SMS gateway costs |
| Language barrier | English-first MVP; Igbo keyword support and UI translation is a near-term follow-up, not v0 |

## 9. Roadmap

- ~~**Phase 0:** this spec, pick pilot LGA(s), confirm who moderates.~~ Spec done, app live; pilot LGA(s) and moderator team still open (§10).
- ~~**Phase 1 (MVP):** web report + map + SMS (simulated) + moderator queue.~~ **Done** — live at the deployed URL, now covering all 5 states / 95 LGAs rather than a single-LGA pilot.
- **Phase 2 (next):** real SMS gateway (paid shortcode), per-moderator accounts + audit trail, community confirmation/upvotes, resolved-status notifications, photo uploads.
- **Phase 3:** USSD menu option, Igbo language support, NDPR compliance pass.
- **Phase 4:** analytics view for government/NGO/diaspora partners, the ₦1,000/year membership-dues model, anonymous tip-reward system (from the org's own business plan).

## 10. Open questions

- Which specific LGA(s) get real moderation attention/outreach first — the app supports all 95 from day one, but a small team can't meaningfully moderate all of them at once. Do we already have contacts in a particular LGA to seed initial reports?
- Who moderates at launch — and what's the expected report volume they need to handle?
- Budget for a real SMS gateway (Africa's Talking production or alternative) once past demo stage — needs a paid shortcode.
- Should web reporters be able to optionally leave a phone number for follow-up (e.g., "water fixed, can you confirm?"), and how is that stored/used?

## 11. Running the MVP demo locally

Requires `uv` (already used to manage this project) — no other services to install.

```bash
uv sync                      # installs dependencies incl. dev/test tools
uv run uvicorn somfound.main:app --reload
```

Then open:

- `http://localhost:8000/` — the public map (seeded with one demo report per state, real coordinates)
- `http://localhost:8000/report` — submit a web report
- `http://localhost:8000/moderate` — moderator queue (HTTP Basic auth; defaults to `moderator` / `somfound-demo` — override via `MODERATOR_USERNAME` / `MODERATOR_PASSWORD` env vars before any real deployment)

Run the test suite: `uv run pytest`.

The database is a local SQLite file (`somfound.db`, gitignored) that's created and seeded automatically on first run — delete it to reset to a clean demo state.

### Where the LGA data comes from

`seed.py` seeds all 95 real LGAs across Anambra (21), Abia (17), Ebonyi (13), Enugu (17), and
Imo (27) — names cross-checked against Wikipedia's per-state LGA lists, coordinates from
[xosasx/nigerian-local-government-areas](https://github.com/xosasx/nigerian-local-government-areas)
(Wikidata-derived). That source had seven verifiable errors (two LGAs with lat/lon swapped,
two pairs of different LGAs sharing identical coordinates, one point six degrees out of range)
— corrected in `seed.py` using general geographic knowledge, flagged inline, not surveyed.
Treat all 95 as approximate pending real GPS/survey data, same caveat as the demo report
content itself.

### Testing SMS without a phone, an SMS gateway, or paying for anything

Open **`http://localhost:8000/sms/simulate`** — type a message the way a reporter would text it (e.g. `WATER Nsukka borehole broken 3 days no fix`), submit, and see exactly how it got parsed (category, urgency, matched LGA, the reply the sender would receive) before it lands in `/moderate` for approval. This is the primary way to demo the SMS half of the app — no telco account, shortcode, or gateway signup needed at all.

For testing the raw webhook shape directly instead (useful when actually wiring up a gateway later):

```bash
curl -X POST http://localhost:8000/sms/inbound \
  -d "from=+2348012345678" \
  -d "text=WATER Nsukka borehole broken 3 days no fix"
```

Wiring `/sms/inbound` to a real SMS provider (Africa's Talking or otherwise) is deliberately deferred to actual pilot deployment — their free sandbox, which this was originally built/tested against, has since been deprecated, and a real gateway needs a paid shortcode anyway. `sms_client.py`/`AT_*` env vars are there for whenever that happens; nothing in the demo depends on them.

## 12. Deploying for free (Vercel — used for the live interactive demo)

The app runs as a single Vercel Python serverless function (`api/index.py`), with every
route rewritten to it via `vercel.json` so the whole FastAPI app — pages, JSON API, SMS
webhook — is served from one deployment. No separate frontend/backend split needed.

1. Push this repo to GitHub (already done — <https://github.com/lotaagulue/somfound>).
2. In the [Vercel dashboard](https://vercel.com/new), **Add New → Project**, import the repo. Vercel should auto-detect the Python runtime from `vercel.json` + `requirements.txt`; no build command changes needed.
3. **Env vars** (Project Settings → Environment Variables) — none are strictly required (the app runs on SQLite with safe defaults with nothing set), but for anything beyond a quick look:
   - `DATABASE_URL` — see "Using Supabase for storage" below. Strongly recommended once more than one person will click around, since plain SQLite on Vercel resets on cold starts (see limitation below).
   - `MODERATOR_USERNAME` / `MODERATOR_PASSWORD` — override the `moderator` / `somfound-demo` defaults before sharing the URL publicly.
   - `AT_USERNAME` / `AT_API_KEY` — only for a real SMS gateway later; not needed for the demo (`/sms/simulate` needs nothing).
4. Deploy. Demo the SMS pipeline at `https://<your-app>.vercel.app/sms/simulate` — no gateway needed.

**If the deployed URL returns `{"detail":"Not Found"}` on every path:** two real bugs produced
exactly this during development, both already fixed in this repo, worth knowing about if a
future Vercel runtime change reopens either:

1. Vercel's edge was caching the function's response by rewrite *destination* rather than the
   original request URL (nothing set `Cache-Control`), so every distinct path served the same
   frozen response from whichever request happened to populate the cache first — fixed by
   `main.py` setting `Cache-Control: no-store` on every response.
2. Vercel's Python runtime delivers every rewritten request with `scope["path"]` hardcoded to
   the function's own address (`/api/index`), not the original browsed URL, so plain routing
   can't tell `/` from `/report` apart — fixed via `vercel_compat.py` (see CLAUDE.md for the
   mechanism: the rewrite passes the real path through as a query param, restored by a small
   ASGI middleware before routing happens).

If `{"detail":"Not Found"}` shows up again after those fixes, check `requested_path` in the
response body first (the app's own 404 handler includes it) — if it's `/api/index` again, one
of the two workarounds above got reverted or the Vercel runtime changed behavior again. If
`https://<your-app>.vercel.app/api/health` itself 404s, the function isn't being invoked at
all — check the Framework Preset in Project Settings isn't overriding `vercel.json`, and that
Root Directory is the repo root.

### Known limitation: SQLite resets on Vercel (fix with Supabase)

Vercel's filesystem is read-only except `/tmp`, so `db.py` stores the SQLite file there
automatically when it detects Vercel's environment. `/tmp` persists only for the lifetime of a
*warm* serverless instance — a cold start (first request after idle, or a fresh instance under
concurrent traffic) gets a freshly reseeded demo DB, and a report submitted in one instance may
not be visible from a different concurrent instance. Fine for a single presenter walking through
the demo in one sitting; not fine for multiple simultaneous viewers or data that needs to
survive between sessions — which is most interactive demos. Fix: point `DATABASE_URL` at a real
Postgres instead.

### Using Supabase for storage

Supabase's free tier gives a real, persistent Postgres — solves the reset problem above with
one env var, no code changes (`db.py` already branches on `DATABASE_URL`'s scheme).

1. Create a project at [supabase.com](https://supabase.com) (free tier).
2. Project Settings → Database → Connection string → select **Transaction** mode (the
   Supavisor pooler, port `6543`) — not the direct connection (port `5432`). Serverless
   functions open many short-lived connections; the pooler is built for exactly that, and
   Postgres's direct connection limit is small enough that serverless traffic can exhaust it.
3. Set that connection string as `DATABASE_URL` in Vercel's Project Settings (and locally in
   `.env` if you want to develop against it instead of SQLite). See `.env.example` for the
   exact format.
4. Redeploy. `/api/health` will report `"db": "postgresql"` once it's picked up.

One caveat that's already handled in code, not just documentation: Supavisor's transaction mode
doesn't support server-side prepared statements, so `db.py` disables SQLAlchemy's statement
cache whenever the URL isn't SQLite — if you swap out `db.py`'s engine setup, keep that.

Regardless of host or storage backend, which LGA(s) get real moderation/outreach focus (§10)
is still an open decision — the *geographic* LGA data itself (§11) is real, not a placeholder;
what's synthetic is only the handful of demo report examples.

### Alternative: Render

`render.yaml` at the repo root also works if you'd rather deploy to
[Render](https://dashboard.render.com/) (**New → Blueprint**) instead of Vercel — same free-tier
tradeoffs (sleeps on idle, non-persistent disk across deploys), same env vars, same Postgres
upgrade path when needed.

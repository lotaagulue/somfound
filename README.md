# Somfound

**Somfound** turns word-of-mouth into a shared, visual picture of what's happening on the ground in a community — starting with a pilot in Anambra State, Nigeria. Anyone can report crime/safety concerns, infrastructure issues, community needs (water, medical help, etc.), or positive local news (a new school, a new borehole) — from a smartphone browser or by plain SMS. Reports show up as color-coded points on a live map so villagers, local leaders, and outside partners (NGOs, government, diaspora) get a real-time, place-based view instead of relying on rumor.

> This repo is a demo build for an already-operating South-East Nigeria community-development nonprofit — not a from-scratch hypothetical. See [CLAUDE.md](CLAUDE.md) for that context and the technical architecture.

## 1. Problem

In many Nigerian villages, information about local events — a robbery, a burst water line, a new clinic opening — spreads by word of mouth, unevenly and often too slowly to act on. There's no shared, place-anchored record that a whole village (or the people who left it) can check. Meanwhile most residents have basic phones, not smartphones, so any solution that only works through an app or WhatsApp excludes the people closest to the ground.

## 2. Core user flows

### A. Report via web app (smartphone/desktop)

1. Open Somfound in a browser (no login required for MVP — optional phone number for follow-up).
2. Drop a pin (defaults to GPS location, editable) or pick a known village/ward from a list.
3. Choose a category, write a short description, optionally attach a photo.
4. Submit → goes to moderator queue → published to the map once approved.

### B. Report via SMS (any phone)

1. Text a short, freeform message to a shortcode, e.g.:
   `WATER Umuoji borehole broken 3 days no fix`
   `HELP Nnewi road robbery near market 9pm armed men`
2. A keyword parser extracts category + location hints from the message.
3. Sender gets an SMS confirmation ("Got it, thanks — under review").
4. Goes to the same moderator queue as web reports.

### C. View the map

1. Anyone (no login) sees a map centered on their village/LGA.
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
- **Confirmation/upvote counts** from other nearby reporters, as an input moderators can see (not auto-publish trigger) — sets up a future move toward community verification once a village has enough active users.

## 5. Data model (draft)

```text
Report
  id
  category            enum: crime_safety | infrastructure | needs_resources | community_dev | other
  urgency              enum: critical | high | moderate | informational
  status                enum: pending | published | rejected | resolved
  title                 short auto/derived summary
  description           free text
  location              lat, lon, village_id (nullable), ward, LGA, state
  source_channel        enum: web | sms
  reporter_ref           hashed phone or anonymous session id (never raw phone in plaintext)
  media[]                photo URLs (web only, MVP)
  confirmations_count    int, default 0
  created_at, published_at, resolved_at
  moderator_id, moderation_notes

Village
  id, name, ward, LGA, state, lat, lon

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

## 7. MVP scope (pilot: one LGA in Anambra State)

- ✅ Web report form (no login, GPS or manual pin) — `/report`
- ✅ SMS report via free-text keyword parsing — `POST /sms/inbound` (real gateway, future) and `/sms/simulate` (in-app demo, no gateway needed)
- ✅ Public map with the 5 categories / 4 urgency colors, filterable by category/urgency/date — `/`
- ✅ Moderator queue (approve/reject/resolve) — `/moderate`
- ✅ Seed village list to anchor locations (placeholder cluster — see §10)

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

- **Phase 0 (now):** this spec, pick pilot LGA/villages, confirm who moderates.
- **Phase 1 (MVP):** web report + map + SMS inbound + moderator queue, single LGA pilot.
- **Phase 2:** USSD menu option, community confirmation/upvotes, resolved-status workflows, Igbo language support.
- **Phase 3:** multi-LGA/state expansion, analytics view for government/NGO partners, funding/monetization model.

## 10. Open questions

- Which specific LGA/villages in Anambra State for the pilot, and do we already have contacts there to seed moderation and initial reports? (The seeded demo data uses a placeholder Idemili North cluster — see §11.)
- Who moderates at launch — and what's the expected report volume they need to handle?
- Budget for the Africa's Talking shortcode/SMS costs during pilot?
- Should web reporters be able to optionally leave a phone number for follow-up (e.g., "water fixed, can you confirm?"), and how is that stored/used?

## 11. Running the MVP demo locally

Requires `uv` (already used to manage this project) — no other services to install.

```bash
uv sync                      # installs dependencies incl. dev/test tools
uv run uvicorn somfound.main:app --reload
```

Then open:

- `http://localhost:8000/` — the public map (seeded with demo reports around a placeholder Anambra village cluster)
- `http://localhost:8000/report` — submit a web report
- `http://localhost:8000/moderate` — moderator queue (HTTP Basic auth; defaults to `moderator` / `somfound-demo` — override via `MODERATOR_USERNAME` / `MODERATOR_PASSWORD` env vars before any real deployment)

Run the test suite: `uv run pytest`.

The database is a local SQLite file (`somfound.db`, gitignored) that's created and seeded automatically on first run — delete it to reset to a clean demo state.

### Testing SMS without a phone, an SMS gateway, or paying for anything

Open **`http://localhost:8000/sms/simulate`** — type a message the way a reporter would text it (e.g. `WATER Umuoji borehole broken 3 days no fix`), submit, and see exactly how it got parsed (category, urgency, matched village, the reply the sender would receive) before it lands in `/moderate` for approval. This is the primary way to demo the SMS half of the app — no telco account, shortcode, or gateway signup needed at all.

For testing the raw webhook shape directly instead (useful when actually wiring up a gateway later):

```bash
curl -X POST http://localhost:8000/sms/inbound \
  -d "from=+2348012345678" \
  -d "text=WATER Umuoji borehole broken 3 days no fix"
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

**If the deployed URL returns `{"detail":"Not Found"}`:** that's FastAPI's own 404 — the app
booted fine, a route just isn't matching. First hit `https://<your-app>.vercel.app/api/health`:
if that responds, the app and DB are fine and it's specifically the root-path rewrite not
applying (check Vercel's dashboard → your project → Deployments → latest → **Functions** tab
confirms `api/index.py` is listed; **Runtime Logs** shows the actual request path; redeploy
after any `vercel.json` change since it's read at build time). If `/api/health` *also* 404s,
the function itself isn't being invoked — check the Framework Preset in Project Settings isn't
overriding `vercel.json`, and that Root Directory is the repo root.

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

Regardless of host or storage backend, the pilot LGA/village data (§10) will still need
updating — none of this deploys real village data, only the placeholder seed set (§11).

### Alternative: Render

`render.yaml` at the repo root also works if you'd rather deploy to
[Render](https://dashboard.render.com/) (**New → Blueprint**) instead of Vercel — same free-tier
tradeoffs (sleeps on idle, non-persistent disk across deploys), same env vars, same Postgres
upgrade path when needed.

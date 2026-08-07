# Somfound

**Somfound** turns word-of-mouth into a shared, visual picture of what's happening on the ground in a community — starting with a pilot in Anambra State, Nigeria. Anyone can report crime/safety concerns, infrastructure issues, community needs (water, medical help, etc.), or positive local news (a new school, a new borehole) — from a smartphone browser or by plain SMS. Reports show up as color-coded points on a live map so villagers, local leaders, and outside partners (NGOs, government, diaspora) get a real-time, place-based view instead of relying on rumor.

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
| 🔴 Red | Critical | active danger, needs immediate attention |
| 🟠 Orange | High | urgent unmet need, not immediately life-threatening |
| 🟡 Yellow | Moderate | ongoing issue, worth knowing, not urgent |
| 🔵 Blue | Informational | neutral/positive news, FYI |
| ⚪ Grey | Pending | submitted, not yet moderator-reviewed |

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

## 6. Proposed architecture

Keeping this to one stack given the repo is already a Python/`uv` project:

- **Backend:** FastAPI (Python) — REST API for report submission, map queries, moderator actions.
- **Database:** PostgreSQL + PostGIS — geospatial queries (points near a village, bounding-box map queries) are first-class, not bolted on.
- **Frontend:** Server-rendered pages (Jinja2 + HTMX) + Leaflet.js for the map. This avoids standing up a separate JS build/deploy for an MVP — one deployable app, one team member can run it. (Revisit a React/Next.js frontend later if the map/UI outgrows this.)
- **SMS gateway:** [Africa's Talking](https://africastalking.com/) — the standard SMS API provider for Nigeria, supports shortcodes and (later) USSD, reasonable local delivery rates. Inbound SMS hits a webhook on the FastAPI backend; a keyword parser assigns category/urgency and creates a `pending` Report.
- **Moderator dashboard:** simple authenticated pages in the same app (no separate admin tool needed for MVP).
- **Hosting:** a single small Postgres + app host (Render/Fly.io/Railway) is enough for a pilot; revisit if traffic/geography demands it.

## 7. MVP scope (pilot: one LGA in Anambra State)

- Web report form (no login, GPS or manual pin)
- SMS report to one shortcode, free-text with keyword parsing
- Public map with the 5 categories / 4 urgency colors, filterable
- Moderator queue (approve/edit/reject/resolve)
- A short list of known villages/wards in the pilot LGA to anchor locations

Explicitly **out of scope for MVP**: USSD, community upvote/confirmation, multi-language (Igbo) UI, native mobile app, analytics dashboard for government/NGO partners, monetization.

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

- Which specific LGA/villages in Anambra State for the pilot, and do we already have contacts there to seed moderation and initial reports?
- Who moderates at launch — and what's the expected report volume they need to handle?
- Budget for the Africa's Talking shortcode/SMS costs during pilot?
- Should web reporters be able to optionally leave a phone number for follow-up (e.g., "water fixed, can you confirm?"), and how is that stored/used?

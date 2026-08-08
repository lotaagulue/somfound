# Planning

Detailed backlog behind README's terse roadmap (§9). That section states the phases in one
line each; this document is the fuller "why it matters" version behind each one, plus the
open decisions in §10 broken out with context. Keep the two in sync — if a phase's scope
changes here, update README §9 too, and vice versa.

## Where we are now

Live, working MVP: map + web reports + SMS simulation + moderation queue, on Vercel +
Supabase, mobile-responsive, installable as a PWA, covering the real 95-LGA / 5-state
geographic scope. That's Phase 1 from README §9, done.

## Phase A — Harden what's live

Cheap, no decisions needed — mostly things that don't require the operator's input, just time.

| Item | Why it matters |
|---|---|
| CI on every PR (GitHub Actions running `pytest`) | Tests currently only run when someone remembers to run them locally. A bad PR could merge silently. |
| Moderation audit trail (`ModerationAction` table) | Was in the original data model, never actually built — approving/rejecting currently overwrites the report with no history of who did what, when. Matters more once there's more than one moderator. |
| Per-moderator accounts (not one shared password) | `/moderate` is currently one shared HTTP Basic credential. Fine for a solo demo, not fine once real people are moderating real crime reports — no accountability per action. |
| Basic error monitoring (Sentry free tier or similar) | Right now, if something breaks in production, the only way to find out is to happen to check. |
| Security review pass | Hasn't been done yet on the actual deployed app (auth, input handling, rate limiting) — worth doing before real users touch it. |
| Real phone screenshot check | The mobile CSS pass was verified mechanically (served HTML/CSS, no headless browser available in-session) but never actually seen rendered on a device. Costs two minutes, closes a real gap. |

## Phase B — Real pilot readiness

Needs decisions from the operator first — these map straight to README §10's open questions.

- **Which LGA(s) get real moderation attention first** — the app supports all 95 LGAs / 5
  states from day one (that part's done, not a placeholder anymore), but a small team can't
  meaningfully moderate all of them at once. Need to pick a starting focus area and confirm
  whether there are already contacts there to seed initial reports.
- **Who moderates** — a real person/team, not just the operator, before this goes to real
  users making real crime reports.
- **SMS gateway + budget** — Africa's Talking production (or an alternative) needs a paid
  shortcode. The one item here with a real recurring cost.
- **Photo uploads** for web reports — currently text-only.
- **NDPR compliance pass** — this handles Nigerian crime/safety data; worth a dedicated
  privacy review before scaling past a demo. Use the `data-privacy-compliance` skill for this
  when ready.

## Phase C — Feature depth (from the org's own business plan, not invented)

The business plan describes three concrete things this app is a natural home for:

- **Anonymous tip reward system** — the plan explicitly proposes this for the crime hotline.
  Reports are anonymous today, but there's no reward mechanism at all yet.
- **First-aid kit box locations** — the plan's other Q1 priority (across all 95 LGAs). Could
  be a second map layer/category showing installed resource locations, not just incident
  reports.
- **Community confirmation/upvotes** — flagged as a v0 simplification when the moderation
  model was first designed; becomes valuable once an LGA has enough active reporters that
  peer confirmation is meaningful.

## Phase D — Scale (once the pilot proves out)

- USSD (structured menu input for feature phones)
- Igbo language support (SMS keywords + UI)
- Deepen coverage within the real 5-state / 95-LGA scope as the pilot expands (the app already
  supports the full scope structurally — this phase is about actual on-the-ground reach/usage,
  not more code)
- Analytics dashboard for government/NGO/diaspora partners (also in the business plan)
- The ₦1,000/year membership-dues model from the business plan, once there's something worth
  paying for

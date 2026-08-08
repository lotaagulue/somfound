"""Public-facing HTML pages: the map and the web report form."""

import json
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from somfound import crud
from somfound.db import get_session
from somfound.models import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    URGENCY_COLORS,
    URGENCY_LABELS,
    Category,
    SourceChannel,
    Urgency,
    Wallet,
)
from somfound.llm_classifier import guess_category_urgency_with_llm
from somfound.paths import TEMPLATES_DIR
from somfound.seed import STATES
from somfound.sms_parser import guess_category_urgency

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Client-side maxlength on the textarea is the primary guard; this is
# defense-in-depth for anyone submitting straight to the endpoint.
MAX_DESCRIPTION_LENGTH = 2000


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limiting anonymous (no-phone) web
    reports. Prefer X-Forwarded-For (set by Vercel's edge and Render's proxy)
    over request.client.host, which on a proxied deploy is just the proxy's
    own address, not the real visitor."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _lgas_by_state_json(session: Session) -> str:
    """State -> [{id, name, lat, lon}], for the report form's cascading
    state/LGA picker. Server-controlled data only (no user input), but still
    escape `<` so a stray LGA name can't break out of the <script> tag."""
    grouped: dict[str, list[dict]] = {state: [] for state in STATES}
    for lga in crud.list_lgas(session):
        grouped.setdefault(lga.state, []).append(
            {"id": lga.id, "name": lga.name, "lat": lga.lat, "lon": lga.lon}
        )
    return json.dumps(grouped).replace("<", "\\u003c")


@router.get("/")
def map_page(request: Request):
    return templates.TemplateResponse(
        request,
        "map.html",
        {
            "categories": [(c.value, label) for c, label in CATEGORY_LABELS.items()],
            "urgencies": [(u.value, label) for u, label in URGENCY_LABELS.items()],
            "urgency_legend": [
                {"label": label, "color": URGENCY_COLORS[u]} for u, label in URGENCY_LABELS.items()
            ],
            "category_legend": [
                {"label": label, "icon": CATEGORY_ICONS[c]} for c, label in CATEGORY_LABELS.items()
            ],
        },
    )


def _report_form_context(session: Session, **extra) -> dict:
    return {
        "states": STATES,
        "lgas_by_state_json": _lgas_by_state_json(session),
        "categories": [(c.value, label) for c, label in CATEGORY_LABELS.items()],
        "urgencies": [(u.value, label) for u, label in URGENCY_LABELS.items()],
        "submitted": False,
        "rate_limited": False,
        "description_too_long": False,
        "max_description_length": MAX_DESCRIPTION_LENGTH,
        "auto_categorized": False,
        "used_llm": False,
        "detected_category_label": "",
        "detected_urgency_label": "",
        "submission_token": "",
        "gave_phone": False,
        **extra,
    }


@router.get("/report")
def report_form(request: Request, session: Session = Depends(get_session)):
    # A fresh, random token per form load — echoed back as a hidden field and
    # checked on submit (see submit_report) so a browser resubmitting this
    # exact POST (e.g. hitting "back" past a no-store page, or a double-tap)
    # replays the original confirmation instead of silently creating a
    # second report and, worse, a second orphaned anonymous wallet.
    token = secrets.token_urlsafe(16)
    return templates.TemplateResponse(
        request, "report_form.html", _report_form_context(session, submission_token=token)
    )


@router.post("/report")
def submit_report(
    request: Request,
    category: str = Form(""),
    urgency: str = Form(""),
    description: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    lga_id: int | None = Form(None),
    phone: str = Form(""),
    wallet_code: str = Form(""),
    submission_token: str = Form(""),
    session: Session = Depends(get_session),
):
    # Checked before anything else — a resubmission of an already-processed
    # token isn't a new report at all, so it shouldn't be validated,
    # rate-limited, or given a fresh wallet; just show what already happened.
    existing = crud.find_report_by_submission_token(session, submission_token)
    if existing is not None:
        wallet = session.get(Wallet, existing.wallet_id) if existing.wallet_id else None
        return templates.TemplateResponse(
            request,
            "report_form.html",
            _report_form_context(
                session,
                submitted=True,
                wallet_code=wallet.wallet_code if wallet else "",
                gave_phone=bool(wallet.phone_hash) if wallet else False,
                submission_token=submission_token,
            ),
        )

    if len(description) > MAX_DESCRIPTION_LENGTH:
        return templates.TemplateResponse(
            request, "report_form.html", _report_form_context(session, description_too_long=True)
        )

    # Unlike SMS (always has a phone), the web form's phone field is
    # optional, so there's nothing to rate-limit against for an anonymous
    # submission unless we fall back to something else — a hash of the
    # client IP. Same shared threshold/query as SMS (crud.MAX_PENDING_PER_REPORTER),
    # so it self-resets as moderators clear the queue rather than being a
    # hard ban. Tradeoff worth knowing: reporters behind the same shared/NAT
    # IP (e.g. one community's only internet gateway) share this bucket.
    # Checked before categorization below so a rate-limited request doesn't
    # waste an LLM call.
    reporter_ref = crud.hash_reporter_contact(phone) or crud.hash_reporter_contact(_client_ip(request))
    if crud.count_pending_reports(session, reporter_ref) >= crud.MAX_PENDING_PER_REPORTER:
        return templates.TemplateResponse(
            request, "report_form.html", _report_form_context(session, rate_limited=True)
        )

    # Category/urgency are optional on the form — most reporters just
    # describe what's happening and we guess, the same keyword-matching
    # engine SMS uses but scanning the whole sentence instead of only a
    # leading keyword (see sms_parser.guess_category_urgency). Anyone who
    # expands the "set it yourself" disclosure and picks an explicit value
    # overrides the guess for that field only — a moderator still reviews
    # every report before it's public either way.
    guessed_category, guessed_urgency, keyword_matched = guess_category_urgency(description)
    used_llm = False
    # The LLM fallback only makes sense when there's nothing else to go
    # on: no keyword hit, and the reporter didn't set either field
    # themselves. It's explicitly a fallback for the cases keywords miss,
    # not a second opinion on cases they already handle — keeps this optional,
    # free-tier-quota-friendly integration limited to where it actually adds
    # value.
    if not category and not urgency and not keyword_matched:
        llm_result = guess_category_urgency_with_llm(description)
        if llm_result is not None:
            guessed_category, guessed_urgency = llm_result
            used_llm = True
    try:
        final_category = Category(category) if category else guessed_category
    except ValueError:
        final_category = guessed_category
    try:
        final_urgency = Urgency(urgency) if urgency else guessed_urgency
    except ValueError:
        final_urgency = guessed_urgency
    auto_categorized = not category or not urgency

    # Every report gets a wallet — see crud.resolve_wallet_for_report for the
    # three-way logic (explicit code > phone-linked > brand new anonymous
    # one). Rendered directly rather than redirect-after-post specifically
    # so a freshly generated wallet code (shown exactly once) never has to
    # travel through a URL query string, where it'd sit in browser history.
    wallet = crud.resolve_wallet_for_report(session, wallet_code=wallet_code, reporter_contact=phone)
    crud.create_report(
        session,
        category=final_category,
        urgency=final_urgency,
        description=description,
        lat=lat,
        lon=lon,
        lga_id=lga_id,
        source_channel=SourceChannel.WEB,
        reporter_contact=phone,
        reporter_ref=reporter_ref,
        wallet_id=wallet.id,
        submission_token=submission_token,
    )
    return templates.TemplateResponse(
        request,
        "report_form.html",
        _report_form_context(
            session,
            submitted=True,
            wallet_code=wallet.wallet_code,
            gave_phone=bool(wallet.phone_hash),
            auto_categorized=auto_categorized,
            used_llm=used_llm,
            detected_category_label=CATEGORY_LABELS[final_category],
            detected_urgency_label=URGENCY_LABELS[final_urgency],
            # Echoed back into the hidden field: if THIS response is what
            # ends up getting resubmitted (browser "back" past no-store,
            # etc.), the check at the top of this function will match it.
            submission_token=submission_token,
        ),
    )

"""Public-facing HTML pages: the map and the web report form."""

import json

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
)
from somfound.paths import TEMPLATES_DIR
from somfound.seed import STATES

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
        **extra,
    }


@router.get("/report")
def report_form(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "report_form.html", _report_form_context(session))


@router.post("/report")
def submit_report(
    request: Request,
    category: Category = Form(...),
    urgency: Urgency = Form(...),
    description: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    lga_id: int | None = Form(None),
    phone: str = Form(""),
    wallet_code: str = Form(""),
    session: Session = Depends(get_session),
):
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
    reporter_ref = crud.hash_reporter_contact(phone) or crud.hash_reporter_contact(_client_ip(request))
    if crud.count_pending_reports(session, reporter_ref) >= crud.MAX_PENDING_PER_REPORTER:
        return templates.TemplateResponse(
            request, "report_form.html", _report_form_context(session, rate_limited=True)
        )

    # Every report gets a wallet — see crud.resolve_wallet_for_report for the
    # three-way logic (explicit code > phone-linked > brand new anonymous
    # one). Rendered directly rather than redirect-after-post specifically
    # so a freshly generated wallet code (shown exactly once) never has to
    # travel through a URL query string, where it'd sit in browser history.
    wallet = crud.resolve_wallet_for_report(session, wallet_code=wallet_code, reporter_contact=phone)
    crud.create_report(
        session,
        category=category,
        urgency=urgency,
        description=description,
        lat=lat,
        lon=lon,
        lga_id=lga_id,
        source_channel=SourceChannel.WEB,
        reporter_contact=phone,
        reporter_ref=reporter_ref,
        wallet_id=wallet.id,
    )
    return templates.TemplateResponse(
        request,
        "report_form.html",
        _report_form_context(session, submitted=True, wallet_code=wallet.wallet_code),
    )

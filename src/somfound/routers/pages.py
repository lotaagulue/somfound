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
        wallet_id=wallet.id,
    )
    return templates.TemplateResponse(
        request,
        "report_form.html",
        _report_form_context(session, submitted=True, wallet_code=wallet.wallet_code),
    )

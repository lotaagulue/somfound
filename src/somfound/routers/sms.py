"""SMS-related routes:

- `POST /sms/inbound` — a real inbound-SMS webhook, shaped to match Africa's
  Talking's callback format (https://developers.africastalking.com/docs/sms/callback).
  Wiring this to a live gateway is future/pilot-stage work — see README.
- `GET`/`POST /sms/simulate` — an in-app page that drives the exact same
  parsing/moderation pipeline without any telco account, so the SMS half of
  the demo doesn't depend on external infrastructure.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from somfound.db import get_session
from somfound.paths import TEMPLATES_DIR
from somfound.sms_client import send_confirmation
from somfound.sms_service import process_inbound_sms

router = APIRouter(prefix="/sms", tags=["sms"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.post("/inbound")
def inbound_sms(
    from_: str = Form(..., alias="from"),
    text: str = Form(...),
    session: Session = Depends(get_session),
) -> dict:
    outcome = process_inbound_sms(session, from_phone=from_, text=text)
    send_confirmation(from_, outcome.reply)  # no-op unless real AT credentials are configured
    return {"status": "ok", "report_id": outcome.report_id}


@router.get("/simulate")
def simulate_sms_form(request: Request):
    return templates.TemplateResponse(request, "sms_simulate.html", {"outcome": None})


@router.post("/simulate")
def simulate_sms_submit(
    request: Request,
    phone: str = Form("+2348012345678"),
    text: str = Form(...),
    session: Session = Depends(get_session),
):
    outcome = process_inbound_sms(session, from_phone=phone, text=text)
    return templates.TemplateResponse(
        request,
        "sms_simulate.html",
        {"outcome": outcome, "submitted_text": text, "submitted_phone": phone},
    )

"""The public wallet lookup/redeem page, plus the moderator redemption
fulfillment queue. See models.py's Wallet/RedemptionRequest docstrings for
the design: no login, a wallet is found by its code or by re-entering the
phone number that created it, and redeeming requires a plaintext contact
phone (the one deliberate exception to this app's hash-only-phone rule,
scoped narrowly to actually delivering a reward)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from somfound import crud
from somfound.auth import require_moderator
from somfound.db import get_session
from somfound.models import REDEMPTION_STATUS_LABELS, RedemptionStatus, Wallet
from somfound.paths import TEMPLATES_DIR

router = APIRouter(tags=["wallet"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _wallet_view_context(session: Session, wallet: Wallet, **extra) -> dict:
    return {
        "wallet": wallet,
        "reward_options": crud.list_active_reward_options(session),
        "redemptions": crud.list_redemptions(session, wallet_id=wallet.id),
        **extra,
    }


@router.get("/wallet")
def wallet_lookup_form(request: Request):
    return templates.TemplateResponse(request, "wallet.html", {"wallet": None})


@router.post("/wallet")
def wallet_lookup(
    request: Request,
    identifier: str = Form(...),
    session: Session = Depends(get_session),
):
    wallet = crud.find_wallet(session, identifier)
    if wallet is None:
        return templates.TemplateResponse(
            request, "wallet.html", {"wallet": None, "not_found": True, "identifier": identifier}
        )
    return templates.TemplateResponse(request, "wallet.html", _wallet_view_context(session, wallet))


@router.post("/wallet/{wallet_code}/redeem")
def redeem(
    request: Request,
    wallet_code: str,
    reward_option_id: int = Form(...),
    contact_phone: str = Form(...),
    session: Session = Depends(get_session),
):
    wallet = crud.find_wallet(session, wallet_code)
    reward_option = crud.get_reward_option(session, reward_option_id)
    if wallet is None or reward_option is None or not reward_option.active:
        raise HTTPException(status_code=404, detail="Wallet or reward not found")
    if wallet.points_balance < reward_option.points_cost:
        raise HTTPException(status_code=400, detail="Not enough points for this reward")
    if not contact_phone.strip():
        raise HTTPException(status_code=400, detail="A contact phone number is required to deliver a reward")

    crud.create_redemption(session, wallet, reward_option, contact_phone=contact_phone.strip())
    return templates.TemplateResponse(
        request, "wallet.html", _wallet_view_context(session, wallet, just_redeemed=True)
    )


@router.get("/redemptions")
def redemptions_admin(
    request: Request,
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    redemptions = crud.list_redemptions(session)
    wallet_codes = {r.wallet_id: session.get(Wallet, r.wallet_id) for r in redemptions}
    return templates.TemplateResponse(
        request,
        "redemptions_admin.html",
        {
            "redemptions": redemptions,
            "wallet_codes": {wid: (w.wallet_code if w else "?") for wid, w in wallet_codes.items()},
            "status_labels": REDEMPTION_STATUS_LABELS,
        },
    )


@router.post("/redemptions/{redemption_id}/{new_status}")
def resolve_redemption(
    redemption_id: int,
    new_status: str,
    notes: str = Form(""),
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    redemption = crud.get_redemption(session, redemption_id)
    if redemption is None:
        raise HTTPException(status_code=404, detail="Redemption not found")
    try:
        status = RedemptionStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown status") from None
    crud.resolve_redemption(session, redemption, status=status, notes=notes)
    return RedirectResponse(url="/redemptions", status_code=303)

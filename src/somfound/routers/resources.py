"""First-aid kit box (and future resource-type) locations. Public read via
/api/resources for the map layer; everything that creates/edits a resource
requires moderator auth — installation is the org's own team's job, there's
no public submission path here (unlike Report)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from somfound import crud
from somfound.auth import require_moderator
from somfound.db import get_session
from somfound.models import (
    RESOURCE_STATUS_COLORS,
    RESOURCE_STATUS_LABELS,
    RESOURCE_TYPE_ICONS,
    RESOURCE_TYPE_LABELS,
    ResourceStatus,
    ResourceType,
)
from somfound.paths import TEMPLATES_DIR

router = APIRouter(tags=["resources"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/api/resources")
def api_list_resources(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "id": r.id,
            "resource_type": r.resource_type.value,
            "type_label": RESOURCE_TYPE_LABELS[r.resource_type],
            "icon": RESOURCE_TYPE_ICONS[r.resource_type],
            "status": r.status.value,
            "status_label": RESOURCE_STATUS_LABELS[r.status],
            "color": RESOURCE_STATUS_COLORS[r.status],
            "lat": r.lat,
            "lon": r.lon,
            "notes": r.notes,
        }
        for r in crud.list_resources(session)
    ]


@router.get("/resources")
def resources_admin(
    request: Request,
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    return templates.TemplateResponse(
        request,
        "resources_admin.html",
        {
            "resources": crud.list_resources(session),
            "lgas": crud.list_lgas(session),
            "resource_types": [(t.value, label) for t, label in RESOURCE_TYPE_LABELS.items()],
            "statuses": [(s.value, label) for s, label in RESOURCE_STATUS_LABELS.items()],
            "type_labels": RESOURCE_TYPE_LABELS,
            "status_labels": RESOURCE_STATUS_LABELS,
        },
    )


@router.post("/resources")
def create_resource(
    resource_type: ResourceType = Form(...),
    status: ResourceStatus = Form(ResourceStatus.PLANNED),
    lga_id: int | None = Form(None),
    lat: float = Form(...),
    lon: float = Form(...),
    notes: str = Form(""),
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    crud.create_resource(
        session, resource_type=resource_type, status=status, lga_id=lga_id, lat=lat, lon=lon, notes=notes
    )
    return RedirectResponse(url="/resources", status_code=303)


@router.post("/resources/{resource_id}/status")
def update_resource_status(
    resource_id: int,
    status: ResourceStatus = Form(...),
    notes: str = Form(""),
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    resource = crud.get_resource(session, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    crud.update_resource_status(session, resource, status=status, notes=notes)
    return RedirectResponse(url="/resources", status_code=303)

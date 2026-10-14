"""HTTP API used by the web app. Everything is scoped to the visitor's own workspace."""
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import CompanyGraph
from app.changes import ChangeError, ConflictError, apply_proposal, preview_proposal, preview_undo, undo_change
from app.config import settings
from app.db import get_session
from app.documents import (
    INLINE_TYPES, Forbidden, decide_delivery, get_file, send_document, upload_document,
)
from app.models import AiCall, Change, Organization, Person, utcnow
from app.schemas import AskRequest, ChangeProposal, DecisionRequest
from app.seed import ADMIN_ROLE, OWNER_KEY
from app.state import build_state
from app.translator import TranslationError, default_client, translate
from app.workspaces import COOKIE, cleanup_expired, create_demo_workspace, find_workspace, sign

router = APIRouter(prefix="/api")


# ---------- dependencies ----------

def get_llm():
    """Returns an AI client, or None when no API key is configured. Overridden in tests."""
    return default_client() if settings.anthropic_api_key else None


def _set_cookie(response: Response, org: Organization):
    response.set_cookie(COOKIE, sign(org.public_id), max_age=settings.workspace_ttl_days * 86400,
                        httponly=True, samesite="lax", secure=settings.cookie_secure)


def current_org(request: Request, s: Session = Depends(get_session)) -> Organization:
    org = find_workspace(s, request.cookies.get(COOKIE))
    if org is None:
        raise HTTPException(404, "Your demo workspace has expired. Reload the page to start a fresh one.")
    return org


def acting_person(org: Organization, s: Session, header: str | None, query: str | None) -> str:
    wanted = header or query
    keys = set(s.scalars(select(Person.key).where(Person.org_id == org.id)))
    if wanted in keys:
        return wanted
    if OWNER_KEY in keys:
        return OWNER_KEY
    graph = CompanyGraph(s, org.id)
    partners = sorted(graph.subjects(ADMIN_ROLE, "member_of"))
    return partners[0] if partners else (sorted(keys)[0] if keys else OWNER_KEY)


def me(org: Organization = Depends(current_org), s: Session = Depends(get_session),
       x_acting_as: str | None = Header(default=None), as_: str | None = Query(default=None, alias="as")) -> str:
    return acting_person(org, s, x_acting_as, as_)


def admin(org: Organization = Depends(current_org), person: str = Depends(me),
          s: Session = Depends(get_session)) -> str:
    if ADMIN_ROLE not in CompanyGraph(s, org.id).roles_of(person):
        raise HTTPException(403, "Only partners can change how the firm works.")
    return person


def _errors(fn):
    try:
        return fn()
    except ConflictError as e:
        return JSONResponse(status_code=409, content={"detail": str(e), "preview": e.preview})
    except Forbidden as e:
        raise HTTPException(403, str(e))
    except ChangeError as e:
        raise HTTPException(422, str(e))


# ---------- workspace ----------

@router.get("/health")
def health():
    return {"ok": True}


@router.get("/state")
def state(request: Request, response: Response, s: Session = Depends(get_session),
          x_acting_as: str | None = Header(default=None), llm=Depends(get_llm)):
    org = find_workspace(s, request.cookies.get(COOKIE))
    if org is None:
        cleanup_expired(s)
        org = create_demo_workspace(s)
        _set_cookie(response, org)
    person = acting_person(org, s, x_acting_as, None)
    return build_state(s, org, person, ai_enabled=llm is not None)


@router.post("/workspace/reset")
def reset(response: Response, s: Session = Depends(get_session)):
    org = create_demo_workspace(s)
    _set_cookie(response, org)
    return {"ok": True}


# ---------- plain English ----------

def _check_ai_budget(s: Session, org_id: int):
    now = utcnow()
    hour = s.scalar(select(func.count(AiCall.id)).where(
        AiCall.org_id == org_id, AiCall.created_at > now - timedelta(hours=1)))
    if hour >= settings.ai_limit_per_workspace_per_hour:
        raise HTTPException(429, "You've hit this demo's hourly limit for AI requests. Try again later.")
    day = s.scalar(select(func.count(AiCall.id)).where(AiCall.created_at > now - timedelta(days=1)))
    if day >= settings.ai_limit_per_day:
        raise HTTPException(429, "The demo has reached today's AI limit. Please come back tomorrow.")
    s.add(AiCall(org_id=org_id))
    s.commit()


@router.post("/ask")
def ask(body: AskRequest, org: Organization = Depends(current_org), person: str = Depends(admin),
        s: Session = Depends(get_session), llm=Depends(get_llm)):
    if llm is None:
        raise HTTPException(503, "The AI isn't configured on this server yet (missing ANTHROPIC_API_KEY).")
    _check_ai_budget(s, org.id)
    try:
        t = translate(s, org.id, body.text, client=llm)
    except TranslationError as e:
        raise HTTPException(502, str(e))
    if t.kind == "proposal":
        return {"type": "proposal", **t.preview}
    return {"type": t.kind, "text": t.text}


@router.post("/changes/preview")
def preview(body: ChangeProposal, org: Organization = Depends(current_org), person: str = Depends(admin),
            s: Session = Depends(get_session)):
    return _errors(lambda: preview_proposal(s, org.id, body))


@router.post("/changes", status_code=201)
def apply(body: ChangeProposal, org: Organization = Depends(current_org), person: str = Depends(admin),
          s: Session = Depends(get_session)):
    def run():
        change = apply_proposal(s, org.id, body, actor=person)
        return {"id": change.id, **change.diff}
    return _errors(run)


# ---------- history ----------

@router.get("/history")
def history(org: Organization = Depends(current_org), s: Session = Depends(get_session)):
    g = CompanyGraph(s, org.id)
    rows = s.scalars(select(Change).where(Change.org_id == org.id).order_by(Change.id.desc())).all()
    return [{
        "id": c.id, "actor": c.actor, "actor_name": g.names.get(c.actor, c.actor.title()),
        "summary": c.summary, "created_at": c.created_at.isoformat(), "diff": c.diff,
        "undoable": c.inverse is not None and c.reverted_by is None,
        "reverted_by": c.reverted_by, "reverts": c.reverts,
    } for c in rows]


@router.post("/history/{change_id}/undo/preview")
def undo_preview(change_id: int, org: Organization = Depends(current_org), person: str = Depends(admin),
                 s: Session = Depends(get_session)):
    return _errors(lambda: preview_undo(s, org.id, change_id))


@router.post("/history/{change_id}/undo")
def undo(change_id: int, org: Organization = Depends(current_org), person: str = Depends(admin),
         s: Session = Depends(get_session)):
    def run():
        change = undo_change(s, org.id, change_id, person)
        return {"id": change.id, **change.diff}
    return _errors(run)


# ---------- documents ----------

@router.post("/documents", status_code=201)
async def upload(file: UploadFile = File(...), title: str = Form(""), client_service: str = Form(...),
                 kind: str = Form("other"), amount: str = Form(""),
                 org: Organization = Depends(current_org), person: str = Depends(me),
                 s: Session = Depends(get_session)):
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        value = float(amount.replace(",", "").replace("$", "")) if amount.strip() else None
    except ValueError:
        raise HTTPException(422, "Amount must be a number.")

    def run():
        key, change = upload_document(
            s, org.id, person, title=title, client_service=client_service, kind=kind, amount=value,
            filename=file.filename or "upload", mime=file.content_type or "application/octet-stream",
            content=content)
        return {"key": key, "change": change.id}
    try:
        return _errors(run)
    except HTTPException:
        raise
    except ValueError as e:  # invalid document kind
        raise HTTPException(422, f"Invalid document details: {e}")


@router.get("/documents/{key}/file")
def download(key: str, org: Organization = Depends(current_org), person: str = Depends(me),
             s: Session = Depends(get_session)):
    blob = _errors(lambda: get_file(s, org.id, person, key))
    disposition = "inline" if blob.mime in INLINE_TYPES else "attachment"
    safe_name = blob.filename.replace('"', "")
    return Response(blob.content, media_type=blob.mime, headers={
        "Content-Disposition": f'{disposition}; filename="{safe_name}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/documents/{key}/send")
def send(key: str, org: Organization = Depends(current_org), person: str = Depends(me),
         s: Session = Depends(get_session)):
    d = _errors(lambda: send_document(s, org.id, person, key))
    return {"id": d.id, "status": d.status}


@router.post("/approvals/{delivery_id}/{decision}")
def decide(delivery_id: int, decision: str, body: DecisionRequest | None = None,
           org: Organization = Depends(current_org), person: str = Depends(me),
           s: Session = Depends(get_session)):
    if decision not in ("approve", "reject"):
        raise HTTPException(404, "Unknown decision.")
    note = body.note if body else ""
    d = _errors(lambda: decide_delivery(s, org.id, person, delivery_id, decision == "approve", note))
    return {"id": d.id, "status": d.status}


@router.get("/can")
def check(person: str, action: str, resource: str, org: Organization = Depends(current_org),
          s: Session = Depends(get_session)):
    return CompanyGraph(s, org.id).check(person, action, resource).to_dict()

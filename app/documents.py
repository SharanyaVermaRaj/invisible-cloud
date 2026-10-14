"""The document vault: real files, every access checked by the company model.

Uploading a document is itself a logged, undoable change. Sending a document
to its client goes through the firm's approval rules.
"""
import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import CompanyGraph
from app.changes import ChangeError, apply_proposal
from app.config import settings
from app.models import Delivery, FileBlob, utcnow
from app.schemas import ChangeProposal, DocumentData
from app.seed import ADMIN_ROLE

ALLOWED_TYPES = {
    "application/pdf", "image/png", "image/jpeg", "text/plain", "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain"}


class Forbidden(Exception):
    """The acting person isn't allowed to do this. The message explains why."""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (s or "document")[:40]


def upload_document(session: Session, org_id: int, actor: str, *, title: str, client_service: str,
                    kind: str, amount: float | None, filename: str, mime: str, content: bytes):
    graph = CompanyGraph(session, org_id)
    cs = graph.entities.get(client_service)
    if not cs or cs.type != "client_service":
        raise ChangeError("Choose which client service this document belongs to.")
    if ADMIN_ROLE not in graph.roles_of(actor) and client_service not in graph.objs(actor, "assigned_to"):
        raise Forbidden(f"Only partners or people assigned to {cs.name} can upload documents there.")
    if mime not in ALLOWED_TYPES:
        raise ChangeError("That file type isn't supported. Upload a PDF, image, text, CSV, Word or Excel file.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ChangeError(f"Files can be at most {settings.max_upload_mb} MB.")
    if not content:
        raise ChangeError("That file is empty.")
    title = title.strip() or filename
    data = DocumentData(kind=kind, amount=amount, filename=filename, mime=mime, size=len(content))
    key = f"{_slug(title)}_{secrets.token_hex(3)}"
    proposal = ChangeProposal.model_validate({
        "summary": f"Upload “{title}” to {cs.name}",
        "operations": [
            {"op": "add_entity", "key": key, "type": "document", "name": title[:200],
             "data": data.model_dump(exclude_none=True)},
            {"op": "relate", "subject": key, "relation": "belongs_to", "object": client_service},
        ],
    })
    change = apply_proposal(session, org_id, proposal, actor=actor)
    session.add(FileBlob(org_id=org_id, document_key=key, filename=filename[:255], mime=mime, content=content))
    session.commit()
    return key, change


def get_file(session: Session, org_id: int, actor: str, key: str) -> FileBlob:
    decision = CompanyGraph(session, org_id).check(actor, "read", key)
    if not decision.allowed:
        raise Forbidden(decision.reason)
    blob = session.scalar(select(FileBlob).where(FileBlob.org_id == org_id, FileBlob.document_key == key))
    if not blob:
        raise ChangeError("This document has no file attached.")
    return blob


def latest_delivery(session: Session, org_id: int, key: str) -> Delivery | None:
    return session.scalar(select(Delivery).where(Delivery.org_id == org_id, Delivery.document_key == key)
                          .order_by(Delivery.id.desc()).limit(1))


def send_document(session: Session, org_id: int, actor: str, key: str) -> Delivery:
    graph = CompanyGraph(session, org_id)
    decision = graph.check(actor, "send", key)
    if not decision.allowed:
        raise Forbidden(decision.reason)
    last = latest_delivery(session, org_id, key)
    if last and last.status == "pending":
        raise ChangeError("This document is already waiting for approval.")
    need = graph.approval_needed(actor, key)
    delivery = Delivery(
        org_id=org_id, document_key=key, requested_by=actor,
        status="pending" if need else "sent",
        approval_rule=need["rule"] if need else None,
        approver_role=need["approver_role"] if need else None,
        decided_at=None if need else utcnow(),
    )
    session.add(delivery)
    session.commit()
    return delivery


def decide_delivery(session: Session, org_id: int, actor: str, delivery_id: int,
                    approve: bool, note: str = "") -> Delivery:
    d = session.get(Delivery, delivery_id)
    if not d or d.org_id != org_id:
        raise ChangeError("That request doesn't exist.")
    if d.status != "pending":
        raise ChangeError("That request has already been decided.")
    graph = CompanyGraph(session, org_id)
    if d.approver_role not in graph.roles_of(actor):
        role = graph.name(d.approver_role or "")
        raise Forbidden(f"Only a {role.lower()} can decide this request.")
    if d.document_key not in graph.entities:
        raise ChangeError("That document no longer exists.")
    d.status = "sent" if approve else "rejected"
    d.decided_by = actor
    d.note = note
    d.decided_at = utcnow()
    session.commit()
    return d

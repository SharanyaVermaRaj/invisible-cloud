"""Demo workspaces: every visitor gets a private copy of the demo firm.

The browser keeps a signed cookie pointing at its workspace. Workspaces older
than WORKSPACE_TTL_DAYS are deleted automatically.
"""
import secrets
from datetime import timedelta
from pathlib import Path

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.changes import apply_proposal, delete_org_rows
from app.config import settings
from app.models import FileBlob, Organization, utcnow
from app.seed import DEMO_FIRM, FIRM_NAME

COOKIE = "ic_workspace"
SEED_FILES = Path(__file__).resolve().parent / "seed_files"

_serializer = URLSafeSerializer(settings.secret_key, salt="workspace")


def sign(public_id: str) -> str:
    return _serializer.dumps(public_id)


def unsign(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _serializer.loads(token)
    except BadSignature:
        return None


def create_demo_workspace(session: Session) -> Organization:
    org = Organization(public_id=secrets.token_urlsafe(18), name=FIRM_NAME)
    session.add(org)
    session.commit()
    apply_proposal(session, org.id, DEMO_FIRM, actor="system", undoable=False)
    for op in DEMO_FIRM.operations:
        if getattr(op, "type", None) == "document":
            path = SEED_FILES / f"{op.key}.pdf"
            if path.exists():
                session.add(FileBlob(org_id=org.id, document_key=op.key, filename=path.name,
                                     mime="application/pdf", content=path.read_bytes()))
    session.commit()
    return org


def find_workspace(session: Session, token: str | None) -> Organization | None:
    public_id = unsign(token)
    if not public_id:
        return None
    return session.scalar(select(Organization).where(Organization.public_id == public_id))


def cleanup_expired(session: Session, limit: int = 25) -> int:
    cutoff = utcnow() - timedelta(days=settings.workspace_ttl_days)
    old = session.scalars(select(Organization.id).where(Organization.created_at < cutoff).limit(limit)).all()
    for org_id in old:
        delete_org_rows(session, org_id)
    session.commit()
    return len(old)

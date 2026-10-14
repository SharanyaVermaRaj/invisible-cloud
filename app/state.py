"""Everything the web app needs to draw one screen, computed from the company model."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import CompanyGraph
from app.models import Delivery, FileBlob, Organization
from app.rules import KIND_LABELS, describe_rule
from app.schemas import ACTIONS
from app.seed import ADMIN_ROLE, SUGGESTIONS


def _iso(dt):
    return dt.isoformat() if dt else None


def build_state(session: Session, org: Organization, me: str, ai_enabled: bool) -> dict:
    g = CompanyGraph(session, org.id)
    my_roles = g.roles_of(me)
    is_admin = ADMIN_ROLE in my_roles

    people = [{
        "key": p.key, "name": p.name, "title": p.title, "email": p.email,
        "roles": sorted(g.roles_of(p.key)),
        "assignments": sorted(g.objs(p.key, "assigned_to")),
        "contact_for": sorted(g.objs(p.key, "client_contact")),
    } for p in sorted(g.people.values(), key=lambda p: p.name)]

    client_services = []
    for cs in g.of_type("client_service"):
        client_services.append({
            "key": cs.key, "name": cs.name,
            "client": next(iter(g.objs(cs.key, "of_client")), None),
            "service": next(iter(g.objs(cs.key, "of_service")), None),
            "assignees": sorted(g.subjects(cs.key, "assigned_to")),
            "documents": sorted(g.subjects(cs.key, "belongs_to")),
        })

    blobs = set(session.scalars(select(FileBlob.document_key).where(FileBlob.org_id == org.id)))
    deliveries: dict[str, Delivery] = {}
    for d in session.scalars(select(Delivery).where(Delivery.org_id == org.id).order_by(Delivery.id)):
        deliveries[d.document_key] = d

    documents, hidden = [], 0
    for doc in g.of_type("document"):
        mine = {a: g.check(me, a, doc.key).to_dict() for a in ACTIONS}
        if not mine["read"]["allowed"] and not is_admin:
            hidden += 1
            continue
        data = doc.data or {}
        cs = g.doc_client_service(doc.key)
        item = {
            "key": doc.key, "name": doc.name, "kind": data.get("kind", "other"),
            "kind_label": KIND_LABELS.get(data.get("kind", "other"), ("document",))[0],
            "amount": data.get("amount"), "filename": data.get("filename"), "size": data.get("size"),
            "client_service": cs, "client": next(iter(g.doc_clients(doc.key)), None),
            "has_file": doc.key in blobs, "my_access": mine,
            "approval": g.approval_needed(me, doc.key) if mine["send"]["allowed"] else None,
        }
        d = deliveries.get(doc.key)
        if d and (is_admin or mine["edit"]["allowed"]):
            item["delivery"] = {"id": d.id, "status": d.status, "requested_by": d.requested_by,
                                "decided_by": d.decided_by, "created_at": _iso(d.created_at),
                                "decided_at": _iso(d.decided_at)}
        if is_admin:
            item["access"] = {a: sorted(p for p in g.people if g.check(p, a, doc.key).allowed)
                              for a in ACTIONS}
        documents.append(item)

    approvals = []
    for d in deliveries.values():
        if d.status == "pending" and d.approver_role in my_roles and d.document_key in g.entities:
            approvals.append({
                "id": d.id, "document": d.document_key, "document_name": g.name(d.document_key),
                "requested_by": d.requested_by, "requested_by_name": g.name(d.requested_by),
                "amount": g.doc_amount(d.document_key),
                "reason": g.describe(d.approval_rule) if d.approval_rule in g.rules else "",
                "created_at": _iso(d.created_at),
            })

    rules = [{
        "key": k, "version": row.version, "text": row.text, "type": row.definition.get("type"),
        "description": describe_rule(g.rules[k], g.names), "definition": row.definition,
    } for k, row in g.rule_rows.items()]

    me_person = g.people.get(me)
    return {
        "workspace": {"name": org.name, "created_at": _iso(org.created_at)},
        "ai_enabled": ai_enabled,
        "suggestions": SUGGESTIONS,
        "me": {"key": me, "name": me_person.name if me_person else me,
               "title": me_person.title if me_person else "", "roles": sorted(my_roles),
               "is_admin": is_admin},
        "names": {k: v for k, v in g.names.items()
                  if is_admin or g.entities.get(k) is None or g.entities[k].type != "document"
                  or k in {doc["key"] for doc in documents}},
        "people": people,
        "roles": [{"key": e.key, "name": e.name} for e in g.of_type("role")],
        "clients": [{"key": e.key, "name": e.name,
                     "contacts": sorted(g.subjects(e.key, "client_contact")),
                     "services": sorted(g.subjects(e.key, "of_client"))} for e in g.of_type("client")],
        "services": [{"key": e.key, "name": e.name} for e in g.of_type("service")],
        "client_services": client_services,
        "rules": rules,
        "documents": documents,
        "hidden_documents": hidden,
        "approvals": approvals,
        "kinds": [{"key": k, "label": v[0]} for k, v in KIND_LABELS.items()],
    }

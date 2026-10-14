"""The single enforcement point. Every module asks `can()` and nothing else."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, Person, Relationship, Rule
from app.rules import describe_rule, parse_rule
from app.schemas import ACTIONS, GRANTABLE, AccessRule, ApprovalRule, ExemptionRule, RestrictionRule


@dataclass
class Decision:
    allowed: bool
    reason: str
    rule: str | None = None

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason, "rule": self.rule}


class CompanyGraph:
    """In-memory snapshot of one organization's company model.

    Small firms have a few hundred facts at most, so loading them per request
    is fast. When that stops being true, this class is what gets swapped for
    OpenFGA; the tuples are already in its format.
    """

    def __init__(self, session: Session, org_id: int):
        self.people = {p.key: p for p in session.scalars(select(Person).where(Person.org_id == org_id))}
        self.entities = {e.key: e for e in session.scalars(select(Entity).where(Entity.org_id == org_id))}
        self.out: dict[tuple[str, str], set[str]] = {}
        self.inc: dict[tuple[str, str], set[str]] = {}
        for r in session.scalars(select(Relationship).where(Relationship.org_id == org_id)):
            self.out.setdefault((r.subject, r.relation), set()).add(r.object)
            self.inc.setdefault((r.object, r.relation), set()).add(r.subject)
        active = session.scalars(
            select(Rule).where(Rule.org_id == org_id, Rule.active.is_(True)).order_by(Rule.key)
        ).all()
        self.rule_rows = {r.key: r for r in active}
        self.rules = {r.key: parse_rule(r.definition) for r in active}
        self.names = {k: p.name for k, p in self.people.items()}
        self.names.update({k: e.name for k, e in self.entities.items()})

    # ---- basic lookups ----

    def objs(self, subject: str, relation: str) -> set[str]:
        return self.out.get((subject, relation), set())

    def subjects(self, obj: str, relation: str) -> set[str]:
        return self.inc.get((obj, relation), set())

    def name(self, key: str) -> str:
        return self.names.get(key, key)

    def of_type(self, type_: str) -> list[Entity]:
        return sorted((e for e in self.entities.values() if e.type == type_), key=lambda e: e.name)

    def roles_of(self, person: str) -> set[str]:
        return self.objs(person, "member_of")

    def doc_kind(self, doc: str) -> str:
        return ((self.entities[doc].data or {}).get("kind")) or "other"

    def doc_amount(self, doc: str) -> float | None:
        return (self.entities[doc].data or {}).get("amount")

    def doc_client_service(self, doc: str) -> str | None:
        return next(iter(sorted(self.objs(doc, "belongs_to"))), None)

    def doc_clients(self, doc: str) -> set[str]:
        clients = set()
        for cs in self.objs(doc, "belongs_to"):
            clients |= self.objs(cs, "of_client")
        return clients

    def describe(self, rule_key: str) -> str:
        return describe_rule(self.rules[rule_key], self.names)

    # ---- the decision ----

    def check(self, person: str, action: str, doc: str) -> Decision:
        if person not in self.people:
            return Decision(False, f"Unknown person “{person}”.")
        if doc not in self.entities or self.entities[doc].type != "document":
            return Decision(False, f"Unknown document “{doc}”.")
        if action not in ACTIONS:
            return Decision(False, f"Unknown action “{action}”.")

        if action == "send":
            base = self.check(person, "edit", doc)
            if not base.allowed:
                return Decision(False, "Sending a document requires edit access. " + base.reason, base.rule)
            granted = Decision(True, base.reason, base.rule)
        else:
            granted = self._grant(person, action, doc)
            if not granted.allowed:
                return granted

        roles = self.roles_of(person)
        kind = self.doc_kind(doc)
        for key, rule in self.rules.items():
            if (isinstance(rule, RestrictionRule) and rule.action == action
                    and rule.doc_kind in (None, kind) and not roles & set(rule.roles)):
                return Decision(False, f"Blocked by “{self.describe(key)}”", key)
        return granted

    def _grant(self, person: str, action: str, doc: str) -> Decision:
        roles = self.roles_of(person)
        for key, rule in self.rules.items():
            if not isinstance(rule, AccessRule) or rule.role not in roles:
                continue
            if action not in rule.actions and "*" not in rule.actions:
                continue
            if rule.scope == "all":
                return Decision(True, f"Allowed by “{self.describe(key)}”", key)
            if rule.scope == "assigned":
                shared = self.objs(person, "assigned_to") & self.objs(doc, "belongs_to")
                if shared:
                    cs = sorted(shared)[0]
                    return Decision(True, f"Allowed by “{self.describe(key)}” "
                                          f"(assigned to {self.name(cs)})", key)
            if rule.scope == "own_client":
                shared = self.objs(person, "client_contact") & self.doc_clients(doc)
                if shared:
                    c = sorted(shared)[0]
                    return Decision(True, f"Allowed by “{self.describe(key)}” "
                                          f"(contact for {self.name(c)})", key)
        return Decision(False, "No rule gives access to this document.")

    def approval_needed(self, person: str, doc: str) -> dict | None:
        """If sending this document needs someone's approval, say whose and why."""
        kind, amount = self.doc_kind(doc), self.doc_amount(doc)
        if amount is None:
            return None
        roles = self.roles_of(person)
        for key, rule in self.rules.items():
            if not (isinstance(rule, ApprovalRule) and rule.doc_kind == kind and amount > rule.min_amount):
                continue
            if rule.approver_role in roles:
                continue
            exempt = any(
                isinstance(e, ExemptionRule) and e.role in roles and e.doc_kind == kind
                and amount <= e.max_amount
                for e in self.rules.values()
            )
            if not exempt:
                return {"rule": key, "approver_role": rule.approver_role, "reason": self.describe(key)}
        return None

    def matrix(self) -> set[tuple[str, str, str]]:
        """Every (person, action, document) currently allowed."""
        docs = [k for k, e in self.entities.items() if e.type == "document"]
        return {(p, a, d) for p in self.people for d in docs for a in ACTIONS
                if self.check(p, a, d).allowed}


def can(session: Session, org_id: int, person: str, action: str, resource: str) -> Decision:
    return CompanyGraph(session, org_id).check(person, action, resource)


__all__ = ["CompanyGraph", "Decision", "can", "GRANTABLE"]

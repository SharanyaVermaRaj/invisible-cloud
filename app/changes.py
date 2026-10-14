"""The only way the company model changes.

    validate -> apply in a transaction -> compute who gains/loses access
             -> check rule conflicts -> preview (roll back) or commit + log

Every applied change stores its inverse operations, so any change can be
undone later by applying the inverse as a new change (like `git revert`).
"""
from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.authz import CompanyGraph
from app.models import Change, Entity, Organization, Person, Relationship, Rule
from app.rules import Conflict, describe_rule, find_conflicts, fix_for, parse_rule
from app.seed import ADMIN_ROLE
from app.schemas import (
    RELATIONS, AccessRule, AddEntity, AddPerson, ApprovalRule, ChangeProposal, DocumentData,
    ExemptionRule, Relate, RemoveEntity, RemovePerson, RemoveRule, RestrictionRule, SetRule, Unrelate,
)


class ChangeError(ValueError):
    """A proposal that can't be applied. The message is written for humans."""


class ConflictError(ChangeError):
    """The proposal is valid but contradicts existing rules. Carries a full preview with resolutions."""

    def __init__(self, preview: dict):
        super().__init__("This change conflicts with an existing rule.")
        self.preview = preview


# ---------- helpers ----------

def _person(session, org_id, key) -> Person | None:
    return session.scalar(select(Person).where(Person.org_id == org_id, Person.key == key))


def _entity(session, org_id, key) -> Entity | None:
    return session.scalar(select(Entity).where(Entity.org_id == org_id, Entity.key == key))


def _kind(session, org_id, key) -> str | None:
    if _person(session, org_id, key):
        return "person"
    e = _entity(session, org_id, key)
    return e.type if e else None


def _name(session, org_id, key) -> str:
    p = _person(session, org_id, key)
    if p:
        return p.name
    e = _entity(session, org_id, key)
    return e.name if e else key


def _active_rule(session, org_id, key) -> Rule | None:
    return session.scalar(select(Rule).where(Rule.org_id == org_id, Rule.key == key, Rule.active.is_(True)))


def _rule_roles(defn) -> set[str]:
    if isinstance(defn, AccessRule | ExemptionRule):
        return {defn.role}
    if isinstance(defn, RestrictionRule):
        return set(defn.roles)
    if isinstance(defn, ApprovalRule):
        return {defn.approver_role}
    return set()


def _rels_touching(session, org_id, key) -> list[Relationship]:
    return session.scalars(select(Relationship).where(
        Relationship.org_id == org_id, or_(Relationship.subject == key, Relationship.object == key),
    ).order_by(Relationship.id)).all()


def _relate_op(r: Relationship) -> dict:
    return {"op": "relate", "subject": r.subject, "relation": r.relation, "object": r.object}


TYPE_LABELS = {"role": "role", "client": "client", "service": "service",
               "client_service": "client service", "document": "document"}


def _describe_relation(session, org_id, subject, relation, obj, removing: bool) -> str:
    s, o = _name(session, org_id, subject), _name(session, org_id, obj)
    if relation == "member_of":
        return f"{s} is no longer {o}" if removing else f"{s} becomes {o}"
    if relation == "assigned_to":
        return f"Unassign {s} from {o}" if removing else f"Assign {s} to {o}"
    if relation == "client_contact":
        return f"{s} is no longer a contact for {o}" if removing else f"{s} becomes a contact for {o}"
    if relation in ("of_client", "of_service"):
        return f"Unlink {s} from {o}" if removing else f"Link {s} to {o}"
    if relation == "belongs_to":
        return f"Take {s} out of {o}" if removing else f"File {s} under {o}"
    return f"{subject} {'no longer ' if removing else ''}{relation} {obj}"


def _check_version(op, current: Rule | None) -> None:
    if op.if_version is None:
        return
    actual = current.version if current else 0
    if actual != op.if_version:
        raise ChangeError(f"the rule “{op.key}” has been changed since")


# ---------- applying one operation ----------

def _apply_op(session: Session, org_id: int, op, names: dict[str, str]) -> tuple[str, list[dict]]:
    """Validate and apply one operation. Returns (plain-English description, inverse ops)."""
    if isinstance(op, AddPerson | AddEntity):
        if _kind(session, org_id, op.key):
            raise ChangeError(f"“{op.key}” already exists")
        if isinstance(op, AddPerson):
            session.add(Person(org_id=org_id, key=op.key, name=op.name, email=op.email, title=op.title))
            return f"Add {op.name} to the firm", [{"op": "remove_person", "key": op.key}]
        data = None
        if op.type == "document":
            data = DocumentData.model_validate(op.data or {}).model_dump(exclude_none=True)
        elif op.data:
            raise ChangeError(f"only documents carry extra data (got data for {op.type} “{op.key}”)")
        session.add(Entity(org_id=org_id, key=op.key, type=op.type, name=op.name, data=data))
        return f"Add {TYPE_LABELS[op.type]} “{op.name}”", [{"op": "remove_entity", "key": op.key}]

    if isinstance(op, RemovePerson):
        person = _person(session, org_id, op.key)
        if not person:
            raise ChangeError(f"unknown person “{op.key}”")
        rels = _rels_touching(session, org_id, op.key)
        inverse = [{"op": "add_person", "key": person.key, "name": person.name,
                    "email": person.email, "title": person.title}] + [_relate_op(r) for r in rels]
        n_assign = sum(1 for r in rels if r.relation == "assigned_to")
        for r in rels:
            session.delete(r)
        session.delete(person)
        extra = f" (and {n_assign} assignment{'s' if n_assign != 1 else ''})" if n_assign else ""
        return f"Remove {person.name} from the firm{extra}", inverse

    if isinstance(op, RemoveEntity):
        ent = _entity(session, org_id, op.key)
        if not ent:
            raise ChangeError(f"unknown “{op.key}”")
        if ent.type == "role":
            for r in session.scalars(select(Rule).where(Rule.org_id == org_id, Rule.active.is_(True))):
                if op.key in _rule_roles(parse_rule(r.definition)):
                    raise ChangeError(f"the role “{ent.name}” is used by rule “{r.key}”; "
                                      f"change or remove that rule first")
        dependents = {"client": "of_client", "service": "of_service", "client_service": "belongs_to"}
        if ent.type in dependents:
            deps = session.scalars(select(Relationship.subject).where(
                Relationship.org_id == org_id, Relationship.object == op.key,
                Relationship.relation == dependents[ent.type])).all()
            if deps:
                listed = ", ".join(sorted(names.get(d, d) for d in deps))
                raise ChangeError(f"“{ent.name}” still has {listed}; remove or move those first")
        rels = _rels_touching(session, org_id, op.key)
        inverse = [{"op": "add_entity", "key": ent.key, "type": ent.type, "name": ent.name,
                    "data": ent.data}] + [_relate_op(r) for r in rels]
        for r in rels:
            session.delete(r)
        session.delete(ent)
        return f"Remove {TYPE_LABELS[ent.type]} “{ent.name}”", inverse

    if isinstance(op, Relate | Unrelate):
        if op.relation not in RELATIONS:
            raise ChangeError(f"unknown relation “{op.relation}”")
        subj_kinds, obj_kinds = RELATIONS[op.relation]
        sk, ok = _kind(session, org_id, op.subject), _kind(session, org_id, op.object)
        if sk is None:
            raise ChangeError(f"unknown “{op.subject}”")
        if ok is None:
            raise ChangeError(f"unknown “{op.object}”")
        if sk not in subj_kinds or ok not in obj_kinds:
            raise ChangeError(
                f"“{op.relation}” must link {'/'.join(sorted(subj_kinds))} → "
                f"{'/'.join(sorted(obj_kinds))}, got {sk} → {ok}"
            )
        existing = session.scalar(select(Relationship).where(
            Relationship.org_id == org_id, Relationship.subject == op.subject,
            Relationship.relation == op.relation, Relationship.object == op.object))
        flipped = {"subject": op.subject, "relation": op.relation, "object": op.object}
        if isinstance(op, Relate):
            if existing:
                raise ChangeError(f"{op.subject} is already {op.relation} {op.object}")
            if op.relation == "belongs_to" and session.scalar(select(Relationship.id).where(
                    Relationship.org_id == org_id, Relationship.subject == op.subject,
                    Relationship.relation == "belongs_to")):
                raise ChangeError(f"“{op.subject}” is already filed under a client service; "
                                  f"unrelate it first")
            session.add(Relationship(org_id=org_id, **flipped))
            return (_describe_relation(session, org_id, op.subject, op.relation, op.object, False),
                    [{"op": "unrelate", **flipped}])
        if not existing:
            raise ChangeError(f"{op.subject} is not {op.relation} {op.object}")
        session.delete(existing)
        return (_describe_relation(session, org_id, op.subject, op.relation, op.object, True),
                [{"op": "relate", **flipped}])

    if isinstance(op, SetRule):
        for role in _rule_roles(op.definition):
            if _kind(session, org_id, role) != "role":
                raise ChangeError(f"rule “{op.key}” refers to unknown role “{role}”")
        old = _active_rule(session, org_id, op.key)
        _check_version(op, old)
        version = 1
        if old:
            old.active = False
            version = old.version + 1
            inverse = [{"op": "set_rule", "key": op.key, "text": old.text, "definition": old.definition,
                        "if_version": version}]
        else:
            inverse = [{"op": "remove_rule", "key": op.key, "if_version": version}]
        session.add(Rule(org_id=org_id, key=op.key, version=version, text=op.text,
                         definition=op.definition.model_dump(), active=True))
        verb = "New rule" if version == 1 else f"Update rule (v{version})"
        return f"{verb}: {describe_rule(op.definition, names)}", inverse

    if isinstance(op, RemoveRule):
        old = _active_rule(session, org_id, op.key)
        if not old:
            raise ChangeError(f"no active rule “{op.key}”")
        _check_version(op, old)
        old.active = False
        return (f"Remove rule: {describe_rule(old.definition, names)}",
                [{"op": "set_rule", "key": op.key, "text": old.text, "definition": old.definition,
                  "if_version": 0}])

    raise ChangeError(f"unsupported operation {op!r}")  # pragma: no cover


# ---------- running a whole proposal ----------

@dataclass
class RunResult:
    summary: str
    operations: list[str]
    gained: list[dict]
    lost: list[dict]
    conflicts: list[Conflict]
    inverse: list[dict]
    rules_after: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "summary": self.summary,
            "operations": self.operations,
            "gained": self.gained,
            "lost": self.lost,
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


def _run(session: Session, org_id: int, proposal: ChangeProposal) -> RunResult:
    if not session.get(Organization, org_id):
        raise ChangeError(f"unknown organization {org_id}")
    before_graph = CompanyGraph(session, org_id)
    before = before_graph.matrix()
    names = dict(before_graph.names)

    steps, inverse, touched = [], [], set()
    for i, op in enumerate(proposal.operations, 1):
        # names of things added earlier in this proposal
        names.update({o.key: o.name for o in proposal.operations[:i] if isinstance(o, AddPerson | AddEntity)})
        try:
            desc, inv = _apply_op(session, org_id, op, names)
        except ChangeError as e:
            raise ChangeError(f"Step {i}: {e}") from None
        steps.append(desc)
        inverse = inv + inverse
        if isinstance(op, SetRule):
            touched.add(op.key)
        session.flush()

    after_graph = CompanyGraph(session, org_id)
    if not after_graph.subjects(ADMIN_ROLE, "member_of"):
        raise ChangeError(f"the firm needs at least one {after_graph.name(ADMIN_ROLE).lower()}, "
                          f"and this change would leave none")
    after = after_graph.matrix()
    names.update(after_graph.names)
    conflicts = find_conflicts(after_graph.rules, touched, names)

    def fmt(items):
        return [{"person": p, "person_name": names.get(p, p), "action": a,
                 "resource": d, "resource_name": names.get(d, d)} for p, a, d in sorted(items)]

    return RunResult(proposal.summary, steps, fmt(after - before), fmt(before - after),
                     conflicts, inverse, dict(after_graph.rules), names)


def _with_rule_edits(proposal: ChangeProposal, edits: dict, existing: set[str], names) -> ChangeProposal | None:
    """Return a copy of the proposal with rule edits folded in (None = remove the rule)."""
    ops = [o.model_dump() for o in proposal.operations]
    for key, defn in edits.items():
        idx = next((i for i, o in enumerate(ops) if o["op"] == "set_rule" and o["key"] == key), None)
        if defn is None:
            if idx is not None:
                ops.pop(idx)
                if key in existing:
                    ops.append({"op": "remove_rule", "key": key})
            else:
                ops.append({"op": "remove_rule", "key": key})
        else:
            new_op = {"op": "set_rule", "key": key, "text": describe_rule(defn, names),
                      "definition": defn.model_dump()}
            if idx is not None:
                ops[idx] = new_op
            else:
                ops.append(new_op)
    if not ops:
        return None
    summary = proposal.summary
    if not summary.endswith("(adjusted)"):
        summary = (summary[:480] + " (adjusted)")
    return ChangeProposal.model_validate({"summary": summary, "operations": ops})


def _resolutions(session, org_id, proposal, result: RunResult) -> list[dict]:
    touched = {o.key for o in proposal.operations if isinstance(o, SetRule)}
    existing = set(session.scalars(select(Rule.key).where(Rule.org_id == org_id, Rule.active.is_(True))))
    options = []
    for favour in ("a", "b"):
        defs = dict(result.rules_after)
        edits = {}
        for c in result.conflicts:
            if c.rule_a not in defs or c.rule_b not in defs:
                continue
            for key, defn in fix_for(c, defs, favour).items():
                edits[key] = defn
                if defn is None:
                    defs.pop(key, None)
                else:
                    defs[key] = defn
        edits_existing = any(k not in touched for k in edits)
        new_removed = any(d is None and k in touched for k, d in edits.items())
        if edits_existing:
            label = "Change the existing rule"
        elif new_removed or not edits:
            label = "Keep the existing rule"
        else:
            label = "Adjust your new rule"

        candidate = _with_rule_edits(proposal, edits, existing, result.names)
        if candidate is None:
            # Resolving this way leaves nothing to do: the change simply isn't made.
            options.append({"id": favour, "label": label, "proposal": None,
                            "changes": ["Nothing changes. The new rule isn't added."],
                            "gained": [], "lost": [], "operations": []})
            continue
        try:
            check = _run(session, org_id, candidate)
        except ChangeError:
            continue
        finally:
            session.rollback()
        if check.conflicts:
            continue
        changes = [f"Remove rule “{k}”" if d is None else describe_rule(d, result.names)
                   for k, d in edits.items()]
        options.append({"id": favour, "label": label, "changes": changes,
                        "proposal": candidate.model_dump(),
                        "gained": check.gained, "lost": check.lost, "operations": check.operations})
    return options


def preview_proposal(session: Session, org_id: int, proposal: ChangeProposal) -> dict:
    """Show exactly what would change, then roll everything back."""
    try:
        result = _run(session, org_id, proposal)
    finally:
        session.rollback()
    data = result.public()
    data["proposal"] = proposal.model_dump()
    data["resolutions"] = _resolutions(session, org_id, proposal, result) if result.conflicts else []
    return data


def apply_proposal(session: Session, org_id: int, proposal: ChangeProposal, actor: str = "owner",
                   *, undoable: bool = True, reverts: int | None = None) -> Change:
    try:
        result = _run(session, org_id, proposal)
        if result.conflicts:
            session.rollback()
            raise ConflictError(preview_proposal(session, org_id, proposal))
        change = Change(org_id=org_id, actor=actor, summary=proposal.summary,
                        proposal=proposal.model_dump(), diff=result.public(),
                        inverse=result.inverse if undoable else None, reverts=reverts)
        session.add(change)
        session.flush()
        if reverts is not None:
            original = session.get(Change, reverts)
            original.reverted_by = change.id
        session.commit()
        return change
    except ConflictError:
        raise
    except Exception:
        session.rollback()
        raise


# ---------- undo ----------

def _undo_proposal(session: Session, org_id: int, change_id: int) -> tuple[Change, ChangeProposal]:
    c = session.get(Change, change_id)
    if not c or c.org_id != org_id:
        raise ChangeError("That change doesn't exist.")
    if c.reverted_by:
        raise ChangeError("That change has already been undone.")
    if c.inverse is None:
        raise ChangeError("That change can't be undone.")
    summary = f"Undo: {c.summary}"
    return c, ChangeProposal.model_validate({"summary": summary[:500], "operations": c.inverse})


def preview_undo(session: Session, org_id: int, change_id: int) -> dict:
    _, proposal = _undo_proposal(session, org_id, change_id)
    try:
        return preview_proposal(session, org_id, proposal)
    except ChangeError as e:
        raise ChangeError(f"Can't undo this because later changes depend on it. {e}") from None


def undo_change(session: Session, org_id: int, change_id: int, actor: str) -> Change:
    c, proposal = _undo_proposal(session, org_id, change_id)
    try:
        return apply_proposal(session, org_id, proposal, actor, reverts=c.id)
    except ConflictError:
        raise ChangeError("Undoing this would conflict with rules added since. "
                          "Change those rules first.") from None
    except ChangeError as e:
        raise ChangeError(f"Can't undo this because later changes depend on it. {e}") from None


def delete_org_rows(session: Session, org_id: int) -> None:
    from app.models import ORG_TABLES
    for table in ORG_TABLES:
        session.execute(delete(table).where(table.org_id == org_id))
    session.execute(delete(Organization).where(Organization.id == org_id))

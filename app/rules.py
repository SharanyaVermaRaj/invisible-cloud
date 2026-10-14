"""Deterministic reasoning about rules: plain-English descriptions and conflict detection.

No AI here. Conflicts are found by comparing typed rule definitions, and every
suggested resolution is itself an ordinary, typed rule edit.
"""
from dataclasses import dataclass, field

from pydantic import TypeAdapter

from app.schemas import GRANTABLE, AccessRule, ApprovalRule, ExemptionRule, RestrictionRule, RuleDefinition

_rule_adapter = TypeAdapter(RuleDefinition)

KIND_LABELS = {
    "tax_return": ("tax return", "tax returns"),
    "w2": ("W-2", "W-2s"),
    "payroll_report": ("payroll report", "payroll reports"),
    "financial_statement": ("financial statement", "financial statements"),
    "invoice": ("invoice", "invoices"),
    "engagement_letter": ("engagement letter", "engagement letters"),
    "other": ("document", "documents"),
}


def parse_rule(definition: dict):
    return _rule_adapter.validate_python(definition)


def kind_label(kind: str | None, plural: bool = False) -> str:
    if kind is None:
        return "documents" if plural else "document"
    singular, many = KIND_LABELS.get(kind, (kind.replace("_", " "), kind.replace("_", " ") + "s"))
    return many if plural else singular


def money(amount: float) -> str:
    return f"${amount:,.0f}" if float(amount).is_integer() else f"${amount:,.2f}"


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def role_plural(role: str, names: dict[str, str]) -> str:
    name = names.get(role, role.replace("_", " ").title())
    return name if name.endswith("s") else name + "s"


def describe_rule(defn, names: dict[str, str]) -> str:
    """Render a typed rule as one plain-English sentence."""
    if isinstance(defn, dict):
        defn = parse_rule(defn)
    if isinstance(defn, AccessRule):
        actions = list(GRANTABLE) if "*" in defn.actions else [a for a in GRANTABLE if a in defn.actions]
        scope = {
            "all": "every document",
            "assigned": "documents for the client services they're assigned to",
            "own_client": "their own company's documents",
        }[defn.scope]
        return f"{role_plural(defn.role, names)} can {_join(actions)} {scope}."
    if isinstance(defn, RestrictionRule):
        roles = _join([role_plural(r, names).lower() for r in defn.roles])
        return f"Only {roles} can {defn.action} {kind_label(defn.doc_kind, plural=True)}."
    if isinstance(defn, ApprovalRule):
        approver = names.get(defn.approver_role, defn.approver_role).lower()
        return (f"{kind_label(defn.doc_kind, plural=True).capitalize()} over {money(defn.min_amount)} "
                f"need {approver} approval before they're sent.")
    if isinstance(defn, ExemptionRule):
        return (f"{role_plural(defn.role, names)} can send {kind_label(defn.doc_kind, plural=True)} "
                f"up to {money(defn.max_amount)} without approval.")
    raise ValueError(f"unknown rule {defn!r}")


# ---------- Conflicts ----------

@dataclass
class Conflict:
    kind: str            # "grant_vs_restriction" | "approval_vs_exemption"
    rule_a: str          # access rule / approval rule
    rule_b: str          # restriction rule / exemption rule
    message: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "rules": [self.rule_a, self.rule_b],
                "message": self.message, "detail": self.detail}


def _granted(rule: AccessRule) -> set[str]:
    return set(GRANTABLE) if "*" in rule.actions else set(rule.actions)


def find_conflicts(rules: dict[str, object], touched: set[str], names: dict[str, str]) -> list[Conflict]:
    """Return conflicts among active rules that involve at least one touched rule.

    rules:   key -> typed definition (the full active rule set after the change)
    touched: keys of rules created or edited by the change being checked
    """
    found = []
    items = sorted(rules.items())
    for ka, a in items:
        for kb, b in items:
            if ka not in touched and kb not in touched:
                continue
            if isinstance(a, AccessRule) and isinstance(b, RestrictionRule):
                # A doc-kind-specific restriction is a deliberate exception, not a contradiction.
                if b.doc_kind is None and b.action in _granted(a) and a.role not in b.roles:
                    found.append(Conflict(
                        "grant_vs_restriction", ka, kb,
                        f"“{describe_rule(a, names)}” lets {role_plural(a.role, names).lower()} "
                        f"{b.action} documents, but “{describe_rule(b, names)}” forbids it.",
                        {"role": a.role, "action": b.action},
                    ))
            if isinstance(a, ApprovalRule) and isinstance(b, ExemptionRule):
                if (a.doc_kind == b.doc_kind and b.role != a.approver_role
                        and b.max_amount > a.min_amount):
                    found.append(Conflict(
                        "approval_vs_exemption", ka, kb,
                        f"“{describe_rule(b, names)}” would let {role_plural(b.role, names).lower()} "
                        f"send {kind_label(a.doc_kind, plural=True)} between {money(a.min_amount)} and "
                        f"{money(b.max_amount)} with no approval, but “{describe_rule(a, names)}” "
                        f"requires it.",
                        {"doc_kind": a.doc_kind, "min_amount": a.min_amount, "max_amount": b.max_amount},
                    ))
    return found


def fix_for(conflict: Conflict, rules: dict[str, object], favour: str):
    """The rule edits that resolve one conflict.

    favour="a" keeps rule A's intent (the grant / the approval),
    favour="b" keeps rule B's intent (the restriction / the exemption).
    Returns {rule_key: new_definition_or_None}; None means remove the rule.
    """
    a, b = rules[conflict.rule_a], rules[conflict.rule_b]
    if conflict.kind == "grant_vs_restriction":
        if favour == "a":   # the grant wins: let this role do the action
            return {conflict.rule_b: b.model_copy(update={"roles": [*b.roles, a.role]})}
        remaining = [x for x in GRANTABLE if x in _granted(a) and x != b.action]
        if not remaining:
            return {conflict.rule_a: None}
        return {conflict.rule_a: a.model_copy(update={"actions": remaining})}
    if conflict.kind == "approval_vs_exemption":
        if favour == "a":   # approval threshold wins: cap the exemption at it
            if a.min_amount <= 0:
                return {conflict.rule_b: None}
            return {conflict.rule_b: b.model_copy(update={"max_amount": a.min_amount})}
        return {conflict.rule_a: a.model_copy(update={"min_amount": b.max_amount})}
    raise ValueError(conflict.kind)

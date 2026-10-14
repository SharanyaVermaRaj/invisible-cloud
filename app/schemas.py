"""The fixed vocabulary the system understands.

The AI layer may only emit a ChangeProposal built from these operations and
rule types. It can never write SQL, code, or touch tables directly.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

Key = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,60}$")]

EntityType = Literal["role", "client", "service", "client_service", "document"]
DocKind = Literal[
    "tax_return", "w2", "payroll_report", "financial_statement", "invoice",
    "engagement_letter", "other",
]
Action = Literal["read", "edit", "share", "send"]
GrantableAction = Literal["read", "edit", "share"]  # "send" requires "edit"

ACTIONS = ("read", "edit", "share", "send")
GRANTABLE = ("read", "edit", "share")

# relation -> (allowed subject kinds, allowed object kinds).
# "person" means a Person; anything else is an Entity type.
RELATIONS: dict[str, tuple[set[str], set[str]]] = {
    "member_of": ({"person"}, {"role"}),                   # sarah member_of partner
    "assigned_to": ({"person"}, {"client_service"}),       # john assigned_to acme_tax
    "client_contact": ({"person"}, {"client"}),            # dana client_contact acme
    "of_client": ({"client_service"}, {"client"}),         # acme_tax of_client acme
    "of_service": ({"client_service"}, {"service"}),       # acme_tax of_service tax_prep
    "belongs_to": ({"document"}, {"client_service"}),      # acme_w2 belongs_to acme_payroll
}


# ---------- Document metadata ----------

class DocumentData(BaseModel):
    kind: DocKind = "other"
    amount: float | None = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    filename: str | None = None
    mime: str | None = None
    size: int | None = None


# ---------- Rules ----------

class AccessRule(BaseModel):
    """'<role>s can <actions> documents within <scope>.'

    scope: all        - every document in the organization
           assigned   - documents of client services the person is assigned to
           own_client - documents of the client the person is a contact for
    """
    type: Literal["access"] = "access"
    role: Key
    actions: list[Literal["read", "edit", "share", "*"]] = Field(min_length=1)
    scope: Literal["all", "assigned", "own_client"]


class RestrictionRule(BaseModel):
    """'Only <roles> can <action> <documents of kind>.' Overrides any grant."""
    type: Literal["restriction"] = "restriction"
    action: Action
    roles: list[Key] = Field(min_length=1)
    doc_kind: DocKind | None = None  # None = every kind of document


class ApprovalRule(BaseModel):
    """'<doc kind> over <min_amount> need <approver_role> approval before they're sent.'"""
    type: Literal["approval"] = "approval"
    doc_kind: DocKind
    min_amount: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    approver_role: Key


class ExemptionRule(BaseModel):
    """'<role>s can send <doc kind> up to <max_amount> without approval.'"""
    type: Literal["exemption"] = "exemption"
    role: Key
    doc_kind: DocKind
    max_amount: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)


RuleDefinition = Annotated[
    Union[AccessRule, RestrictionRule, ApprovalRule, ExemptionRule],
    Field(discriminator="type"),
]


# ---------- Operations ----------

class AddPerson(BaseModel):
    op: Literal["add_person"] = "add_person"
    key: Key
    name: str = Field(min_length=1, max_length=200)
    email: str = ""
    title: str = ""


class AddEntity(BaseModel):
    op: Literal["add_entity"] = "add_entity"
    key: Key
    type: EntityType
    name: str = Field(min_length=1, max_length=200)
    data: dict | None = None  # only for documents (see DocumentData)


class RemovePerson(BaseModel):
    """Removes a person and every relationship they have (e.g. someone leaves the firm)."""
    op: Literal["remove_person"] = "remove_person"
    key: Key


class RemoveEntity(BaseModel):
    """Removes a client, service, client service or document and its relationships."""
    op: Literal["remove_entity"] = "remove_entity"
    key: Key


class Relate(BaseModel):
    op: Literal["relate"] = "relate"
    subject: Key
    relation: str
    object: Key


class Unrelate(BaseModel):
    op: Literal["unrelate"] = "unrelate"
    subject: Key
    relation: str
    object: Key


class SetRule(BaseModel):
    """Create a rule, or edit it (same key = new version)."""
    op: Literal["set_rule"] = "set_rule"
    key: Key
    text: str = Field(min_length=1, max_length=1000)
    definition: RuleDefinition
    # Used by undo: only apply if the rule is still at this version (0 = must not exist).
    if_version: int | None = Field(default=None, ge=0)


class RemoveRule(BaseModel):
    op: Literal["remove_rule"] = "remove_rule"
    key: Key
    if_version: int | None = Field(default=None, ge=0)


Operation = Annotated[
    Union[AddPerson, AddEntity, RemovePerson, RemoveEntity, Relate, Unrelate, SetRule, RemoveRule],
    Field(discriminator="op"),
]


class ChangeProposal(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    operations: list[Operation] = Field(min_length=1, max_length=200)


# ---------- API request bodies ----------

class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class DecisionRequest(BaseModel):
    note: str = Field(default="", max_length=500)

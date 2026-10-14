"""Bad proposals are rejected with readable errors, and nothing partial is applied."""
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.changes import ChangeError, apply_proposal
from app.models import Change
from tests.conftest import allowed, proposal


@pytest.mark.parametrize("op, message", [
    ({"op": "relate", "subject": "mke", "relation": "assigned_to", "object": "acme_payroll"}, "unknown “mke”"),
    ({"op": "relate", "subject": "john", "relation": "assigned_to", "object": "acme"},
     "must link person → client_service, got person → client"),
    ({"op": "relate", "subject": "john", "relation": "manages", "object": "mike"}, "unknown relation"),
    ({"op": "relate", "subject": "john", "relation": "assigned_to", "object": "acme_tax"}, "already assigned_to"),
    ({"op": "unrelate", "subject": "john", "relation": "assigned_to", "object": "acme_payroll"}, "is not assigned_to"),
    ({"op": "add_person", "key": "john", "name": "John 2"}, "already exists"),
    ({"op": "remove_rule", "key": "nope"}, "no active rule"),
    ({"op": "remove_person", "key": "nobody"}, "unknown person"),
    ({"op": "remove_entity", "key": "partner"}, "is used by rule"),
    ({"op": "remove_entity", "key": "acme"}, "still has"),
    ({"op": "relate", "subject": "acme_w2", "relation": "belongs_to", "object": "acme_tax"}, "already filed"),
    ({"op": "add_entity", "key": "x", "type": "client", "name": "X", "data": {"kind": "w2"}}, "only documents"),
    ({"op": "set_rule", "key": "x", "text": "Interns see all",
      "definition": {"type": "access", "role": "intern", "actions": ["read"], "scope": "all"}}, "unknown role"),
])
def test_invalid_operations_are_rejected(session, firm, op, message):
    with pytest.raises(ChangeError, match=message):
        apply_proposal(session, firm, proposal("test", op))


def test_failed_proposal_is_all_or_nothing(session, firm):
    with pytest.raises(ChangeError, match="Step 2"):
        apply_proposal(session, firm, proposal(
            "typo",
            {"op": "unrelate", "subject": "mike", "relation": "assigned_to", "object": "acme_payroll"},
            {"op": "relate", "subject": "sarha", "relation": "assigned_to", "object": "acme_payroll"},
        ))
    assert allowed(session, firm, "mike", "read", "acme_payroll_report")
    assert session.scalar(select(func.count(Change.id)).where(Change.org_id == firm)) == 1


def test_removing_a_client_in_dependency_order_works(session, firm):
    apply_proposal(session, firm, proposal(
        "We no longer work with Globex.",
        {"op": "remove_entity", "key": "globex_statement"},
        {"op": "remove_entity", "key": "globex_invoice"},
        {"op": "remove_entity", "key": "globex_books"},
        {"op": "remove_entity", "key": "globex"},
    ))


def test_schema_rejects_unknown_operations():
    with pytest.raises(ValidationError):
        proposal("x", {"op": "drop_table", "table": "people"})


def test_schema_rejects_unknown_rule_type():
    with pytest.raises(ValidationError):
        proposal("x", {"op": "set_rule", "key": "x", "text": "t",
                       "definition": {"type": "superuser", "role": "partner"}})


def test_schema_rejects_bad_keys():
    with pytest.raises(ValidationError):
        proposal("x", {"op": "remove_person", "key": "Robert'); DROP TABLE people;--"})

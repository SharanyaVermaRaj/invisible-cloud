"""Every change can be undone, like `git revert`."""
import pytest
from sqlalchemy import select

from app.authz import CompanyGraph
from app.changes import ChangeError, apply_proposal, preview_undo, undo_change
from app.models import Change, Rule
from tests.conftest import HANDOVER, allowed, proposal


def test_undo_reassignment(session, firm):
    change = apply_proposal(session, firm, HANDOVER)
    preview = preview_undo(session, firm, change.id)
    assert {x["person"] for x in preview["gained"]} == {"mike"}
    undo = undo_change(session, firm, change.id, "elena")
    assert allowed(session, firm, "mike", "read", "acme_w2")
    assert not allowed(session, firm, "sarah", "read", "acme_w2")
    assert session.get(Change, change.id).reverted_by == undo.id
    assert undo.reverts == change.id


def test_cannot_undo_twice(session, firm):
    change = apply_proposal(session, firm, HANDOVER)
    undo_change(session, firm, change.id, "elena")
    with pytest.raises(ChangeError, match="already been undone"):
        undo_change(session, firm, change.id, "elena")


def test_setup_cannot_be_undone(session, firm):
    setup = session.scalar(select(Change).where(Change.org_id == firm).order_by(Change.id))
    with pytest.raises(ChangeError, match="can't be undone"):
        undo_change(session, firm, setup.id, "elena")


def test_undo_of_undo_redoes(session, firm):
    change = apply_proposal(session, firm, HANDOVER)
    undo = undo_change(session, firm, change.id, "elena")
    undo_change(session, firm, undo.id, "elena")
    assert allowed(session, firm, "sarah", "read", "acme_w2")


def test_undo_offboarding_restores_everything(session, firm):
    change = apply_proposal(session, firm, proposal("Mike left", {"op": "remove_person", "key": "mike"}))
    undo_change(session, firm, change.id, "elena")
    g = CompanyGraph(session, firm)
    assert g.people["mike"].name == "Mike Russo"
    assert g.objs("mike", "assigned_to") == {"acme_payroll"}
    assert g.roles_of("mike") == {"accountant"}


def test_undo_rule_edit_restores_previous_definition(session, firm):
    change = apply_proposal(session, firm, proposal(
        "Raise the approval threshold.",
        {"op": "set_rule", "key": "tax_return_approval", "text": "Over $9,000",
         "definition": {"type": "approval", "doc_kind": "tax_return", "min_amount": 9000, "approver_role": "partner"}},
    ))
    undo_change(session, firm, change.id, "elena")
    rule = session.scalar(select(Rule).where(Rule.org_id == firm, Rule.key == "tax_return_approval",
                                             Rule.active.is_(True)))
    assert rule.version == 3 and rule.definition["min_amount"] == 5000


def test_undo_blocked_by_later_change(session, firm):
    first = apply_proposal(session, firm, HANDOVER)
    apply_proposal(session, firm, proposal(
        "Sarah is off Acme payroll too.",
        {"op": "unrelate", "subject": "sarah", "relation": "assigned_to", "object": "acme_payroll"},
    ))
    with pytest.raises(ChangeError, match="later changes depend on it"):
        undo_change(session, firm, first.id, "elena")


def test_undo_of_old_rule_edit_does_not_clobber_newer_edit(session, firm):
    def threshold(n):
        return proposal(f"Threshold {n}", {"op": "set_rule", "key": "tax_return_approval", "text": f"Over {n}",
            "definition": {"type": "approval", "doc_kind": "tax_return", "min_amount": n, "approver_role": "partner"}})
    first = apply_proposal(session, firm, threshold(6000))
    apply_proposal(session, firm, threshold(7000))
    with pytest.raises(ChangeError, match="has been changed since"):
        undo_change(session, firm, first.id, "elena")


def test_undo_rule_removal_blocked_if_recreated(session, firm):
    removed = apply_proposal(session, firm, proposal("Drop it", {"op": "remove_rule", "key": "tax_return_approval"}))
    apply_proposal(session, firm, proposal("New one", {"op": "set_rule", "key": "tax_return_approval", "text": "x",
        "definition": {"type": "approval", "doc_kind": "tax_return", "min_amount": 100, "approver_role": "partner"}}))
    with pytest.raises(ChangeError, match="has been changed since"):
        undo_change(session, firm, removed.id, "elena")

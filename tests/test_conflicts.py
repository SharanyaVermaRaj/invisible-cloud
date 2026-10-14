"""Conflicting rules are caught before they apply, with concrete ways to resolve them."""
import pytest

from app.authz import CompanyGraph
from app.changes import ConflictError, apply_proposal, preview_proposal
from app.schemas import ChangeProposal
from tests.conftest import ACCOUNTANTS_SHARE, EXEMPTION, allowed, proposal


def test_exemption_above_approval_threshold_is_a_conflict(session, firm):
    p = preview_proposal(session, firm, EXEMPTION)
    assert len(p["conflicts"]) == 1
    c = p["conflicts"][0]
    assert c["kind"] == "approval_vs_exemption"
    assert c["rules"] == ["tax_return_approval", "accountant_tax_exemption"]
    assert "$5,000 and $10,000" in c["message"]
    labels = {r["id"]: r["label"] for r in p["resolutions"]}
    assert labels == {"a": "Keep the existing rule", "b": "Apply your new rule"}


def test_conflicting_change_cannot_be_applied(session, firm):
    with pytest.raises(ConflictError) as e:
        apply_proposal(session, firm, EXEMPTION)
    assert e.value.preview["resolutions"]
    assert "accountant_tax_exemption" not in CompanyGraph(session, firm).rules


def test_keep_existing_caps_the_exemption(session, firm):
    p = preview_proposal(session, firm, EXEMPTION)
    keep = next(r for r in p["resolutions"] if r["id"] == "a")
    assert keep["changes"] == ["Accountants can send tax returns up to $5,000 without approval."]
    apply_proposal(session, firm, ChangeProposal.model_validate(keep["proposal"]))
    rules = CompanyGraph(session, firm).rules
    assert rules["accountant_tax_exemption"].max_amount == 5000
    assert rules["tax_return_approval"].min_amount == 5000


def test_new_rule_wins_raises_the_threshold(session, firm):
    p = preview_proposal(session, firm, EXEMPTION)
    win = next(r for r in p["resolutions"] if r["id"] == "b")
    assert win["changes"] == ["Tax returns over $10,000 need partner approval before they're sent."]
    apply_proposal(session, firm, ChangeProposal.model_validate(win["proposal"]))
    rules = CompanyGraph(session, firm).rules
    assert rules["accountant_tax_exemption"].max_amount == 10000
    assert rules["tax_return_approval"].min_amount == 10000


def test_grant_vs_restriction(session, firm):
    p = preview_proposal(session, firm, ACCOUNTANTS_SHARE)
    assert [c["kind"] for c in p["conflicts"]] == ["grant_vs_restriction"]
    by_id = {r["id"]: r for r in p["resolutions"]}
    # Apply the new rule: accountants are added to the restriction.
    assert by_id["a"]["label"] == "Apply your new rule"
    assert by_id["a"]["changes"] == ["Only partners and accountants can share documents."]
    # Keep the restriction: the new grant has nothing left, so it isn't created at all.
    assert by_id["b"]["label"] == "Keep the existing rule"
    assert by_id["b"]["proposal"] is None


def test_apply_new_share_rule(session, firm):
    p = preview_proposal(session, firm, ACCOUNTANTS_SHARE)
    choice = next(r for r in p["resolutions"] if r["id"] == "a")
    apply_proposal(session, firm, ChangeProposal.model_validate(choice["proposal"]))
    assert allowed(session, firm, "john", "share", "acme_tax_return")
    assert not allowed(session, firm, "john", "share", "acme_w2")  # still only assigned docs


def test_restriction_added_later_conflicts_with_existing_grant(session, firm):
    p = preview_proposal(session, firm, proposal(
        "Only partners can edit documents.",
        {"op": "set_rule", "key": "partners_edit", "text": "Only partners can edit documents.",
         "definition": {"type": "restriction", "action": "edit", "roles": ["partner"]}},
    ))
    assert p["conflicts"][0]["rules"] == ["accountants_assigned", "partners_edit"]
    keep_new = next(r for r in p["resolutions"] if r["label"] == "Apply your new rule")
    assert keep_new["changes"] == [
        "Accountants can read documents for the client services they're assigned to."]


def test_kind_specific_restriction_is_not_a_conflict(session, firm):
    p = preview_proposal(session, firm, proposal(
        "Only partners can edit tax returns.",
        {"op": "set_rule", "key": "partners_edit_tax", "text": "Only partners can edit tax returns.",
         "definition": {"type": "restriction", "action": "edit", "roles": ["partner"], "doc_kind": "tax_return"}},
    ))
    assert p["conflicts"] == []
    apply_proposal(session, firm, ChangeProposal.model_validate(p["proposal"]))
    assert not allowed(session, firm, "john", "edit", "acme_tax_return")
    assert allowed(session, firm, "john", "edit", "globex_statement")


def test_exemption_within_threshold_is_fine(session, firm):
    p = preview_proposal(session, firm, proposal(
        "Accountants can send tax returns up to $4,000 without approval.",
        {"op": "set_rule", "key": "small_returns", "text": "x",
         "definition": {"type": "exemption", "role": "accountant", "doc_kind": "tax_return", "max_amount": 4000}},
    ))
    assert p["conflicts"] == []

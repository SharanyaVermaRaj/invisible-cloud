"""The AI layer, tested with a scripted fake model (no API key needed)."""
import json
from types import SimpleNamespace

import pytest

from app.translator import TOOLS, TranslationError, model_snapshot, translate
from tests.conftest import allowed


def tool_call(name, data, id_="t1"):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name=name, input=data, id=id_)])


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


HANDOVER = {"summary": "Sarah will handle Acme's payroll instead of Mike", "operations": [
    {"op": "unrelate", "subject": "mike", "relation": "assigned_to", "object": "acme_payroll"},
    {"op": "relate", "subject": "sarah", "relation": "assigned_to", "object": "acme_payroll"},
]}


def test_valid_proposal_is_previewed_not_applied(session, firm):
    t = translate(session, firm, "Sarah will handle Acme's payroll", client=FakeLLM(tool_call("propose_change", HANDOVER)))
    assert t.kind == "proposal"
    assert any(x["person"] == "mike" for x in t.preview["lost"])
    assert allowed(session, firm, "mike", "read", "acme_w2")


def test_model_gets_company_model_and_must_use_a_tool(session, firm):
    llm = FakeLLM(tool_call("propose_change", HANDOVER))
    translate(session, firm, "anything", client=llm)
    req = llm.requests[0]
    assert req["tool_choice"] == {"type": "auto"}
    assert {t["name"] for t in req["tools"]} == {"propose_change", "ask_clarification", "answer"}
    assert '"acme_payroll"' in req["messages"][0]["content"]
    assert "Owner says: anything" in req["messages"][0]["content"]


def test_snapshot_includes_computed_access(session, firm):
    snap = model_snapshot(session, firm)
    assert snap["access"]["acme_w2"]["read"] == ["dana", "elena", "mike"]
    json.dumps(snap)


def test_questions_and_answers_pass_through(session, firm):
    t = translate(session, firm, "John takes over Acme",
                  client=FakeLLM(tool_call("ask_clarification", {"question": "Which Acme service?"})))
    assert (t.kind, t.text) == ("question", "Which Acme service?")
    t = translate(session, firm, "Who can see the W-2?",
                  client=FakeLLM(tool_call("answer", {"text": "Elena, Mike and Dana."})))
    assert (t.kind, t.text) == ("answer", "Elena, Mike and Dana.")


def test_conflicting_proposal_is_returned_with_resolutions(session, firm):
    exemption = {"summary": "Accountants can send tax returns up to $10,000 without approval", "operations": [
        {"op": "set_rule", "key": "acct_exempt", "text": "Accountants can send tax returns up to $10,000 without approval",
         "definition": {"type": "exemption", "role": "accountant", "doc_kind": "tax_return", "max_amount": 10000}}]}
    t = translate(session, firm, "x", client=FakeLLM(tool_call("propose_change", exemption)))
    assert t.preview["conflicts"] and len(t.preview["resolutions"]) == 2


def test_invalid_proposal_gets_one_correction_round(session, firm):
    bad = {"summary": "typo", "operations": [
        {"op": "relate", "subject": "sarha", "relation": "assigned_to", "object": "acme_payroll"}]}
    llm = FakeLLM(tool_call("propose_change", bad, "t1"), tool_call("propose_change", HANDOVER, "t2"))
    assert translate(session, firm, "x", client=llm).kind == "proposal"
    retry = llm.requests[1]["messages"][-1]["content"][0]
    assert retry["tool_use_id"] == "t1" and retry["is_error"] and "sarha" in retry["content"]


def test_ai_cannot_create_documents(session, firm):
    sneaky = {"summary": "x", "operations": [{"op": "add_entity", "key": "fake", "type": "document", "name": "Fake"}]}
    llm = FakeLLM(tool_call("propose_change", sneaky), tool_call("propose_change", sneaky))
    with pytest.raises(TranslationError, match="uploading files"):
        translate(session, firm, "x", client=llm)


def test_schema_violations_are_corrected(session, firm):
    bad = {"summary": "x", "operations": [{"op": "drop_table", "table": "people"}]}
    llm = FakeLLM(tool_call("propose_change", bad), tool_call("propose_change", HANDOVER))
    assert translate(session, firm, "x", client=llm).kind == "proposal"


def test_service_errors_become_friendly_messages(session, firm):
    class Broken:
        class messages:
            @staticmethod
            def create(**_):
                raise ConnectionError("down")
    with pytest.raises(TranslationError, match="didn't respond"):
        translate(session, firm, "x", client=Broken())


def test_tool_schema_is_plain_json_with_required_discriminators():
    schema = TOOLS[0]["input_schema"]
    text = json.dumps(schema)
    assert "$ref" not in text and "discriminator" not in text
    for branch in schema["properties"]["operations"]["items"]["oneOf"]:
        assert branch["required"][0] == "op"
    set_rule = next(b for b in schema["properties"]["operations"]["items"]["oneOf"]
                    if b["properties"]["op"]["const"] == "set_rule")
    for rule in set_rule["properties"]["definition"]["oneOf"]:
        assert rule["required"][0] == "type"


def text_reply(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_plain_text_reply_is_retried_then_used_as_answer(session, firm):
    llm = FakeLLM(text_reply("Sure!"), tool_call("propose_change", HANDOVER))
    assert translate(session, firm, "x", client=llm).kind == "proposal"
    assert "exactly one of the tools" in llm.requests[1]["messages"][-1]["content"]
    llm = FakeLLM(text_reply("Elena and Mike."), text_reply("Elena and Mike."))
    t = translate(session, firm, "Who can see it?", client=llm)
    assert (t.kind, t.text) == ("answer", "Elena and Mike.")

"""Natural language -> ChangeProposal (or a question, or an answer).

The model never touches the database. It must call exactly one tool:
  propose_change     -> a ChangeProposal, validated by Pydantic and dry-run
  ask_clarification  -> a question back to the owner
  answer             -> a reply to a question, grounded in the computed access table
If a proposal fails validation, the error goes back to the model once so it
can correct itself. Nothing is applied here; the owner still confirms.
"""
import json
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.authz import CompanyGraph
from app.changes import ChangeError, preview_proposal
from app.config import settings
from app.rules import KIND_LABELS, describe_rule
from app.schemas import ACTIONS, RELATIONS, AddEntity, ChangeProposal

MAX_ATTEMPTS = 2

SYSTEM_PROMPT = """You are the translation layer of a cloud for small businesses. You turn the \
owner's plain-English statements into structured changes to their company model.

You never change anything yourself. Call exactly one tool:
- propose_change: the owner described a change to how the firm works.
- answer: the owner asked a question. Answer only from <company_model>, using its \
"access" table for who can do what. Be brief and specific.
- ask_clarification: the statement is ambiguous, refers to someone or something that \
doesn't exist and isn't clearly being created, or needs something the vocabulary can't express.

Vocabulary
Relations (subject -> object):
{relations}

Rule types (inside set_rule.definition):
- access: {{role, actions: [read|edit|share|*], scope}}. scope "all" = every document; \
"assigned" = documents of client services the person is assigned to; "own_client" = \
documents of the client the person is a contact for.
- restriction: {{action: read|edit|share|send, roles: [...], doc_kind or null}}. \
"Only X can do Y." Overrides any access grant.
- approval: {{doc_kind, min_amount, approver_role}}. "<kind> over $N need <role> approval \
before they're sent."
- exemption: {{role, doc_kind, max_amount}}. "<role>s can send <kind> up to $N without approval."
Document kinds: {kinds}
Sending a document to its client requires edit access.

Guidelines
- Use existing keys exactly as they appear in the company model. Never guess a key.
- New keys are lowercase snake_case and must not collide with existing ones.
- "Y instead of X", "X is no longer...": unrelate the old fact, relate the new one.
- A role change = unrelate the old member_of, relate the new one.
- Someone leaving the firm = remove_person.
- A new person: add_person, then member_of their role, then any assignments.
- If an assignment needs a client service that doesn't exist (e.g. a client getting a \
new service), add_entity the client_service, then relate it with of_client and \
of_service, then assign.
- To change an existing rule, use set_rule with its existing key (this creates a new version). \
Prefer a new rule key for a genuinely new rule.
- Never create documents: they are added by uploading files.
- Don't try to avoid conflicts with existing rules. Propose what the owner asked for; the \
system detects conflicts and lets the owner choose.
- Keep the summary close to the owner's own words. Use the minimum set of operations."""

ANSWER_TOOL = {
    "name": "answer",
    "description": "Answer the owner's question from the company model. Do not propose changes.",
    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
}
CLARIFY_TOOL = {
    "name": "ask_clarification",
    "description": "Ask the owner one short question when the request can't be translated safely.",
    "input_schema": {"type": "object", "properties": {"question": {"type": "string"}},
                     "required": ["question"]},
}


def _plain_schema(model) -> dict:
    """Inline $refs and drop Pydantic-only keywords so the schema is plain JSON Schema."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            out = {k: resolve(v) for k, v in node.items() if k not in ("discriminator", "title")}
            props = out.get("properties", {})
            consts = [name for name, p in props.items() if isinstance(p, dict) and "const" in p]
            if consts:  # discriminator fields ("op", "type") must always be present
                out["required"] = consts + [r for r in out.get("required", []) if r not in consts]
            return out
        if isinstance(node, list):
            return [resolve(n) for n in node]
        return node

    return resolve(schema)


TOOLS = [
    {"name": "propose_change",
     "description": "Propose a change to the company model. The owner reviews a preview before it applies.",
     "input_schema": _plain_schema(ChangeProposal)},
    ANSWER_TOOL,
    CLARIFY_TOOL,
]


@dataclass
class Translation:
    kind: str                     # "proposal" | "question" | "answer"
    preview: dict | None = None
    text: str | None = None


class TranslationError(RuntimeError):
    pass


def default_client():
    import anthropic  # imported lazily so tests don't need a key
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def model_snapshot(session: Session, org_id: int) -> dict:
    """A compact, JSON-friendly view of the company model for the AI."""
    g = CompanyGraph(session, org_id)
    docs = g.of_type("document")
    return {
        "people": [{"key": p.key, "name": p.name, "title": p.title,
                    "roles": sorted(g.roles_of(p.key))} for p in g.people.values()],
        "entities": [{"key": e.key, "type": e.type, "name": e.name}
                     for e in g.entities.values() if e.type != "document"],
        "documents": [{"key": d.key, "name": d.name, "kind": g.doc_kind(d.key),
                       "amount": g.doc_amount(d.key), "client_service": g.doc_client_service(d.key)}
                      for d in docs],
        "relationships": [[s, rel, o] for (s, rel), objs in sorted(g.out.items())
                          for o in sorted(objs) if rel != "belongs_to"],
        "rules": [{"key": k, "meaning": describe_rule(r, g.names), "definition": r.model_dump()}
                  for k, r in g.rules.items()],
        "access": {d.key: {a: sorted(p for p in g.people if g.check(p, a, d.key).allowed)
                           for a in ACTIONS} for d in docs},
    }


def _system() -> str:
    relations = "\n".join(f"- {rel}: {'/'.join(sorted(s))} -> {'/'.join(sorted(o))}"
                          for rel, (s, o) in RELATIONS.items())
    return SYSTEM_PROMPT.format(relations=relations, kinds=", ".join(KIND_LABELS))


def translate(session: Session, org_id: int, text: str, client=None) -> Translation:
    client = client or default_client()
    snapshot = json.dumps(model_snapshot(session, org_id), separators=(",", ":"))
    messages = [{
        "role": "user",
        "content": f"<company_model>\n{snapshot}\n</company_model>\n\nOwner says: {text}",
    }]

    last_error = None
    for _ in range(MAX_ATTEMPTS):
        try:
            response = client.messages.create(
                model=settings.model, max_tokens=4000, system=_system(), tools=TOOLS,
                tool_choice={"type": "any"}, messages=messages,
            )
        except Exception as e:  # network, auth, rate limits
            raise TranslationError(f"The AI service didn't respond ({type(e).__name__}). Try again.") from e
        call = next((b for b in response.content if b.type == "tool_use"), None)
        if call is None:
            raise TranslationError("The AI didn't return a usable answer. Try rephrasing.")

        if call.name == "ask_clarification":
            return Translation(kind="question", text=str(call.input.get("question", "")))
        if call.name == "answer":
            return Translation(kind="answer", text=str(call.input.get("text", "")))

        try:
            proposal = ChangeProposal.model_validate(call.input)
            if any(isinstance(o, AddEntity) and o.type == "document" for o in proposal.operations):
                raise ChangeError("documents can't be created here; they are added by uploading files")
            preview = preview_proposal(session, org_id, proposal)
            return Translation(kind="proposal", preview=preview)
        except (ValidationError, ChangeError) as e:
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": call.id, "is_error": True,
                    "content": f"That proposal was rejected: {last_error}. "
                               f"Fix it, or ask a clarifying question.",
                }]},
            ]
    raise TranslationError(f"I couldn't turn that into a valid change. {last_error}")

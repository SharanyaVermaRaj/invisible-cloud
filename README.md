# Invisible Cloud — V0 core

Describe how your business works; the software follows.

This is week 1: the **company model**, the **change pipeline**, and the
**permission engine**. No AI yet. That's deliberate: the AI layer will only be
allowed to produce `ChangeProposal`s, so this core has to be correct first.

## Run it

```bash
pip install -r requirements.txt
python demo.py              # the Sarah/Mike story in the terminal
pytest -q                   # 33 tests
uvicorn app.main:app --reload   # API docs at http://127.0.0.1:8000/docs

export ANTHROPIC_API_KEY=sk-ant-...   # needed only for the AI layer
python chat.py              # talk to the company in plain English
```

## How it fits together

| File | Job |
|------|-----|
| `app/models.py` | The company model: people, entities, relationship tuples, versioned rules, change log |
| `app/schemas.py` | The fixed vocabulary: entity types, relations, rule types, operations |
| `app/changes.py` | The only way the model changes: validate → apply → diff → preview or commit |
| `app/authz.py` | `can(person, action, resource)`, the single enforcement point |
| `app/main.py` | FastAPI endpoints |
| `app/seed.py` | The demo accounting firm |
| `app/translator.py` | Plain English → `ChangeProposal` via Claude tool use, with one self-correction round |
| `chat.py` | Interactive terminal: type a statement, see the preview, confirm |

## Principles

1. Nothing edits tables directly. Every change is a `ChangeProposal`.
2. Every proposal is all-or-nothing and logged in `changes`.
3. Every proposal can be previewed: you see who gains and loses access before it applies.
4. Rules are typed (`access` with scope `all` / `assigned` / `own_client`), never free-form.
5. Apps only ever call `can()`.

## Next

- Week 2: document vault + tracker modules calling `can()`; Google login
- ~~Week 3: natural language → `ChangeProposal`~~ done (`/ask`, `chat.py`); web confirm UI still to do
- Week 4: approval rules, conflict detection, timeline + undo

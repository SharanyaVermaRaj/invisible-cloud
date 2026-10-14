# Invisible Cloud

**Describe how your business works in plain English. Your software follows.**

A cloud for small firms where the business itself is the source of truth. The owner says
what changed ("Mike is no longer handling Acme's payroll. Sarah will handle it."), sees
exactly who gains and loses access to which documents, and confirms. Files, permissions and
approvals update everywhere at once. Conflicting rules are caught before they apply, and
every change can be undone.

The live demo gives each visitor a private copy of a fictional accounting firm,
Parkside Accounting, with real stored documents.

## What's in the prototype

- **Plain-English changes.** New hires, reassignments, promotions, people leaving, new rules,
  and questions like "Who can see Acme's W-2?"
- **Preview before anything happens.** Every change shows the exact access gained and lost.
- **A real document vault.** Files are stored and every open, send and upload is checked by
  the firm's rules.
- **Approvals.** "Tax returns over $5,000 need partner approval" actually holds sends for sign-off.
- **Conflict detection.** Contradictory rules are flagged, with concrete ways to resolve them.
- **History and undo.** Every change is versioned. Undo any of them, like `git revert`.
- **View as anyone.** Switch persona to see the firm through an accountant's or client's eyes.

## Run it on your computer

You need Python 3.11+. Node.js 20+ is only needed if you change the frontend.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # then paste your ANTHROPIC_API_KEY into .env
uvicorn app.main:app --reload      # .env is loaded automatically
```

Open http://127.0.0.1:8000. The built website is already included in `app/static`.

To work on the frontend with live reload, run the server as above, then in a second terminal:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, talks to the Python server
npm run build      # writes the production site into app/static
```

## Tests

```bash
pytest -q                                   # 99 tests, in-memory SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_db pytest -q   # against Postgres
```

The AI layer is tested with a scripted stand-in, so tests never need an API key or cost money.

## Deploying

See [docs/DEPLOY.md](docs/DEPLOY.md) for putting it on your own domain (about 30 minutes).

## How it works

See [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) for the architecture and a guided tour of
every file.

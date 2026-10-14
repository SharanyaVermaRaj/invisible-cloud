# How Invisible Cloud works

This is the guide to read before talking to anyone about the product. It explains every
moving part in plain words, so you can answer "how does it actually work?" from memory.

## The idea in one paragraph

Every business has a model of itself in people's heads: who works there, what role they
have, which clients they handle, and the rules about who can see and do what. Invisible Cloud
stores that model explicitly, as data, and makes it the **single source of truth**. Documents,
permissions and approvals are never configured directly. They are always *computed* from the
model. The owner changes the model by describing changes in plain English. An AI translates
the sentence into a proposed change, but a deterministic system validates it, checks it for
conflicts, previews its effect, and applies it only after the owner confirms.

## What happens when someone types a sentence

```text
"Mike is no longer handling Acme's payroll. Sarah will handle it."
        │
        ▼
1. Translator (app/translator.py)
   Sends Claude the sentence plus a snapshot of the company model.
   Claude must answer with exactly one tool call:
     propose_change   → a ChangeProposal using our fixed vocabulary
     answer           → a reply to a question
     ask_clarification→ a question back to the owner
        │
        ▼
2. Validation (app/schemas.py, app/changes.py)
   The proposal must match the schema (unknown operations are rejected outright),
   then every step is checked: do these people exist? is this relationship allowed?
   If it fails, the error goes back to Claude once so it can fix its own mistake.
        │
        ▼
3. Dry run (app/changes.py → preview_proposal)
   The change is applied inside a database transaction, the access of every person to
   every document is computed before and after, rule conflicts are checked, and then the
   transaction is rolled back. Nothing is saved.
        │
        ▼
4. Preview (frontend)
   "Unassign Mike from Acme – Payroll / Assign Sarah to Acme – Payroll"
   "Sarah gains: Acme W-2, Acme payroll report. Mike loses: the same."
        │
        ▼
5. Confirm → apply_proposal
   The same steps run again for real, the change is committed, and it's written to the
   change log together with its inverse (the steps that would undo it).
```

The AI never writes to the database, never generates code, and never decides who can see
what. It only suggests a structured change. That is the answer to "what if the AI hallucinates?"

## The company model

Stored in Postgres (see `app/models.py`):

| Table | What it holds | Example |
| --- | --- | --- |
| `people` | Everyone at the firm, including client contacts | Sarah Chen |
| `entities` | Roles, clients, services, client services, documents | Acme – Payroll |
| `relationships` | Facts of the form *subject, relation, object* | sarah, assigned_to, acme_payroll |
| `rules` | Typed business rules, versioned | Accountants can read and edit assigned documents |
| `changes` | Every change ever applied, with its inverse | "Mike is no longer handling…" |
| `file_blobs` | The actual uploaded files | Acme W-2 Summary.pdf |
| `deliveries` | Requests to send documents to clients, and approvals | John → Acme tax return, pending |

The relationship format (subject, relation, object) is the same idea Google uses for
permissions across Drive, Calendar and YouTube, described in its "Zanzibar" paper. Open-source
engines like OpenFGA use the same format, so this can move to a dedicated permission engine
later without changing the data.

## The rules

There are four rule types (`app/schemas.py`). Keeping them typed instead of free text is what
makes the system checkable:

- **Access:** "Accountants can read and edit documents for client services they're assigned to."
  Scope is one of: every document, assigned client services, or their own company (for clients).
- **Restriction:** "Only partners can share documents." Overrides any access rule.
- **Approval:** "Tax returns over $5,000 need partner approval before they're sent."
- **Exemption:** "Accountants can send tax returns up to $3,000 without approval."

Sending a document requires edit access, plus passing any approval rule.

## Deciding who can do what

`app/authz.py` holds the one function every part of the app asks: *can this person do this
action on this document?* It loads the firm's model, then:

1. Finds an access rule that applies to one of the person's roles and covers the document.
2. Checks no restriction blocks it.
3. Returns the answer **and the reason**, like "Allowed by: Accountants can read and edit
   documents for the client services they're assigned to (assigned to Acme – Payroll)."

The document list, file downloads, the access map, approvals and the previews all use this same
function. There is no second place where permissions live, so they can't drift apart.

## Conflict detection

`app/rules.py` compares rules pairwise. Two contradictions are detected today:

- An access rule grants an action that a restriction forbids for that role.
- An exemption lets a role skip approval above an approval rule's threshold.

For each conflict it builds two resolutions, each one a normal, typed rule edit (for example
"adjust your new rule: cap the exemption at $5,000" or "change the existing rule: raise the
approval threshold to $10,000"), and dry-runs both so the owner sees their exact effect before
choosing. A conflicting change can't be applied until it's resolved.

Two more guardrails: the firm can never be left without a partner (so nobody can lock
themselves out), and a document with no amount is treated as needing approval when an
approval rule covers its kind.

## Undo

When a change is applied, each step records its own inverse: assigning becomes unassigning,
adding a person becomes removing them, removing a person restores them *and all their
relationships*, editing a rule restores the previous version. Undo applies the inverse as a new
change, so history is never rewritten. If later changes make an undo impossible (for example,
the assignment it would remove is already gone), it says so instead of guessing.

## Demo workspaces

Each visitor gets their own copy of Parkside Accounting (`app/workspaces.py`). The browser
holds a signed cookie that points at the visitor's workspace, so nobody can see or change
anyone else's. Workspaces are deleted after 7 days. The "Viewing as" switch lets a visitor see
the firm as any person, which is how the demo shows rules being enforced. In a real product
that switch would be replaced by each person signing in.

## A tour of the files

```text
app/
  main.py         Web server: the API under /api and the built website for everything else
  api.py          Every API endpoint, each scoped to the visitor's workspace
  config.py       Settings read from environment variables
  db.py           Database connection (SQLite locally, Postgres in production)
  models.py       Database tables (the company model)
  schemas.py      The fixed vocabulary: relations, rule types, operations
  rules.py        Plain-English rule descriptions and conflict detection
  authz.py        The single permission check, with reasons
  changes.py      Validate, dry-run, apply, undo. The only code that changes the model
  translator.py   Sentence → structured proposal, using Claude with tool calls
  documents.py    Uploads, downloads, sending and approvals
  state.py        Everything one screen of the web app needs
  workspaces.py   Per-visitor demo firms and cleanup
  seed.py         The demo firm, its rules and suggested sentences
  seed_files/     The sample PDFs (fictional)
  static/         The built website (generated by `npm run build`)
frontend/src/
  landing/        Landing page and the self-playing access map
  app/            The demo: Ask, Documents, Access map, People, Rules, History, Approvals
  api.ts          Typed calls to the Python API
  ui.tsx          Shared pieces: icons, avatars, the access diff, notifications
  styles.css      The whole visual design
tests/            99 tests covering scenarios, conflicts, undo, documents, the AI layer and the API
```

## Design choices worth being able to explain

**Why not let the AI write code or configuration?** Because a small firm can't review
Terraform or SQL. A fixed vocabulary means every possible change is one we built and tested,
and the preview means the owner checks the effect, not the mechanism.

**Why compute access instead of storing it?** Stored permissions drift: someone forgets to
remove one. Computing access from the model every time means "Mike left" removes everything
Mike could reach, with nothing to forget.

**Why build on Postgres and existing hosting instead of our own servers?** Same reason Vercel
and Supabase do: the value is the layer on top. Customers never see the infrastructure.

**What's real and what's demo?** Real: the model, rules, permission checks, conflict detection,
undo, file storage, approvals, the AI translation and its validation. Demo-only: the persona
switch instead of sign-in, and fictional sample data.

## Questions you might be asked

- *"What stops the AI from doing something dangerous?"* It can only emit operations from a
  fixed list, every proposal is validated and previewed, and nothing applies without the
  owner's confirmation. An unknown operation is rejected by the schema before any code runs.
- *"What if the AI misunderstands?"* The owner sees the plain-English steps and exact access
  changes before confirming, and can undo afterwards.
- *"How does this connect to tools firms already use?"* Today the vault is built in. Next is
  syncing the same model to Google Drive or Microsoft 365 sharing, so one sentence updates
  permissions there too.
- *"How is this different from practice-management software?"* Those tools have their own
  permission screens. Here, permissions aren't configured at all; they're computed from a
  description of the business, conflicts are caught, and every change is reversible.
- *"How does it scale?"* Per-request computation is fast for firms of 5–50 people. Beyond
  that, the relationship data moves to a dedicated permission engine like OpenFGA, which
  uses the same format.

## What to build next

1. Sign-in with Google, replacing the persona switch.
2. Sync to Google Drive sharing, so the model controls permissions in a tool firms already use.
3. More rule types: time-limited access, client-portal visibility.
4. A firm onboarding flow: describe your firm in a paragraph and get a starting model.

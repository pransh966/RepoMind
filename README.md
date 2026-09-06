# RepoMind — a codebase-aware RAG assistant

Ask questions about a codebase and get answers grounded in the actual source,
with citations to the exact file and line range they came from.

## v2: accounts, multiple repos, history, separate frontend

This version adds:
- **Accounts** -- register/login with email+password (JWT-based), each user's
  repos and history are private to them (`app/auth.py`, `app/db.py`).
- **Connect a repo two ways**: a public git URL (server-side `git clone
  --depth 1`) or uploading a `.zip`. Each connected repo gets its own FAISS
  index under `data/repos/<repo_id>/`.
- **Query history**, persisted per user per repo in **PostgreSQL**, with
  per-question delete and per-repo "clear all" (`DELETE /history/{id}`,
  `DELETE /history?repo_id=`).
- **A separate frontend** (`frontend/`) -- plain HTML/CSS/JS, no build step,
  served independently from the API and talking to it over `fetch()`.

### Extra setup requirements for v2
- **PostgreSQL must be installed and running.** Create a database once:
  `psql -U postgres -c "CREATE DATABASE repomind;"`, then set `DATABASE_URL`
  in `.env` (see `.env.example`).
- **`git` must be installed and on PATH** on the machine running the backend
  -- it's what powers "connect via git URL". Check with `git --version`;
  install from git-scm.com if missing. Zip upload doesn't need this.
- New Python deps: `PyJWT`, `python-multipart`, `psycopg2-binary` -- already
  added to `requirements.txt`.
- **Set a real `JWT_SECRET` in `.env`** before using this beyond your own
  laptop -- the shipped default is for local dev only. Any random long
  string works, e.g. generate one with `python -c "import secrets;
  print(secrets.token_hex(32))"`.

### Running it (two processes: backend + frontend)
```bash
# Terminal 1 -- backend API
pip install -r requirements.txt
uvicorn app.main:app --reload           # http://127.0.0.1:8000

# Terminal 2 -- frontend (any static file server works)
cd frontend
python -m http.server 5500              # http://127.0.0.1:5500
```
Open `http://127.0.0.1:5500`, create an account, connect a repo (git URL or
zip upload), and start asking questions. If your backend runs somewhere
other than `127.0.0.1:8000`, update `API_BASE` at the top of
`frontend/app.js`.

### v2 API summary
```
POST   /auth/register   { email, password }          -> { token, user }
POST   /auth/login      { email, password }          -> { token, user }
GET    /auth/me                                        (needs Bearer token)

POST   /repos/git       { git_url, name? }            (needs Bearer token)
POST   /repos/upload    multipart file=<zip>          (needs Bearer token)
GET    /repos                                          (needs Bearer token)
DELETE /repos/{repo_id}                                (needs Bearer token)

POST   /query           { repo_id, question, top_k? } (needs Bearer token)
GET    /history?repo_id=<optional>                     (needs Bearer token)
DELETE /history/{history_id}                           (needs Bearer token)
DELETE /history?repo_id=<required>   -- clears all history for one repo
```
The old single-repo `scripts/ingest_cli.py` still works standalone for quick
local testing, but it's not wired into the accounts/history system -- use
the API endpoints above for the full experience.

---

## The original single-user version (still true of the core RAG pipeline)

```
repo files --> AST-aware chunking --> local embeddings --> FAISS index
                                                                 |
user question --> embed --> retrieve top-k --> LLM (grounded prompt) --> answer + citations
```

## Why this isn't just another "chat with your docs" tutorial

1. **AST-aware chunking, not fixed-size windows.** Most RAG tutorials split
   text every N characters, which routinely cuts a function in half mid-body.
   `app/chunking.py` parses Python with the `ast` module and chunks at
   function/class boundaries, so retrieval returns whole, coherent units of
   code. Non-Python files fall back to a line-based sliding window with
   overlap (still structure-aware, not character-count-blind).
2. **Grounded answers, not just retrieval.** The system prompt in `app/llm.py`

   explicitly instructs the model to answer only from retrieved context and
   say so when it can't — the actual mechanism that reduces hallucination,
   not just a claim.
3. **Local embeddings, pluggable generation.** Embedding runs locally via
   `sentence-transformers` — free, fast, works offline. Only the final
   answer-generation call needs a paid API key, and that provider is
   swappable (OpenAI / Anthropic / a zero-key mock for local dev and tests).
4. **A real (if simple) rate limiter**, not a claimed one — see
   `rate_limit_middleware` in `app/main.py`.

## Quickstart

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # defaults to LLM_PROVIDER=mock, no key needed

uvicorn app.main:app --reload
```

Open **http://localhost:8000** — you'll get a minimal chat UI (no build step,
plain HTML/JS in `static/index.html`).

Index a repo either from the UI's flow via the API, or from the CLI:

```bash
python scripts/ingest_cli.py --repo /path/to/some/repo
```

Then ask a question:

```bash
curl -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How does authentication work in this codebase?"}'
```

To use a real LLM instead of the mock provider, set in `.env`:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

## Running with Docker

```bash
docker compose up --build
```

## Tests

```bash
pytest -v
```

Tests use a tiny deterministic fake embedding function instead of loading the
real model — keeps the suite fast and runnable with no network access, since
the tests are checking control flow (ingest → store → retrieve → answer), not
embedding quality.

## Project layout

```
app/
  main.py         FastAPI app: /ingest, /query, /health, rate limiting
  chunking.py     AST-aware Python chunking + fallback text chunking
  embeddings.py   Local sentence-transformers wrapper
  vector_store.py FAISS flat index + JSON metadata, save/load
  llm.py          Pluggable LLM client (OpenAI / Anthropic / mock) + grounded prompt
  ingest.py       Orchestrates the ingestion pipeline
  config.py       Typed settings from .env
  models.py       Pydantic request/response schemas
scripts/
  ingest_cli.py   Ingest a repo without running the API server
static/
  index.html      No-build-step chat UI
tests/
  test_chunking.py, test_vector_store.py, test_api.py
```

## Honest limitations / what I'd do next

Worth being upfront about these — they're good interview material, not
embarrassing gaps:

- **Flat FAISS index** (`IndexFlatIP`) does exact brute-force search. Correct
  choice for a single repo's worth of chunks; would swap to `IndexHNSWFlat`
  or `IndexIVFFlat` if this needed to scale to many large repos or many
  concurrent users.
- **Single-process in-memory state.** The vector store and rate limiter live
  in one process's memory. Running multiple workers/replicas would need the
  store behind a shared service and the rate limiter backed by Redis.
- **No chunk deduplication** across repeated re-ingestion — re-running
  `/ingest` on the same repo currently appends rather than replacing.
- **No streaming responses.** The LLM call is synchronous; a real product
  would stream tokens back to the UI.

## Suggested resume bullet (fill in your own measured numbers — don't reuse
## these placeholders as-is)

> Built a retrieval-augmented codebase Q&A system with AST-aware chunking and
> citation-grounded answers, reducing [measure: hallucinated/unsupported
> claims] by indexing a [N]-file repository into a FAISS vector store with
> local embeddings; served via FastAPI with a token-bucket rate limiter,
> p95 query latency [X]ms.

Only ship the bracketed numbers once you've actually measured them on a real
repo — that's the difference between a defensible resume line and one that
falls apart in the first follow-up question.

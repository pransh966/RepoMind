from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import jwt as pyjwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import db
from app.auth import create_token, decode_token, hash_password, verify_password
from app.config import settings
from app.embeddings import embed_texts
from app.ingest import clone_git_repo, extract_zip_upload, ingest_repository
from app.llm import get_llm_client
from app.models import (
    Citation, GitIngestRequest, HistoryItem, LoginRequest, QueryRequest, QueryResponse,
    RegisterRequest, RepoOut, TokenResponse, UserOut,
)
from app.vector_store import VectorStore

REPOS_DIR = Path(settings.data_dir) / "repos"

_store_cache: dict[int, VectorStore] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("[startup] Database ready.")
    yield


app = FastAPI(title="RepoMind", description="Codebase-aware RAG assistant", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_request_log: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = settings.rate_limit_window_seconds
    log = _request_log[client_ip]

    while log and now - log[0] > window:
        log.popleft()

    if len(log) >= settings.rate_limit_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")

    log.append(now)
    return await call_next(request)


_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> dict:
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing bearer token. Log in first.")
    try:
        payload = decode_token(creds.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Log in again.")
    row = db.get_user_by_id(int(payload["sub"]))
    if row is None:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return dict(row)


def _repo_dir(repo_id: int) -> Path:
    return REPOS_DIR / str(repo_id)


def _get_store(repo_id: int) -> VectorStore:
    if repo_id not in _store_cache:
        try:
            _store_cache[repo_id] = VectorStore.load(_repo_dir(repo_id))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="This repo's index could not be found on disk.")
    return _store_cache[repo_id]


def _row_to_repo_out(row) -> RepoOut:
    return RepoOut(
        id=row["id"], name=row["name"], source=row["source"], source_ref=row["source_ref"],
        chunks_count=row["chunks_count"], created_at=row["created_at"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest):
    if db.get_user_by_email(req.email) is not None:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    password_hash, salt = hash_password(req.password)
    user_id = db.create_user(req.email, password_hash, salt)
    token = create_token(user_id, req.email)
    return TokenResponse(token=token, user=UserOut(id=user_id, email=req.email))


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    row = db.get_user_by_email(req.email)
    if row is None or not verify_password(req.password, row["password_hash"], row["salt"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_token(row["id"], row["email"])
    return TokenResponse(token=token, user=UserOut(id=row["id"], email=row["email"]))


@app.get("/auth/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], email=user["email"])


@app.post("/repos/git", response_model=RepoOut)
def create_repo_from_git(req: GitIngestRequest, user: dict = Depends(get_current_user)):
    name = req.name or req.git_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    repo_id = db.create_repo(user["id"], name=name, source="git", source_ref=req.git_url)

    try:
        clone_dir = clone_git_repo(req.git_url)
    except ValueError as e:
        db.delete_repo(repo_id)
        raise HTTPException(status_code=422, detail=str(e))

    try:
        store, stats = ingest_repository(str(clone_dir))
        if stats["chunks_created"] == 0:
            raise ValueError("No indexable files were found in that repository.")
        store.save(_repo_dir(repo_id))
        db.update_repo_chunks(repo_id, stats["chunks_created"])
    except Exception as e:
        db.delete_repo(repo_id)
        shutil.rmtree(_repo_dir(repo_id), ignore_errors=True)
        detail = str(e) if isinstance(e, ValueError) else f"Ingestion failed: {e}"
        raise HTTPException(status_code=422, detail=detail)
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)

    return _row_to_repo_out(db.get_repo(repo_id, user["id"]))


@app.post("/repos/upload", response_model=RepoOut)
async def create_repo_from_upload(
    file: UploadFile = File(...), name: str | None = Form(None), user: dict = Depends(get_current_user)
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Only .zip uploads are supported.")

    content = await file.read()
    repo_name = name or file.filename[:-4]
    repo_id = db.create_repo(user["id"], name=repo_name, source="upload", source_ref=file.filename)

    try:
        extract_root, tmp_dir = extract_zip_upload(content)
    except ValueError as e:
        db.delete_repo(repo_id)
        raise HTTPException(status_code=422, detail=str(e))

    try:
        store, stats = ingest_repository(str(extract_root))
        if stats["chunks_created"] == 0:
            raise ValueError("No indexable files were found in that zip.")
        store.save(_repo_dir(repo_id))
        db.update_repo_chunks(repo_id, stats["chunks_created"])
    except Exception as e:
        db.delete_repo(repo_id)
        shutil.rmtree(_repo_dir(repo_id), ignore_errors=True)
        detail = str(e) if isinstance(e, ValueError) else f"Ingestion failed: {e}"
        raise HTTPException(status_code=422, detail=detail)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return _row_to_repo_out(db.get_repo(repo_id, user["id"]))


@app.get("/repos", response_model=list[RepoOut])
def list_repos(user: dict = Depends(get_current_user)):
    return [_row_to_repo_out(r) for r in db.list_repos(user["id"])]


@app.delete("/repos/{repo_id}")
def delete_repo(repo_id: int, user: dict = Depends(get_current_user)):
    row = db.get_repo(repo_id, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="Repo not found.")
    shutil.rmtree(_repo_dir(repo_id), ignore_errors=True)
    db.delete_repo(repo_id)
    _store_cache.pop(repo_id, None)
    return {"deleted": True}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, user: dict = Depends(get_current_user)):
    repo_row = db.get_repo(req.repo_id, user["id"])
    if repo_row is None:
        raise HTTPException(status_code=404, detail="Repo not found.")

    store = _get_store(req.repo_id)
    if store.size == 0:
        raise HTTPException(status_code=400, detail="This repo's index is empty.")

    start = time.perf_counter()
    top_k = req.top_k or settings.top_k

    query_vector = embed_texts([req.question])[0]
    results = store.search(query_vector, top_k)
    chunks = [c for c, _ in results]

    client = get_llm_client(
        settings.llm_provider,
        settings.openai_api_key, settings.openai_model,
        settings.anthropic_api_key, settings.anthropic_model,
        settings.groq_api_key, settings.groq_model,
    )
    answer = client.generate(req.question, chunks)

    citations = [
        Citation(file=c.file, start_line=c.start_line, end_line=c.end_line,
                 snippet=c.text[:300], score=round(score, 4))
        for c, score in results
    ]
    latency_ms = round((time.perf_counter() - start) * 1000, 1)

    db.add_history(
        user["id"], req.repo_id, req.question, answer,
        json.dumps([c.model_dump() for c in citations]), latency_ms,
    )

    return QueryResponse(answer=answer, citations=citations, latency_ms=latency_ms,
                          chunks_considered=len(chunks))


@app.get("/history", response_model=list[HistoryItem])
def get_history(repo_id: int | None = None, user: dict = Depends(get_current_user)):
    rows = db.list_history(user["id"], repo_id)
    items = []
    for r in rows:
        items.append(HistoryItem(
            id=r["id"], repo_id=r["repo_id"], question=r["question"], answer=r["answer"],
            citations=json.loads(r["citations"]), latency_ms=r["latency_ms"], created_at=r["created_at"],
        ))
    return items


@app.delete("/history/{history_id}")
def delete_history_item(history_id: int, user: dict = Depends(get_current_user)):
    deleted = db.delete_history_item(history_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="History item not found.")
    return {"deleted": True}


@app.delete("/history")
def clear_history(repo_id: int, user: dict = Depends(get_current_user)):
    repo_row = db.get_repo(repo_id, user["id"])
    if repo_row is None:
        raise HTTPException(status_code=404, detail="Repo not found.")
    count = db.clear_history(user["id"], repo_id)
    return {"deleted": count}

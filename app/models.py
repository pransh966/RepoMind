"""Request/response schemas shared across the API."""
from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    repo_path: str = Field(..., description="Absolute or relative path to a local repo/folder to index")
    include_extensions: list[str] | None = Field(
        default=None,
        description="File extensions to include, e.g. ['.py', '.md']. Defaults to a sensible code+docs set.",
    )


class IngestResponse(BaseModel):
    files_scanned: int
    files_ingested: int
    chunks_created: int
    skipped_files: list[str]


class QueryRequest(BaseModel):
    repo_id: int
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    file: str
    start_line: int
    end_line: int
    snippet: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    latency_ms: float
    chunks_considered: int


# --- Auth --------------------------------------------------------------

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str


class UserOut(BaseModel):
    id: int
    email: str


class TokenResponse(BaseModel):
    token: str
    user: UserOut


# --- Repos --------------------------------------------------------------

class GitIngestRequest(BaseModel):
    git_url: str = Field(..., min_length=1)
    name: str | None = None


class RepoOut(BaseModel):
    id: int
    name: str
    source: str
    source_ref: str | None
    chunks_count: int
    created_at: str


# --- History --------------------------------------------------------------

class HistoryItem(BaseModel):
    id: int
    repo_id: int
    question: str
    answer: str
    citations: list[Citation]
    latency_ms: float | None
    created_at: str

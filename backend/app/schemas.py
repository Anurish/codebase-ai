from typing import List

from pydantic import BaseModel, Field

from .config import DEFAULT_REPOSITORY_ID


class ChatRequest(BaseModel):
    question: str
    repository: str = Field(
        default=DEFAULT_REPOSITORY_ID,
        min_length=1,
        max_length=512,
    )


class Source(BaseModel):
    file: str
    path: str
    lines: str
    score: str
    content: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]


class IndexResponse(BaseModel):
    files: int
    chunks: int
    repository: str = DEFAULT_REPOSITORY_ID
    name: str = DEFAULT_REPOSITORY_ID
    github_url: str | None = None
    branch: str | None = None


class GitHubIndexRequest(BaseModel):
    github_url: str = Field(min_length=1, max_length=2048)
    branch: str = Field(default="main", min_length=1, max_length=255)


class RepositoryInfo(BaseModel):
    repository: str
    name: str
    github_url: str | None = None
    branch: str | None = None
    files: int
    chunks: int


class ReviewFinding(BaseModel):
    category: str
    severity: str
    title: str
    explanation: str
    file: str
    lines: str
    evidence: str
    recommended_fix: str
    confidence: str
    potential: bool = False


class ReviewSummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    informational: int = 0
    potential: int = 0


class ReviewResponse(BaseModel):
    findings: List[ReviewFinding]
    summary: ReviewSummary
    overall_review: str
    sources: List[Source]
    reviewed_chunks: int


class HealthComponent(BaseModel):
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str
    repository: HealthComponent
    database: HealthComponent
    pgvector: HealthComponent
    gemini: HealthComponent
    indexed_files: int
    indexed_chunks: int
    repository_root: str
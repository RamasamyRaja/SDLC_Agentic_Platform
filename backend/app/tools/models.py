"""
Typed input/output models for every tool. Every tool input is validated
via one of these Pydantic models before a tool function ever runs — no
tool accepts a raw dict.
"""
import uuid

from pydantic import BaseModel, Field, field_validator


# ============================================================
# read_file
# ============================================================


class ReadFileInput(BaseModel):
    repository_id: uuid.UUID
    file_path: str = Field(..., min_length=1, max_length=1024)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @field_validator("end_line")
    @classmethod
    def end_line_not_before_start(cls, value: int | None, info) -> int | None:
        start = info.data.get("start_line")
        if value is not None and start is not None and value < start:
            raise ValueError("end_line must be >= start_line")
        return value


class ReadFileOutput(BaseModel):
    path: str
    start_line: int
    end_line: int
    content: str
    truncated: bool
    total_lines: int


# ============================================================
# search_code
# ============================================================


class SearchCodeInput(BaseModel):
    repository_id: uuid.UUID
    query: str = Field(..., min_length=1, max_length=500)
    file_pattern: str | None = Field(default=None, max_length=255)
    max_results: int | None = Field(default=None, ge=1, le=200)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class SearchMatch(BaseModel):
    file: str
    line: int
    text: str


class SearchCodeOutput(BaseModel):
    matches: list[SearchMatch] = Field(default_factory=list)
    truncated: bool


# ============================================================
# repository_structure
# ============================================================


class RepositoryStructureInput(BaseModel):
    repository_id: uuid.UUID
    max_depth: int | None = Field(default=None, ge=1, le=20)
    max_entries: int | None = Field(default=None, ge=1, le=2000)


class TreeEntry(BaseModel):
    path: str
    type: str  # "file" | "dir"


class RepositoryStructureOutput(BaseModel):
    entries: list[TreeEntry] = Field(default_factory=list)
    truncated: bool


# ============================================================
# modify_file
# ============================================================


class ModifyFileInput(BaseModel):
    repository_id: uuid.UUID
    file_path: str = Field(..., min_length=1, max_length=1024)
    old_content: str = Field(..., min_length=1)
    new_content: str

    @field_validator("old_content")
    @classmethod
    def old_content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("old_content must not be blank")
        return value


class ModifyFileOutput(BaseModel):
    path: str
    success: bool
    bytes_changed: int
    message: str


# ============================================================
# git_diff
# ============================================================


class GitDiffInput(BaseModel):
    repository_id: uuid.UUID


class GitDiffOutput(BaseModel):
    files_changed: list[str] = Field(default_factory=list)
    additions: int
    deletions: int
    diff_text: str
    summary: str
    truncated: bool

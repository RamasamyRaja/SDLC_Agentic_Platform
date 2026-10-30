"""
Typed schemas for the reasoning layer's input contract and structured
output contract. These are plain Pydantic models (not DB models, not API
schemas) — the input contract is what context_builder.py produces and
prompts.py serializes into the user prompt; the output contract is what
Mistral's response must validate against.
"""
from pydantic import BaseModel, Field, field_validator

PROMPT_VERSION = "v1"


# ============================================================
# Input contract (context sent TO the model)
# ============================================================


class TaskContext(BaseModel):
    id: str
    title: str | None
    description: str


class RepositoryContext(BaseModel):
    id: str
    languages: list[str] = Field(default_factory=list)


class StructuralSymbol(BaseModel):
    """One entry from the repository's structural knowledge (Milestone 3,
    via the Milestone 4 CodeChunk index — see context_builder.py for why)."""

    file_path: str
    symbol_name: str | None
    chunk_type: str
    language: str | None


class RetrievedChunk(BaseModel):
    """One semantically-retrieved chunk (Milestone 4)."""

    file_path: str
    symbol_name: str | None
    language: str | None
    content: str
    score: float


class ReasoningInput(BaseModel):
    """The complete, bounded context sent to Mistral for one analysis."""

    task: TaskContext
    repository: RepositoryContext
    structural_context: list[StructuralSymbol] = Field(default_factory=list)
    retrieved_context: list[RetrievedChunk] = Field(default_factory=list)


# ============================================================
# Output contract (structured result FROM the model)
# ============================================================


class Understanding(BaseModel):
    goal: str
    affected_area: str


class RelevantFile(BaseModel):
    file_path: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    # Set by grounding (app/llm/grounding.py) AFTER the model responds —
    # never populated by the model itself. True if `file_path` actually
    # appears in the supplied context; False flags a likely hallucination.
    grounded: bool | None = None


class AffectedSymbol(BaseModel):
    file_path: str
    symbol_name: str
    reason: str
    grounded: bool | None = None  # see RelevantFile.grounded


class ImplementationStep(BaseModel):
    step: int = Field(ge=1)
    description: str
    target_files: list[str] = Field(default_factory=list)


class ReasoningResult(BaseModel):
    summary: str
    understanding: Understanding
    relevant_files: list[RelevantFile] = Field(default_factory=list)
    affected_symbols: list[AffectedSymbol] = Field(default_factory=list)
    implementation_plan: list[ImplementationStep] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    # MODEL-REPORTED confidence — never treated as a verified probability
    # by the application. See README "Milestone 5" / grounding.py.
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary must not be empty")
        return value

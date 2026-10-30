from app.llm.grounding import ground_result
from app.llm.schemas import (
    AffectedSymbol,
    ReasoningInput,
    ReasoningResult,
    RelevantFile,
    RepositoryContext,
    RetrievedChunk,
    StructuralSymbol,
    TaskContext,
    Understanding,
)


def _context() -> ReasoningInput:
    return ReasoningInput(
        task=TaskContext(id="t1", title="t", description="d"),
        repository=RepositoryContext(id="r1", languages=["python"]),
        structural_context=[
            StructuralSymbol(
                file_path="src/investigation_service.py",
                symbol_name="InvestigationService",
                chunk_type="CLASS",
                language="python",
            )
        ],
        retrieved_context=[
            RetrievedChunk(
                file_path="src/investigation_service.py",
                symbol_name="delete_investigation",
                language="python",
                content="def delete_investigation(self, id): ...",
                score=0.9,
            )
        ],
    )


def test_grounding_marks_valid_file_reference_as_grounded():
    result = ReasoningResult(
        summary="s",
        understanding=Understanding(goal="g", affected_area="a"),
        relevant_files=[RelevantFile(file_path="src/investigation_service.py", reason="r", confidence=0.9)],
        confidence=0.8,
    )
    grounded = ground_result(result, _context())
    assert grounded.relevant_files[0].grounded is True


def test_grounding_flags_nonexistent_file_reference():
    result = ReasoningResult(
        summary="s",
        understanding=Understanding(goal="g", affected_area="a"),
        relevant_files=[RelevantFile(file_path="src/does_not_exist.py", reason="r", confidence=0.9)],
        confidence=0.8,
    )
    grounded = ground_result(result, _context())
    assert grounded.relevant_files[0].grounded is False


def test_grounding_marks_valid_symbol_as_grounded():
    result = ReasoningResult(
        summary="s",
        understanding=Understanding(goal="g", affected_area="a"),
        affected_symbols=[
            AffectedSymbol(
                file_path="src/investigation_service.py", symbol_name="delete_investigation", reason="r"
            )
        ],
        confidence=0.8,
    )
    grounded = ground_result(result, _context())
    assert grounded.affected_symbols[0].grounded is True


def test_grounding_flags_hallucinated_symbol():
    result = ReasoningResult(
        summary="s",
        understanding=Understanding(goal="g", affected_area="a"),
        affected_symbols=[
            AffectedSymbol(
                file_path="src/investigation_service.py", symbol_name="totally_made_up_method", reason="r"
            )
        ],
        confidence=0.8,
    )
    grounded = ground_result(result, _context())
    assert grounded.affected_symbols[0].grounded is False


def test_grounding_does_not_remove_ungrounded_entries():
    """Flagged entries must still be returned, not silently deleted."""
    result = ReasoningResult(
        summary="s",
        understanding=Understanding(goal="g", affected_area="a"),
        relevant_files=[RelevantFile(file_path="src/fake.py", reason="r", confidence=0.9)],
        confidence=0.8,
    )
    grounded = ground_result(result, _context())
    assert len(grounded.relevant_files) == 1


def test_grounding_checks_structural_context_too_not_just_retrieved():
    """A symbol that only appears in structural_context (not retrieved_context)
    must still be recognized as grounded — structural knowledge counts."""
    result = ReasoningResult(
        summary="s",
        understanding=Understanding(goal="g", affected_area="a"),
        relevant_files=[RelevantFile(file_path="src/investigation_service.py", reason="r", confidence=0.9)],
        affected_symbols=[
            AffectedSymbol(
                file_path="src/investigation_service.py", symbol_name="InvestigationService", reason="r"
            )
        ],
        confidence=0.8,
    )
    grounded = ground_result(result, _context())
    assert grounded.relevant_files[0].grounded is True
    assert grounded.affected_symbols[0].grounded is True

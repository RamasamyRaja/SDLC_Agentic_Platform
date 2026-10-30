"""
Grounding: practical, deterministic checks of Mistral's claims against the
repository context actually supplied to it — NOT a general hallucination
detector.

What this checks: whether each `relevant_files[].file_path` and
`affected_symbols[].(file_path, symbol_name)` the model named actually
appears somewhere in the `ReasoningInput` it was given (structural context
or retrieved context). If not, that entry is flagged `grounded=False`
rather than silently trusted — the model-reported `confidence` on that
entry is not treated as proof it's correct.

What this does NOT do: verify the model's *reasoning* is correct, verify
the implementation plan is sound, or check anything beyond
file-path/symbol-name membership. Flagged entries are still returned (not
deleted) — the caller decides what to do with an ungrounded claim; hiding
it would just be another kind of silent trust.
"""
from app.llm.schemas import ReasoningInput, ReasoningResult


def ground_result(result: ReasoningResult, context: ReasoningInput) -> ReasoningResult:
    known_files = {s.file_path for s in context.structural_context} | {
        c.file_path for c in context.retrieved_context
    }
    known_symbols = {
        (s.file_path, s.symbol_name) for s in context.structural_context if s.symbol_name
    } | {(c.file_path, c.symbol_name) for c in context.retrieved_context if c.symbol_name}

    grounded_files = [
        rf.model_copy(update={"grounded": rf.file_path in known_files})
        for rf in result.relevant_files
    ]
    grounded_symbols = [
        sym.model_copy(update={"grounded": (sym.file_path, sym.symbol_name) in known_symbols})
        for sym in result.affected_symbols
    ]

    return result.model_copy(
        update={"relevant_files": grounded_files, "affected_symbols": grounded_symbols}
    )

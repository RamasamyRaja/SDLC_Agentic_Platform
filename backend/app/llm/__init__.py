"""
LLM reasoning layer (Milestone 5).

Provider abstraction (provider.py / mistral_provider.py) -> prompts.py ->
context_builder.py (consumes Milestone 3 structural data and Milestone 4
retrieval — never re-parses or re-embeds anything itself) -> service.py
(the single entry point: reasoning_service.analyze_task()).

Mistral is a reasoning component only. It does not write to the database,
clone repositories, run Tree-sitter, query Milvus, execute code, or modify
files — see README "Milestone 5" for the full boundary.
"""

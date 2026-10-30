"""
Thin wrapper around Tree-sitter parsing.

Reads a file's bytes, selects the grammar via the registry, parses it, and
reports whether the resulting tree contains parse errors — without ever
raising on malformed source. A file that fails to parse cleanly is reported
via `ParsedFile.has_error`, not an exception; one bad file must not abort
analysis of the rest of the repository.
"""
from dataclasses import dataclass

from tree_sitter import Node, Tree

from app.analysis.models import SupportedLanguage
from app.analysis.tree_sitter.registry import get_parser


@dataclass
class ParsedFile:
    language: SupportedLanguage
    source: bytes
    tree: Tree | None
    has_error: bool
    error_message: str | None = None

    @property
    def root_node(self) -> Node | None:
        return self.tree.root_node if self.tree is not None else None


def parse_source(source: bytes, language: SupportedLanguage) -> ParsedFile:
    """Parse raw source bytes with the grammar for `language`."""
    try:
        parser = get_parser(language)
        tree = parser.parse(source)
    except Exception as exc:  # noqa: BLE001 - a bad grammar/input must not crash the whole run
        return ParsedFile(
            language=language,
            source=source,
            tree=None,
            has_error=True,
            error_message=f"{exc.__class__.__name__}: {exc}",
        )

    has_error = tree.root_node.has_error
    return ParsedFile(
        language=language,
        source=source,
        tree=tree,
        has_error=has_error,
        error_message="syntax error(s) detected by Tree-sitter" if has_error else None,
    )


def node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def node_line(node: Node) -> int:
    """1-indexed line number for a node's start position."""
    return node.start_point[0] + 1


def node_end_line(node: Node) -> int:
    """1-indexed line number for a node's end position."""
    return node.end_point[0] + 1

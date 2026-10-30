"""
Java structural extraction, walking the tree-sitter-java AST.

Node-type reference (tree-sitter-java grammar):
  class_declaration     -> name: identifier, body: class_body
  class_body              -> method_declaration
  method_declaration       -> name: identifier, parameters: formal_parameters
  formal_parameters         -> formal_parameter (type, name: identifier)
  import_declaration        -> a scoped_identifier (or asterisk_import) for the fully-qualified name
  method_invocation           -> object (optional), name: identifier, arguments: argument_list
"""
from tree_sitter import Node

from app.analysis.models import CallInfo, ClassInfo, FunctionInfo, ImportInfo
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult
from app.analysis.tree_sitter.parser import node_end_line, node_line, node_text


def _param_names(params_node: Node, source: bytes) -> list[str]:
    names: list[str] = []
    for child in params_node.children:
        if child.type == "formal_parameter":
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                names.append(node_text(name_node, source))
    return names


def extract(root: Node, source: bytes, file_path: str) -> LanguageExtractionResult:
    result = LanguageExtractionResult()

    def walk(node: Node, enclosing_class: str | None, enclosing_function: str | None) -> None:
        if node.type in ("class_declaration", "interface_declaration", "record_declaration"):
            name_node = node.child_by_field_name("name")
            class_name = node_text(name_node, source) if name_node else "<anonymous>"
            method_names: list[str] = []

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    if child.type in ("method_declaration", "constructor_declaration"):
                        m_name_node = child.child_by_field_name("name")
                        if m_name_node is not None:
                            method_names.append(node_text(m_name_node, source))

            result.classes.append(
                ClassInfo(
                    name=class_name,
                    file=file_path,
                    line=node_line(node),
                    end_line=node_end_line(node),
                    methods=method_names,
                )
            )

            for child in node.children:
                walk(child, class_name, enclosing_function)
            return

        if node.type in ("method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            func_name = node_text(name_node, source) if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            params = _param_names(params_node, source) if params_node else []

            result.functions.append(
                FunctionInfo(
                    name=func_name,
                    file=file_path,
                    line=node_line(node),
                    end_line=node_end_line(node),
                    enclosing_class=enclosing_class,
                    parameters=params,
                )
            )

            for child in node.children:
                walk(child, enclosing_class, func_name)
            return

        if node.type == "import_declaration":
            # Children are: 'import' [static] (scoped_identifier | identifier) ['.' '*'] ';'
            # The fully-qualified name is whichever scoped_identifier/identifier
            # comes right before the closing ';' (excluding a trailing '*').
            name_parts = [
                c for c in node.children if c.type in ("scoped_identifier", "identifier")
            ]
            if name_parts:
                imported = node_text(name_parts[-1], source)
                result.imports.append(ImportInfo(file=file_path, imported=imported, line=node_line(node)))

        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                callee = node_text(name_node, source)
                result.calls.append(
                    CallInfo(
                        file=file_path,
                        caller=enclosing_function,
                        callee=callee,
                        line=node_line(node),
                    )
                )

        for child in node.children:
            walk(child, enclosing_class, enclosing_function)

    walk(root, None, None)
    return result

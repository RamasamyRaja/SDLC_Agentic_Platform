"""
Python structural extraction, walking the tree-sitter-python AST directly.

Node-type reference (tree-sitter-python grammar):
  class_definition      -> name: identifier, body: block
  function_definition   -> name: identifier, parameters: parameters, body: block
  parameters            -> identifier | default_parameter | typed_parameter | ...
  import_statement      -> dotted_name (possibly multiple, comma-separated)
  import_from_statement -> dotted_name (module), then more dotted_name/identifier for names
  call                  -> function: identifier | attribute, arguments: argument_list
  attribute             -> object, '.', attribute (the attribute IS the method name)

This module only extracts what it can read directly off the AST — it does
not attempt to resolve what a call actually points to, or what a
dynamically-computed import resolves to.
"""
from tree_sitter import Node

from app.analysis.models import CallInfo, ClassInfo, FunctionInfo, ImportInfo
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult
from app.analysis.tree_sitter.parser import node_end_line, node_line, node_text


def _param_names(params_node: Node, source: bytes) -> list[str]:
    names: list[str] = []
    for child in params_node.children:
        if child.type == "identifier":
            names.append(node_text(child, source))
        elif child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
            name_node = child.child_by_field_name("name") or next(
                (c for c in child.children if c.type == "identifier"), None
            )
            if name_node is not None:
                names.append(node_text(name_node, source))
        # *args / **kwargs and bare '*'/'/' separators are skipped deliberately.
    return names


def _call_callee_name(func_node: Node, source: bytes) -> str | None:
    if func_node.type == "identifier":
        return node_text(func_node, source)
    if func_node.type == "attribute":
        attr_node = func_node.child_by_field_name("attribute")
        if attr_node is not None:
            return node_text(attr_node, source)
    return None


def extract(root: Node, source: bytes, file_path: str) -> LanguageExtractionResult:
    result = LanguageExtractionResult()

    def walk(node: Node, enclosing_class: str | None, enclosing_function: str | None) -> None:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = node_text(name_node, source) if name_node else "<anonymous>"
            method_names: list[str] = []

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    if child.type == "function_definition":
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

        if node.type == "function_definition":
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

        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    result.imports.append(
                        ImportInfo(file=file_path, imported=node_text(child, source), line=node_line(node))
                    )
                elif child.type == "aliased_import":
                    mod_node = child.child_by_field_name("name")
                    if mod_node is not None:
                        result.imports.append(
                            ImportInfo(file=file_path, imported=node_text(mod_node, source), line=node_line(node))
                        )

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            if module_node is not None:
                result.imports.append(
                    ImportInfo(file=file_path, imported=node_text(module_node, source), line=node_line(node))
                )

        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node is not None:
                callee = _call_callee_name(func_node, source)
                if callee:
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

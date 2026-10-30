"""
JavaScript structural extraction, walking the tree-sitter-javascript AST.

Node-type reference (tree-sitter-javascript grammar):
  class_declaration     -> name: identifier, body: class_body
  class_body             -> method_definition (property_identifier name)
  function_declaration  -> name: identifier, parameters: formal_parameters
  method_definition       -> name: property_identifier, parameters: formal_parameters
  formal_parameters       -> identifier | assignment_pattern | rest_pattern | ...
  import_statement        -> source: string
  call_expression          -> function: identifier | member_expression, arguments
  member_expression         -> object, property: property_identifier

Arrow functions assigned to a const/let/var (a very common pattern, e.g.
`export const deleteInvestigation = (id) => ...`) are also captured as
functions, since excluding them would miss a large share of real-world JS.
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
        elif child.type in ("assignment_pattern", "rest_pattern"):
            id_node = next((c for c in child.children if c.type == "identifier"), None)
            if id_node is not None:
                names.append(node_text(id_node, source))
    return names


def _call_callee_name(func_node: Node, source: bytes) -> str | None:
    if func_node.type == "identifier":
        return node_text(func_node, source)
    if func_node.type == "member_expression":
        prop_node = func_node.child_by_field_name("property")
        if prop_node is not None:
            return node_text(prop_node, source)
    return None


def extract(root: Node, source: bytes, file_path: str) -> LanguageExtractionResult:
    result = LanguageExtractionResult()

    def walk(node: Node, enclosing_class: str | None, enclosing_function: str | None) -> None:
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            class_name = node_text(name_node, source) if name_node else "<anonymous>"
            method_names: list[str] = []

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    if child.type == "method_definition":
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

        if node.type in ("function_declaration", "method_definition"):
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

        # `const deleteInvestigation = (id) => { ... }` style arrow functions.
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node is not None and value_node is not None and value_node.type == "arrow_function":
                func_name = node_text(name_node, source)
                params_node = value_node.child_by_field_name("parameters")
                params = _param_names(params_node, source) if params_node else []

                result.functions.append(
                    FunctionInfo(
                        name=func_name,
                        file=file_path,
                        line=node_line(node),
                        end_line=node_end_line(value_node),
                        enclosing_class=enclosing_class,
                        parameters=params,
                    )
                )

                for child in value_node.children:
                    walk(child, enclosing_class, func_name)
                return

        if node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            if source_node is not None:
                # Strip surrounding quotes from the string node's text.
                raw = node_text(source_node, source)
                module = raw.strip("'\"`")
                result.imports.append(ImportInfo(file=file_path, imported=module, line=node_line(node)))

        if node.type == "call_expression":
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

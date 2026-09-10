from __future__ import annotations

import ast
from pathlib import Path

from tools.CodeImport.model import CodeEdge, CodeImportResult, CodeNode, ImportFinding


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _file_ref(path: Path, root: Path) -> str:
    return f"file:{_rel(path, root)}"


def _function_ref(path: Path, root: Path, qualname: str) -> str:
    return f"function:{_rel(path, root)}::{qualname}"


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


class PythonAstParser:
    id = "python.ast"
    language = "python"
    suffixes = (".py",)

    def accepts(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in self.suffixes

    def parse_file(self, path: Path, *, root: Path) -> CodeImportResult:
        result = CodeImportResult(source=root)
        file_ref = _file_ref(path, root)
        result.nodes[file_ref] = CodeNode(file_ref, _rel(path, root), "file", path)

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            result.findings.append(ImportFinding(self.id, path, str(exc)))
            return result

        function_refs: dict[str, str] = {}
        function_nodes: list[tuple[ast.AST, str, str]] = []

        def collect(body: list[ast.stmt], prefix: str = "") -> None:
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualname = f"{prefix}.{node.name}" if prefix else node.name
                    ref = _function_ref(path, root, qualname)
                    function_refs[qualname] = ref
                    function_refs.setdefault(node.name, ref)
                    function_nodes.append((node, qualname, ref))
                    result.nodes[ref] = CodeNode(ref, qualname, "function", path)
                    result.edges.append(CodeEdge(
                        ref=f"containment:{file_ref}->{ref}",
                        relation="containment",
                        parent_ref=file_ref,
                        child_ref=ref,
                        source_path=path,
                        line=getattr(node, "lineno", None),
                    ))
                    collect(node.body, qualname)
                elif isinstance(node, ast.ClassDef):
                    class_prefix = f"{prefix}.{node.name}" if prefix else node.name
                    collect(node.body, class_prefix)

        collect(tree.body)

        import_index = 0
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [f"{module}.{alias.name}".strip(".") for alias in node.names]
            for name in names:
                import_index += 1
                target = f"module:{name}"
                result.nodes.setdefault(target, CodeNode(target, name, "module"))
                result.edges.append(CodeEdge(
                    ref=f"import:{file_ref}:{import_index}",
                    relation="import",
                    parent_ref=file_ref,
                    child_ref=target,
                    source_path=path,
                    line=getattr(node, "lineno", None),
                ))

        call_index = 0
        for function_node, qualname, caller_ref in function_nodes:
            for node in ast.walk(function_node):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func)
                if not name:
                    continue
                target_ref = function_refs.get(name) or function_refs.get(name.split(".")[-1])
                if target_ref is None:
                    target_ref = f"callable:{name}"
                    result.nodes.setdefault(target_ref, CodeNode(target_ref, name, "callable"))
                call_index += 1
                result.edges.append(CodeEdge(
                    ref=f"function_call:{caller_ref}:{call_index}",
                    relation="function_call",
                    parent_ref=caller_ref,
                    child_ref=target_ref,
                    source_path=path,
                    line=getattr(node, "lineno", None),
                ))

        result.edges.sort(key=lambda edge: (edge.relation, edge.parent_ref, edge.child_ref, edge.ref))
        return result

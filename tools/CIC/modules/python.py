from __future__ import annotations

import ast
from typing import Any

from CIC.modules.python_primitives import compile_python_function_node


def _span(node: ast.AST) -> dict[str, int | None]:
    return {"line": getattr(node, "lineno", None), "column": getattr(node, "col_offset", None), "end_line": getattr(node, "end_lineno", None), "end_column": getattr(node, "end_col_offset", None)}


def _name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Subscript):
        base = _name(node.value)
        return f"{base}[...]" if base else None
    return None


def _operator(node: ast.AST) -> str:
    return node.__class__.__name__


class _FunctionFacts(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls=[]; self.reads=[]; self.writes=[]; self.assignments=[]; self.operators=[]; self.comparisons=[]; self.branches=[]; self.loops=[]; self.returns=[]; self.raises=[]; self.awaits=[]; self.yields=[]; self.lambdas=[]
    def visit_FunctionDef(self,node): return None
    def visit_AsyncFunctionDef(self,node): return None
    def visit_ClassDef(self,node): return None
    def visit_Lambda(self,node): self.lambdas.append({"span":_span(node)}); return None
    def visit_Name(self,node):
        fact={"name":node.id,"span":_span(node)}
        if isinstance(node.ctx,ast.Load): self.reads.append(fact)
        elif isinstance(node.ctx,(ast.Store,ast.Del)): self.writes.append(fact)
        self.generic_visit(node)
    def visit_Call(self,node): self.calls.append({"target":_name(node.func),"args":len(node.args),"kwargs":[kw.arg for kw in node.keywords],"span":_span(node)}); self.generic_visit(node)
    def visit_Assign(self,node): self.assignments.append({"targets":[_name(t) for t in node.targets],"span":_span(node)}); self.generic_visit(node)
    def visit_AnnAssign(self,node): self.assignments.append({"targets":[_name(node.target)],"annotated":True,"span":_span(node)}); self.generic_visit(node)
    def visit_AugAssign(self,node): self.assignments.append({"targets":[_name(node.target)],"augmented":_operator(node.op),"span":_span(node)}); self.operators.append({"operator":_operator(node.op),"span":_span(node)}); self.generic_visit(node)
    def visit_BinOp(self,node): self.operators.append({"operator":_operator(node.op),"span":_span(node)}); self.generic_visit(node)
    def visit_BoolOp(self,node): self.operators.append({"operator":_operator(node.op),"span":_span(node)}); self.generic_visit(node)
    def visit_UnaryOp(self,node): self.operators.append({"operator":_operator(node.op),"span":_span(node)}); self.generic_visit(node)
    def visit_Compare(self,node): self.comparisons.append({"operators":[_operator(op) for op in node.ops],"span":_span(node)}); self.generic_visit(node)
    def visit_If(self,node): self.branches.append({"kind":"if","span":_span(node)}); self.generic_visit(node)
    def visit_IfExp(self,node): self.branches.append({"kind":"if_expression","span":_span(node)}); self.generic_visit(node)
    def visit_Match(self,node): self.branches.append({"kind":"match","cases":len(node.cases),"span":_span(node)}); self.generic_visit(node)
    def visit_For(self,node): self.loops.append({"kind":"for","span":_span(node)}); self.generic_visit(node)
    def visit_AsyncFor(self,node): self.loops.append({"kind":"async_for","span":_span(node)}); self.generic_visit(node)
    def visit_While(self,node): self.loops.append({"kind":"while","span":_span(node)}); self.generic_visit(node)
    def visit_Return(self,node): self.returns.append({"value":_name(node.value),"span":_span(node)}); self.generic_visit(node)
    def visit_Raise(self,node): self.raises.append({"exception":_name(node.exc),"span":_span(node)}); self.generic_visit(node)
    def visit_Await(self,node): self.awaits.append({"target":_name(node.value),"span":_span(node)}); self.generic_visit(node)
    def visit_Yield(self,node): self.yields.append({"value":_name(node.value),"span":_span(node)}); self.generic_visit(node)
    def visit_YieldFrom(self,node): self.yields.append({"value":_name(node.value),"from":True,"span":_span(node)}); self.generic_visit(node)


def _parameters(node):
    args=node.args; positional=[*args.posonlyargs,*args.args]; defaults_offset=len(positional)-len(args.defaults); result=[]
    for index,arg in enumerate(positional): result.append({"name":arg.arg,"kind":"positional_only" if index<len(args.posonlyargs) else "positional","annotation":ast.unparse(arg.annotation) if arg.annotation is not None else None,"has_default":index>=defaults_offset,"span":_span(arg)})
    if args.vararg: result.append({"name":args.vararg.arg,"kind":"vararg","annotation":ast.unparse(args.vararg.annotation) if args.vararg.annotation else None,"span":_span(args.vararg)})
    for index,arg in enumerate(args.kwonlyargs): result.append({"name":arg.arg,"kind":"keyword_only","annotation":ast.unparse(arg.annotation) if arg.annotation is not None else None,"has_default":args.kw_defaults[index] is not None,"span":_span(arg)})
    if args.kwarg: result.append({"name":args.kwarg.arg,"kind":"kwarg","annotation":ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else None,"span":_span(args.kwarg)})
    return result


def _function_record(node,source,owner=None):
    facts=_FunctionFacts(); [facts.visit(statement) for statement in node.body]
    scoped=f"{owner}.{node.name}" if owner else node.name
    primitive=compile_python_function_node(node)
    nested=[_function_record(statement,source,owner=f"{scoped}.<locals>") for statement in node.body if isinstance(statement,(ast.FunctionDef,ast.AsyncFunctionDef))]
    return {"kind":"method" if owner and ".<locals>" not in owner else "function","name":node.name,"owner":owner,"qualified_name":scoped,"async":isinstance(node,ast.AsyncFunctionDef),"parameters":_parameters(node),"returns_annotation":ast.unparse(node.returns) if node.returns is not None else None,"decorators":[ast.unparse(item) for item in node.decorator_list],"span":_span(node),"source":ast.get_source_segment(source,node),"source_state":"archived" if primitive.decomposition_state=="complete" else "active","decomposition_state":primitive.decomposition_state,"primitive_decomposition":{"primitive_set_ref":primitive.primitive_set_ref,"decomposition_state":primitive.decomposition_state,"body":list(primitive.body),"unresolved":list(primitive.unresolved),"canonical_ready":primitive.canonical_ready,"authority":"implementation_evidence"},"nested_functions":nested,"logic":{"calls":facts.calls,"reads":facts.reads,"writes":facts.writes,"assignments":facts.assignments,"operators":facts.operators,"comparisons":facts.comparisons,"branches":facts.branches,"loops":facts.loops,"returns":facts.returns,"raises":facts.raises,"awaits":facts.awaits,"yields":facts.yields,"lambdas":facts.lambdas}}


def extract_python(path: str, source: str) -> dict[str, Any]:
    try: tree=ast.parse(source,filename=path,type_comments=True)
    except SyntaxError as exc: return {"language_id":"python","parser_id":"python","parser_available":True,"diagnostics":[{"code":"SYNTAX_ERROR","message":exc.msg,"line":exc.lineno,"column":exc.offset}],"symbols":[],"imports":[],"evidence":[]}
    imports=[]; symbols=[]; evidence=[]
    for node in tree.body:
        if isinstance(node,ast.Import):
            for alias in node.names: imports.append({"kind":"import","module":alias.name,"alias":alias.asname,"span":_span(node)})
        elif isinstance(node,ast.ImportFrom): imports.append({"kind":"from_import","module":node.module,"level":node.level,"names":[{"name":alias.name,"alias":alias.asname} for alias in node.names],"span":_span(node)})
        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): symbols.append(_function_record(node,source))
        elif isinstance(node,ast.ClassDef): symbols.append({"kind":"class","name":node.name,"bases":[ast.unparse(base) for base in node.bases],"decorators":[ast.unparse(item) for item in node.decorator_list],"methods":[_function_record(child,source,owner=node.name) for child in node.body if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef))],"span":_span(node)})
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]; symbols.append({"kind":"variable","names":[_name(target) for target in targets],"annotation":ast.unparse(node.annotation) if isinstance(node,ast.AnnAssign) and node.annotation is not None else None,"span":_span(node)})
        else: evidence.append({"kind":node.__class__.__name__,"span":_span(node)})
    return {"language_id":"python","parser_id":"python","parser_available":True,"diagnostics":[],"symbols":symbols,"imports":imports,"evidence":evidence}

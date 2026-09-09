from __future__ import annotations

import re
from typing import Any

_IDENT=r"[A-Za-z_$][A-Za-z0-9_$]*"


def _span(source:str,index:int)->dict[str,int]:
    line=source.count("\n",0,index)+1
    last=source.rfind("\n",0,index)
    return {"line":line,"column":index if last<0 else index-last-1}


def _balanced_body(source:str,open_index:int)->tuple[str,int] | None:
    depth=0; quote=None; escaped=False; i=open_index
    while i<len(source):
        ch=source[i]
        if quote:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch==quote: quote=None
        else:
            if ch in {'\"',"'","`"}: quote=ch
            elif source.startswith("//",i):
                end=source.find("\n",i+2); i=len(source) if end<0 else end; continue
            elif source.startswith("/*",i):
                end=source.find("*/",i+2); i=len(source) if end<0 else end+2; continue
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0: return source[open_index+1:i],i+1
        i+=1
    return None


def _logic(body:str,base:int,source:str)->dict[str,Any]:
    calls=[]; reads=[]; writes=[]; assignments=[]; operators=[]; comparisons=[]; branches=[]; loops=[]; returns=[]; raises=[]; awaits=[]; yields=[]
    for m in re.finditer(rf"\b({_IDENT}(?:\s*\.\s*{_IDENT})*)\s*\(",body):
        target=re.sub(r"\s+","",m.group(1))
        if target not in {"if","while","for","switch","catch","function"}: calls.append({"target":target,"args":None,"kwargs":[],"span":_span(source,base+m.start())})
    for m in re.finditer(rf"\b(const|let|var)\s+({_IDENT})\s*(=)?",body):
        name=m.group(2); writes.append({"name":name,"span":_span(source,base+m.start(2))})
        if m.group(3): assignments.append({"targets":[name],"declaration":True,"span":_span(source,base+m.start(2))})
    for m in re.finditer(rf"\b({_IDENT})\s*(\+=|-=|\*=|/=|%=|=)",body):
        assignments.append({"targets":[m.group(1)],"operator":m.group(2),"span":_span(source,base+m.start())}); writes.append({"name":m.group(1),"span":_span(source,base+m.start())})
    for m in re.finditer(r"===|!==|==|!=|<=|>=|<|>|&&|\|\||\?\?|\+|-|\*|/|%",body):
        op=m.group(0); operators.append({"operator":op,"span":_span(source,base+m.start())})
        if op in {"===","!==","==","!=","<","<=",">",">="}: comparisons.append({"operators":[op],"span":_span(source,base+m.start())})
    for keyword,target in (("if",branches),("switch",branches),("catch",branches),("for",loops),("while",loops),("do",loops)):
        for m in re.finditer(rf"\b{keyword}\b",body): target.append({"kind":keyword,"span":_span(source,base+m.start())})
    for keyword,target in (("return",returns),("throw",raises),("await",awaits),("yield",yields)):
        for m in re.finditer(rf"\b{keyword}\b",body): target.append({"span":_span(source,base+m.start())})
    for m in re.finditer(rf"\b({_IDENT})\b",body): reads.append({"name":m.group(1),"span":_span(source,base+m.start())})
    return {"calls":calls,"reads":reads,"writes":writes,"assignments":assignments,"operators":operators,"comparisons":comparisons,"branches":branches,"loops":loops,"returns":returns,"raises":raises,"awaits":awaits,"yields":yields,"lambdas":[]}


def _parameters(text:str)->list[dict[str,Any]]:
    result=[]
    for part in text.split(","):
        part=part.strip()
        if not part: continue
        name=part.split("=",1)[0].strip()
        result.append({"name":name,"kind":"positional","annotation":None,"has_default":"=" in part,"span":{}})
    return result


def extract_javascript(path:str,source:str)->dict[str,Any]:
    diagnostics=[]; symbols=[]; imports=[]; exports=[]; evidence=[]
    for m in re.finditer(r"//[^\n]*|/\*.*?\*/",source,re.S): evidence.append({"kind":"comment","text":m.group(0),"span":_span(source,m.start())})
    for m in re.finditer(rf"\bimport\s+(.+?)\s+from\s+(['\"])(.+?)\2\s*;?|\bimport\s+(['\"])(.+?)\4\s*;?",source,re.S):
        module=m.group(3) or m.group(5); clause=(m.group(1) or "").strip(); names=[]
        if clause:
            if clause.startswith("*"):
                mm=re.search(rf"\bas\s+({_IDENT})",clause); names.append({"imported":"*","local":mm.group(1),"kind":"ImportNamespaceSpecifier"}) if mm else None
            elif clause.startswith("{"):
                for item in clause.strip("{} ").split(","):
                    parts=[p.strip() for p in re.split(r"\bas\b",item)];
                    if parts and parts[0]: names.append({"imported":parts[0],"local":parts[-1],"kind":"ImportSpecifier"})
            else:
                first=clause.split(",",1)[0].strip();
                if first: names.append({"imported":"default","local":first,"kind":"ImportDefaultSpecifier"})
        imports.append({"kind":"import","module":module,"names":names,"span":_span(source,m.start())})
    function_pattern=re.compile(rf"(?P<export>\bexport\s+)?(?P<async>\basync\s+)?function\s+(?P<name>{_IDENT})\s*\((?P<params>[^)]*)\)\s*{{")
    occupied=[]
    for m in function_pattern.finditer(source):
        body_info=_balanced_body(source,m.end()-1)
        if body_info is None: diagnostics.append({"code":"UNCLOSED_JS_DELIMITER","message":f"function body is not closed: {m.group('name')}",**_span(source,m.start())}); continue
        body,end=body_info; occupied.append((m.start(),end)); name=m.group("name")
        symbols.append({"kind":"function","name":name,"owner":None,"qualified_name":name,"async":bool(m.group("async")),"generator":False,"parameters":_parameters(m.group("params")),"returns_annotation":None,"decorators":[],"span":_span(source,m.start()),"source":source[m.start():end],"source_state":"active","decomposition_state":"not_decomposed","primitive_decomposition":{"primitive_set_ref":"CW_LOGIC_PRIMITIVES","decomposition_state":"not_decomposed","body":[],"unresolved":[{"reason":"JAVASCRIPT_PRIMITIVE_COMPILER_NOT_CONNECTED"}],"canonical_ready":False,"authority":"implementation_evidence"},"nested_functions":[],"logic":_logic(body,m.end(),source)})
        if m.group("export"): exports.append({"kind":"local_export","exported_name":name,"local_name":name,"target_kind":"function","target_qualified_name":name,"span":_span(source,m.start())})
    arrow_pattern=re.compile(rf"(?P<export>\bexport\s+)?\b(?:const|let|var)\s+(?P<name>{_IDENT})\s*=\s*(?P<async>async\s+)?(?P<params>\([^)]*\)|{_IDENT})\s*=>\s*")
    for m in arrow_pattern.finditer(source):
        if any(a<=m.start()<b for a,b in occupied): continue
        name=m.group("name"); params=m.group("params").strip(); params=params[1:-1] if params.startswith("(") else params
        if m.end()<len(source) and source[m.end()]=="{":
            body_info=_balanced_body(source,m.end())
            if body_info is None: continue
            body,end=body_info
        else:
            end=source.find(";",m.end()); end=len(source) if end<0 else end; body=source[m.end():end]
        symbols.append({"kind":"function","name":name,"owner":None,"qualified_name":name,"async":bool(m.group("async")),"generator":False,"parameters":_parameters(params),"returns_annotation":None,"decorators":[],"span":_span(source,m.start()),"source":source[m.start():end],"source_state":"active","decomposition_state":"not_decomposed","primitive_decomposition":{"primitive_set_ref":"CW_LOGIC_PRIMITIVES","decomposition_state":"not_decomposed","body":[],"unresolved":[{"reason":"JAVASCRIPT_PRIMITIVE_COMPILER_NOT_CONNECTED"}],"canonical_ready":False,"authority":"implementation_evidence"},"nested_functions":[],"logic":_logic(body,m.end(),source)})
        if m.group("export"): exports.append({"kind":"local_export","exported_name":name,"local_name":name,"target_kind":"function","target_qualified_name":name,"span":_span(source,m.start())})
    for m in re.finditer(rf"\bexport\s*{{([^}}]+)}}(?:\s*from\s*(['\"])(.+?)\2)?",source,re.S):
        module=m.group(3)
        for item in m.group(1).split(","):
            parts=[p.strip() for p in re.split(r"\bas\b",item)]; local=parts[0] if parts else ""; exported=parts[-1] if parts else ""
            if not local: continue
            exports.append({"kind":"re_export" if module else "local_export","exported_name":exported,"local_name":local,"source_module":module,"target_kind":"unresolved_re_export" if module else ("function" if any(s.get("qualified_name")==local for s in symbols) else "reference"),"target_qualified_name":None if module else local,"span":_span(source,m.start())})
    return {"language_id":"javascript","parser_id":"cic-js-python-2","parser_available":True,"diagnostics":diagnostics,"symbols":symbols,"imports":imports,"exports":exports,"evidence":evidence,"javascript":{"comments":[e for e in evidence if e.get("kind")=="comment"],"unsupported":[]}}

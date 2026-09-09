from __future__ import annotations

from typing import Any


def extract_css(path:str,source:str)->dict[str,Any]:
    """Stdlib-only CSS evidence extractor. Keeps syntax as evidence; no semantic guessing."""
    diagnostics=[]; rules=[]; at_rules=[]; references=[]; comments=[]
    i=0; n=len(source); line=1
    while i<n:
        if source.startswith("/*",i):
            end=source.find("*/",i+2)
            if end<0: comments.append({"kind":"comment","text":source[i+2:],"line":line}); diagnostics.append({"code":"UNCLOSED_CSS_COMMENT","message":"CSS comment is not closed","line":line}); break
            text=source[i+2:end]; comments.append({"kind":"comment","text":text,"line":line}); line+=source[i:end+2].count("\n"); i=end+2; continue
        ch=source[i]
        if ch=="\n": line+=1; i+=1; continue
        if ch.isspace(): i+=1; continue
        start=i; start_line=line; brace=source.find("{",i); semi=source.find(";",i)
        if source[i]=="@" and (semi>=0 and (brace<0 or semi<brace)):
            prelude=source[i:semi].strip(); parts=prelude.split(None,1); name=parts[0][1:] if parts else ""; value=parts[1] if len(parts)>1 else ""; at_rules.append({"kind":"at_rule","name":name,"prelude":value,"block":None,"line":start_line,"column":0});
            if name.lower() in {"import","namespace"}: references.append({"kind":"css_reference","reference_type":name.lower(),"target":value,"line":start_line,"column":0})
            line+=source[i:semi+1].count("\n"); i=semi+1; continue
        if brace<0: break
        prelude=source[i:brace].strip(); depth=1; j=brace+1; quote=None; escaped=False
        while j<n and depth:
            c=source[j]
            if quote:
                if escaped: escaped=False
                elif c=="\\": escaped=True
                elif c==quote: quote=None
            else:
                if c in {'\"',"'"}: quote=c
                elif c=="{": depth+=1
                elif c=="}": depth-=1
            j+=1
        if depth: diagnostics.append({"code":"UNCLOSED_CSS_BLOCK","message":f"CSS block is not closed: {prelude}","line":start_line}); body=source[brace+1:]; i=n
        else: body=source[brace+1:j-1]; i=j
        if prelude.startswith("@"): parts=prelude.split(None,1); at_rules.append({"kind":"at_rule","name":parts[0][1:],"prelude":parts[1] if len(parts)>1 else "","block":body,"line":start_line,"column":0})
        else:
            declarations=[]
            for piece in body.split(";"):
                if ":" not in piece: continue
                name,value=piece.split(":",1); name=name.strip(); value=value.strip()
                if not name: continue
                important=value.lower().endswith("!important"); normalized=value[:-10].rstrip() if important else value
                declarations.append({"kind":"declaration","name":name,"value":normalized,"important":important,"line":start_line,"column":0})
                lower=normalized.lower(); pos=0
                while True:
                    p=lower.find("url(",pos)
                    if p<0: break
                    q=normalized.find(")",p+4); raw=normalized[p+4:q if q>=0 else len(normalized)].strip().strip("'\"")
                    if raw: references.append({"kind":"css_reference","reference_type":"url","property":name,"target":raw,"line":start_line,"column":0})
                    pos=(q+1) if q>=0 else len(normalized)
            rules.append({"kind":"style_rule","selectors":[s.strip() for s in prelude.split(",") if s.strip()],"declarations":declarations,"line":start_line,"column":0})
        line+=source[start:i].count("\n")
    return {"language_id":"css","parser_id":"cic-css-stdlib-1","parser_available":True,"diagnostics":diagnostics,"symbols":rules,"imports":[],"exports":[],"evidence":[*comments,*at_rules,*references],"css":{"rules":rules,"at_rules":at_rules,"references":references,"comments":comments}}

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

_VOID_ELEMENTS=frozenset({"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"})

def _attr_map(attrs): return {str(name):value for name,value in attrs}

class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False); self.elements=[]; self.comments=[]; self.text_nodes=[]; self.entities=[]; self.declarations=[]; self.references=[]; self.inline_events=[]; self.stack=[]; self.diagnostics=[]
    def _position(self): line,column=self.getpos(); return {"line":line,"column":column}
    def _parent_index(self): return self.stack[-1] if self.stack else None
    def _record_element(self,tag,attrs,self_closing=False):
        normalized=tag.lower(); attr_values=_attr_map(attrs); index=len(self.elements)
        record={"kind":"element","index":index,"tag":normalized,"parent_index":self._parent_index(),"attributes":[{"name":n,"value":v} for n,v in attrs],"id":attr_values.get("id"),"classes":str(attr_values.get("class") or "").split(),"self_closing":self_closing or normalized in _VOID_ELEMENTS,"span":self._position()}; self.elements.append(record)
        refs={"script":("src",),"link":("href",),"img":("src","srcset"),"source":("src","srcset"),"a":("href",),"form":("action",),"iframe":("src",)}
        for attr_name in refs.get(normalized,()):
            value=attr_values.get(attr_name)
            if isinstance(value,str) and value: self.references.append({"kind":"html_reference","tag":normalized,"attribute":attr_name,"target":value,"element_index":index,"span":self._position()})
        for name,value in attrs:
            lowered=name.lower()
            if lowered.startswith("on") and len(lowered)>2: self.inline_events.append({"kind":"inline_event_attribute","event_name":lowered[2:],"attribute":lowered,"source":value,"element_index":index,"span":self._position(),"canonical_semantic_authority":False})
        return index
    def handle_starttag(self,tag,attrs):
        index=self._record_element(tag,attrs)
        if self.elements[index]["self_closing"] is False: self.stack.append(index)
    def handle_startendtag(self,tag,attrs): self._record_element(tag,attrs,True)
    def handle_endtag(self,tag):
        normalized=tag.lower()
        if not self.stack: self.diagnostics.append({"code":"UNMATCHED_END_TAG","message":f"closing tag has no open element: {normalized}",**self._position()}); return
        match=None
        for offset in range(len(self.stack)-1,-1,-1):
            if self.elements[self.stack[offset]]["tag"]==normalized: match=offset; break
        if match is None: self.diagnostics.append({"code":"UNMATCHED_END_TAG","message":f"closing tag does not match open stack: {normalized}",**self._position()}); return
        if match!=len(self.stack)-1:
            for orphan in self.stack[match+1:]: self.diagnostics.append({"code":"IMPLICITLY_CLOSED_TAG","message":f"element implicitly closed before </{normalized}>: {self.elements[orphan]['tag']}",**self._position()})
        del self.stack[match:]
    def handle_data(self,data):
        if data: self.text_nodes.append({"kind":"text","parent_index":self._parent_index(),"text":data,"whitespace_only":data.isspace(),"span":self._position()})
    def handle_comment(self,data): self.comments.append({"kind":"comment","text":data,"span":self._position()})
    def handle_decl(self,decl): self.declarations.append({"kind":"declaration","value":decl,"span":self._position()})
    def handle_entityref(self,name): self.entities.append({"kind":"entity_ref","name":name,"span":self._position()})
    def handle_charref(self,name): self.entities.append({"kind":"char_ref","name":name,"span":self._position()})
    def unknown_decl(self,data): self.declarations.append({"kind":"unknown_declaration","value":data,"span":self._position()})

def extract_html(path:str,source:str)->dict[str,Any]:
    parser=_Extractor()
    try: parser.feed(source); parser.close()
    except Exception as exc: parser.diagnostics.append({"code":"HTML_PARSE_ERROR","message":str(exc)})
    for index in parser.stack: parser.diagnostics.append({"code":"UNCLOSED_TAG","message":f"open element not explicitly closed: {parser.elements[index]['tag']}","element_index":index})
    ids={}
    for element in parser.elements:
        value=element.get("id")
        if isinstance(value,str) and value: ids.setdefault(value,[]).append(int(element["index"]))
    for value,indexes in sorted(ids.items()):
        if len(indexes)>1: parser.diagnostics.append({"code":"DUPLICATE_HTML_ID","message":f"duplicate HTML id: {value}","element_indexes":indexes})
    return {"language_id":"html","parser_id":"cic-html-stdlib-1","parser_available":True,"diagnostics":parser.diagnostics,"symbols":parser.elements,"imports":[],"exports":[],"evidence":[*parser.declarations,*parser.comments,*parser.text_nodes,*parser.entities,*parser.references,*parser.inline_events],"html":{"elements":parser.elements,"references":parser.references,"inline_event_attributes":parser.inline_events,"comments":parser.comments,"text_nodes":parser.text_nodes,"declarations":parser.declarations,"entity_references":parser.entities}}

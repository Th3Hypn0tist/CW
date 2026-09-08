#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from dataclasses import asdict,dataclass
from pathlib import Path
try:
 from .cw_spec_common import read_json,resolve_bundle
 from .cw_compose import compose_documents
 from . import cw_spec_lint
except ImportError:
 from cw_spec_common import read_json,resolve_bundle
 from cw_compose import compose_documents
 import cw_spec_lint
VER='2.1.0'
@dataclass
class F: severity:str; code:str; file:str; path:str; message:str
class C:
 def __init__(s):s.f=[]
 def a(s,v,c,p,x,m):s.f.append(F(v,c,str(p),x,m))
 def e(s,c,p,x,m):s.a('ERROR',c,p,x,m)
 def u(s,c,p,x,m):s.a('UNREADY',c,p,x,m)
def dl(v):return [x for x in v if isinstance(x,dict)] if isinstance(v,list) else []
def artifact_paths(root):
 if root.is_file():return [root]
 if not root.is_dir():raise FileNotFoundError(root)
 paths=[p for p in root.rglob('*') if p.is_file() and p.suffix in {'.cw','.json'}]
 return sorted(paths,key=lambda p:(p.as_posix().casefold(),p.as_posix()))
def split(d):
 out=[];dep=0;start=0
 for i,ch in enumerate(d):
  dep+=ch=='<';dep-=ch=='>'
  if ch=='|' and dep==0:out.append(d[start:i]);start=i+1
 out.append(d[start:]);return [x.strip() for x in out]
def tm(v,d):
 if not isinstance(d,str):return True
 ps=split(d)
 if len(ps)>1:return any(tm(v,x) for x in ps)
 if d=='null':return v is None
 if d=='string' or d.endswith('_ref'):return isinstance(v,str) and bool(v)
 if d in {'logic_value','logic_statement','logic_representation','required_link_ref'}:return isinstance(v,dict)
 if d=='endpoint_constraint':return isinstance(v,(str,dict))
 if d=='non_negative_integer':return isinstance(v,int) and not isinstance(v,bool) and v>=0
 if d=='integer':return isinstance(v,int) and not isinstance(v,bool)
 if d=='boolean':return isinstance(v,bool)
 if d=='object':return isinstance(v,dict)
 if d.startswith('array<') and d.endswith('>'):return isinstance(v,list) and all(tm(x,d[6:-1]) for x in v)
 return True
def schema(v,s,c,file,path,name):
 if not isinstance(s,dict):return
 if not isinstance(v,dict):c.e('VALUE_NOT_OBJECT',file,path,name+' must be object');return
 fields=s.get('fields',{}) if isinstance(s.get('fields'),dict) else {}
 for f in s.get('required',[]) if isinstance(s.get('required'),list) else []:
  if f not in v:c.e('VALUE_REQUIRED_FIELD_MISSING',file,path+'.'+f,f'{name} requires {f!r}')
 for f,d in fields.items():
  if f in v and not tm(v[f],d):c.e('VALUE_TYPE_MISMATCH',file,path+'.'+f,f'expected {d!r}')
def sections(n,nts,cache,stack=None):
 if n in cache:return cache[n]
 stack=list(stack or [])
 if n in stack:raise ValueError('cycle')
 stack.append(n);out=[]
 for p in nts[n].get('extends',[]):
  for x in sections(p,nts,cache,stack):
   if x not in out:out.append(x)
 for x in nts[n].get('sections',[]):
  if x not in out:out.append(x)
 cache[n]=out;return out
def inherits(nt,want,nts):
 if nt==want:return True
 seen=set();st=[nt]
 while st:
  x=st.pop()
  if x in seen or x not in nts:continue
  seen.add(x)
  for p in nts[x].get('extends',[]):
   if p==want:return True
   st.append(p)
 return False
def main()->int:
 a=argparse.ArgumentParser();a.add_argument('input',type=Path);a.add_argument('--spec-set',type=Path);a.add_argument('--ccf',type=Path);a.add_argument('--nodetypes',type=Path);a.add_argument('--rulesets',type=Path);a.add_argument('--spec-dir',type=Path);a.add_argument('--skip-spec-lint',action='store_true');a.add_argument('--json',action='store_true');x=a.parse_args()
 try:b=resolve_bundle(spec_set=x.spec_set,ccf=x.ccf,nodetypes=x.nodetypes,rulesets=x.rulesets,spec_dir=x.spec_dir,default_start=Path(__file__).parent)
 except Exception as e:print(f'RESULT: IMPLEMENTATION_FAILURE\n{e}',file=sys.stderr);return 2
 if not x.skip_spec_lint:
  lc=cw_spec_lint.lint_bundle(b)
  if any(z.severity=='ERROR' for z in lc.f):print('RESULT: INVALID_SPECIFICATION',file=sys.stderr);return 1
 c=C()
 try:
  paths=artifact_paths(x.input);docs=compose_documents(paths,read_json)
  nts={z['id']:z for z in dl(b.nodetypes.get('nodetypes')) if isinstance(z.get('id'),str)}
  prs={z['id']:z for z in dl(b.rulesets.get('property_rulesets')) if isinstance(z.get('id'),str)}
  lrs={z['id']:z for z in dl(b.rulesets.get('link_rulesets')) if isinstance(z.get('id'),str)}
  nr=b.rulesets.get('node_ruleset',{});readers=nr.get('section_readers',{}) if isinstance(nr,dict) else {}
  psets={z['id']:z for z in dl(b.rulesets.get('logic_primitive_sets')) if isinstance(z.get('id'),str)}
  shape=b.ccf.get('contract_shape',{});objs={};owners={}
  for p,d in docs:
   for f in shape.get('required',[]) if isinstance(shape,dict) else []:
    if f not in d:c.e('CONTRACT_REQUIRED_FIELD_MISSING',p,'$.'+f,f'missing {f!r}')
   for ei,e in enumerate(d.get('entities',[]) if isinstance(d.get('entities'),list) else []):
    if not isinstance(e,dict):continue
    eid=e.get('id')
    if isinstance(eid,str):
     if eid in objs:c.e('CANONICAL_ID_DUPLICATE',p,f'$.entities[{ei}].id',eid)
     objs[eid]=('Entity',e,p);owners[eid]=eid
    for pi,q in enumerate(e.get('properties',[]) if isinstance(e.get('properties'),list) else []):
     if not isinstance(q,dict):continue
     qid=q.get('id')
     if isinstance(qid,str):
      if qid in objs:c.e('CANONICAL_ID_DUPLICATE',p,f'$.entities[{ei}].properties[{pi}].id',qid)
      objs[qid]=('Property',q,p);owners[qid]=eid
  cache={};links=[]
  for p,d in docs:
   for ei,e in enumerate(d.get('entities',[]) if isinstance(d.get('entities'),list) else []):
    if not isinstance(e,dict):continue
    ep=f'$.entities[{ei}]';nt=e.get('entity_type_ref')
    if nt not in nts:c.e('NODETYPE_UNRESOLVED',p,ep+'.entity_type_ref',repr(nt));ss=[]
    else:ss=sections(nt,nts,cache)
    for s in ss:
     r=readers.get(s)
     if isinstance(r,dict) and r.get('kind')=='entity_field' and r.get('required') is True and r.get('field') not in e:c.u('NODE_SECTION_REQUIRED_FIELD_MISSING',p,ep+'.'+str(r.get('field')),s)
    for pi,q in enumerate(e.get('properties',[]) if isinstance(e.get('properties'),list) else []):
     if not isinstance(q,dict):continue
     pp=f'{ep}.properties[{pi}]';pt=q.get('property_type_ref');rr=q.get('ruleset_ref');rule=lrs.get(rr) if pt=='link' else prs.get(rr)
     if rule is None:c.e('RULESET_REF_UNRESOLVED',p,pp+'.ruleset_ref',repr(rr));continue
     if pt!='link' and rule.get('property_type_ref')!=pt:c.e('RULESET_TYPE_MISMATCH',p,pp+'.ruleset_ref',str(pt))
     schema(q.get('value'),rule.get('value_schema'),c,p,pp+'.value',str(rr));v=q.get('value')
     if not isinstance(v,dict):continue
     for fld,pol in (rule.get('reference_constraints',{}) if isinstance(rule.get('reference_constraints'),dict) else {}).items():
      vals=v.get(fld);vals=vals if isinstance(vals,list) else [vals]
      for j,ref in enumerate(vals):
       if ref is None:continue
       obj=objs.get(ref)
       if obj is None:c.u('CANONICAL_REFERENCE_UNRESOLVED',p,pp+f'.value.{fld}[{j}]',repr(ref));continue
       kind,t,_=obj;ak=pol.get('allowed_canonical_kinds') if isinstance(pol,dict) else None
       if isinstance(ak,list) and kind not in ak:c.e('REFERENCE_KIND_INCOMPATIBLE',p,pp+'.value.'+fld,kind)
       ap=pol.get('allowed_property_type_refs') if isinstance(pol,dict) else None
       if kind=='Property' and isinstance(ap,list) and t.get('property_type_ref') not in ap:c.e('REFERENCE_PROPERTY_INCOMPATIBLE',p,pp+'.value.'+fld,str(t.get('property_type_ref')))
       an=pol.get('allowed_nodetype_refs') if isinstance(pol,dict) else None
       if kind=='Entity' and isinstance(an,list):
        tn=t.get('entity_type_ref');ok=isinstance(tn,str) and any(inherits(tn,z,nts) for z in an)
        if not ok:c.e('REFERENCE_NODETYPE_INCOMPATIBLE',p,pp+'.value.'+fld,str(tn))
     if pt=='link':
      links.append(q);rel=v.get('link_type_ref')
      if rule.get('relation_policy','fixed')!='open' and rel!=rule.get('link_type_ref'):c.e('LINK_RELATION_RULESET_MISMATCH',p,pp+'.value.link_type_ref',str(rel))
      for side in ('parent_ref','child_ref'):
       ref=v.get(side);obj=objs.get(ref)
       if obj is None:c.u('LINK_ENDPOINT_UNRESOLVED',p,pp+'.value.'+side,repr(ref));continue
       cs=rule.get('endpoint_constraints',{}).get(side,[]) if isinstance(rule.get('endpoint_constraints'),dict) else []
       if cs:
        kind,t,_=obj;ok=False
        for z in cs:
         if z.startswith('property:') and kind=='Property' and t.get('property_type_ref')==z.split(':',1)[1]:ok=True
         if z.startswith('entity_nodetype:') and kind=='Entity' and isinstance(t.get('entity_type_ref'),str) and inherits(t['entity_type_ref'],z.split(':',1)[1],nts):ok=True
        if not ok:c.e('LINK_ENDPOINT_INCOMPATIBLE',p,pp+'.value.'+side,str(cs))
     if pt=='function' and isinstance(v.get('logic'),dict):
      lg=v['logic'];schema(lg,rule.get('logic_schema'),c,p,pp+'.value.logic',str(rr))
      if psets.get(lg.get('primitive_set_ref')) is None:c.e('LOGIC_PRIMITIVE_SET_UNRESOLVED',p,pp+'.value.logic.primitive_set_ref',repr(lg.get('primitive_set_ref')))
  byreq={}
  for q in links:
   v=q.get('value',{});r=v.get('required_link_ref') if isinstance(v,dict) else None
   if isinstance(r,dict):byreq.setdefault((r.get('entity_ref'),r.get('required_link_id')),[]).append(q)
  for p,d in docs:
   for ei,e in enumerate(d.get('entities',[]) if isinstance(d.get('entities'),list) else []):
    if not isinstance(e,dict) or e.get('entity_type_ref') not in nts:continue
    if 'required_links' not in sections(e['entity_type_ref'],nts,cache):continue
    for ri,r in enumerate(e.get('required_links',[]) if isinstance(e.get('required_links'),list) else []):
     rp=f'$.entities[{ei}].required_links[{ri}]';schema(r,nr.get('required_link_schema'),c,p,rp,'Required Link')
     if not isinstance(r,dict):continue
     hits=[]
     for q in byreq.get((e.get('id'),r.get('id')),[]):
      v=q.get('value',{});side=r.get('self_endpoint')
      if v.get('link_type_ref')==r.get('link_type_ref') and side in {'parent_ref','child_ref'} and v.get(side)==e.get('id'):hits.append(q)
     if isinstance(r.get('min'),int) and len(hits)<r['min']:c.u('REQUIRED_LINK_UNSATISFIED',p,rp,f'{len(hits)} < {r["min"]}')
     if isinstance(r.get('max'),int) and len(hits)>r['max']:c.e('REQUIRED_LINK_MAX_EXCEEDED',p,rp,f'{len(hits)} > {r["max"]}')
  res='INVALID_MODEL' if any(z.severity=='ERROR' for z in c.f) else ('UNREADY' if any(z.severity=='UNREADY' for z in c.f) else 'READY')
 except Exception as e:print(f'RESULT: IMPLEMENTATION_FAILURE\n{e}',file=sys.stderr);return 2
 if x.json:print(json.dumps({'validator_version':VER,'result':res,'findings':[asdict(z) for z in c.f]},indent=2))
 else:
  print(f'CW artifact validator v{VER}\nCCF {b.ccf.get("version")} / NodeTypes {b.nodetypes.get("version")} / Rulesets {b.rulesets.get("version")}')
  for z in c.f:print(f'{z.severity} {z.code} {Path(z.file).name} {z.path}: {z.message}')
  print('\nRESULT:',res)
 return 1 if res=='INVALID_MODEL' else 0
if __name__=='__main__':raise SystemExit(main())

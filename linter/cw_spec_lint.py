#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from dataclasses import asdict,dataclass
from pathlib import Path
from typing import Any,Dict,List,Mapping,Optional,Set
try:
 from .cw_spec_common import SpecBundle,resolve_bundle
except ImportError:
 from cw_spec_common import SpecBundle,resolve_bundle
VER='2.0.0'; SEMVER=re.compile(r'^\d+\.\d+\.\d+$')
@dataclass
class F: severity:str; code:str; file:str; path:str; message:str
class C:
 def __init__(s): s.f=[]
 def e(s,c,p,x,m): s.f.append(F('ERROR',c,str(p),x,m))
def dl(v): return [x for x in v if isinstance(x,dict)] if isinstance(v,list) else []
def unique(items,key,c,file,path,kind):
 out={}
 for i,x in enumerate(items):
  v=x.get(key)
  if not isinstance(v,str) or not v:c.e(kind+'_ID_INVALID',file,f'{path}[{i}].{key}',f'{key} must be non-empty')
  elif v in out:c.e(kind+'_ID_DUPLICATE',file,f'{path}[{i}].{key}',f'duplicate {v!r}')
  else:out[v]=x
 return out
def schema(v,c,file,path):
 if not isinstance(v,dict):c.e('SCHEMA_INVALID',file,path,'schema must be object');return
 r,o,f=v.get('required',[]),v.get('optional',[]),v.get('fields')
 if not isinstance(r,list) or not all(isinstance(x,str) for x in r):c.e('SCHEMA_REQUIRED_INVALID',file,path+'.required','must be string array');r=[]
 if not isinstance(o,list) or not all(isinstance(x,str) for x in o):c.e('SCHEMA_OPTIONAL_INVALID',file,path+'.optional','must be string array');o=[]
 if not isinstance(f,dict):c.e('SCHEMA_FIELDS_INVALID',file,path+'.fields','must be object');return
 miss=(set(r)|set(o))-set(f)
 if miss:c.e('SCHEMA_FIELDS_MISSING',file,path+'.fields',f'missing {sorted(miss)}')
def sections(nt,nts,cache,stack=None):
 if nt in cache:return cache[nt]
 stack=list(stack or [])
 if nt in stack:raise ValueError(' -> '.join(stack+[nt]))
 stack.append(nt); out=[]; x=nts[nt]
 for p in x.get('extends',[]):
  if p not in nts:raise KeyError(p)
  for q in sections(p,nts,cache,stack):
   if q not in out:out.append(q)
 v=x.get('sections')
 if not isinstance(v,list) or not all(isinstance(q,str) and q for q in v):raise TypeError('sections must be non-empty string array')
 for q in v:
  if q not in out:out.append(q)
 cache[nt]=out;return out
def lint_bundle(b:SpecBundle)->C:
 c=C(); cf=b.ccf.get('id') or ('CANONICAL_CONTRACT_FORMAT' if b.ccf.get('type')=='canonical_contract_format' else None)
 if b.nodetypes.get('ccf_ref')!=cf:c.e('NODETYPES_CCF_REF_MISMATCH',b.nodetypes_path,'$.ccf_ref',f'expected {cf!r}')
 if b.rulesets.get('ccf_ref')!=cf:c.e('RULESETS_CCF_REF_MISMATCH',b.rulesets_path,'$.ccf_ref',f'expected {cf!r}')
 if b.rulesets.get('nodetypes_ref')!=b.nodetypes.get('id'):c.e('RULESETS_NODETYPES_REF_MISMATCH',b.rulesets_path,'$.nodetypes_ref','selected NodeTypes id mismatch')
 for d,p in ((b.nodetypes,b.nodetypes_path),(b.rulesets,b.rulesets_path)):
  if not isinstance(d.get('version'),str) or not SEMVER.match(d['version']):c.e('VERSION_INVALID',p,'$.version','semantic x.y.z required')
 nts=unique(dl(b.nodetypes.get('nodetypes')),'id',c,b.nodetypes_path,'$.nodetypes','NODETYPE')
 nr=b.rulesets.get('node_ruleset'); readers=nr.get('section_readers') if isinstance(nr,dict) else None
 if not isinstance(nr,dict) or nr.get('id')!='RULESET_NODE' or nr.get('root')!='Entity':c.e('NODE_RULESET_INVALID',b.rulesets_path,'$.node_ruleset','RULESET_NODE root must be Entity');readers={}
 if not isinstance(readers,dict):c.e('NODE_SECTION_READERS_INVALID',b.rulesets_path,'$.node_ruleset.section_readers','must be object');readers={}
 cache={}
 for i,n in enumerate(dl(b.nodetypes.get('nodetypes'))):
  nid=n.get('id')
  if not isinstance(nid,str):continue
  try:ss=sections(nid,nts,cache)
  except Exception as e:c.e('NODETYPE_INHERITANCE_INVALID',b.nodetypes_path,f'$.nodetypes[{i}]',str(e));continue
  for s in ss:
   if s not in readers:c.e('NODETYPE_SECTION_UNRESOLVED',b.nodetypes_path,f'$.nodetypes[{i}].sections',f'{s!r} has no RULESET_NODE reader')
 prs=dl(b.rulesets.get('property_rulesets')); lrs=dl(b.rulesets.get('link_rulesets'))
 pri=unique(prs,'id',c,b.rulesets_path,'$.property_rulesets','PROPERTY_RULESET'); lri=unique(lrs,'id',c,b.rulesets_path,'$.link_rulesets','LINK_RULESET')
 for x in set(pri)&set(lri):c.e('RULESET_ID_DUPLICATE',b.rulesets_path,'$.link_rulesets',f'duplicate Ruleset id {x!r}')
 ptypes=set()
 for i,r in enumerate(prs):
  t=r.get('property_type_ref')
  if not isinstance(t,str) or not t:c.e('PROPERTY_TYPE_INVALID',b.rulesets_path,f'$.property_rulesets[{i}].property_type_ref','non-empty required')
  else:ptypes.add(t)
  schema(r.get('value_schema'),c,b.rulesets_path,f'$.property_rulesets[{i}].value_schema')
 open_count=0; fixed=set(); flows={x.get('id') for x in dl(b.rulesets.get('flow_patterns')) if isinstance(x.get('id'),str)}
 for i,r in enumerate(lrs):
  if r.get('property_type_ref')!='link':c.e('LINK_PROPERTY_TYPE_INVALID',b.rulesets_path,f'$.link_rulesets[{i}].property_type_ref','must be link')
  rel=r.get('link_type_ref'); pol=r.get('relation_policy','fixed')
  if pol=='open':
   open_count+=1
   if rel!='*':c.e('OPEN_LINK_WILDCARD_INVALID',b.rulesets_path,f'$.link_rulesets[{i}].link_type_ref','open Link must use *')
  elif isinstance(rel,str):
   if rel in fixed:c.e('LINK_RELATION_DUPLICATE',b.rulesets_path,f'$.link_rulesets[{i}].link_type_ref',f'duplicate {rel!r}')
   fixed.add(rel)
  schema(r.get('value_schema'),c,b.rulesets_path,f'$.link_rulesets[{i}].value_schema')
  ep=r.get('endpoint_constraints')
  if isinstance(ep,dict):
   for side,vals in ep.items():
    for j,v in enumerate(vals if isinstance(vals,list) else []):
     if isinstance(v,str) and v.startswith('entity_nodetype:') and v.split(':',1)[1] not in nts:c.e('ENDPOINT_NODETYPE_UNRESOLVED',b.rulesets_path,f'$.link_rulesets[{i}].endpoint_constraints.{side}[{j}]',v)
     if isinstance(v,str) and v.startswith('property:') and v.split(':',1)[1] not in ptypes and v!='property:link':c.e('ENDPOINT_PROPERTY_UNRESOLVED',b.rulesets_path,f'$.link_rulesets[{i}].endpoint_constraints.{side}[{j}]',v)
  fl=r.get('flow')
  if isinstance(fl,dict):
   if isinstance(fl.get('pattern_ref'),str) and fl['pattern_ref'] not in flows:c.e('FLOW_UNRESOLVED',b.rulesets_path,f'$.link_rulesets[{i}].flow.pattern_ref',fl['pattern_ref'])
   for j,z in enumerate(fl.get('cases',[]) if isinstance(fl.get('cases'),list) else []):
    if isinstance(z,dict) and isinstance(z.get('pattern_ref'),str) and z['pattern_ref'] not in flows:c.e('FLOW_UNRESOLVED',b.rulesets_path,f'$.link_rulesets[{i}].flow.cases[{j}]',z['pattern_ref'])
 if isinstance(b.rulesets.get('generic_link_model'),dict) and b.rulesets['generic_link_model'].get('relation_vocabulary')=='open' and open_count!=1:c.e('GENERIC_LINK_COUNT_INVALID',b.rulesets_path,'$.link_rulesets',f'exactly one open generic Link required, got {open_count}')
 for s,r in readers.items():
  if not isinstance(r,dict):c.e('SECTION_READER_INVALID',b.rulesets_path,f'$.node_ruleset.section_readers.{s}','must be object');continue
  if r.get('kind')=='property_group':
   t=r.get('property_type_ref')
   if t!='link' and t not in ptypes:c.e('SECTION_PROPERTY_UNRESOLVED',b.rulesets_path,f'$.node_ruleset.section_readers.{s}',str(t))
  elif r.get('kind')!='entity_field':c.e('SECTION_READER_KIND_INVALID',b.rulesets_path,f'$.node_ruleset.section_readers.{s}.kind',str(r.get('kind')))
 for i,ps in enumerate(dl(b.rulesets.get('logic_primitive_sets'))):
  seen=set()
  for j,p in enumerate(dl(ps.get('primitives'))):
   op=p.get('op')
   if not isinstance(op,str) or not op:c.e('LOGIC_OP_INVALID',b.rulesets_path,f'$.logic_primitive_sets[{i}].primitives[{j}].op','non-empty required')
   elif op in seen:c.e('LOGIC_OP_DUPLICATE',b.rulesets_path,f'$.logic_primitive_sets[{i}].primitives[{j}].op',op)
   else:seen.add(op)
 return c
def main()->int:
 a=argparse.ArgumentParser();a.add_argument('--spec-set',type=Path);a.add_argument('--ccf',type=Path);a.add_argument('--nodetypes',type=Path);a.add_argument('--rulesets',type=Path);a.add_argument('--dir',type=Path);a.add_argument('--json',action='store_true');a.add_argument('--coverage',action='store_true');x=a.parse_args()
 try:b=resolve_bundle(spec_set=x.spec_set,ccf=x.ccf,nodetypes=x.nodetypes,rulesets=x.rulesets,spec_dir=x.dir,default_start=Path(__file__).parent);c=lint_bundle(b)
 except Exception as e:print(json.dumps({'result':'IMPLEMENTATION_FAILURE','message':str(e)}) if x.json else f'cw_spec_lint: {e}');return 2
 err=sum(z.severity=='ERROR' for z in c.f)
 if x.json:print(json.dumps({'linter_version':VER,'result':'INVALID_SPECIFICATION' if err else 'VALID_SPECIFICATION','findings':[asdict(z) for z in c.f]},indent=2))
 else:
  print(f'CW spec lint v{VER}\nCCF {b.ccf.get("version")} / NodeTypes {b.nodetypes.get("version")} / Rulesets {b.rulesets.get("version")}')
  for z in c.f:print(f'{z.severity} {z.code} {Path(z.file).name} {z.path}: {z.message}')
  print(f'\n{"FAIL" if err else "PASS"}: {err} error(s)')
  if x.coverage:print('Coverage: specification-driven; concrete NodeType/domain vocabulary hardcoded: no; Node sections: RULESET_NODE.section_readers')
 return 1 if err else 0
if __name__=='__main__':raise SystemExit(main())

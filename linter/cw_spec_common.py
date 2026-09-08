from __future__ import annotations
import hashlib,json,os
from dataclasses import dataclass
from pathlib import Path
from typing import Any,Dict,Mapping,Optional,Sequence,Tuple
SPEC_SET_TYPE='cw_specification_set'
class DuplicateKeyError(ValueError):pass
def _pairs(pairs:Sequence[Tuple[str,Any]])->Dict[str,Any]:
 d={}
 for k,v in pairs:
  if k in d:raise DuplicateKeyError(f'duplicate JSON key: {k!r}')
  d[k]=v
 return d
def read_json(p:Path)->Dict[str,Any]:
 d=json.loads(p.read_text(encoding='utf-8'),object_pairs_hook=_pairs)
 if not isinstance(d,dict):raise ValueError(f'{p}: top-level JSON must be object')
 return d
def git_blob_sha(p:Path)->str:
 b=p.read_bytes();return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def classify_spec(d:Mapping[str,Any])->Optional[str]:
 if d.get('type')=='canonical_contract_format' or d.get('id')=='CANONICAL_CONTRACT_FORMAT':return 'ccf'
 if isinstance(d.get('nodetypes'),list) and isinstance(d.get('nodetype_schema'),dict):return 'nodetypes'
 if isinstance(d.get('property_rulesets'),list) and isinstance(d.get('link_rulesets'),list):return 'rulesets'
 return None
@dataclass(frozen=True)
class SpecBundle:
 ccf_path:Path;ccf:Dict[str,Any];nodetypes_path:Path;nodetypes:Dict[str,Any];rulesets_path:Path;rulesets:Dict[str,Any];manifest_path:Optional[Path]=None;manifest:Optional[Dict[str,Any]]=None
def _path(m:Path,v:Any,role:str)->Path:
 s=v if isinstance(v,str) else v.get('path') if isinstance(v,dict) else None
 if not isinstance(s,str):raise ValueError(f'{role} needs path')
 p=Path(s);return p.resolve() if p.is_absolute() else (m.parent/p).resolve()
def load_spec_set(p:Path)->SpecBundle:
 p=p.resolve();m=read_json(p)
 if m.get('type')!=SPEC_SET_TYPE:raise ValueError(f'{p}: invalid spec-set type')
 q=[]
 for role in ('ccf','nodetypes','rulesets'):
  if role not in m:raise ValueError(f'{p}: missing {role}')
  f=_path(p,m[role],role)
  if not f.is_file():raise FileNotFoundError(f)
  if isinstance(m[role],dict) and m[role].get('git_blob_sha'):
   if git_blob_sha(f)!=m[role]['git_blob_sha']:raise ValueError(f'{role} blob hash mismatch')
  q.extend((f,read_json(f)))
 return SpecBundle(*q,p,m)
def explicit(c:Path,n:Path,r:Path)->SpecBundle:
 c,n,r=c.resolve(),n.resolve(),r.resolve();return SpecBundle(c,read_json(c),n,read_json(n),r,read_json(r))
def discover(p:Path)->SpecBundle:
 f={'ccf':[],'nodetypes':[],'rulesets':[]}
 for q in sorted(p.resolve().glob('*.json')):
  try:d=read_json(q);k=classify_spec(d)
  except Exception:continue
  if k:f[k].append((q,d))
 bad=[k for k,v in f.items() if len(v)!=1]
 if bad:raise RuntimeError('spec directory must contain exactly one each; bad: '+','.join(bad))
 return SpecBundle(f['ccf'][0][0],f['ccf'][0][1],f['nodetypes'][0][0],f['nodetypes'][0][1],f['rulesets'][0][0],f['rulesets'][0][1])
def default(start:Path)->SpecBundle:
 for p in [start.resolve(),*start.resolve().parents]:
  m=p/'spec_sets'/'CW_CORE.json'
  if m.is_file():return load_spec_set(m)
  try:return discover(p)
  except Exception:pass
  if (p/'.git').exists():break
 raise RuntimeError('no spec bundle; use --spec-set or explicit files')
def resolve_bundle(*,spec_set=None,ccf=None,nodetypes=None,rulesets=None,spec_dir=None,default_start=None)->SpecBundle:
 modes=sum(x is not None for x in (spec_set,spec_dir))+int(any(x is not None for x in (ccf,nodetypes,rulesets)))
 if modes>1:raise ValueError('choose one specification selection mode')
 if spec_set:return load_spec_set(spec_set)
 if spec_dir:return discover(spec_dir)
 if any(x is not None for x in (ccf,nodetypes,rulesets)):
  if not all(x is not None for x in (ccf,nodetypes,rulesets)):raise ValueError('explicit mode needs all three files')
  return explicit(ccf,nodetypes,rulesets)
 return default(default_start or Path(__file__).parent)

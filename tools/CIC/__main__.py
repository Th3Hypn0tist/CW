from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from . import import_folder, ingest_cw, validate_toolchain
from .cw_version import verify_cw_versions


def _selftest(cw_root=None,spec_set=None)->dict:
    with tempfile.TemporaryDirectory(prefix="cw-cic-selftest-") as tmp:
        root=Path(tmp); source=root/"source"; target=root/"model"; source.mkdir()
        (source/"main.py").write_text("def enabled(flag: bool):\n    if flag:\n        return True\n    return False\n",encoding="utf-8")
        result=import_folder(source,target,cw_root=cw_root,spec_set=spec_set)
        document=ingest_cw(target); verify_cw_versions(document)
        versioned=[e for e in document.get("entities",[]) if isinstance(e,dict) and isinstance(e.get("timestamp"),str) and isinstance(e.get("hash"),str)]
        if len(versioned)!=len(document.get("entities",[])): raise RuntimeError("selftest produced unversioned Entity")
        if "specification_ref" in document: raise RuntimeError("CIC persisted temporary validation binding")
        return {"status":"PASS","files_imported":result.files_imported,"shards":result.shard_count,"entities":len(document.get("entities",[])),"version_stamps":"verified","specification_bound":False}


def main(argv=None)->int:
    parser=argparse.ArgumentParser(prog="python -m tools.CIC"); sub=parser.add_subparsers(dest="command",required=True)
    check=sub.add_parser("validate-tools"); check.add_argument("--cw-root"); check.add_argument("--spec-set")
    selftest=sub.add_parser("selftest"); selftest.add_argument("--cw-root"); selftest.add_argument("--spec-set")
    imp=sub.add_parser("import"); imp.add_argument("code_folder"); imp.add_argument("cw_folder"); imp.add_argument("--force",action="store_true"); imp.add_argument("--cw-root"); imp.add_argument("--spec-set")
    args=parser.parse_args(argv)
    if args.command=="validate-tools":
        report=validate_toolchain(cw_root=args.cw_root,spec_set=args.spec_set); print(json.dumps({"status":"PASS","report":report},ensure_ascii=False,indent=2)); return 0
    if args.command=="selftest":
        print(json.dumps(_selftest(args.cw_root,args.spec_set),ensure_ascii=False,indent=2)); return 0
    result=import_folder(Path(args.code_folder),Path(args.cw_folder),force=args.force,cw_root=args.cw_root,spec_set=args.spec_set)
    print(json.dumps({"status":"OK","code_folder":str(result.code_folder),"cw_folder":str(result.cw_folder),"cw_path":str(result.cw_path),"ir_path":str(result.ir_path),"shards":result.shard_count,"files_seen":result.files_seen,"files_imported":result.files_imported,"diagnostics":result.diagnostic_summary,"specification_bound":False,"version_stamped":True},ensure_ascii=False,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())

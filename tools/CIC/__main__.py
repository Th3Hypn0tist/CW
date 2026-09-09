from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from . import format_filetree, format_links, import_folder, ingest_cw, report_cw, scan_folder, validate_toolchain
from .cw_version import verify_cw_versions
from .report import format_cw_report


def _selftest(cw_root=None, spec_set=None) -> dict:
    with tempfile.TemporaryDirectory(prefix="cw-cic-selftest-") as tmp:
        root = Path(tmp)
        source = root / "source"
        target = root / "model"
        source.mkdir()
        (source / "main.py").write_text(
            "def enabled(flag: bool):\n    if flag:\n        return True\n    return False\n",
            encoding="utf-8",
        )
        result = import_folder(source, target, cw_root=cw_root, spec_set=spec_set)
        document = ingest_cw(target)
        verify_cw_versions(document)
        versioned = [
            entity
            for entity in document.get("entities", [])
            if isinstance(entity, dict)
            and isinstance(entity.get("timestamp"), str)
            and isinstance(entity.get("hash"), str)
        ]
        if len(versioned) != len(document.get("entities", [])):
            raise RuntimeError("selftest produced unversioned Entity")
        if "specification_ref" in document:
            raise RuntimeError("CIC persisted temporary validation binding")
        return {
            "status": "PASS",
            "files_imported": result.files_imported,
            "shards": result.shard_count,
            "entities": len(document.get("entities", [])),
            "version_stamps": "verified",
            "specification_bound": False,
        }


def _forbidden_import_modules(path: Path) -> list[str]:
    forbidden = {"CIC.api_legacy", "CIC.structuretree"}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise RuntimeError(f"cannot inspect CIC Python source {path}: {exc}") from exc

    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for module in forbidden:
                    if alias.name == module or alias.name.startswith(module + "."):
                        hits.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
            for module in forbidden:
                if node.module == module or node.module.startswith(module + "."):
                    hits.add(node.module)
    return sorted(hits)


def _release_check(cw_root=None, spec_set=None) -> dict:
    root = Path(cw_root).expanduser().resolve() if cw_root else next(
        parent for parent in Path(__file__).resolve().parents if (parent / "spec_sets").is_dir() and (parent / "linter").is_dir()
    )
    cic_root = Path(__file__).resolve().parent

    forbidden_files = [path for path in (cic_root / "api_legacy.py", cic_root / "structuretree.py") if path.exists()]
    forbidden_imports: list[str] = []
    for path in cic_root.rglob("*.py"):
        for module in _forbidden_import_modules(path):
            forbidden_imports.append(f"{path.relative_to(root)} -> {module}")
    if forbidden_files or forbidden_imports:
        raise RuntimeError(
            f"CIC release contains forbidden duplicate/domain remnants: files={forbidden_files}, imports={forbidden_imports}"
        )

    tool_report = validate_toolchain(cw_root=root, spec_set=spec_set)
    selftest_report = _selftest(root, spec_set)

    tools_path = str(root / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    suite = unittest.defaultTestLoader.discover(str(cic_root / "tests"), pattern="test*.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("CIC regression suite failed:\n" + stream.getvalue())

    return {
        "status": "PASS",
        "toolchain": "validated",
        "selftest": selftest_report,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "forbidden_files": 0,
        "forbidden_imports": 0,
        "specification_bound": False,
        "cw_root": str(root),
        "spec_report": tool_report,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.CIC")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("validate-tools")
    check.add_argument("--cw-root")
    check.add_argument("--spec-set")

    selftest = sub.add_parser("selftest")
    selftest.add_argument("--cw-root")
    selftest.add_argument("--spec-set")

    release_check = sub.add_parser("release-check")
    release_check.add_argument("--cw-root")
    release_check.add_argument("--spec-set")

    scan = sub.add_parser("scan")
    scan.add_argument("code_folder")

    imp = sub.add_parser("import")
    imp.add_argument("code_folder")
    imp.add_argument("cw_folder")
    imp.add_argument("--force", action="store_true")
    imp.add_argument("--cw-root")
    imp.add_argument("--spec-set")

    report = sub.add_parser("report")
    report.add_argument("cw_input")
    report.add_argument("--json", action="store_true", dest="as_json")

    test = sub.add_parser("test")
    test_sub = test.add_subparsers(dest="test_kind", required=True)
    for name in ("cw", "filetree", "links"):
        item = test_sub.add_parser(name)
        item.add_argument("cw_input")

    printer = sub.add_parser("print")
    print_sub = printer.add_subparsers(dest="print_kind", required=True)
    for name in ("filetree", "links"):
        item = print_sub.add_parser(name)
        item.add_argument("cw_input")

    args = parser.parse_args(argv)
    if args.command == "validate-tools":
        print(json.dumps({"status": "PASS", "report": validate_toolchain(cw_root=args.cw_root, spec_set=args.spec_set)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "selftest":
        print(json.dumps(_selftest(args.cw_root, args.spec_set), ensure_ascii=False, indent=2))
        return 0
    if args.command == "release-check":
        print(json.dumps(_release_check(args.cw_root, args.spec_set), ensure_ascii=False, indent=2))
        return 0
    if args.command == "scan":
        result = scan_folder(Path(args.code_folder))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["cw_gate_b"]["status"] == "PASS" else 1
    if args.command == "import":
        result = import_folder(Path(args.code_folder), Path(args.cw_folder), force=args.force, cw_root=args.cw_root, spec_set=args.spec_set)
        print(json.dumps({
            "status": "OK",
            "code_folder": str(result.code_folder),
            "cw_folder": str(result.cw_folder),
            "cw_path": str(result.cw_path),
            "ir_path": str(result.ir_path),
            "shards": result.shard_count,
            "files_seen": result.files_seen,
            "files_imported": result.files_imported,
            "diagnostics": result.diagnostic_summary,
            "specification_bound": False,
            "version_stamped": True,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.command == "report":
        result = report_cw(Path(args.cw_input))
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else format_cw_report(result))
        return 0 if result["verdict"] == "PASS" else 1
    if args.command == "test":
        document = ingest_cw(Path(args.cw_input))
        if args.test_kind == "filetree":
            format_filetree(document)
        elif args.test_kind == "links":
            format_links(document)
        print(json.dumps({"status": "PASS", "test": args.test_kind}))
        return 0
    if args.command == "print":
        document = ingest_cw(Path(args.cw_input))
        print(format_filetree(document) if args.print_kind == "filetree" else format_links(document))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

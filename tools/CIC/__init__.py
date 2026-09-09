from __future__ import annotations

import sys

# CW owns the authoritative CIC source under tools/CIC, while synchronized
# consumer copies may live as a top-level CIC package. Register the canonical
# package alias before importing submodules so the same implementation works in
# both locations without rewriting baseline module imports.
sys.modules.setdefault("CIC", sys.modules[__name__])

from .api import ImportBundle, ImportResult, ToolchainValidationError, import_files, import_folder, validate_toolchain
from .cw import CWValidationError, file_refs, filetree, format_filetree, format_links, ingest_cw, ingest_cw_files, links, load_cw, validate_cw
from .report import build_cw_report, format_cw_report, report_cw
from .scan import scan_folder

__all__ = [
    "ImportBundle",
    "ImportResult",
    "ToolchainValidationError",
    "import_files",
    "import_folder",
    "validate_toolchain",
    "CWValidationError",
    "load_cw",
    "validate_cw",
    "ingest_cw",
    "ingest_cw_files",
    "file_refs",
    "filetree",
    "format_filetree",
    "links",
    "format_links",
    "build_cw_report",
    "format_cw_report",
    "report_cw",
    "scan_folder",
]

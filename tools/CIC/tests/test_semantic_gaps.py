from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from CIC import import_folder, import_files
from CIC.profiles import profile_options
from CIC.semantic_gaps import gap_report


RUNNER_SOURCE = '''from concurrent.futures import ThreadPoolExecutor
import threading

_executor = None

def ensure_worker():
    global _executor
    _executor = ThreadPoolExecutor(max_workers=8)
    worker = threading.Thread(target=_worker_loop)
    worker.start()

def stop_job(job, cancel_event):
    cancel_event.set()
    job.future.cancel()

def _job_entry(raw_line, cancel_event):
    return _call_step_executor(raw_line, cancel_event)

def _worker_loop():
    return None
'''

STORE_SOURCE = '''RUNNER_DEFS_SYMBOL = "#SYSTEM:runtime:runners"
'''


class CICSemanticGapTests(unittest.TestCase):
    def test_aigmos_runner_rules_classify_gaps(self) -> None:
        bundle = import_files([
            {"path": "system/runtime/runner.py", "content": RUNNER_SOURCE},
            {"path": "system/runtime/runner_store.py", "content": STORE_SOURCE},
        ])
        report = gap_report(bundle.ir, profile_options("aigmos")["semantic_gap_rules"])
        ids = {item["id"] for item in report["gaps"]}
        self.assertIn("AIGMOS_RUNNER_CONCURRENT_SCHEDULING", ids)
        self.assertIn("AIGMOS_RUNNER_CANCELLATION", ids)
        self.assertIn("AIGMOS_RUNNER_DYNAMIC_COMMAND_DISPATCH", ids)
        self.assertIn("AIGMOS_RUNNER_DURABLE_DEFINITION_STATE", ids)
        self.assertGreaterEqual(report["summary"]["cw_semantic_gaps"], 3)
        self.assertEqual(report["summary"]["cic_mapping_gaps"], 1)

    def test_profile_import_writes_gap_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "package"
            runtime = source / "system" / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "runner.py").write_text(RUNNER_SOURCE, encoding="utf-8")
            (runtime / "runner_store.py").write_text(STORE_SOURCE, encoding="utf-8")
            import_folder(source, target, profile="aigmos")
            report_path = target / "Diagnostics" / "semantic_gaps.json"
            self.assertTrue(report_path.is_file())
            import json
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["canonical_semantic_authority"])
            self.assertGreaterEqual(report["summary"]["blocking"], 3)


if __name__ == "__main__":
    unittest.main()

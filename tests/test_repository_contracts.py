#!/usr/bin/env python3
"""Check replay tooling contracts and deliberately exercise failure recording."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_core


class ReplayContracts(unittest.TestCase):
    def test_shell_entry_points_parse(self):
        for path in sorted((check_core.ROOT / "scripts").glob("*.sh")):
            with self.subTest(script=path.name):
                subprocess.run(["bash", "-n", str(path)], check=True)

    def test_full_preserves_regression_order(self):
        names = [name for name, _ in check_core.commands("full")]
        required = ["original-regression", "timing-regression", "buffered-regression",
                    "stage5-stress", "stage5-reset-phases", "stage5-live-audit", "core-evidence"]
        self.assertEqual([name for name in names if name in required], required)

    def test_evidence_needs_no_simulator(self):
        commands = check_core.commands("evidence")
        self.assertTrue(all(argv[0] == "python3" for _, argv in commands))
        self.assertEqual(commands[-1][1], ["python3", "benchmarks/report_core.py", "--check"])

    def test_quick_does_not_overwrite_partial_regression_summaries(self):
        names = [name for name, _ in check_core.commands("quick")]
        self.assertIn("native-smoke", names)
        self.assertNotIn("stage5-stress", names)
        self.assertNotIn("original-regression", names)
        self.assertNotIn("timing-accounting", names)
        self.assertNotIn("buffered-accounting", names)
        self.assertNotIn("core-report-tests", names)

    def test_nonzero_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "failed.log"
            code = check_core.execute([sys.executable, "-c", "print('deliberate failure'); raise SystemExit(7)"], log, 5)
            self.assertEqual(code, 7)
            self.assertIn("deliberate failure", log.read_text())

    def test_timeout_is_named(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "timeout.log"
            code = check_core.execute([sys.executable, "-c", "import time; time.sleep(10)"], log, 0.1)
            self.assertEqual(code, 124)
            self.assertIn("CHECK_CORE_TIMEOUT", log.read_text())


if __name__ == "__main__":
    unittest.main()

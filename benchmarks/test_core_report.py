#!/usr/bin/env python3
"""Deliberate evidence/report faults using preserved native records, not a DUT model."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import report_core as core


class CoreAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((core.ROOT / core.SUMMARY).read_text())
        cls.cases = core.benchmark.matrix()

    def matrix_fault(self, change):
        report = copy.deepcopy(self.report)
        change(report)
        with self.assertRaises(core.AuditError):
            core.validate_matrix(report, self.cases)

    def test_complete_matrix(self):
        self.assertEqual(len(core.validate_matrix(self.report, self.cases)), 2616)

    def test_missing_run(self):
        self.matrix_fault(lambda report: report['runs'].pop())

    def test_duplicate_replacing_run(self):
        self.matrix_fault(lambda report: report['runs'].__setitem__(-1, report['runs'][0]))

    def test_changed_matrix_hash(self):
        self.matrix_fault(lambda report: report.__setitem__('matrix_sha256', '0' * 64))

    def test_unmatched_memory_settings(self):
        self.matrix_fault(lambda report: report['runs'][0]['config'].__setitem__('a_interval', 99))

    def test_unmatched_input_schedule(self):
        self.matrix_fault(lambda report: report['runs'][0]['input_sha256'].__setitem__('dataset', '0' * 64))

    def test_failed_run(self):
        self.matrix_fault(lambda report: report['runs'][0].__setitem__('passed', False))

    def test_stale_or_missing_source_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'source.sv').write_text('original\n')
            manifest = {'source.sv': core.digest(root / 'source.sv')}
            core.verify_hashes(root, manifest, ['source.sv'])
            (root / 'source.sv').write_text('changed\n')
            with self.assertRaises(core.AuditError):
                core.verify_hashes(root, manifest, ['source.sv'])
            with self.assertRaises(core.AuditError):
                core.verify_hashes(root, {}, ['source.sv'])

    def run_fixture(self, root):
        run = copy.deepcopy(self.report['runs'][0])
        original = core.ROOT / run['records']
        path = root / 'blocks.csv'
        path.write_bytes(original.read_bytes())
        (root / 'run.log').write_text('PASS benchmark\n')
        run['records'] = 'blocks.csv'
        self.store(root, run)
        return run, path

    def store(self, root, run):
        (root / 'result.json').write_text(json.dumps(run))

    def test_real_native_record_reaccounts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, _ = self.run_fixture(root)
            core.verify_run(root, run)

    def test_raw_record_hash_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, path = self.run_fixture(root)
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(core.AuditError, 'record hash'):
                core.verify_run(root, run)

    def test_bad_conservation_even_with_updated_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, path = self.run_fixture(root)
            rows = core.benchmark.rows(path)
            rows[0]['backlog'] += 1
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            run['records_sha256'] = core.digest(path)
            self.store(root, run)
            with self.assertRaisesRegex(core.AuditError, 'accounting failed'):
                core.verify_run(root, run)

    def test_modified_cached_metric_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, _ = self.run_fixture(root)
            run['metrics']['steady']['words_per_cycle'] += .1
            self.store(root, run)
            with self.assertRaisesRegex(core.AuditError, 'Recomputed metrics'):
                core.verify_run(root, run)

    def test_missing_native_pass_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, _ = self.run_fixture(root)
            (root / 'run.log').write_text('compilation failed\n')
            with self.assertRaisesRegex(core.AuditError, 'PASS marker'):
                core.verify_run(root, run)

    def test_per_run_summary_disagreement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, _ = self.run_fixture(root)
            stored = copy.deepcopy(run)
            stored['passed'] = False
            self.store(root, stored)
            with self.assertRaisesRegex(core.AuditError, 'Per-run result'):
                core.verify_run(root, run)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(core.AuditError):
            core.safe_path(core.ROOT, '../outside.csv')

    def test_optimized_python_fails_closed(self):
        result = subprocess.run([sys.executable, '-O', str(Path(core.__file__)), '--check'],
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Run without Python -O', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)

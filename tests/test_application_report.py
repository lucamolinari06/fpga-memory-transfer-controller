#!/usr/bin/env python3
"""Fault the report's declared-input/configuration binding, without running a DUT."""
import copy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import report_application as report


class ReportContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=json.loads((report.app.OUT/'summary.json').read_text())
        cls.verification=json.loads((report.app.OUT/'verification.json').read_text())
        cls.updates=json.loads((report.app.OUT/'updates.json').read_text())
        cls.declared=report.declared_inputs()

    def run_copy(self):
        return copy.deepcopy(self.summary['runs'][0])

    def reject(self,run,diagnostic):
        with self.assertRaisesRegex(AssertionError,diagnostic):
            report.validate_run_contract(run,self.declared)

    def test_all_native_run_contracts_match_declarations(self):
        runs=self.summary['runs']+self.verification['records']+self.updates['records']
        self.assertEqual(len(runs),428)
        for run in runs:
            report.validate_run_contract(run,self.declared)
        report.validate_inputs(self.summary['input_sha256'],self.declared)
        report.validate_inputs(self.verification['inputs'],self.declared)
        report.validate_inputs(self.updates['inputs'],self.declared)

    def test_self_consistent_wrong_timing_is_rejected(self):
        run=self.run_copy()
        run['config']['b_latency']=999
        run['command']=[value if not value.startswith('+b_latency=') else '+b_latency=999' for value in run['command']]
        self.reject(run,'DECLARED_CONFIG')

    def test_mislabeled_timing_point_is_rejected(self):
        run=self.run_copy();run['case']['timing']='a_slow'
        self.reject(run,'DECLARED_CONFIG')

    def test_missing_and_extra_config_are_rejected(self):
        for operation in ('missing','extra'):
            with self.subTest(operation=operation):
                run=self.run_copy()
                if operation=='missing':del run['config']['a_interval']
                else:run['config']['unlisted_control']=1
                self.reject(run,'DECLARED_CONFIG')

    def test_wrong_workload_input_is_rejected(self):
        run=self.run_copy()
        source=next(name for name in run['input_sha256'] if name.endswith('/sequential.hex'))
        run['input_sha256'][source.replace('sequential','hot')]=run['input_sha256'].pop(source)
        self.reject(run,'DECLARED_INPUT_MANIFEST')

    def test_changed_fixture_hash_is_rejected(self):
        inputs=dict(self.declared)
        name=next(name for name in inputs if name.endswith('/dataset.hex'))
        inputs[name]='0'*64
        with self.assertRaisesRegex(AssertionError,'DECLARED_INPUT_MANIFEST'):
            report.validate_inputs(inputs,self.declared,False)

    def test_wrong_permutation_seed_is_rejected(self):
        records=list(range(128));random.Random(report.app.SEED+1).shuffle(records)
        data=''.join(f'{16*record:08x}\n' for record in records*4).encode()
        inputs=dict(self.declared)
        name=next(name for name in inputs if name.endswith('/permuted.hex'))
        inputs[name]=hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(AssertionError,'DECLARED_INPUT_MANIFEST'):
            report.validate_inputs(inputs,self.declared,False)

    def test_missing_summary_input_is_rejected(self):
        inputs=dict(self.declared);inputs.pop(next(iter(inputs)))
        with self.assertRaisesRegex(AssertionError,'DECLARED_INPUT_MANIFEST'):
            report.validate_inputs(inputs,self.declared,False)

    def test_wrong_expected_diagnostic_is_rejected(self):
        run=copy.deepcopy(next(run for run in self.verification['records'] if run['case'].get('fault')==1))
        run['expected_failure']='APP_TIMEOUT'
        self.reject(run,'EXPECTED_DIAGNOSTIC')

    def test_bounds_diagnostic_depends_on_architecture(self):
        for arch,diagnostic in [('b_only','APP_MEMORY_BOUNDS'),('hybrid','APP_MEMORY_BOUNDS'),
                                ('header_first','HEADER_COMMAND_ADDRESS'),('cached_b','CACHE_REQUEST_BOUNDS')]:
            self.assertEqual(report.expected_failure(dict(arch=arch,fault=5)),diagnostic)

    def test_recorded_argv_must_match_declared_config(self):
        run=self.run_copy()
        run['command']=[value if not value.startswith('+b_latency=') else '+b_latency=999' for value in run['command']]
        self.reject(run,'RECORDED_CONFIG_ARG')

    def test_duplicate_plusarg_is_rejected(self):
        run=self.run_copy();run['command'].append('+b_latency=12')
        self.reject(run,'DUPLICATE_PLUSARG')

    def test_wrong_recorded_input_path_is_rejected(self):
        run=self.run_copy()
        run['command']=[value if not value.startswith('+fixture=') else '+fixture=/elsewhere/not-the-fixture.hex' for value in run['command']]
        self.reject(run,'RECORDED_INPUT_ARG')

    def test_optimized_python_fails_closed(self):
        result=subprocess.run([sys.executable,'-O',str(ROOT/'benchmarks/report_application.py'),'--check'],
                              capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Run without Python -O',result.stderr)


if __name__=='__main__':
    unittest.main(verbosity=2)

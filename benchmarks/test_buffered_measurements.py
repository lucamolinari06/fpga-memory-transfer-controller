#!/usr/bin/env python3
"""Accounting checks use the actual approved two-block RTL trace, including corruption."""
import csv,json,tempfile,unittest
from pathlib import Path
import run_double_buffer as b
class Accounting(unittest.TestCase):
    def setUp(self):
        self.case=dict(name='hand_table',N=8,S=3,early=1,profile=0,workload='sequential',warmup=1,measured=1)
        self.path=b.ROOT/'build/stage4/hand_table/blocks.csv';self.data=b.rows(self.path)
    def measure(self,data):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'records.csv'
            with path.open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
            return b.summarize(path,self.case,2,2,b.old.DEFAULTS)
    def test_known_two_block_trace(self):
        m=self.measure(self.data)
        self.assertEqual((m['startup_first'],m['whole_intervals'],m['steady']['cycles']),(5,25,9))
        self.assertEqual(m['latency']['command_first']['mean'],17)
        self.assertGreater(self.data[0]['backlog'],0)
        self.assertLess(m['steady']['a_beats']+m['steady']['b_beats'],m['steady']['useful'])
    def reject(self,key,value):
        self.data[0][key]=value
        with self.assertRaises(AssertionError):self.measure(self.data)
    def test_backlog_corruption(self):self.reject('backlog',0)
    def test_occupancy_corruption(self):self.reject('occupancy',0)
    def test_capacity_corruption(self):self.reject('backlog_max',17)
    def test_sink_schedule_corruption(self):self.reject('intentional',1)
    def test_wrong_command_address(self):self.reject('base',264)
    def test_wrong_public_request(self):self.reject('request_a',0)
    def test_boundary_bypass(self):
        self.data[1]['first']=17
        with self.assertRaises(AssertionError):self.measure(self.data)
    def test_missing_record(self):
        with self.assertRaises(AssertionError):self.measure(self.data[:1])
    def test_gated_control(self):
        self.case['early']=0
        with self.assertRaises(AssertionError):self.measure(self.data)
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Accounting))
    root=b.ROOT/'build/stage4_accounting';root.mkdir(exist_ok=True)
    (root/'summary.json').write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,source_sha256=b.old.hashes(['benchmarks/test_buffered_measurements.py','benchmarks/run_double_buffer.py'])),indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)

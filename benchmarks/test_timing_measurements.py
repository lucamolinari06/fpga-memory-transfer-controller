#!/usr/bin/env python3
"""Accounting mutation tests based on a real fixed-table RTL run."""
import csv, tempfile, unittest
from pathlib import Path
import run_memory_timing as t
class Accounting(unittest.TestCase):
    def setUp(self):
        self.path=t.ROOT/'build/memory_timing_integration/table/blocks.csv'
        with self.path.open() as stream:self.rows=list(csv.DictReader(stream))
        self.case=dict(N=4,S=2,warmup=1,measured=1,early=1,profile=3)
        self.cfg=dict(t.old.DEFAULTS,a_interval=1,b_latency=2)
    def check(self):return t.summarize(self.path,self.case,2,self.cfg,[0]*8192)
    def mutate(self,key,delta):
        self.rows[-1][key]=str(int(self.rows[-1][key])+delta)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'blocks.csv'
            with p.open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(self.rows[0]));w.writeheader();w.writerows(self.rows)
            self.path=p
            with self.assertRaises(AssertionError):self.check()
    def test_fixed(self):
        m=self.check();self.assertEqual((m['whole_intervals'],m['steady']['cycles']),(29,11))
        self.assertEqual(m['latency']['command_first']['mean'],5)
        self.assertEqual(m['latency']['command_complete']['mean'],10)
    def test_service(self):self.mutate('a_grants',1)
    def test_ready(self):self.mutate('intentional',1)
    def test_busy(self):self.mutate('b_busy',1)
    def test_first_valid(self):self.mutate('valid_first_b',1)
    def test_address(self):self.mutate('base',4)
    def test_occupancy(self):self.mutate('slot_sum',1)
    def test_shared_cap(self):self.mutate('shared_reserved',100)
if __name__=='__main__':unittest.main()

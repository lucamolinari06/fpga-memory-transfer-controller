#!/usr/bin/env python3
"""Deliberately corrupt synthetic accounting ledgers, never simulate the DUT."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest

import run_application as app


class Accounting(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.directory = self.root/"runs/case"
        self.directory.mkdir(parents=True)
        (self.root/"inputs").mkdir()
        self.values = app.fixture_words()
        self.fixture = self.root/"inputs/dataset.hex"
        self.fixture.write_text("".join(f"{v:08x}\n" for v in self.values))
        self.case = dict(arch="b_only",workload="sequential",threshold=50,queries=1)
        self.records=[]
        for i,base in enumerate(app.order_for("sequential",1)):
            selected=self.values[base+1]<50
            self.records.append(dict(record=i,base=base,release=2*i,offered=20*i,command=20*i,
                result=20*i+19,id=self.values[base],selected=int(selected),
                sum=sum(self.values[base+2:base+16]) if selected else 0,
                a_beats=0,b_beats=16*(i+1),b_requests=i+1,cache_hits=0,cache_misses=0))
        selected=sum(r['selected'] for r in self.records)
        self.metrics=dict(preload_cycles=0,preload_words=0,query_cycles=2560,records=128,
            selected=selected,a_beats=0,b_beats=2048,b_requests=128,useless_payload=14*(128-selected),
            cache_hits=0,cache_misses=0,reset_applied=0)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self):
        for name,rows in [("records",self.records),("metrics",[self.metrics])]:
            with (self.directory/f"{name}.csv").open("w") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

    def test_valid_ledger_and_nearest_rank(self):
        self.write(); result=app.account(self.directory,self.case)
        self.assertEqual(result['end_to_end_cycles'],2560)
        self.assertEqual(result['command_to_result']['p99'],19)
        self.assertEqual(app.distribution([1,2,3,4])['p95'],4)

    def test_each_result_field_corruption_is_rejected(self):
        original=copy.deepcopy(self.records)
        for field in ('id','selected','sum','base','record'):
            with self.subTest(field=field):
                self.records=copy.deepcopy(original);self.records[0][field]^=1;self.write()
                with self.assertRaises(AssertionError):app.account(self.directory,self.case)

    def test_missing_result_is_rejected(self):
        self.records.pop();self.write()
        with self.assertRaisesRegex(AssertionError,'RESULT_COUNT'):app.account(self.directory,self.case)

    def test_traffic_and_preload_faults_are_rejected(self):
        original=self.metrics.copy()
        for field in ('a_beats','b_beats','b_requests','useless_payload','preload_words','preload_cycles','cache_hits','query_cycles'):
            with self.subTest(field=field):
                self.metrics=original.copy();self.metrics[field]+=1;self.write()
                with self.assertRaises(AssertionError):app.account(self.directory,self.case)

    def test_release_schedule_is_independent_and_checked(self):
        self.records[1]['release']=3;self.write()
        with self.assertRaisesRegex(AssertionError,'RESULT_TIMESTAMPS'):app.account(self.directory,self.case)

    def test_fixture_contract_rejects_bad_keys_ids_and_width(self):
        for index,value in [(1,100),(16,self.values[0]),(2,2**32)]:
            with self.subTest(index=index):
                values=self.values.copy();values[index]=value
                self.fixture.write_text("".join(f"{v:x}\n" for v in values))
                with self.assertRaises(AssertionError):app.read_fixture(self.fixture)

    def test_update_phase_accounting_and_changed_results(self):
        self.case.update(workload='hot',update_epoch=1)
        for suffix in ('.epoch0.csv',''):
            values=self.values.copy()
            if not suffix:values[1]=99;values[18]=0xffffffff
            records=[]
            for i,base in enumerate(app.order_for('hot',1)):
                selected=values[base+1]<50
                records.append(dict(record=i,base=base,release=2*i,offered=20*i,command=20*i,
                    result=20*i+19,id=values[base],selected=int(selected),
                    sum=sum(values[base+2:base+16]) if selected else 0,
                    a_beats=0,b_beats=16*(i+1),b_requests=i+1,cache_hits=0,cache_misses=0))
            selected=sum(r['selected'] for r in records)
            metrics=dict(self.metrics,selected=selected,useless_payload=14*(128-selected),reset_applied=int(not suffix))
            for name,rows in [('records',[*records]),('metrics',[metrics])]:
                with (self.directory/(name+'.csv'+suffix)).open('w') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        phases=dict(first_preload_cycles=0,first_query_cycles=2560,quiet_cycles=20,write_cycles=2,
                    writes=2,reset_cycles=3,second_preload_cycles=0,second_query_cycles=2560,total_cycles=5145)
        def write_phases(values):
            with (self.directory/'metrics.csv.update.csv').open('w') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(values));writer.writeheader();writer.writerow(values)
        write_phases(phases)
        self.assertEqual(app.account_update(self.directory,self.case)['phases']['total_cycles'],5145)
        for field in ('writes','reset_cycles','total_cycles','second_preload_cycles'):
            with self.subTest(field=field):
                corrupted=dict(phases);corrupted[field]+=1;write_phases(corrupted)
                with self.assertRaises(AssertionError):app.account_update(self.directory,self.case)


if __name__=='__main__':
    unittest.main()

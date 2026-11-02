#!/usr/bin/env python3
"""Provenance/pairing audit of the completed finite experiment (no new simulation)."""
import hashlib,json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/raw/memory_timing'
def main():
    report=json.loads((OUT/'summary.json').read_text())
    assert report['passed'] and len(report['runs'])==1230 and len(report['comparisons'])==410
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    for path,h in report['source_sha256'].items():assert digest(ROOT/path)==h,path
    for path in ['build/memory_timing/summary.json','build/memory_timing_integration/summary.json']:
        verification=json.loads((ROOT/path).read_text());assert verification['passed']
        for source,h in verification['source_sha256'].items():assert digest(ROOT/source)==h,source
    groups=defaultdict(list);checked_inputs={}
    for r in report['runs']:
        assert r['passed'] and r['source_sha256']==report['source_sha256']
        assert (ROOT/r['records']).is_file()
        for path,h in r['input_sha256'].items():
            if path not in checked_inputs:checked_inputs[path]=digest(ROOT/path)
            assert checked_inputs[path]==h,path
        groups[r['case']['name']].append(r)
    for name,rs in groups.items():
        assert len(rs)==3 and {r['mode'] for r in rs}=={'A-only','B-only','hybrid'}
        assert len({json.dumps(r['case'],sort_keys=True) for r in rs})==1
        assert len({json.dumps(r['input_sha256'],sort_keys=True) for r in rs})==1
        if rs[0]['case']['group']!='rate_control':
            assert len({json.dumps(r['config'],sort_keys=True) for r in rs})==1
        else:
            a,b,h=rs;assert a['config']==b['config']
            assert dict(a['config'],a_interval=2,b_interval=2)==h['config']
    result=dict(passed=True,runs=1230,matched_triplets=len(groups),distinct_input_files=len(checked_inputs),
                words_checked=sum(r['metrics']['whole']['useful'] for r in report['runs']),
                statement='Current source hashes match; every input hash matches; workload/calendar/configuration paired across every triplet, except explicitly labeled nominal-rate controls.')
    (OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS provenance and pairing audit',result['runs'],'runs')
if __name__=='__main__':main()

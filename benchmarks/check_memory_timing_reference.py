#!/usr/bin/env python3
"""Exact fresh P0 comparison and immutability check of the historical experiment."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'results/raw/memory_timing'
    old=json.loads((ROOT/'results/raw/single_buffer/summary.json').read_text())
    new=json.loads((out/'p0/summary.json').read_text())
    assert old['passed'] and new['passed'] and len(old['runs'])==len(new['runs'])==78
    for a,b in zip(old['runs'],new['runs']):
        assert a['case']==b['case'] and a['mode']==b['mode'] and a['metrics']==b['metrics']
        assert (ROOT/a['records']).read_bytes()==(ROOT/b['records']).read_bytes()
    manifest=json.loads((out/'reference-sha256.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
    (out/'p0-equivalence.json').write_text(json.dumps(dict(passed=True,runs=78,per_block_csv='byte-identical',
        metrics='exactly equal',reference_files_verified=len(manifest)),indent=2)+'\n')
    print('PASS exact P0 replay and preserved reference:',len(manifest),'files')
if __name__=='__main__':main()

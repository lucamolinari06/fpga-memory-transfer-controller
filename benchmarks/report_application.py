#!/usr/bin/env python3
"""Re-audit native application records before deriving finite-tier comparisons."""
import argparse
from collections import Counter,defaultdict
import csv
import io
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import run_application as app


def expected_config(case):
    config=dict(zip(('a_latency','a_interval','b_latency','b_interval'),app.TIMINGS[case['timing']]))
    config.update(ready_period=case.get('ready_period',9),ready_cycles=case.get('ready_cycles',6),
                  reset_at=case.get('reset_at',0),fault=case.get('fault',0),update_epoch=case.get('update_epoch',0))
    return config


def expected_failure(case):
    fault=case.get('fault',0)
    if fault==5:
        return {'header_first':'HEADER_COMMAND_ADDRESS','cached_b':'CACHE_REQUEST_BOUNDS'}.get(case['arch'],'APP_MEMORY_BOUNDS')
    return {0:None,1:'APP_SUM_MISMATCH',2:'APP_SELECTION_MISMATCH',3:'APP_ID_MISMATCH',4:'APP_MISSING_RESULT'}[fault]


def declared_inputs():
    """Bind the published benchmark to its declared fixture and seed, not itself."""
    inputs={'dataset.hex':app.fixture_words()}
    inputs.update({kind+'.hex':app.order_for(kind,4) for kind in app.WORKLOADS})
    prefix=str(app.OUT.relative_to(ROOT))+'/inputs/'
    return {prefix+name:hashlib.sha256(''.join(f'{word:08x}\n' for word in words).encode()).hexdigest()
            for name,words in inputs.items()}


def validate_inputs(recorded,declared,check_files=True):
    assert recorded==declared,'DECLARED_INPUT_MANIFEST'
    if check_files:
        for path,digest in recorded.items():assert app.sha(ROOT/path)==digest,('INPUT_CONTENT',path)


def validate_run_contract(run,declared):
    case=run['case']
    config=expected_config(case)
    assert run['config']==config,'DECLARED_CONFIG'
    prefix=str(app.OUT.relative_to(ROOT))+'/inputs/'
    names=(prefix+'dataset.hex',prefix+case['workload']+'.hex')
    validate_inputs(run['input_sha256'],{name:declared[name] for name in names},False)
    assert run['expected_failure']==expected_failure(case),'EXPECTED_DIAGNOSTIC'
    argv=run['command']
    assert argv and all(value.startswith('+') and '=' in value for value in argv[1:]),'RECORDED_ARGV'
    pairs=[value[1:].split('=',1) for value in argv[1:]]
    args=dict(pairs)
    assert len(args)==len(pairs),'DUPLICATE_PLUSARG'
    assert set(args)==set(config)|{'fixture','order','records','metrics','threshold','queries'},'RECORDED_ARGV_FIELDS'
    for key,value in dict(config,threshold=case['threshold'],queries=case['queries']).items():
        assert args[key]==str(value),('RECORDED_CONFIG_ARG',key)
    # Historical absolute prefixes may differ when the archive is moved. Match
    # repository-relative suffixes, and never execute recorded command strings.
    for key,name in [('fixture',names[0]),('order',names[1])]:
        assert args[key].endswith('/'+name),('RECORDED_INPUT_ARG',key)
    log_parent=str(Path(run['log']).parent)
    for key in ('records','metrics'):
        assert args[key].endswith('/'+log_parent+'/'+key+'.csv'),('RECORDED_OUTPUT_ARG',key)


def outcome(candidate,reference):
    return 'win' if candidate < reference else 'tie' if candidate == reference else 'loss'


def csv_text(rows):
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    return stream.getvalue()


def audit():
    if not __debug__:
        raise RuntimeError('Run without Python -O: native accounting uses assertions')
    summary=json.loads((app.OUT/'summary.json').read_text())
    verification=json.loads((app.OUT/'verification.json').read_text())
    updates=json.loads((app.OUT/'updates.json').read_text())
    assert summary['passed'] and summary['scope']=='full' and len(summary['runs'])==384
    assert summary['source_sha256']==app.hashes()==verification['source_sha256']
    assert verification['passed'] and verification['outcomes']==40 and len(verification['records'])==40
    assert updates['passed'] and updates['outcomes']==4 and updates['source_sha256']==summary['source_sha256']
    assert [r['case'] for r in updates['records']]==list(app.update_matrix()),'UPDATE_MATRIX'
    assert [r['case'] for r in summary['runs']]==list(app.matrix()),'MATRIX'
    assert [r['case'] for r in verification['records']]==list(app.verification_matrix()),'VERIFICATION_MATRIX'
    assert summary['seed']==app.SEED,'DECLARED_SEED'
    declared=declared_inputs()
    validate_inputs(summary['input_sha256'],declared)
    validate_inputs(verification['inputs'],declared)
    validate_inputs(updates['inputs'],declared)
    for run in verification['records']+summary['runs']+updates['records']:
        assert run['passed'] and run['source_sha256']==summary['source_sha256']
        validate_run_contract(run,declared)
        for p,h in run['input_sha256'].items(): assert app.sha(ROOT/p)==h,p
        log=ROOT/run['log'];assert app.sha(log)==run['log_sha256']
        assert json.loads((log.parent/'result.json').read_text())==run
        if run['expected_failure']:
            assert run['exit_code'] not in (0,124) and run['expected_failure'] in log.read_text()
        else:
            assert run['exit_code']==0 and 'PASS application' in log.read_text()
            assert app.sha(ROOT/run['records'])==run['records_sha256']
            assert app.account(log.parent,run['case'])==run['metrics']
            if run['case'].get('update_epoch'):
                assert app.account_update(log.parent,run['case'])==run['update']
                assert set(run['update_file_sha256'])=={'records.csv.epoch0.csv','metrics.csv.epoch0.csv','metrics.csv.update.csv'},'UPDATE_FILE_MANIFEST'
                for p,h in run['update_file_sha256'].items():assert app.sha(log.parent/p)==h,p
    groups=defaultdict(dict)
    for run in summary['runs']:
        c=run['case']; key=(c['workload'],c['threshold'],c['timing'],c['queries'])
        assert c['arch'] not in groups[key];groups[key][c['arch']]=run
    for group in groups.values():
        assert set(group)==set(app.ARCHES)
        assert len({json.dumps(r['config'],sort_keys=True) for r in group.values()})==1
        assert len({json.dumps(r['input_sha256'],sort_keys=True) for r in group.values()})==1
    return summary,verification,groups,updates


def render(summary,verification,groups,updates):
    flat=[];paired=[]
    for run in summary['runs']:
        row=dict(run['case'])
        for key,value in run['metrics'].items():
            if isinstance(value,dict):
                row.update({key+'_'+stat:val for stat,val in value.items()})
            elif not isinstance(value,list):row[key]=value
        flat.append(row)
    for key,group in groups.items():
        row=dict(zip(('workload','threshold','timing','queries'),key))
        for arch,run in group.items():
            m=run['metrics']
            for metric in ('end_to_end_cycles','query_cycles','preload_cycles','b_beats','useless_payload','cache_hits','cache_misses'):
                row[arch+'_'+metric]=m[metric]
            row[arch+'_release_p99']=m['release_to_result']['p99']
        for arch in app.ARCHES[1:]:
            row[arch+'_vs_b_only']=outcome(row[arch+'_end_to_end_cycles'],row['b_only_end_to_end_cycles'])
        best=min(row[a+'_end_to_end_cycles'] for a in app.ARCHES)
        row['fastest_architectures']=';'.join(a for a in app.ARCHES if row[a+'_end_to_end_cycles']==best)
        paired.append(row)
    rows=['# Finite-tier record analytics: native application results','',
          '384 native runs form 96 matched four-way configurations. Each architecture processes identical 128-record query orders, thresholds, release schedules, and readiness patterns. Both stores are finite: B holds 2,048 authoritative words; header A or cache data capacity is 256 words. Header preload is actual B reads and A writes, included in end-to-end cycles. These are exploratory simulation timings, not measured hardware.','',
          f"The separate correctness campaign passes {verification['outcomes']} outcomes: 20 clean cases and 20 named expected failures. Every benchmark result is independently checked by logical record address and fixture values; traffic and cache accounting are re-derived by this report.",'',
          '## Selected comparisons, including the preload bill','',
          '| Workload | Threshold | Timing | Queries | B-only cycles | Eager hybrid cycles | Header-first cycles | Cached B cycles | Fastest |',
          '| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for row in paired:
        if row['threshold'] in (25,100) and row['timing'] in ('base','a_slow'):
            rows.append('| '+' | '.join(str(row[k]) for k in ('workload','threshold','timing','queries','b_only_end_to_end_cycles','hybrid_end_to_end_cycles','header_first_end_to_end_cycles','cached_b_end_to_end_cycles','fastest_architectures'))+' |')
    rows += ['', '## Wins, ties and losses against B-only, by experiment family','',
             'Each count spans only the four declared thresholds (0/25/50/100) for one workload, timing point and query count. These counts are not probabilities or a cross-workload average. Every column uses cost-inclusive end-to-end cycles.','',
             '| Workload | Timing | Queries | Eager hybrid W/T/L | Header-first W/T/L | Cached B W/T/L |',
             '| --- | --- | ---: | --- | --- | --- |']
    for workload in app.WORKLOADS:
        for timing in app.TIMINGS:
            for queries in (1,4):
                selected=[r for r in paired if (r['workload'],r['timing'],r['queries'])==(workload,timing,queries)]
                fields=[]
                for arch in app.ARCHES[1:]:
                    counts=Counter(r[arch+'_vs_b_only'] for r in selected)
                    fields.append('/'.join(str(counts[k]) for k in ('win','tie','loss')))
                rows.append(f'| {workload} | {timing} | {queries} | '+' | '.join(fields)+' |')
    rows += ['', '## Executed quiescent updates and reload','',
             'Four additional native runs first complete a hot query, drain for 20 cycles, perform two authoritative B write handshakes, share reset for three edges, reload headers where applicable, then repeat the query. Word 1 becomes 99 and word 18 becomes 0xffffffff. The result oracle independently detects changed selection and changed selected-record sums. Both epoch ledgers and every phase are retained.','',
             '| Architecture | First preload | First query | Writes / cycles | Reset | Second preload | Second query | Total cycles including quiet guard |',
             '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |']
    for run in updates['records']:
        p=run['update']['phases']
        rows.append(f"| {run['case']['arch']} | {p['first_preload_cycles']} | {p['first_query_cycles']} | {p['writes']} / {p['write_cycles']} | {p['reset_cycles']} | {p['second_preload_cycles']} | {p['second_query_cycles']} | {p['total_cycles']} |")
    rows += ['', 'These writes use the simulation model\'s one-write-per-cycle load port. This is a quiescent update protocol, not live coherence or a physical write-bandwidth result. See the [predeclared update addendum](../docs/application-update-contract.md).', '', '## How to read the evidence','',
             '- `end_to_end_cycles = preload_cycles + query_cycles`. One and four query sequences are actually executed; later-query durations and cache reuse are in the per-run JSON. The separate four-case update experiment includes writes, invalidation and repeat preload; it is not mixed into the 384-run matrix.',
             '- Record i has fixed release edge 2i from query start. Release-to-result tails include host queue waiting. First-offer-to-result and accepted-command-to-result are reported separately because backpressure changes those timestamps. All percentile calculations use nearest rank; the final result edge is included in query duration.',
             '- Hybrid always eagerly fetches 14 payload words per record. Header-first requests a payload only after its key passes. `useless_payload` counts backing-store payload words for records rejected by the fixed predicate. Cache hits avoid a B transaction; its 16 direct-mapped lines deliberately conflict for the conflict workload.',
             '- Header-first is serial and uses fewer assembly resources. Hybrid has two interfaces. The cache has 256 data words plus tags/validity and its own control. Equal data capacity is not equal area, frequency, bandwidth, power, or implementation cost.',
             '- This is a useful predicate-and-sum scan primitive with immutable query epochs, a native user-fixture entrypoint, and quiescent updates. Concurrent updates, coherence, physical memory controllers, real applications beyond this fixed format, synthesis and board measurements remain open.', '',
             'See [application contract](../docs/application-contract.md), [all run metrics](application-metrics.csv), [all paired comparisons](application-comparisons.csv), and [raw evidence](raw/application/summary.json).','']
    machine=dict(passed=True,runs=384,matched_sets=96,verification_outcomes=40,update_outcomes=4,
                 checked_records=sum(r['metrics']['records'] for r in summary['runs']),
                 sources=summary['source_sha256'],inputs=summary['input_sha256'],
                 analysis_sha256={name:app.sha(ROOT/name) for name in
                                  ('benchmarks/report_application.py','tests/test_application_report.py')},
                 evidence_summary_sha256=app.sha(app.OUT/'summary.json'),
                 verification_summary_sha256=app.sha(app.OUT/'verification.json'),
                 update_summary_sha256=app.sha(app.OUT/'updates.json'),updates=[r['update']|{'arch':r['case']['arch']} for r in updates['records']],
                 paired_comparisons=paired)
    return {'application-metrics.csv':csv_text(flat),'application-comparisons.csv':csv_text(paired),
            'application-tables.md':'\n'.join(rows),'application-summary.json':json.dumps(machine,indent=2)+'\n'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    summary,verification,groups,updates=audit(); outputs=render(summary,verification,groups,updates)
    for name,text in outputs.items():
        path=ROOT/'results'/name
        if args.check:assert path.read_text()==text, f'STALE_REPORT {name}'
        else:path.write_text(text)
    print('PASS application audit: 384 native record sets, 96 matched groups, 40 correctness + 4 update outcomes')


if __name__=='__main__':main()

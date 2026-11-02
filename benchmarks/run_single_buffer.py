#!/usr/bin/env python3
"""Execute matched RTL benchmarks. No performance result comes from a Python DUT model."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from run_baseline import dataset, run

OUT = ROOT / 'results/raw/single_buffer'
SOURCES = ['rtl/sync_bank.sv', 'rtl/single_memory_controller.sv', 'rtl/hybrid_controller.sv',
           'sim/models/behavioral_memory.sv', 'sim/models/stream_sink.sv',
           'sim/tb/address_scoreboard.sv', 'sim/tb/benchmark_tb.sv']
MODES = ['A-only', 'B-only', 'hybrid']
COUNTERS = ['useful', 'unavailable', 'intentional', 'held', 'slot_sum', 'backlog_sum', 'early_words']
COUNTERS += [f'{m}_{k}' for m in 'ab' for k in ['requests', 'beats', 'offered', 'blocked', 'busy']]
DEFAULTS = dict(a_latency=2, a_interval=3, a_burst=256, a_gap=0, a_cooldown=0,
                a_accept_period=1, a_accept_cycles=1,
                b_latency=6, b_interval=1, b_burst=256, b_gap=0, b_cooldown=0,
                b_accept_period=1, b_accept_cycles=1,
                sink_period=1, sink_cycles=1, stall_start=0, stall_length=0)


def matrix():
    cases = []
    def add(name, n=8, s=3, group='primary', warmup=64, measured=1024, early=1, **args):
        cases.append(dict(name=name, N=n, S=s, group=group, warmup=warmup, measured=measured,
                          early=early, args=dict(DEFAULTS, **args)))
    add('default')
    add('equal_fast', a_latency=2, b_latency=2, a_interval=1)
    add('equal_slow', a_latency=2, b_latency=2, b_interval=3)
    add('reversed_latency', a_latency=12, b_latency=2)
    add('slow_A', a_interval=8, b_latency=2)
    add('late_B', a_latency=1, a_interval=1, b_latency=40)
    add('slow_sink', sink_period=16, sink_cycles=1)
    add('bursts_cooldown', a_burst=2, a_gap=4, a_cooldown=17,
        b_burst=2, b_gap=5, b_cooldown=25)
    add('request_skew', a_accept_period=17, b_accept_period=31)
    for s in [0, 1, 7, 8]:
        add(f'split_{s}', s=s)
    add('tiny_B', n=1, s=0)
    add('tiny_A', n=1, s=1)
    add('large_prefix8', n=32, s=8)
    add('large_prefix24', n=32, s=24)
    add('maximum_block', n=256, s=64)
    add('equal_balanced', n=32, s=16, a_interval=1, b_latency=2)
    # A second useful/poor split of slow A, deliberately retain the loss to B.
    add('oversized_slow_prefix', s=7, a_interval=8, b_latency=2)
    for name, args in [('default', {}), ('slow_sink', dict(sink_period=16, sink_cycles=1))]:
        add(f'{name}_gated', group='ablation', early=0, **args)
    add('aggregate_rate_control', n=32, s=16, group='rate_control', a_interval=1, b_latency=2)
    add('short_default', group='short', warmup=1, measured=1)
    # Warmup/window sensitivity without recompilation.
    add('default_long_window', group='sensitivity', warmup=128, measured=2048)
    add('request_skew_long_window', group='sensitivity', warmup=128, measured=2048,
        a_accept_period=17, b_accept_period=31)
    return cases


def hashes(paths):
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


def validate_prerequisites():
    """A stale passing report cannot authorize a benchmark of changed RTL/models."""
    result = {}
    for stage in (2, 3):
        path = ROOT/f'build/stage{stage}/summary.json'
        report = json.loads(path.read_text())
        assert report['passed'] and len(report['cases']) == {2:36, 3:32}[stage], path
        assert all(c['passed'] for c in report['cases']), path
        assert all(hashes([p])[p] == digest for p,digest in report['source_sha256'].items()), 'Stale regression'
        result[f'stage{stage}'] = report
    return result


def ready_before(end, cfg):
    """Number of ready edges in [0,end), using clock schedule, not DUT progress."""
    period, active = cfg['sink_period'], cfg['sink_cycles']
    def periodic(t):
        return (t//period)*active + min(t % period, active)
    lo = min(end, cfg['stall_start'])
    hi = min(end, cfg['stall_start']+cfg['stall_length'])
    return periodic(end) - (periodic(hi)-periodic(lo))


def summarize(path, case, mode, cfg):
    with path.open() as stream:
        rows = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]
    n, s, w, m = case['N'], case['S'], case['warmup'], case['measured']
    assert len(rows) == w+m and rows[0]['command'] == 0
    lengths = [n,0] if mode == 0 else [0,n] if mode == 1 else [s,n-s]
    previous = None
    for j,row in enumerate(rows):
        assert row['block'] == j and row['base'] == 256+(j % 128)*n
        assert row['useful'] == (j+1)*n
        assert row['useful']+row['unavailable']+row['intentional'] == row['last']+1
        assert row['intentional'] == row['last']+1-ready_before(row['last']+1, cfg)
        assert row['held'] <= row['intentional']
        assert 0 <= row['steady_backlog_max'] <= row['backlog_max'] <= n
        assert row['slot_sum'] == row['last']+1-(j+1)  # immediate command on next edge
        if previous:
            assert row['command'] == previous['last']+1
            assert all(row[k] >= previous[k] for k in COUNTERS)
        reqs = []
        for iface, length in zip('ab', lengths):
            r, f, d = [row[f'{k}_{iface}'] for k in ['request','response_first','response_last']]
            assert row[f'{iface}_requests'] == (j+1)*(length > 0)
            assert row[f'{iface}_beats'] == (j+1)*length
            assert row[f'{iface}_offered'] == row[f'{iface}_beats'] and row[f'{iface}_blocked'] == 0
            if length:
                reqs.append(r)
                assert r > row['command'] and r % cfg[f'{iface}_accept_period'] < cfg[f'{iface}_accept_cycles']
                assert f-r == cfg[f'{iface}_latency']
                assert d-f == (length-1)*cfg[f'{iface}_interval'] + ((length-1)//cfg[f'{iface}_burst'])*cfg[f'{iface}_gap']
                prior_busy = previous[f'{iface}_busy'] if previous else 0
                assert row[f'{iface}_busy']-prior_busy == d-r
                if previous:
                    assert r >= previous[f'response_last_{iface}']+1+cfg[f'{iface}_cooldown']
            else:
                assert r == f == d == -1 and row[f'{iface}_busy'] == 0
        assert row['first'] >= min(reqs)+2 and row['last']-row['first'] >= n-1
        if not case['early']:
            assert row['first'] >= max(row['response_last_a'],row['response_last_b'])+2
            assert row['early_words'] == 0
        previous = row
    # Fixed edge checks (hand-derived from the published synchronous-read contract).
    if case['name'] in ('default', 'short_default', 'default_long_window'):
        assert (rows[0]['first'], rows[0]['last']) == [(5,26),(9,16),(5,16)][mode]
    if case['name'] == 'equal_fast':
        assert (rows[0]['first'],rows[0]['last']) == (5,12)
    if case['name'] == 'default_gated':
        assert (rows[0]['first'],rows[0]['last']) == [(26,33),(16,23),(13,20)][mode]
    end, cut = rows[-1], rows[w-1]
    def window(start, previous, maximum):
        cycles = end['last']-start
        counts = {k:end[k]-(previous[k] if previous else 0) for k in COUNTERS}
        assert counts['useful']+counts['unavailable']+counts['intentional'] == cycles
        assert counts['useful'] == (m if previous else w+m)*n
        ret = dict(start_exclusive=start, end_inclusive=end['last'], cycles=cycles, **counts)
        ret.update(words_per_cycle=counts['useful']/cycles,
                   slot_average=counts['slot_sum']/cycles, slot_max=1,
                   backlog_average=counts['backlog_sum']/cycles, backlog_max=maximum)
        for iface in 'ab':
            ret[f'{iface}_accepted_rate'] = counts[f'{iface}_beats']/cycles
            ret[f'{iface}_busy_service_rate'] = (counts[f'{iface}_beats']/counts[f'{iface}_busy']
                                                if counts[f'{iface}_busy'] else 0)
        return ret
    def stats(values):
        ordered = sorted(values)
        return dict(min=min(values), mean=statistics.mean(values), max=max(values),
                    p95=ordered[(95*len(values)+99)//100-1])
    measured = rows[w:]
    latency = {}
    for name, values in {
        'command_first':[r['first']-r['command'] for r in measured],
        'command_complete':[r['last']-r['command'] for r in measured],
        'request_first':[r['first']-min(r[k] for k in ['request_a','request_b'] if r[k]>=0) for r in measured],
        'request_complete':[r['last']-min(r[k] for k in ['request_a','request_b'] if r[k]>=0) for r in measured],
        'request_skew':[abs(r['request_a']-r['request_b']) if min(r['request_a'],r['request_b'])>=0 else 0 for r in measured]
    }.items():
        latency[name] = stats(values)
    return dict(whole_intervals=end['last']-rows[0]['command'], reset_to_last=end['last'],
                startup_first=rows[0]['first']-rows[0]['command'],
                whole=window(-1, None, end['backlog_max']),
                steady=window(cut['last'], cut, end['steady_backlog_max']), latency=latency,
                nominal_rates={i:1/(cfg[f'{i}_interval']+cfg[f'{i}_gap']/cfg[f'{i}_burst']) for i in 'ab'})


def outcome(hybrid, baseline):
    return 'win' if hybrid < baseline else 'loss' if hybrid > baseline else 'tie'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append', help='Select named case(s); writes selected-summary.json.')
    args = parser.parse_args()
    cases = matrix()
    if args.case:
        assert not set(args.case)-{c['name'] for c in cases}, 'Unknown case'
        cases = [c for c in cases if c['name'] in args.case]
    OUT.mkdir(parents=True, exist_ok=True)
    prerequisites = validate_prerequisites()
    (OUT/'correctness-prerequisites.json').write_text(json.dumps(prerequisites, indent=2)+'\n')
    work = Path(tempfile.mkdtemp(prefix='fpga-benchmark-'))
    fixture = work/'dataset.hex'
    dataset(fixture)
    source_paths = SOURCES+['benchmarks/run_single_buffer.py','tests/run_baseline.py','scripts/benchmark.sh']
    report = dict(passed=False, scope='selected' if args.case else 'full', randomized=False, seed=None,
                  platform=platform.platform(), python=sys.version,
                  verilator=subprocess.check_output(['verilator','--version'], text=True).strip(),
                  clang=subprocess.check_output(['clang','--version'], text=True).strip(),
                  source_sha256=hashes(source_paths), fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                  timing='Edge 0 = first rising edge after shared reset release; first command accepts at edge 0.',
                  runs=[])
    summary = OUT/('selected-summary.json' if args.case else 'summary.json')
    summary.write_text(json.dumps(report,indent=2)+'\n')
    (OUT/('selected-comparisons.csv' if args.case else 'comparisons.csv')).unlink(missing_ok=True)
    for source in SOURCES:
        shutil.copy2(ROOT/source, work/Path(source).name)
    def build(key):
        n,s,mode,early = key
        tag = f'{n}_{s}_{mode}_{early}'
        cmd = ['verilator','--binary','--timing','--assert','-Wall','--top-module','benchmark_tb',
               '--Mdir',f'obj_{tag}','-o','benchmark','-j','2',f'-GBLOCK_WORDS={n}',
               f'-GSPLIT_WORDS={s}',f'-GMODE={mode}',f'-GEARLY_DELIVERY={early}']
        cmd += [Path(p).name for p in SOURCES]
        assert run(cmd, work, OUT/f'build_{tag}.log', timeout=180) == 0, f'Build {tag}'
        print(f'Built N={n} S={s} mode={mode} early={early}', flush=True)
        return key, work/f'obj_{tag}/benchmark'
    success = False
    try:
        cache = {}
        for case in cases:
            keys = [(case['N'],case['S'],mode,case['early']) for mode in range(3)]
            with ThreadPoolExecutor(max_workers=2) as pool:
                cache.update(pool.map(build, [key for key in keys if key not in cache]))
            for mode in range(3):
                tag = f'{case["name"]}_{mode}'
                cfg = dict(case['args'])
                if case['group'] == 'rate_control' and mode == 2:
                    cfg.update(a_interval=2,b_interval=2)
                directory = OUT/tag
                directory.mkdir(exist_ok=True)
                records = directory/'blocks.csv'
                cmd = [str(cache[case['N'],case['S'],mode,case['early']]),f'+dataset={fixture}',f'+records={records}',
                       f'+blocks={case["warmup"]+case["measured"]}',f'+warmup={case["warmup"]}']
                cmd += [f'+{key}={value}' for key,value in cfg.items()]
                code = run(cmd, directory, directory/'run.log', timeout=60)
                entry = dict(case=case, mode=MODES[mode], config=cfg, exit_code=code,
                             passed=False, records=str(records.relative_to(ROOT)), command=cmd)
                report['runs'].append(entry)
                assert code == 0 and 'PASS benchmark' in (directory/'run.log').read_text(), tag
                entry['metrics'] = summarize(records,case,mode,cfg)
                entry['passed'] = True
                summary.write_text(json.dumps(report,indent=2)+'\n')
                print(f'PASS {tag}: whole={entry["metrics"]["whole_intervals"]} cycles; '
                      f'steady={entry["metrics"]["steady"]["words_per_cycle"]:.6f} words/cycle', flush=True)
        comparisons = []
        for case in cases:
            runs = [r for r in report['runs'] if r['case']['name'] == case['name']]
            a,b,h = [r['metrics'] for r in runs]
            comparisons.append(dict(case=case['name'],group=case['group'],N=case['N'],S=case['S'],
                A_cycles=a['whole_intervals'],B_cycles=b['whole_intervals'],H_cycles=h['whole_intervals'],
                H_vs_A=outcome(h['whole_intervals'],a['whole_intervals']),
                H_vs_B=outcome(h['whole_intervals'],b['whole_intervals']),
                A_over_H=a['whole_intervals']/h['whole_intervals'],B_over_H=b['whole_intervals']/h['whole_intervals'],
                A_rate=a['steady']['words_per_cycle'],B_rate=b['steady']['words_per_cycle'],H_rate=h['steady']['words_per_cycle'],
                steady_H_vs_A=outcome(h['steady']['cycles'],a['steady']['cycles']),
                steady_H_vs_B=outcome(h['steady']['cycles'],b['steady']['cycles'])))
        report['comparisons'] = comparisons
        # Endpoints must behave identically to the corresponding baseline in every metric.
        for r in report['runs']:
            if r['mode'] == 'hybrid' and r['case']['S'] in (0,r['case']['N']):
                baseline = 'B-only' if r['case']['S'] == 0 else 'A-only'
                other = next(x for x in report['runs'] if x['case']['name']==r['case']['name'] and x['mode']==baseline)
                assert r['metrics'] == other['metrics'], 'Endpoint equivalence'
        filename = 'selected-comparisons.csv' if args.case else 'comparisons.csv'
        with (OUT/filename).open('w') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(comparisons[0]))
            writer.writeheader(); writer.writerows(comparisons)
        success = True
    finally:
        report['passed'] = success
        summary.write_text(json.dumps(report,indent=2)+'\n')
        if success:
            shutil.rmtree(work)
        else:
            print(f'Failure: binaries/fixture retained at {work}', flush=True)
    print(f'PASS {len(report["runs"])} RTL runs, {len(cases)} matched triplets; scope={report["scope"]}',flush=True)


if __name__ == '__main__':
    main()

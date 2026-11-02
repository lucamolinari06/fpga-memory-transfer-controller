#!/usr/bin/env python3
"""Native finite-tier application experiment; Python only orchestrates and audits."""
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/raw/application"
ARCHES = ("b_only", "hybrid", "header_first", "cached_b")
WORKLOADS = ("sequential", "permuted", "hot", "conflict")
TIMINGS = {"base": (2, 1, 12, 1), "b_constrained": (2, 1, 12, 3), "a_slow": (20, 2, 4, 1)}
SOURCES = ["rtl/sync_bank.sv", "rtl/buffered_transfer_controller.sv", "rtl/record_reduce.sv",
           "rtl/header_first_controller.sv", "rtl/record_cache.sv", "sim/models/application_memory.sv",
           "sim/tb/record_application_tb.sv"]
SEED = 9173


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes():
    return {p: sha(ROOT / p) for p in SOURCES + ["tests/run_application.py"]}


def fixture_words():
    words = []
    for record in range(128):
        words += [0xABC00000 + record, (record * 37 + 11) % 100]
        words += [((record*16 + offset)*2654435761 + 2779077210) % 2**32 for offset in range(2, 16)]
    return words


def order_for(kind, queries=4):
    if kind == "sequential":
        records = list(range(128))
    elif kind == "permuted":
        records = list(range(128)); random.Random(SEED).shuffle(records)
    elif kind == "hot":
        records = list(range(8))*16
    elif kind == "conflict":
        records = [16*i for i in range(8)]*16
    else:
        raise ValueError(kind)
    return [record*16 for record in records]*queries


def read_fixture(path):
    words = [int(line, 16) for line in path.read_text().split()]
    assert len(words) == 2048 and all(0 <= v < 2**32 for v in words), "FIXTURE_SIZE_OR_VALUE"
    assert len(set(words[::16])) == 128, "FIXTURE_DUPLICATE_ID"
    assert all(0 <= v < 100 for v in words[1::16]), "FIXTURE_KEY_RANGE"
    return words


def write_inputs(dataset=None):
    root = OUT / "inputs"; root.mkdir(parents=True, exist_ok=True)
    fixture = root / "dataset.hex"
    values = read_fixture(dataset) if dataset else fixture_words()
    fixture.write_text("".join(f"{v:08x}\n" for v in values))
    for kind in WORKLOADS:
        (root / f"{kind}.hex").write_text("".join(f"{v:08x}\n" for v in order_for(kind)))
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(root.glob("*.hex"))}


def distribution(values):
    ordered = sorted(values)
    return dict(mean=sum(values)/len(values), p95=ordered[math.ceil(.95*len(values))-1],
                p99=ordered[math.ceil(.99*len(values))-1], max=max(values))


def account(directory, case, suffix=""):
    """Re-score every result from logical fixture addresses; derive traffic exactly."""
    with (directory / ("records.csv"+suffix)).open() as stream:
        records = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(stream)]
    with (directory / ("metrics.csv"+suffix)).open() as stream:
        metrics = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(stream)]
    assert len(metrics) == 1, "METRICS_ROWS"
    m = metrics[0]
    values = read_fixture(directory.parent.parent/"inputs/dataset.hex")
    if case.get("update_epoch") and not suffix:
        values[1]=99; values[18]=0xffffffff
    order = order_for(case["workload"], case["queries"])
    assert len(records) == len(order) == m["records"], "RESULT_COUNT"
    selected = 0; rejected = 0; misses = 0; unused_miss_payload = 0
    tags = [None]*16
    for i, (record, base) in enumerate(zip(records, order)):
        wanted = values[base+1] < case["threshold"]
        wanted_sum = sum(values[base+2:base+16]) if wanted else 0
        assert record["record"] == i and record["base"] == base, "RESULT_ADDRESS"
        assert (record["id"], record["selected"], record["sum"]) == (values[base], int(wanted), wanted_sum), "RESULT_VALUE"
        assert record["release"] == 2*i and record["release"] <= record["offered"] <= record["command"] < record["result"], "RESULT_TIMESTAMPS"
        if i:
            assert records[i-1]["command"] < record["command"] and records[i-1]["result"] < record["result"], "RESULT_ORDER"
        selected += wanted; rejected += not wanted
        line = (base//16) % 16
        if tags[line] != base:
            misses += 1; unused_miss_payload += 14*(not wanted); tags[line] = base
    arch = case["arch"]; count = len(order)
    a_words = 2*count if arch in ("hybrid", "header_first") else 0
    b_words = {"b_only":16*count,"hybrid":14*count,"header_first":14*selected,"cached_b":16*misses}[arch]
    b_reqs = {"b_only":count,"hybrid":count,"header_first":selected,"cached_b":misses}[arch]
    useless = {"b_only":14*rejected,"hybrid":14*rejected,"header_first":0,"cached_b":unused_miss_payload}[arch]
    assert (m["selected"],m["a_beats"],m["b_beats"],m["b_requests"],m["useless_payload"]) == (selected,a_words,b_words,b_reqs,useless), "TRAFFIC_ACCOUNTING"
    assert m["preload_words"] == (256 if a_words else 0), "PRELOAD_WORDS"
    assert (m["preload_cycles"] > 0) == bool(a_words), "PRELOAD_CYCLES"
    assert m["query_cycles"] == records[-1]["result"]+1, "QUERY_ENDPOINT"
    assert m["reset_applied"] == int(case.get("reset_at", 0)>0 or (bool(case.get("update_epoch")) and not suffix)), "RESET_EPOCH"
    assert (m["cache_hits"],m["cache_misses"]) == ((count-misses,misses) if arch == "cached_b" else (0,0)), "CACHE_ACCOUNTING"
    for key in ("a_beats", "b_beats", "b_requests", "cache_hits", "cache_misses"):
        assert records[-1][key] == m[key], "COUNTER_ENDPOINT"
    result = dict(m, end_to_end_cycles=m["preload_cycles"]+m["query_cycles"],
                  records_per_query_cycle=count/m["query_cycles"],
                  records_per_end_to_end_cycle=count/(m["preload_cycles"]+m["query_cycles"]),
                  release_to_result=distribution([r["result"]-r["release"] for r in records]),
                  offer_to_result=distribution([r["result"]-r["offered"] for r in records]),
                  command_to_result=distribution([r["result"]-r["command"] for r in records]))
    boundaries = [records[128*(q+1)-1]["result"]+1 for q in range(case["queries"])]
    result["query_completion_cycles"] = boundaries
    result["query_duration_cycles"] = [boundaries[0]] + [b-a for a,b in zip(boundaries,boundaries[1:])]
    return result


def account_update(directory,case):
    first=account(directory,case,".epoch0.csv")
    second=account(directory,case)
    with (directory/"metrics.csv.update.csv").open() as stream:
        rows=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(stream)]
    assert len(rows)==1,"UPDATE_ROWS"
    update=rows[0]
    assert update['writes']==2 and update['write_cycles']==2 and update['reset_cycles']==3 and update['quiet_cycles']==20,"UPDATE_PHASES"
    assert (update['first_preload_cycles'],update['first_query_cycles'])==(first['preload_cycles'],first['query_cycles']),"UPDATE_FIRST_EPOCH"
    assert (update['second_preload_cycles'],update['second_query_cycles'])==(second['preload_cycles'],second['query_cycles']),"UPDATE_SECOND_EPOCH"
    assert update['total_cycles']==sum(v for k,v in update.items() if k not in ('total_cycles','writes')),"UPDATE_TOTAL"
    assert first['selected']-second['selected']==16,"UPDATE_CHANGED_SELECTION"
    return dict(phases=update,first_epoch=first,second_epoch=second)


def run(command, cwd, log, timeout=180):
    with log.open("w") as stream:
        try:
            return subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            stream.write("\nAPP_RUNNER_TIMEOUT\n"); return 124


class Builds:
    def __init__(self):
        self.hashes = hashes()
        digest = hashlib.sha256(json.dumps(self.hashes, sort_keys=True).encode()).hexdigest()[:16]
        self.work = Path(tempfile.gettempdir()) / f"fpga-application-{digest}"
        self.work.mkdir(exist_ok=True)
        for source in SOURCES:
            shutil.copy2(ROOT/source, self.work/Path(source).name)
        self.cache = {}

    def build(self, arch):
        if arch in self.cache:
            return self.cache[arch]
        index = ARCHES.index(arch); exe = self.work/f"obj_{index}/application"
        command = ["verilator","--binary","--timing","--assert","--trace","-Wall",
                   "--top-module","record_application_tb",f"-GARCH={index}","--Mdir",f"obj_{index}",
                   "-o","application","-j","2"] + [Path(p).name for p in SOURCES]
        log = OUT/f"build-{arch}.log"
        if not exe.exists():
            code = run(command,self.work,log,240)
            assert code == 0, ("APP_BUILD",arch,code,log.read_text()[-5000:])
        self.cache[arch] = exe
        return exe


def execute(builds, case, verification=False):
    name = "_".join(str(case[k]) for k in ("arch","workload","threshold","timing","queries"))
    if verification:
        name += f"_f{case.get('fault',0)}_r{case.get('reset_at',0)}_ready{case.get('ready_cycles',6)}"
    if case.get('update_epoch'):name+='_update'
    directory = OUT / ("verification" if verification else "runs") / name
    directory.mkdir(parents=True, exist_ok=True)
    command = [str(builds.build(case["arch"])),f"+fixture={OUT/'inputs/dataset.hex'}",
               f"+order={OUT/'inputs'/str(case['workload']+'.hex')}",f"+records={directory/'records.csv'}",
               f"+metrics={directory/'metrics.csv'}",f"+threshold={case['threshold']}",f"+queries={case['queries']}"]
    config = dict(zip(("a_latency","a_interval","b_latency","b_interval"),TIMINGS[case["timing"]]))
    config.update(ready_period=case.get("ready_period",9),ready_cycles=case.get("ready_cycles",6),
                  reset_at=case.get("reset_at",0),fault=case.get("fault",0),update_epoch=case.get("update_epoch",0))
    command += [f"+{k}={v}" for k,v in config.items()]
    code = run(command,directory,directory/"run.log")
    log = (directory/"run.log").read_text()
    expected = {1:"APP_SUM_MISMATCH",2:"APP_SELECTION_MISMATCH",3:"APP_ID_MISMATCH",
                4:"APP_MISSING_RESULT",5:"APP_MEMORY_BOUNDS"}.get(config["fault"])
    if config["fault"] == 5:
        expected = {"header_first":"HEADER_COMMAND_ADDRESS", "cached_b":"CACHE_REQUEST_BOUNDS"}.get(case["arch"],expected)
    passed = code == 0 and "PASS application" in log if expected is None else code not in (0,124) and expected in log
    result = dict(case=case,config=config,passed=passed,expected_failure=expected,exit_code=code,
                  command=command,source_sha256=builds.hashes,
                  input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [OUT/"inputs/dataset.hex", OUT/"inputs"/f"{case['workload']}.hex"]},
                  log=str((directory/"run.log").relative_to(ROOT)),log_sha256=sha(directory/"run.log"))
    if passed and expected is None:
        result["metrics"] = account(directory,case)
        result["records"] = str((directory/"records.csv").relative_to(ROOT))
        result["records_sha256"] = sha(directory/"records.csv")
        if config['update_epoch']:
            result['update']=account_update(directory,case)
            result['update_file_sha256']={p.name:sha(p) for p in [directory/'records.csv.epoch0.csv',directory/'metrics.csv.epoch0.csv',directory/'metrics.csv.update.csv']}
    (directory/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    assert passed, (name,code,expected,log[-5000:])
    print("PASS",name,expected or "native + independent result/traffic accounting",flush=True)
    return result


def verification_matrix():
    for arch in ARCHES:
        base = dict(arch=arch,workload="sequential",threshold=50,timing="base",queries=1)
        yield base
        for threshold in (0,100): yield dict(base,threshold=threshold)
        yield dict(base,workload="hot",ready_period=13,ready_cycles=1)
        yield dict(base,reset_at=40)
        for fault in range(1,6): yield dict(base,fault=fault)


def matrix():
    for arch,workload,threshold,timing,queries in itertools.product(ARCHES,WORKLOADS,(0,25,50,100),TIMINGS,(1,4)):
        yield dict(arch=arch,workload=workload,threshold=threshold,timing=timing,queries=queries)


def update_matrix():
    for arch in ARCHES:
        yield dict(arch=arch,workload="hot",threshold=50,timing="base",queries=1,update_epoch=1)


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot",action="store_true")
    parser.add_argument("--verify-only",action="store_true")
    parser.add_argument("--updates-only",action="store_true",help="run four quiescent update/invalidate/reload cases")
    parser.add_argument("--query",action="store_true",help="execute one usable native query instead of the benchmark matrix")
    parser.add_argument("--dataset-hex",type=Path,help="2048 uint32 words: 128 records of ID, key 0..99, 14 payload samples")
    parser.add_argument("--arch",choices=ARCHES,default="hybrid")
    parser.add_argument("--threshold",type=int,default=50)
    parser.add_argument("--workload",choices=WORKLOADS,default="sequential")
    parser.add_argument("--timing",choices=TIMINGS,default="base")
    parser.add_argument("--queries",type=int,choices=(1,4),default=1)
    parser.add_argument("--output-dir",type=Path,help="output directory inside this checkout (query mode only)")
    args=parser.parse_args()
    if args.dataset_hex or args.output_dir:
        args.query = True
    if not 0 <= args.threshold <= 100:
        parser.error("--threshold must be in 0..100")
    if args.query:
        OUT = (args.output_dir or ROOT/"build/application_query").resolve()
        if not OUT.is_relative_to(ROOT):
            parser.error("--output-dir must be inside this checkout")
    OUT.mkdir(parents=True,exist_ok=True); inputs=write_inputs(args.dataset_hex); builds=Builds()
    if args.updates_only:
        results=[execute(builds,c,True) for c in update_matrix()]
        (OUT/'updates.json').write_text(json.dumps(dict(passed=True,outcomes=4,source_sha256=builds.hashes,inputs=inputs,records=results),indent=2)+'\n')
        return
    if args.query:
        case=dict(arch=args.arch,workload=args.workload,threshold=args.threshold,timing=args.timing,queries=args.queries)
        result=execute(builds,case)
        (OUT/"query.json").write_text(json.dumps(dict(passed=True,result=result,inputs=inputs),indent=2)+"\n")
        print("Native result CSV:",ROOT/result["records"])
        return
    if args.pilot:
        cases=[dict(arch=a,workload="sequential",threshold=50,timing="base",queries=1) for a in ARCHES]
        results=[execute(builds,c,True) for c in cases]
        target="pilot.json"
    else:
        results=[execute(builds,c,True) for c in verification_matrix()]
        target="verification.json"
    verification=dict(passed=True,outcomes=len(results),source_sha256=builds.hashes,inputs=inputs,records=results,
                      simulator=subprocess.check_output(["verilator","--version"],text=True).strip())
    (OUT/target).write_text(json.dumps(verification,indent=2)+"\n")
    if not args.pilot:
        updates=[execute(builds,c,True) for c in update_matrix()]
        (OUT/'updates.json').write_text(json.dumps(dict(passed=True,outcomes=4,source_sha256=builds.hashes,inputs=inputs,records=updates),indent=2)+'\n')
    if not(args.pilot or args.verify_only):
        results=[execute(builds,c) for c in matrix()]
        summary=dict(passed=True,scope="full",runs=results,source_sha256=builds.hashes,input_sha256=inputs,
                     seed=SEED,verification_outcomes=len(verification["records"]),simulator=verification["simulator"],
                     statement="384 native runs, four finite-tier alternatives, 96 matched four-way configurations; no hardware measurements.")
        (OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("PASS application campaign",target,flush=True)


if __name__ == "__main__":
    main()

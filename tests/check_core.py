#!/usr/bin/env python3
"""One entry point for actual native checks; never substitutes a Python DUT model."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def commands(mode):
    """Ordered commands: full regression before evidence auditing."""
    portable = [
        ("original-accounting", ["python3", "benchmarks/test_measurements.py"]),
        ("repository-contracts", ["python3", "tests/test_repository_contracts.py"]),
    ]
    generated_accounting = [
        ("timing-accounting", ["python3", "benchmarks/test_timing_measurements.py"]),
        ("buffered-accounting", ["python3", "benchmarks/test_buffered_measurements.py"]),
    ]
    saved_evidence_tests = [
        ("core-report-tests", ["python3", "benchmarks/test_core_report.py"]),
    ]
    evidence = [("core-evidence", ["python3", "benchmarks/report_core.py", "--check"])]
    if mode == "evidence":
        return portable + saved_evidence_tests + evidence
    common = [
        ("tool-inventory", ["bash", "scripts/check_tools.sh"]),
        ("strict-lint", ["bash", "scripts/lint.sh"]),
        ("native-smoke", ["bash", "scripts/smoke.sh"]),
    ]
    if mode == "quick":
        return common + portable
    return common + [
        ("original-regression", ["bash", "scripts/test.sh"]),
        ("timing-regression", ["bash", "scripts/test_memory_timing.sh"]),
        ("buffered-regression", ["bash", "scripts/test_buffered.sh"]),
        ("stage5-stress", ["bash", "scripts/test_stage5.sh"]),
        ("stage5-reset-phases", ["bash", "scripts/test_stage5_reset_phases.sh"]),
        ("stage5-live-audit", ["python3", "tests/audit_stage5.py"]),
    ] + portable + generated_accounting + saved_evidence_tests + evidence


def snapshot():
    paths = []
    for directory in ("rtl", "sim", "tests", "benchmarks", "scripts"):
        paths += [p for p in (ROOT / directory).rglob("*")
                  if p.is_file() and p.suffix in (".sv", ".py", ".sh", ".txt", ".sha256")
                  and "__pycache__" not in p.parts]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def execute(argv, log, timeout):
    """Bound a whole child process group, preserving output even on interruption."""
    with log.open("w") as stream:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            interrupted = isinstance(exc, KeyboardInterrupt)
            stream.write("\nCHECK_CORE_INTERRUPTED\n" if interrupted else "\nCHECK_CORE_TIMEOUT\n")
            return 130 if interrupted else 124


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--quick", action="store_true", help="lint, native smoke and accounting tests; not full RTL correctness")
    modes.add_argument("--evidence", action="store_true", help="audit saved evidence and accounting without a simulator")
    parser.add_argument("--list", action="store_true", help="print planned commands without executing or claiming checks")
    parser.add_argument("--timeout", type=int, default=3600, help="per-command timeout in seconds (default 3600)")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    mode = "quick" if args.quick else "evidence" if args.evidence else "full"
    planned = commands(mode)
    if args.list:
        for name, argv in planned:
            print(f"{name}: {shlex.join(argv)}")
        return 0
    # Unique path means a failed attempt is never overwritten by a later pass.
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{os.getpid()}"
    out = ROOT / "build/stage6" / tag
    out.mkdir(parents=True)
    report = dict(schema_version=1, mode=mode, started_utc=timestamp(), finished_utc=None,
                  passed=False, host=platform.platform(), python=sys.version,
                  source_sha256=snapshot(), commands=[], planned_commands=len(planned),
                  meaning="Command exit statuses from this invocation; saved benchmark audits are not new RTL benchmark runs.")
    def save():
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    save()
    print(f"Check logs: {out.relative_to(ROOT)}", flush=True)
    for index, (name, argv) in enumerate(planned, 1):
        log = out / f"{index:02d}-{name}.log"
        record = dict(name=name, argv=argv, log=str(log.relative_to(ROOT)),
                      started_utc=timestamp(), exit_code=None, elapsed_seconds=None)
        report["commands"].append(record)
        save()
        print(f"[{index}/{len(planned)}] {shlex.join(argv)}", flush=True)
        start = time.monotonic()
        try:
            code = execute(argv, log, args.timeout)
        except OSError as exc:
            log.write_text(f"CHECK_CORE_EXEC_ERROR: {exc}\n")
            code = 127
        record.update(exit_code=code, elapsed_seconds=round(time.monotonic() - start, 3),
                      finished_utc=timestamp(), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        save()
        print(f"{'PASS' if code == 0 else 'FAIL'} {name} ({record['elapsed_seconds']}s); {record['log']}", flush=True)
        if code:
            print(log.read_text(errors="replace")[-6000:], file=sys.stderr)
            break
    after = snapshot()
    # New, independent experiments may be authored while the preserved core
    # runs. Every source present at invocation must remain byte-identical.
    report["source_changed_during_run"] = sorted(
        p for p in report["source_sha256"]
        if after.get(p) != report["source_sha256"][p])
    report["sources_added_during_run"] = sorted(set(after) - set(report["source_sha256"]))
    report["finished_utc"] = timestamp()
    report["passed"] = (len(report["commands"]) == len(planned)
                        and all(r["exit_code"] == 0 for r in report["commands"])
                        and not report["source_changed_during_run"])
    save()
    print(f"{'PASS' if report['passed'] else 'FAIL'} {mode} checks: {out.relative_to(ROOT)}/summary.json", flush=True)
    if report["source_changed_during_run"]:
        print("Source files changed during execution; rerun against a stable source tree.", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

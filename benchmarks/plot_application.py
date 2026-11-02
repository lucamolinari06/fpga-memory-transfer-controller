#!/usr/bin/env python3
"""Render audited native application comparisons; no performance simulation."""
import json
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import report_application


def main():
    # Regeneration must fail if the native inputs, sources or published table drift.
    summary, verification, groups, updates = report_application.audit()
    rendered = report_application.render(summary, verification, groups, updates)
    for name, content in rendered.items():
        if (ROOT / "results" / name).read_text() != content:
            raise SystemExit("Stale application report: " + name)
    paired = json.loads(rendered["application-summary.json"])["paired_comparisons"]
    cases = [
        ("sequential", 25, 1, "One scan: preload erases the selective-fetch gain"),
        ("sequential", 25, 4, "Four scans: reuse amortizes header preload"),
        ("hot", 100, 1, "Hot eight-record set: whole-record caching wins"),
        ("conflict", 100, 1, "Conflicting records: cache capacity is not enough"),
    ]
    arches = ("b_only", "hybrid", "header_first", "cached_b")
    labels = ("B-only", "Eager\nhybrid", "Header\nfirst", "Cached\nB")
    colors = ("#244863", "#07867d", "#bb6c23", "#72549b")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.spines.left": False, "axes.spines.bottom": False,
                         "axes.titleweight": "bold", "axes.labelcolor": "#334155",
                         "xtick.color": "#334155", "ytick.color": "#64748b"})
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.subplots_adjust(top=.79, bottom=.18, left=.08, right=.98, hspace=.57, wspace=.25)
    fig.suptitle("Placement, selectivity and reuse change the winner", x=.08, y=.97,
                 ha="left", fontsize=20, fontweight="bold", color="#173448")
    fig.text(.08, .925, "Native RTL results • actual header preload included • exploratory memory timings",
             color="#526174", fontsize=11)
    fig.legend(handles=[Patch(facecolor="#536779", label="Query execution"),
                        Patch(facecolor="#e9eef2", edgecolor="#7b8794", hatch="///",
                              label="Header preload (B reads + A writes)")],
               loc="upper left", bbox_to_anchor=(.073, .903), frameon=False, ncol=2)
    for ax, (workload, threshold, queries, title) in zip(axes.flat, cases):
        rows = [r for r in paired if (r["workload"], r["threshold"], r["timing"], r["queries"])
                == (workload, threshold, "base", queries)]
        if len(rows) != 1:
            raise SystemExit("Application figure requires exactly one matched group")
        row = rows[0]
        query = [row[a + "_query_cycles"] for a in arches]
        preload = [row[a + "_preload_cycles"] for a in arches]
        totals = [row[a + "_end_to_end_cycles"] for a in arches]
        ax.bar(range(4), query, color=colors, width=.6, zorder=3)
        ax.bar(range(4), preload, bottom=query, width=.6, color="#e9eef2",
               edgecolor="#7b8794", hatch="///", linewidth=.6, zorder=3)
        for x, value in enumerate(totals):
            ax.text(x, value + max(totals)*.025, f"{value:,}", ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color="#233749")
        ax.set_xticks(range(4), [label + f"\nB: {row[arch + '_b_beats']:,} words"
                                for label, arch in zip(labels, arches)])
        ax.set_ylim(0, max(totals)*1.21)
        ax.set_ylabel("End-to-end cycles ↓")
        ax.set_title(title, loc="left", fontsize=11, pad=25)
        ax.text(0, 1.025, f"{workload} · key < {threshold} · {queries} quer{'y' if queries == 1 else 'ies'}",
                transform=ax.transAxes, color="#64748b", fontsize=9)
        ax.grid(axis="y", color="#e5eaf0", zorder=0)
        ax.tick_params(axis="both", length=0)
        ax.ticklabel_format(axis="y", style="plain")
    fig.text(.08, .075,
             "128 records/query · A latency/interval = 2/1 cycles · B = 12/1 · identical record-release and result-ready schedules",
             color="#526174", fontsize=9)
    fig.text(.08, .048,
             "B labels count query-phase transfers. Four cases shown; all 96 matched configurations retained. Equal data capacity is not equal area.",
             color="#526174", fontsize=9)
    out = ROOT / "results"
    fig.savefig(out / "application-overview.png", dpi=170, facecolor="white")
    fig.savefig(out / "application-overview.svg", facecolor="white",
                metadata={"Title": "Audited native application comparisons",
                          "Description": "Query plus actual header preload; source results/application-summary.json."})
    plt.close(fig)
    manifest = {
        "passed": True,
        "meaning": "Figures derived from independently audited native application records; no new RTL runs.",
        "matplotlib": matplotlib.__version__,
        "selected_cases": [dict(workload=w, threshold=t, queries=q, timing="base")
                           for w, t, q, _ in cases],
        "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in ("benchmarks/plot_application.py", "benchmarks/report_application.py",
                                "results/application-summary.json", "results/application-overview.png",
                                "results/application-overview.svg")},
    }
    (out / "application-plot-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("PASS application PNG/SVG generated from audited native records")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("Run without Python -O: native accounting uses assertions")
    main()

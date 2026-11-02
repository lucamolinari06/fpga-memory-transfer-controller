#!/usr/bin/env python3
"""Rebuild charts solely from a successful, full, recorded RTL sweep."""
import json
import hashlib
import os
from pathlib import Path
import tempfile
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'fpga-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT/'results/raw/single_buffer/summary.json').read_text())
assert report['passed'] and report['scope'] == 'full'
rows = [c for c in report['comparisons'] if c['group'] == 'primary']
names = [f'{r["case"]}  (N={r["N"]}, S={r["S"]})' for r in rows]
y = list(range(len(rows)))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig, axes = plt.subplots(1,2,figsize=(14,12),sharey=True,gridspec_kw={'width_ratios':[1,1.15]})
for offset, key, label, color in [(-.25,'A_rate','A-only','#3b78a3'),(0,'B_rate','B-only','#d28b28'),(.25,'H_rate','Hybrid','#25836e')]:
    axes[0].barh([v+offset for v in y],[r[key] for r in rows],height=.22,label=label,color=color)
axes[0].set_yticks(y, names)
axes[0].invert_yaxis()
axes[0].set_xlabel('Measured throughput (32-bit words/cycle)')
axes[0].set_xlim(0,1)
axes[0].set_title('Steady window: 64 warmup + 1,024 measured blocks',fontsize=11,pad=35)
axes[0].legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=3,frameon=False)
axes[0].grid(axis='x',alpha=.2)
for offset,key,label,color in [(-.22,'A_over_H','Versus A-only','#3b78a3'),(.22,'B_over_H','Versus B-only','#d28b28')]:
    values = [r[key] for r in rows]
    axes[1].scatter(values,[v+offset for v in y],label=label,color=color,s=30,zorder=3)
    for v,j in zip(values,y):
        axes[1].annotate((f'{v:.6f}×' if 0 < abs(v-1) < .005 else f'{v:.2f}×'),(v,j+offset),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
axes[1].axvline(1,color='#555555',lw=1,ls='--')
axes[1].set_xlabel('Baseline whole-workload cycles / hybrid cycles')
axes[1].set_title('Below 1: hybrid loses     1: ties     Above 1: wins',fontsize=11,pad=35)
axes[1].set_xlim(0,max(r['A_over_H'] for r in rows)*1.18)
axes[1].grid(axis='x',alpha=.2)
axes[1].legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,frameon=False)
fig.suptitle('Single-buffer RTL comparison — matched primary configurations',fontsize=15,x=.54,y=.985)
fig.text(.02,.017,'Same logical buffer capacity and sink schedule within each row. Hybrid can use two memory interfaces; baselines use one.\nArchitectural cycles from asserted Verilator simulation; no FPGA clock, area, or physical-memory claim.\nrequest_skew gains only three whole-workload cycles over B; its steady rate ties B. Ratios are rounded.',fontsize=9,color='#444444')
fig.tight_layout(rect=[0,.07,1,.96])
out = ROOT/'results'
for suffix in ['png','svg']:
    fig.savefig(out/f'single-buffer-comparison.{suffix}',dpi=170)
plt.close(fig)
print('Saved results/single-buffer-comparison.png and .svg')

metadata = dict(matplotlib=matplotlib.__version__,
                input_sha256=hashlib.sha256((ROOT/'results/raw/single_buffer/summary.json').read_bytes()).hexdigest(),
                source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                               for name in ['benchmarks/plot_single_buffer.py','benchmarks/report_single_buffer.py',
                                            'benchmarks/requirements-plot-lock.txt']})
(out/'presentation-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')

#!/usr/bin/env python3
"""Standalone figures from the complete, audited native RTL report."""
import hashlib,json,os,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'build/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
report=json.loads((ROOT/'results/raw/double_buffer/summary.json').read_text())
assert report['passed'] and len(report['runs'])==2616
runs=report['runs'];modes=['A-only','B-only','hybrid'];colors=['#2575af','#dd8833','#3b9968']
splits=[(8,1),(8,3),(8,7),(32,8),(32,24),(256,64)]
fig,axes=plt.subplots(3,2,figsize=(12,10),sharex=True,sharey=True,layout='constrained')
for p in [1,2,3]:
    for depth in [1,2]:
        ax=axes[p-1,depth-1]
        for mode,color in zip(modes,colors):
            means=[];lo=[];hi=[]
            for n,s in splits:
                values=[r['metrics']['steady']['words_per_cycle'] for r in runs if r['depth']==depth and r['mode']==mode and r['case']['family']=='path' and r['case']['group']=='primary' and r['case']['workload']=='sequential' and r['case']['early']==1 and r['case']['profile']==p and (r['case']['N'],r['case']['S'])==(n,s)]
                assert len(values)==4
                mean=statistics.mean(values);means.append(mean);lo.append(mean-min(values));hi.append(max(values)-mean)
            ax.errorbar(range(6),means,yerr=[lo,hi],label=mode,color=color,marker='o',capsize=3,linewidth=1.7)
        ax.set_title(f'P{p} · {depth} slot'+('s' if depth==2 else ''))
        ax.grid(axis='y',alpha=.2);ax.set_ylim(0,1.03)
        ax.set_xticks(range(6),[f'{n}/{s}' for n,s in splits])
        if depth==1:ax.set_ylabel('Delivered words / cycle')
        if p==3:ax.set_xlabel('Block words / A-prefix words')
axes[0,0].legend(loc='upper left',fontsize=9)
fig.suptitle('Double buffering under matched memory timing\nSequential, early delivery on · means and ranges across four fixed traces',fontsize=15)
fig.savefig(ROOT/'results/double-buffer-throughput.png',dpi=180);fig.savefig(ROOT/'results/double-buffer-throughput.svg');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(11,4.8),layout='constrained')
for ax,label in zip(axes,['first','complete']):
    for j,(mode,color) in enumerate(zip(modes,colors)):
        for depth in [1,2]:
            rr=[r for r in runs if r['case']['name']=='path_p2_n32_s8_sequential_seed11_early1' and r['depth']==depth and r['mode']==mode];assert len(rr)==1
            stats=rr[0]['metrics']['latency']['command_'+label];x=j+(depth-1.5)*.28
            ax.bar(x,stats['mean'],width=.25,color=color,alpha=1 if depth==1 else .5)
            ax.plot(x,stats['p99'],marker='_',markersize=13,color='black')
    ax.set_xticks(range(3),modes);ax.set_ylabel('Cycles from command acceptance');ax.set_title('First word' if label=='first' else 'Block completion');ax.grid(axis='y',alpha=.2)
fig.suptitle('P2 · N=32, S=8 · trace 11 · early delivery on\nLeft/solid: one slot · right/light: two slots · bars: mean · marks: p99',fontsize=12)
fig.savefig(ROOT/'results/double-buffer-latency.png',dpi=180);fig.savefig(ROOT/'results/double-buffer-latency.svg');plt.close(fig)
(ROOT/'results/double-buffer-plots.json').write_text(json.dumps(dict(report_sha256=hashlib.sha256((ROOT/'results/raw/double_buffer/summary.json').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),matplotlib=matplotlib.__version__,note='Whiskers are the range of four predeclared external traces, not confidence intervals.'),indent=2)+'\n')
print('Generated two PNG/SVG figure pairs')

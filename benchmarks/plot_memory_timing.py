#!/usr/bin/env python3
"""Standalone scientific plots from passing RTL measurements, never a synthetic DUT."""
import csv,hashlib,json,statistics
from pathlib import Path
import os
os.environ.setdefault("MPLCONFIGDIR",str(Path(__file__).resolve().parents[1]/"build/matplotlib"))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/raw/memory_timing'
COLORS=['#2878b5','#eb8d23','#38865b']
MODES=['A-only','B-only','hybrid']
def main():
    report=json.loads((OUT/'summary.json').read_text());assert report['passed']
    runs=report['runs'];files=[]
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(3,3,figsize=(13,10),layout='constrained')
    for j,p in enumerate([1,2,3]):
        chosen=[r for r in runs if r['case']['family']=='path' and r['case']['profile']==p and
                r['case']['N']==8 and r['case']['S']==3 and r['case']['early']==1 and
                r['case']['group']=='primary' and r['case']['workload']=='sequential']
        for i,metric in enumerate(['rate','first','completion']):
            ax=axes[i,j];med=[];lo=[];hi=[]
            for mode in MODES:
                ms=[r['metrics'] for r in chosen if r['mode']==mode]
                values=[m['steady']['words_per_cycle'] if metric=='rate' else
                        m['latency']['command_first']['mean'] if metric=='first' else
                        m['latency']['command_complete']['p99'] for m in ms]
                middle=statistics.median(values);med.append(middle);lo.append(middle-min(values));hi.append(max(values)-middle)
            ax.bar(MODES,med,color=COLORS,yerr=[lo,hi],capsize=4,width=.65)
            ax.set_ylim(0,max(v+h for v,h in zip(med,hi))*1.20);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
            if i==0:ax.set_title(['P1 · independent, quiet','P2 · local reservations','P3 · shared return'][j])
            if j==0:ax.set_ylabel(['Steady words / cycle','Mean first-word latency (cycles)','p99 block completion (cycles)'][i])
            for k,v in enumerate(med):ax.text(k,v+hi[k]+max(med)*.04,f'{v:.3f}' if i==0 else f'{v:.1f}',ha='center',fontsize=9)
    fig.suptitle('Recommended settings · N=8, S=3 · early delivery on · sequential\nBars: median of four traces; whiskers: trace min–max. Exploratory simulation cycles.',fontsize=13)
    for suffix in ['png','svg']:
        path=ROOT/f'results/memory-timing-latency-throughput.{suffix}';fig.savefig(path,dpi=150);files.append(path)
    plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
    splits=[(8,1),(8,3),(8,7),(32,8),(32,24),(256,64)]
    for ax,p in zip(axes,[1,2,3]):
        for mi,mode in enumerate(MODES):
            med=[];lo=[];hi=[]
            for n,s in splits:
                selected=[r['metrics']['steady']['words_per_cycle'] for r in runs if r['mode']==mode and
                    (r['case']['family'],r['case']['profile'],r['case']['N'],r['case']['S'],r['case']['early'],
                     r['case']['group'],r['case']['workload'])==('path',p,n,s,1,'primary','sequential')]
                v=statistics.median(selected);med.append(v);lo.append(v-min(selected));hi.append(max(selected)-v)
            xs=[x+(mi-1)*.24 for x in range(6)]
            ax.bar(xs,med,width=.23,color=COLORS[mi],label=mode,yerr=[lo,hi],capsize=2)
        ax.set_xticks(range(6),[f'{n}/{s}' for n,s in splits],rotation=30)
        ax.set_xlabel('Block words / A-prefix words');ax.set_ylim(0,1.05);ax.set_title(f'P{p}');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0].set_ylabel('Steady words / simulated cycle');axes[-1].legend(loc='upper left',fontsize=8)
    fig.suptitle('Recommended settings · sequential · early on · trace median and min–max\nAll six predeclared splits, including losses to the better baseline',fontsize=12)
    for suffix in ['png','svg']:
        path=ROOT/f'results/memory-timing-splits.{suffix}';fig.savefig(path,dpi=150);files.append(path)
    plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(12,8),layout='constrained')
    for mi,mode in enumerate(MODES):
        r=next(r for r in runs if r['case']['name']=='path_p2_n8_s3_conflict_seed11_early1' and r['mode']==mode)
        with (ROOT/r['records']).open() as f:rows=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
        # Display first 128 measured blocks for legibility; all 1,024 remain in raw data.
        selected=rows[64:192]
        axes[0].plot([x['block']-64 for x in selected],[x['first']-x['command'] for x in selected],color=COLORS[mi],label=mode,lw=1)
        axes[1].plot([x['block']-64 for x in selected],[x['last']-x['command'] for x in selected],color=COLORS[mi],label=mode,lw=1)
        rates=r['metrics']['window32_rates'];axes[2].plot([32*i for i in range(len(rates))],rates,color=COLORS[mi],label=mode,lw=1.3)
    for ax in axes:ax.grid(alpha=.2);ax.legend(loc='upper right',ncol=3,fontsize=8)
    axes[0].set_ylabel('First word (cycles)');axes[1].set_ylabel('Completion (cycles)');axes[2].set_ylabel('32-block words/cycle')
    axes[0].set_xlabel('Measured block index (first 128 shown)');axes[1].set_xlabel('Measured block index (first 128 shown)');axes[2].set_xlabel('Measured block index (all 1,024)')
    fig.suptitle('P2 · N=8, S=3 · alternating same-bank rows · seed 11 · early on\nBlock indices align work; external events stay aligned to absolute reset-relative cycles.',fontsize=12)
    for suffix in ['png','svg']:
        path=ROOT/f'results/memory-timing-variability.{suffix}';fig.savefig(path,dpi=150);files.append(path)
    plt.close(fig)
    metadata=dict(matplotlib=matplotlib.__version__,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  summary_sha256=hashlib.sha256((OUT/'summary.json').read_bytes()).hexdigest(),
                  output_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (OUT/'plot-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('PASS six standalone plot artifacts generated')
if __name__=='__main__':main()

"""Versioned exogenous inputs. This module has no DUT/mode/S inputs."""
import hashlib
import json
import math
from pathlib import Path

SEEDS = [11,29,47,83]
RESOURCES = [('a-phase',3,2),('b-phase',256,16),('maintenance-phase',2048,32),('shared-phase',64,8)]

def digest(seed, resource, index):
    return int.from_bytes(hashlib.sha256(f'memtiming-v1|{seed}|{resource}|{index}'.encode()).digest(),'big')

def active(c, event):
    period,duration,phase=event
    return (c+period-phase)%period<duration

def events(seed):
    return [(p,d,digest(seed,r,0)%p) for r,p,d in RESOURCES]

def gap_bound(schedule, shared):
    period=math.lcm(*(e[0] for e in schedule))
    result=[]
    for iface in range(2):
        available=[not active(c,schedule[iface]) and (iface==0 or not active(c,schedule[2]))
                   and (not shared or not active(c,schedule[3])) for c in range(period)]
        assert any(available), 'NO_PROGRESS_CALENDAR'
        run=maximum=0
        for ok in available*2:
            run=0 if ok else run+1; maximum=max(maximum,run)
        result.append(maximum+1) # distance between service opportunities
    return result

def bound(case, seed):
    # Serialize all N words pessimistically, charge worst row setup+one restart per word.
    # B maintenance period 2048 > 24 setup + 32 pause + 2*max service gap;
    # RR can lose at most one eligible opportunity to the other path.
    gap=max(gap_bound(events(seed),True))*2
    a=case['args']; n=case['N']; blocks=case['warmup']+case['measured']
    perword=max(a['a_interval'],a['b_interval'])+max(a['a_gap'],a['b_gap'])+24+32+gap+2
    perblock=n*perword+max(a['a_latency'],a['b_latency'])+7
    perblock+=max(a['a_cooldown'],a['b_cooldown'])+max(a['a_accept_period'],a['b_accept_period'])
    perblock+=n*a['sink_period']+a['stall_length']+16
    return ((blocks*perblock+128+15)//16)*16

def write_calendar(path, length, seed=None, schedule=None, jitter=True):
    schedule=schedule or events(seed)
    assert length<=67108864
    with path.open('w') as f:
        f.write(str(length)+'\n')
        f.writelines(f'{p} {d} {phase}\n' for p,d,phase in schedule)
        for i in range((length+15)//16):
            v=(digest(seed,'A',i)%3) | ((digest(seed,'B',i)%8)<<2) if jitter else 0
            f.write(f'{v:02x}\n')
    info=dict(version='memtiming-v1',length=length,seed=seed,jitter=jitter,
              periodic_events=schedule,encoding='header: finite length; four period/duration/phase rows; 16-cycle packed A[1:0],B[4:2] jitter samples',
              sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path.with_suffix('.json').write_text(json.dumps(info,indent=2)+'\n')
    return info

def workload(n, kind, length=8192):
    indices=list(range(128))
    if kind=='permuted':
        indices.sort(key=lambda i:hashlib.sha256(f'memtiming-workload-v1|7|{i}'.encode()).digest())
    if kind in ('sequential','permuted'):
        bases=[256+i*n for i in indices]
    elif kind=='conflict': bases=[0,1024] # same bank, alternating row; fixed smaller footprint is explicit
    elif kind=='expanded':
        count=65536//n
        indices=sorted(range(count),key=lambda i:hashlib.sha256(f'memtiming-expanded-v1|7|{i}'.encode()).digest())
        bases=[i*n for i in indices]
    else: raise ValueError(kind)
    return [bases[i%len(bases)] for i in range(length)]

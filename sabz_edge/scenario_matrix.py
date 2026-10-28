"""Explicit queue/arrival/fault scenario matrix using the real kernel and guard.
Synthetic point queues: no collision, turning, pedestrian or camera validation.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import itertools
from .core import APPROACHES,Controller,Observation,Timing
from .cabinet_model import Guard

DT=.1
@dataclass(frozen=True)
class Case:
    name:str
    initial:tuple=(0,0,0,0)
    duration:float=240
    arrivals:tuple=() # (time, approach index)
    blocked:tuple=() # (start, end, approach index)
    sensor_loss:tuple=()
    unhealthy:tuple=()
    occupied:tuple=()
    fast_protection:bool=False
    slow_protection:bool=False


def between(t,intervals):return any(start<=t<end for start,end in intervals)

def run_case(case):
    timing=Timing();kernel=Controller(timing,0);cabinet=Guard(timing,0)
    queues=[deque([0.0]*n) for n in case.initial]
    arrived=list(case.initial);served=[0]*4;first=[None]*4;max_wait=[0.0]*4
    departures=[0.0]*4;recent=[deque() for _ in APPROACHES]
    arrivals=sorted(case.arrivals);pos=0;last_observation=received=None
    stages=[];greens=[];maximums=holds=0;peak=list(case.initial);saturated=0
    previous=('ALL_RED','NS');entered=0.;current_green=None;violations=[]
    for step in range(round(case.duration/DT)+1):
        t=round(step*DT,6)
        while pos<len(arrivals) and arrivals[pos][0]<=t:
            stamp,index=arrivals[pos];queues[index].append(stamp);recent[index].append(stamp);arrived[index]+=1;pos+=1
        for i in range(4):
            while recent[i] and recent[i][0]<t-30:recent[i].popleft()
            peak[i]=max(peak[i],len(queues[i]))
            if queues[i]:max_wait[i]=max(max_wait[i],t-queues[i][0])
        blocked={i for start,end,i in case.blocked if start<=t<end}
        packet={'schema_version':3,'sequence':step,'captured_at':1000000+t,
                'counts':{a:min(500,len(queues[i])) for i,a in enumerate(APPROACHES)},
                'healthy':not between(t,case.unhealthy),'conflict_clear':not between(t,case.occupied),
                'downstream_counts':{a:20 if i in blocked else 0 for i,a in enumerate(APPROACHES)},
                'downstream_capacity':dict.fromkeys(APPROACHES,20),'approaching':dict.fromkeys(APPROACHES,0),
                'arrival_rate':{a:min(5,len(recent[i])/30) for i,a in enumerate(APPROACHES)},
                'oldest_wait_s':{a:min(3600,t-queues[i][0]) if queues[i] else 0 for i,a in enumerate(APPROACHES)},
                'nearest_moving_distance_m':dict.fromkeys(APPROACHES,None),
                'max_approach_speed_mps':dict.fromkeys(APPROACHES,0),'distance_uncertainty_m':dict.fromkeys(APPROACHES,0)}
        if any(len(q)>500 for q in queues):saturated+=1
        # Fixed repeated metric detections test extension bounds, not trajectories.
        if case.fast_protection or case.slow_protection:
            for a in APPROACHES:
                packet['nearest_moving_distance_m'][a]=50 if case.fast_protection else 70
                packet['max_approach_speed_mps'][a]=12 if case.fast_protection else 2.78
        if not between(t,case.sensor_loss):
            last_observation=Observation.parse(packet,1000000+t);received=t
        intent=kernel.tick(t,last_observation,received)
        actual=cabinet.accept(dict(intent,command_sequence=step+1,lease_s=.5),t)
        lamps=actual['lamps'];signature=(actual['stage'],actual['phase'])
        if actual['stage']=='GREEN' and actual['elapsed_s']>timing.max_green+DT+.001:violations.append('maximum_green_exceeded')
        if actual['stage']=='GREEN' and (between(t,case.unhealthy) or between(t,case.sensor_loss)):
            windows=case.unhealthy+case.sensor_loss
            for start,end in windows:
                if start+timing.stale_after+DT<=t<end:violations.append('green_persisted_after_sensor_deadline')
        if any(lamps[a]!='RED' for a in 'NS') and any(lamps[a]!='RED' for a in 'EW'):violations.append('conflicting_outputs')
        if actual['fault'] or intent['fault']:violations.append('unexpected_fault')
        if signature!=previous:
            old_stage,old_phase=previous;elapsed=t-entered
            if old_stage=='YELLOW' and elapsed+1e-7<timing.yellow:violations.append('short_yellow')
            if old_stage=='ALL_RED' and actual['stage']=='GREEN':
                if elapsed+1e-7<timing.all_red:violations.append('short_clearance')
                indexes=(0,1) if actual['phase']=='NS' else (2,3)
                if any(i in blocked for i in indexes):violations.append('green_started_into_blocked_receiving_link')
                if between(t,case.occupied):violations.append('green_started_in_occupied_intersection')
            if old_stage=='GREEN':
                if elapsed+1e-7<timing.min_green and intent['reason']!='sensor_unavailable':violations.append('short_minimum_green')
                if elapsed>timing.max_green+DT+.001:violations.append('maximum_green_exceeded')
                greens.append({'phase':old_phase,'start_s':current_green,'end_s':t,'duration_s':round(elapsed,3),'reason':intent['reason']})
            if actual['stage']=='GREEN':current_green=t
            stages.append({'t':t,'stage':actual['stage'],'phase':actual['phase'],'reason':intent['reason'],'queues':[len(q) for q in queues]})
            previous=signature;entered=t
        if intent['reason']=='maximum_green':maximums+=1
        if intent['reason']=='approach_protection_70m':holds+=1
        for i,a in enumerate(APPROACHES):
            if lamps[a]!='GREEN':departures[i]=t+1 # Simplified startup lost time.
            elif i not in blocked and queues[i] and t>=departures[i]:
                stamp=queues[i].popleft();served[i]+=1;max_wait[i]=max(max_wait[i],t-stamp)
                if first[i] is None:first[i]=t
                departures[i]=t+2 # .5 vehicles/s per approach assumption.
    if case.fast_protection and not (holds and maximums):violations.append('fast_approach_not_bounded_by_maximum')
    if case.slow_protection and holds:violations.append('slow_vehicle_incorrectly_holds_green')
    remaining=[len(q) for q in queues]
    if any(arrived[i]!=served[i]+remaining[i] for i in range(4)):violations.append('vehicle_conservation')
    # Check service to each initially waiting approach in an unobstructed run.
    if not (case.blocked or case.sensor_loss or case.unhealthy or case.occupied):
        for i,count in enumerate(case.initial):
            if count and (first[i] is None or first[i]>75):violations.append('initial_demand_not_served_within_75s')
    return {'name':case.name,'initial':list(case.initial),'duration_s':case.duration,'passed':not violations,
            'violations':sorted(set(violations)),'arrived':arrived,'served':served,'remaining':remaining,
            'first_service_s':first,'max_observed_wait_s':[round(v,2) for v in max_wait],
            'peak_queue':peak,'maximum_green_seen':maximums>0,'approach_hold_seen':holds>0,
            'count_saturation_ticks':saturated,'green_intervals':greens,'transitions':stages,
            'input_sha256':hashlib.sha256(json.dumps(case.__dict__,sort_keys=True).encode()).hexdigest()}


def scenario_matrix():
    cases=[]
    for name,initial in [('empty',(0,0,0,0)),('one_each',(1,1,1,1)),('equal_10',(10,10,10,10)),
                         ('equal_50',(50,50,50,50)),('equal_100',(100,100,100,100)),('overload_250_each',(250,250,250,250))]:
        cases.append(Case(name,initial,duration=600 if '250' in name else 300))
    for index,a in enumerate(APPROACHES):
        for n in (1,50,100):
            q=[0]*4;q[index]=n;cases.append(Case(f'{n}_only_{a}',tuple(q)))
        q=[1]*4;q[index]=50;cases.append(Case(f'50_{a}_others_1',tuple(q)))
        q=[0]*4;q[index]=50;q[(index+2)%4]=1;cases.append(Case(f'50_{a}_one_cross',tuple(q)))
    rush=tuple((round(30+i*.2,3),j) for i in range(300) for j in range(4))
    cases.append(Case('sudden_rush',(1,1,1,1),duration=360,arrivals=rush))
    overload=tuple((float(t),j) for t in range(240) for j in range(4))
    cases.append(Case('sustained_over_capacity',duration=300,arrivals=overload))
    tidal=tuple((t/2,j) for t in range(480) for j in ((0,1) if t<240 else (2,3)))
    cases.append(Case('rush_changes_direction',duration=360,arrivals=tidal))
    cases.extend([Case('one_NS_exit_blocked',(50,0,1,1),blocked=((0,60,0),)),
                  Case('all_exits_blocked_then_reopen',(50,50,50,50),blocked=tuple((0,30,i) for i in range(4))),
                  Case('sensor_feed_loss',(100,100,100,100),sensor_loss=((60,75),)),
                  Case('sensor_unhealthy',(100,100,100,100),unhealthy=((60,75),)),
                  Case('intersection_not_clear',(1,1,1,1),occupied=((0,20),)),
                  Case('fast_70m_extension_bounded',(50,50,1,1),fast_protection=True),
                  Case('slow_70m_no_indefinite_hold',(50,50,1,1),slow_protection=True)])
    return cases


def exhaustive_queue_grid():
    for initial in itertools.product((0,1,50,100),repeat=4):
        yield Case('grid_'+'_'.join(map(str,initial)),initial,duration=90)

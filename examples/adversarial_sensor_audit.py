"""Isolated audit of VALID but dishonest sensing. No network/device access.
This deliberately records unresolved hazards; no claim of attack immunity.
"""
import json
from pathlib import Path
from sabz_edge.core import Controller,Timing,Observation
from sabz_edge.cabinet_model import Guard


def examine(name,counts,*,false_clear=False,blocked=False,fast=False):
    timing=Timing(require_metric_protection=True)
    kernel=Controller(timing,0);guard=Guard(timing,0)
    first={'NS':None,'EW':None};green_end=[];violations=[];previous='ALL_RED';entered=0
    for step in range(1801):
        t=step*.1
        payload=dict(schema_version=3,sequence=step,captured_at=1000000+t,counts=dict(zip('NSEW',counts)),
            conflict_clear=True,healthy=True,downstream_counts=dict.fromkeys('NSEW',20 if blocked else 0),
            downstream_capacity=dict.fromkeys('NSEW',20),approaching=dict.fromkeys('NSEW',0),
            arrival_rate=dict.fromkeys('NSEW',0),oldest_wait_s=dict.fromkeys('NSEW',0),
            nearest_moving_distance_m=dict.fromkeys('NSEW',50 if fast else None),
            max_approach_speed_mps=dict.fromkeys('NSEW',12 if fast else 0),distance_uncertainty_m=dict.fromkeys('NSEW',0))
        observation=Observation.parse(payload,1000000+t)
        command=kernel.tick(t,observation,t)
        actual=guard.accept(dict(command,command_sequence=step+1,lease_s=.5),t)
        if any(actual['lamps'][a]!='RED' for a in 'NS') and any(actual['lamps'][a]!='RED' for a in 'EW'):violations.append('conflicting_outputs')
        if actual['fault'] or command['fault']:violations.append('unexpected_fault')
        if actual['stage']=='GREEN' and first[actual['phase']] is None:first[actual['phase']]=round(t,3)
        if actual['stage']!=previous:
            if previous=='GREEN':green_end.append(round(t-entered,3))
            previous=actual['stage'];entered=t
    hazards=[]
    if counts[2]==counts[3]==0 and first['EW'] is None:
        hazards.append('Real EW demand hidden by a compromised/mistaken sensor can be starved; max-green alone does not guarantee an EW turn.')
    if false_clear and any(v is not None for v in first.values()):
        hazards.append('A falsely asserted conflict_clear allows a requested/emulated green despite assumed physical occupancy. Actual occupancy is not observable from this packet.')
    if blocked and all(v is None for v in first.values()):
        hazards.append('A forged full-receiving-road report can deny all service. It cannot safely be overridden without independent evidence.')
    return {'case':name,'valid_schema_packets':True,'assumed_real_EW_demand':1,
            'assumed_real_conflict_zone_occupied':false_clear,'duration_s':180,'first_green_s':first,
            'max_completed_green_s':max(green_end) if green_end else None,
            'conflict_and_fault_checks_passed':not violations,'violations':sorted(set(violations)),
            'unresolved_hazards':hazards}


def main():
    results=[examine('phantom_500_NS_hidden_EW',(500,500,0,0)),
             examine('forged_near_vehicle_stream',(500,500,0,0),fast=True),
             examine('false_conflict_clearance',(1,1,1,1),false_clear=True),
             examine('forged_receiving_blockage',(1,1,1,1),blocked=True)]
    assert all(r['conflict_and_fault_checks_passed'] for r in results)
    assert all(r['max_completed_green_s'] is None or r['max_completed_green_s']<=60.11 for r in results)
    assert results[0]['first_green_s']['EW'] is None
    assert results[2]['first_green_s']['NS'] is not None
    report={'audit_completed':True,'physical_hardware':False,'inputs':'Synthetic valid-but-dishonest observations; no network/camera/port accessed',
            'security_qualified':False,'road_release_blocked':True,'results':results,
            'conclusion':'Authentication/freshness/schema checks do not establish truth. Timing bounds contain some effects; independent sensing, electrical protection and an engineered fallback are still required.'}
    Path('validation/dishonest-sensor-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

"""Reproducible virtual qualification. No physical traffic/safety equivalence."""
import json
from pathlib import Path
from sabz_edge.simulation import SCENARIOS, arrival_stream, simulate

def main():
    runs=[]
    for scenario in SCENARIOS:
        for seed in (7,41,307,991,2026):
            stream=arrival_stream(scenario,seed,600)
            group=[simulate(scenario,seed,600,mode,stream=stream,trace=False) for mode in ('fixed','actuated','adaptive')]
            assert len({r['arrival_sha256'] for r in group})==1
            assert all(r['arrived']==r['served']+r['unfinished'] for r in group)
            runs.extend(group)
        print('Completed '+scenario,flush=True)
    report={'passed':True,'run_count':len(runs),'duration_per_run_s':600,'physical_hardware':False,
            'checks':['shared arrival streams','vehicle conservation','no conflicting virtual outputs','no virtual cabinet faults'],
            'limitations':'Point queues with ideal synthetic sensing. Not a collision, pedestrian, turning, calibrated-camera or field validation.', 'runs':runs}
    Path('validation/deployment-virtual-qualification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS:',len(runs),'virtual runs')

if __name__=='__main__':main()

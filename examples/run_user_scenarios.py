"""Run explicit user queue cases; save traces and a readable results table."""
import json
from pathlib import Path
from sabz_edge.scenario_matrix import scenario_matrix,run_case,exhaustive_queue_grid

def main():
    rows=[]
    for case in scenario_matrix():
        row=run_case(case);rows.append(row)
        print(('PASS' if row['passed'] else 'FAIL'),row['name'],'first',row['first_service_s'],'left',row['remaining'],row['violations'],flush=True)
    grid=[]
    for case in exhaustive_queue_grid():
        r=run_case(case)
        grid.append({k:v for k,v in r.items() if k not in ('transitions','green_intervals')})
    print('Queue grid:',len(grid),'cases;',sum(not r['passed'] for r in grid),'failures',flush=True)
    Path('validation/exhaustive-queue-grid.json').write_text(json.dumps({'passed':all(r['passed'] for r in grid),'cases':grid},indent=2),encoding='utf-8')
    report={'passed':all(r['passed'] for r in rows) and all(r['passed'] for r in grid),'case_count':len(rows),'additional_queue_grid_cases':len(grid),'approaches':['N','S','E','W'],
            'phase_groups':{'NS':['N','S'],'EW':['E','W']},'physical_hardware':False,
            'limitations':['Point queues; ideal synthetic measurements; no collisions, turns or pedestrians.',
                           'Counts above 500 are capped at the observation boundary; simulator retains true queues and records saturation.',
                           'Five-arm junctions and independent four-phase control are unsupported.','Fixed 70m detections test bounds, not real vehicle trajectories.'],
            'cases':rows}
    Path('validation/user-scenario-matrix.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    lines=['# Explicit traffic-scenario results','',
           'Synthetic two-phase point-queue checks. Times are seconds from startup; -- means no service was needed/observed.',
           'NS serves N and S together; EW serves E and W together. Five-arm junctions are not supported.','',
           '| Case | Initial N/S/E/W | First service N/S/E/W (s) | Served | Remaining | Result |',
           '|---|---|---|---|---|---|']
    for r in rows:
        fmt=lambda values:'/'.join('--' if v is None else str(round(v,1) if isinstance(v,float) else v) for v in values)
        lines.append(f"| {r['name']} | {fmt(r['initial'])} | {fmt(r['first_service_s'])} | {sum(r['served'])} | {sum(r['remaining'])} | {'PASS' if r['passed'] else ', '.join(r['violations'])} |")
    lines+=['','Over-capacity demand may leave queues even when safety and service checks pass. Passing does not mean all traffic cleared or establish field safety.']
    Path('validation/user-scenario-results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert report['passed'],'Scenario failures require investigation'
    print('Completed',len(rows),'cases',flush=True)

if __name__=='__main__':main()

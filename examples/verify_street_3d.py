"""Verify the synthetic street-demo scenarios and optionally decode its video."""
import json
from pathlib import Path
from render_street_3d import run_case, ROOT
import cv2

results={}
for name in ('Fast approach / bounded extension','Slow approach / no indefinite hold','70 vehicles / one waiting bike'):
    records=run_case(name)
    transitions=[]
    previous=None
    for index,r in enumerate(records):
        s=r['state'];signature=(s['stage'],s['phase'])
        assert not (s['lamps']['N']=='GREEN' and s['lamps']['E']=='GREEN')
        if index:
            before=records[index-1]
            assert abs(r['distance']-before['distance'])<=12/15+.001
        if signature!=previous:transitions.append(dict(t=round(r['t'],2),stage=s['stage'],phase=s['phase'],reason=s['reason']))
        previous=signature
    if name.startswith('Fast'):assert any(r['state']['reason']=='approach_protection_70m' for r in records)
    if name.startswith('Slow'):assert any(r['state']['stage']=='YELLOW' and r['t']<12 for r in records)
    if name.startswith('70'):assert any(r['state']['stage']=='GREEN' and r['state']['phase']=='EW' for r in records)
    results[name]={'frames':len(records),'transitions':transitions}
video=ROOT/'validation'/'sabz-street-level-3d.mp4'
if video.exists():
    cap=cv2.VideoCapture(str(video));count=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        assert frame.shape==(720,1280,3)
        count+=1
    cap.release()
    assert count==sum(r['frames'] for r in results.values()),count
    results['video']={'decoded_frames':count,'seconds':count/15}
(ROOT/'validation'/'street-3d-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))

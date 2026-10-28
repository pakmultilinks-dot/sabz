"""Render reproducible controller traces as an engineering video (synthetic input)."""
import json
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sabz_edge.core import Controller, Observation, Timing

ROOT = Path(__file__).resolve().parents[1]

def observation(t, distance=50, speed=12, heavy=False):
    maps = lambda values: dict(zip('NSEW', values))
    data = dict(schema_version=3, sequence=int(t*100)+1, captured_at=1000+t,
        counts=maps((70,0,1,0) if heavy else (1,0,70,0)), conflict_clear=True, healthy=True,
        downstream_counts=maps((0,0,0,0)), downstream_capacity=maps((20,20,20,20)),
        approaching=maps((1,0,0,0)), arrival_rate=maps((0,0,0,0)), oldest_wait_s=maps((0,0,0,0)),
        nearest_moving_distance_m=maps((distance,None,None,None)),
        max_approach_speed_mps=maps((speed,0,0,0)), distance_uncertainty_m=maps((1,1,1,1)))
    return Observation.parse(data,1000+t)

def trace(kind):
    c=Controller(Timing(),0)
    states=[]
    for step in range(1401):
        t=step*.05
        distance,speed=(70,2.78) if kind=='Slow vehicle' else (50,12)
        ob=observation(t,distance,speed,heavy=t<3 or kind=='70 vehicles versus one bike')
        state=c.tick(t,ob,t)
        states.append(dict(t=round(t,2),distance=distance,speed=speed,**state))
    return states


def main():
    out=ROOT/'validation'/'approach-engineering-demo.mp4'
    writer=cv2.VideoWriter(str(out),cv2.VideoWriter_fourcc(*'mp4v'),20,(1280,720))
    if not writer.isOpened(): raise RuntimeError('MP4 encoder unavailable')
    evidence={}
    colors={'GREEN':(90,220,70),'YELLOW':(30,210,250),'RED':(70,70,240)}
    scenes=[('Fast approach',8,13),('Slow vehicle',8,13),('Maximum timer',59,66),('70 vehicles versus one bike',59,69)]
    for title,start,end in scenes:
        states=trace(title); evidence[title]=states
        for frame in range(160):
            t=start+(end-start)*frame/159
            state=states[min(round(t/.05),len(states)-1)]
            im=np.full((720,1280,3),(24,19,15),np.uint8)
            def text(line,y,size=.8,color=(225,230,235)):
                cv2.putText(im,line,(45,y),cv2.FONT_HERSHEY_SIMPLEX,size,color,2,cv2.LINE_AA)
            text('SABZ | Bounded approach protection + fair turns',55,1)
            text('SYNTHETIC CONTROLLER TRACE | NOT ROAD VALIDATION',95,.65,(70,185,250))
            text(title,155,1.1)
            text(f"Clock {state['t']:.2f}s   Phase {state['phase']}   Stage {state['stage']}",215)
            text(f"Decision: {state['reason']}",260)
            text(f"Protection: {state['approach_protection']}",305)
            text(f"Distance {state['distance']} m | Speed {state['speed']*3.6:.1f} km/h",350)
            cv2.rectangle(im,(80,440),(1180,510),(65,65,65),-1)
            stop=1130; scale=12
            cv2.line(im,(stop,425),(stop,525),(255,255,255),3)
            zone=stop-70*scale
            cv2.line(im,(zone,425),(zone,525),(100,190,250),3)
            cv2.putText(im,'70 m',(zone-20,555),cv2.FONT_HERSHEY_SIMPLEX,.6,(100,190,250),2)
            x=int(stop-state['distance']*scale)
            cv2.rectangle(im,(x-20,460),(x+20,490),(210,175,70),-1)
            for i,a in enumerate('NE'):
                cv2.circle(im,(1030+i*100,160),22,colors[state['lamps'][a]],-1)
                cv2.putText(im,a,(1020+i*100,205),cv2.FONT_HERSHEY_SIMPLEX,.6,(230,230,230),2)
            text('70 m zone + <=6 s arrival window; 60 s max green remains binding.',615,.65)
            text('Yellow 3 s / clearance 2 s are bench values requiring site design.',650,.65)
            text('Repeated synthetic detections illustrate decisions, not physical trajectories.',685,.6)
            writer.write(im)
    writer.release()
    (ROOT/'validation'/'approach-video-traces.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    cap=cv2.VideoCapture(str(out)); count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); ok,frame=cap.read();cap.release()
    assert ok and count==640
    cv2.imwrite(str(ROOT/'validation'/'approach-video-preview.png'),frame)
    print(json.dumps({'video':str(out),'frames':count,'duration_s':32,'synthetic':True}))

if __name__=='__main__':main()

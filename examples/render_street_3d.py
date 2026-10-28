"""CPU perspective 3D renderer. Synthetic kinematics, real SABZ controller.
Run: python examples/render_street_3d.py
No surveillance data, external assets or network dependencies.
"""
import json
import math
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sabz_edge.core import Controller, Timing
from render_engineering_video import observation
ROOT=Path(__file__).resolve().parents[1]
FPS=15
DT=1/FPS
W,H=426,450

class View:
    def __init__(self, eye, target):
        self.eye=np.array(eye,dtype=float)
        forward=np.array(target,dtype=float)-self.eye
        forward/=np.linalg.norm(forward)
        right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right)
        up=np.cross(right,forward)
        self.axes=np.array([right,up,forward])
        self.faces=[]
    def polygon(self, vertices, color):
        xyz=(np.array(vertices)-self.eye)@self.axes.T
        # Clip polygons against the near plane rather than dropping the road
        # or ground when a camera sits over a polygon.
        if np.any(xyz[:,2]<.2):
            clipped=[]
            for a,b in zip(xyz,np.roll(xyz,-1,axis=0)):
                if a[2]>=.2:clipped.append(a)
                if (a[2]>=.2)!=(b[2]>=.2):
                    clipped.append(a+(.2-a[2])/(b[2]-a[2])*(b-a))
            if len(clipped)<3:return
            xyz=np.array(clipped)
        points=np.column_stack((W/2+330*xyz[:,0]/xyz[:,2], H*.48-330*xyz[:,1]/xyz[:,2]))
        points=np.clip(points,-100000,100000)
        self.faces.append((float(np.mean(xyz[:,2])),points.astype(np.int32),color))
    def box(self, x,y,z,sx,sy,sz,color):
        p=[(x+dx*sx/2,y+dy*sy/2,z+dz*sz) for dz in (0,1) for dy in (-1,1) for dx in (-1,1)]
        for indexes,shade in [((0,1,3,2),.6),((4,6,7,5),1.1),((0,4,5,1),.8),((2,3,7,6),.95),((0,2,6,4),.7),((1,5,7,3),1)]:
            self.polygon([p[i] for i in indexes],tuple(min(255,int(c*shade)) for c in color))
    def image(self):
        image=np.full((H,W,3),(204,183,151),np.uint8)
        for _,points,color in sorted(self.faces,key=lambda x:x[0],reverse=True):cv2.fillConvexPoly(image,points,color,cv2.LINE_AA)
        return image

def car(v,x,y,bike=False,color=(185,130,55),axis='N'):
    sx,sy=(.65,1.7) if bike else (1.8,4.2)
    if axis=='E':sx,sy=sy,sx
    v.box(x,y,.28,sx,sy,.8,color)
    v.box(x,y,.95,sx*.85,sy*.52,.6,(73,80,88))
    for dx in (-sx*.44,sx*.44):
        for dy in (-sy*.32,sy*.32):v.box(x+dx,y+dy,.1,.25,.48,.45,(30,30,32))

def world(v,state,distance,bike_x,fair):
    v.polygon([(-180,-180,-.1),(180,-180,-.1),(180,180,-.1),(-180,180,-.1)],(91,123,98))
    # Segment the long roads to avoid near-plane rejection from a driver camera.
    for a in range(-150,150,5):
        v.polygon([(-7,a,0),(7,a,0),(7,a+5,0),(-7,a+5,0)],(68,73,78))
        v.polygon([(a,-7,.01),(a+5,-7,.01),(a+5,7,.01),(a,7,.01)],(68,73,78))
        if abs(a)>10:
            v.box(0,a,.025,.14,2.5,.015,(190,205,210))
            v.box(a,0,.026,2.5,.14,.015,(190,205,210))
    for y in (-12,12):v.box(3 if y<0 else -3,y,.04,5,.35,.015,(235,235,235))
    for x in (-12,12):v.box(x,-3 if x<0 else 3,.04,.35,5,.015,(235,235,235))
    v.box(3,-82,.04,6,.3,.02,(235,190,35))
    for x in (-23,24):
        for y in (-95,-60,-28,26,62):
            v.box(x,y,0,15,18,9+(abs(y)%13),(145,154,165))
            for z in (3,6,9):v.box(x+(8 if x<0 else -8),y,z,.1,12,.9,(95,118,131))
    for x,y,approach in ((7,-11,'N'),(-11,-7,'E')):
        v.box(x,y,0,.25,.25,5,(62,65,67));v.box(x,y,4.5,.85,.55,2,(30,32,34))
        for i,name in enumerate(('RED','YELLOW','GREEN')):
            c={'RED':(55,65,240),'YELLOW':(25,210,245),'GREEN':(65,225,65)}[name] if state['lamps'][approach]==name else (45,45,45)
            v.box(x,y-.32,5.9-i*.6,.48,.12,.38,c)
    car(v,3,-12-distance)
    car(v,bike_x,-3,bike=True,color=(65,85,225),axis='E')
    if fair:
        for i in range(16):car(v,3,-20-i*6,color=(95+i*5,130,170-i*4))


def run_case(name):
    c=Controller(Timing(),0)
    fair=name=='70 vehicles / one waiting bike'
    start=55 if fair else 7
    duration=20 if fair else 14
    distance=70 if 'Slow' in name else 60
    speed=2.78 if 'Slow' in name else 12
    bike_x=-15.
    records=[]
    # Continuous tick history is essential; no time-jump overrun or skipped clearance.
    for step in range(int((start+duration)*FPS)):
        t=step*DT
        if t>=start:
            lamp=c.snapshot(t)['lamps']['N']
            if distance>0:
                target=speed
                if lamp!='GREEN':target=min(speed,math.sqrt(max(0,2*2.5*max(0,distance-2))))
                speed=max(0,min(speed+.8*DT,target))
            distance-=speed*DT
            if c.snapshot(t)['lamps']['E']=='GREEN':bike_x+=min(6,(t-max(start,67))*.8 if t>67 else 2)*DT
        # Original queue picks NS at startup; competing demand follows.
        ob=observation(t,max(0,distance),speed,heavy=fair or t<3)
        if distance<=0:
            from dataclasses import replace
            ob=replace(ob,nearest_moving_distance_m=(None,None,None,None),max_approach_speed_mps=(0,0,0,0))
        state=c.tick(t,ob,t)
        if t>=start:records.append(dict(t=t,distance=distance,speed=speed,bike_x=bike_x,state=state))
    return records

def main():
    destination=ROOT/'validation'/'sabz-street-level-3d.mp4'
    writer=cv2.VideoWriter(str(destination),cv2.VideoWriter_fourcc(*'mp4v'),FPS,(1280,720))
    if not writer.isOpened():raise RuntimeError('MP4 encoder unavailable')
    traces={}
    for name in ('Fast approach / bounded extension','Slow approach / no indefinite hold','70 vehicles / one waiting bike'):
        records=run_case(name);traces[name]=records
        for r in records:
            frame=np.full((720,1280,3),(25,23,20),np.uint8)
            def text(s,y,scale=.7,color=(225,230,235)):cv2.putText(frame,s,(24,y),cv2.FONT_HERSHEY_SIMPLEX,scale,color,1,cv2.LINE_AA)
            text('SABZ | Street-level engineering demonstration',36,.9)
            text(name,72,.75)
            # Three cameras observe exactly the same world state and clock.
            cameras=[((3,-12-r['distance']+1,1.65),(3,50-r['distance'],1.65)),((10,-70,2),(0,-10,1)),((8,-10,5.5),(2,-65,1))]
            for j,(eye,target) in enumerate(cameras):
                v=View(eye,target);world(v,r['state'],r['distance'],r['bike_x'],'70 vehicles' in name)
                frame[110:560,j*426:(j+1)*426]=v.image()
                cv2.putText(frame,('DRIVER','ROADSIDE','SIGNAL CAMERA')[j],(j*426+18,100),cv2.FONT_HERSHEY_SIMPLEX,.55,(100,205,240),1,cv2.LINE_AA)
            state=r['state']
            text(f"t={r['t']:.1f}s | {state['phase']} {state['stage']} | {state['reason']}",594)
            text(f"Approach: {max(0,r['distance']):.1f} m | {r['speed']*3.6:.1f} km/h | Protection: {state['approach_protection']}",625,.65)
            text('Synthetic 3D geometry + simplified motion; actual Python controller decisions.',663,.6,(110,195,245))
            text('Not field validation. No pedestrians, turns, collision model or camera detector.',692,.6,(110,195,245))
            writer.write(frame)
        print('Rendered '+name,flush=True)
    writer.release()
    (ROOT/'validation'/'street-3d-traces.json').write_text(json.dumps(traces),encoding='utf-8')
    cap=cv2.VideoCapture(str(destination));n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.set(cv2.CAP_PROP_POS_FRAMES,75);ok,img=cap.read();cap.release()
    assert ok and n==sum(map(len,traces.values()))
    cv2.imwrite(str(ROOT/'validation'/'street-3d-preview.png'),img)
    print(json.dumps(dict(path=str(destination),frames=n,seconds=n/FPS)))
if __name__=='__main__':main()

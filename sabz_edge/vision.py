"""Local camera inference components. No model/frame downloads or image persistence.
Contract: approved YOLOv8 raw COCO-80 ONNX export, 640 square letterbox input.
Detection quality and source exposure timing still need independent validation.
"""
from dataclasses import dataclass
import hashlib
from math import hypot
from pathlib import Path
from .perception import Detection
from .core import APPROACHES,number

VEHICLES={1:'bicycle',2:'car',3:'motorcycle',5:'bus',7:'truck'}

@dataclass(frozen=True)
class Box:
    x1:float
    y1:float
    x2:float
    y2:float
    score:float
    class_id:int
    @property
    def foot(self):return ((self.x1+self.x2)/2,self.y2)


def overlap(a,b):
    width=max(0,min(a.x2,b.x2)-max(a.x1,b.x1));height=max(0,min(a.y2,b.y2)-max(a.y1,b.y1))
    intersection=width*height
    union=(a.x2-a.x1)*(a.y2-a.y1)+(b.x2-b.x1)*(b.y2-b.y1)-intersection
    return intersection/union if union>0 else 0


def decode_yolo(output,*,image_width,image_height,scale,pad_x,pad_y,threshold=.35):
    import numpy as np
    for value,name in ((image_width,'image width'),(image_height,'image height')):
        if type(value) is not int or not 16<=value<=8192:raise ValueError('Invalid '+name)
    number(scale,'letterbox scale',1e-6,40)
    number(pad_x,'horizontal padding',0,640);number(pad_y,'vertical padding',0,640)
    number(threshold,'confidence threshold',.01,1)
    if not isinstance(output,np.ndarray) or output.ndim!=3 or output.shape[0]!=1 or output.shape[1]!=84 or not 1<=output.shape[2]<=20000:
        raise ValueError('Expected raw COCO-80 YOLOv8 output [1,84,N]')
    if not np.isfinite(output).all():raise ValueError('Non-finite model output')
    rows=output[0].T
    scores=rows[:,4:];classes=scores.argmax(axis=1);confidence=scores.max(axis=1)
    if np.any(scores<0) or np.any(scores>1):raise ValueError('Invalid class probabilities')
    indexes=np.flatnonzero(confidence>=threshold)
    if len(indexes)>2000:raise ValueError('Excessive inference candidates')
    boxes=[]
    for i in indexes:
        cls=int(classes[i])
        if cls not in VEHICLES and cls!=0:continue
        cx,cy,w,h=map(float,rows[i,:4])
        if w<=0 or h<=0 or max(abs(cx),abs(cy),w,h)>100000:raise ValueError('Invalid model box')
        x1=max(0,min(image_width,(cx-w/2-pad_x)/scale));x2=max(0,min(image_width,(cx+w/2-pad_x)/scale))
        y1=max(0,min(image_height,(cy-h/2-pad_y)/scale));y2=max(0,min(image_height,(cy+h/2-pad_y)/scale))
        if x2>x1 and y2>y1:boxes.append(Box(x1,y1,x2,y2,float(confidence[i]),cls))
    retained=[]
    for candidate in sorted(boxes,key=lambda b:b.score,reverse=True):
        # Class-aware NMS: a nearby motorcycle must not disappear behind a truck.
        # Cross-class duplicates remain possible and require dataset evaluation.
        if not any(overlap(candidate,old)>.5 and candidate.class_id==old.class_id for old in retained):retained.append(candidate)
    return retained


class YoloOnnx:
    def __init__(self,path,expected_sha256):
        import cv2
        path=Path(path)
        if path.suffix.lower()!='.onnx' or not path.is_file():raise ValueError('Existing local ONNX model required')
        if len(expected_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_sha256):raise ValueError('Approved model SHA-256 required')
        if path.stat().st_size>256*1024**2:raise ValueError('Model exceeds 256 MiB bound')
        with path.open('rb') as f:model_bytes=f.read(256*1024**2+1)
        if len(model_bytes)>256*1024**2:raise ValueError('Model exceeds size bound')
        if hashlib.sha256(model_bytes).hexdigest()!=expected_sha256:raise ValueError('Model hash mismatch')
        import numpy as np
        model_buffer=np.frombuffer(model_bytes,dtype=np.uint8)
        # Explicit classic CPU backend on OpenCV 5; same API as OpenCV 4.
        self.net=(cv2.dnn.readNetFromONNX(model_buffer,cv2.dnn.ENGINE_CLASSIC)
                  if hasattr(cv2.dnn,'ENGINE_CLASSIC') else cv2.dnn.readNetFromONNX(model_buffer))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.sha256=expected_sha256
    def detect(self,image):
        import cv2
        import numpy as np
        if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
            raise ValueError('Expected uint8 BGR frame')
        height,width=image.shape[:2]
        if min(width,height)<16 or width*height>3840*2160:raise ValueError('Unsupported image size')
        scale=min(640/width,640/height);new_width,new_height=round(width*scale),round(height*scale)
        pad_x=(640-new_width)//2;pad_y=(640-new_height)//2
        padded=np.full((640,640,3),114,dtype=np.uint8)
        padded[pad_y:pad_y+new_height,pad_x:pad_x+new_width]=cv2.resize(image,(new_width,new_height))
        blob=cv2.dnn.blobFromImage(padded,1/255.,(640,640),swapRB=True,crop=False)
        self.net.setInput(blob)
        return decode_yolo(self.net.forward(),image_width=width,image_height=height,scale=scale,pad_x=pad_x,pad_y=pad_y)


class RoadTracker:
    """Bounded greedy ground-plane tracker; identity/occlusion are unvalidated."""
    def __init__(self,calibrations):
        self.calibrations=calibrations;self.tracks={};self.next_id=1;self.last_time=None
    def update(self,boxes,now):
        number(now,'frame time',0,1e12)
        if self.last_time is not None and now<=self.last_time:raise ValueError('Frame times must increase')
        if len(boxes)>2000:raise ValueError('Too many boxes')
        self.tracks={k:t for k,t in self.tracks.items() if now-t['at']<=.5}
        used=set();result=[]
        for box in sorted(boxes,key=lambda b:b.score,reverse=True):
            matches=[]
            for approach in APPROACHES:
                try:x,d=self.calibrations[approach].project(*box.foot)
                except ValueError:continue
                matches.append((approach,x,d))
            if not matches:continue
            if len(matches)!=1:raise ValueError('Ambiguous overlapping surveyed road regions')
            if box.class_id==0:raise ValueError('Person in supported road region; pedestrian control not implemented')
            if box.class_id not in VEHICLES:continue
            approach,x,d=matches[0]
            best=None;cost=float('inf')
            for key,track in self.tracks.items():
                if key in used or track['approach']!=approach or track['class']!=box.class_id:continue
                distance=hypot(x-track['x'],d-track['distance'])
                gate=max(1.0,70*(now-track['at'])+self.calibrations[approach].uncertainty)
                if distance<=gate and distance<cost:best,cost=key,distance
            if best is None:
                best=self.next_id;self.next_id+=1
                if best>=2**63:raise ValueError('Tracker identity range exhausted')
            used.add(best)
            self.tracks[best]={'approach':approach,'class':box.class_id,'x':x,'distance':d,'at':now}
            result.append(Detection(best,approach,*box.foot,VEHICLES[box.class_id]))
        if len(self.tracks)>4000:self.tracks.clear();raise ValueError('Tracker memory bound exceeded')
        self.last_time=now
        return result


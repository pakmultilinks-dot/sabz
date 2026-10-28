"""Offline detector acceptance on authorized labelled images. No control outputs.
Reports aggregate metrics; requirements must come from the reviewed deployment.
"""
from collections import defaultdict
from math import isfinite
import argparse
import hashlib
import json
from pathlib import Path
import time
from .core import number
from .server import load_json
from .vision import Box,VEHICLES,YoloOnnx,overlap

CLASSES={0:'person',**VEHICLES}


def annotation(data):
    if not isinstance(data,dict) or set(data)!={'class_id','bbox'}:raise ValueError('Annotation contract mismatch')
    cls=data['class_id'];bbox=data['bbox']
    if type(cls) is not int or cls not in CLASSES or not isinstance(bbox,list) or len(bbox)!=4:raise ValueError('Unsupported annotation')
    x1,y1,x2,y2=(number(v,'box coordinate',0,100000) for v in bbox)
    if x2<=x1 or y2<=y1:raise ValueError('Invalid annotation geometry')
    return Box(x1,y1,x2,y2,1.0,cls)


def score_frame(expected,predicted,iou=.5):
    number(iou,'IoU threshold',.1,1)
    counts={k:{'tp':0,'fp':0,'fn':0,'ground_truth':0} for k in CLASSES}
    used=set()
    for b in expected:
        if b.class_id not in CLASSES:raise ValueError('Unsupported expected class')
        counts[b.class_id]['ground_truth']+=1
    for candidate in sorted(predicted,key=lambda b:b.score,reverse=True):
        if candidate.class_id not in CLASSES:raise ValueError('Unsupported prediction class')
        matches=[(overlap(candidate,g),i) for i,g in enumerate(expected) if i not in used and g.class_id==candidate.class_id]
        match=max(matches,default=(0,None))
        if match[0]>=iou:
            counts[candidate.class_id]['tp']+=1;used.add(match[1])
        else:counts[candidate.class_id]['fp']+=1
    for i,g in enumerate(expected):
        if i not in used:counts[g.class_id]['fn']+=1
    error=abs(sum(b.class_id in VEHICLES for b in expected)-sum(b.class_id in VEHICLES for b in predicted))
    return counts,error


def metrics(counts):
    result={}
    for cls,name in CLASSES.items():
        c=counts[cls];tp,fp,fn=c['tp'],c['fp'],c['fn']
        result[name]={**c,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                      'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
    return result


def acceptance(measured,frames,requirements):
    if not isinstance(requirements,dict) or set(requirements)!={'min_images','min_ground_truth_per_class','min_precision','min_recall'}:
        raise ValueError('Explicit reviewed requirements required')
    for key in ('min_images','min_ground_truth_per_class'):
        if type(requirements[key]) is not int or not 1<=requirements[key]<=100000:raise ValueError('Positive sample thresholds required')
    for key in ('min_precision','min_recall'):
        mapping=requirements[key]
        if not isinstance(mapping,dict) or set(mapping)!=set(CLASSES.values()):raise ValueError('Requirements for all supported detector classes required')
        for value in mapping.values():number(value,key,0,1)
    failures=[]
    if frames<requirements['min_images']:failures.append('insufficient_images')
    for name,c in measured.items():
        if c['ground_truth']<requirements['min_ground_truth_per_class']:failures.append(name+':insufficient_ground_truth')
        for key in ('precision','recall'):
            if c[key] is None or c[key]<requirements['min_'+key][name]:failures.append(name+':'+key)
    return {'requirements_met':not failures,'failures':failures,'commercial_ready':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True,help='JSONL of image-relative path and annotations; authorized local files only')
    p.add_argument('--model',required=True);p.add_argument('--model-sha256',required=True)
    p.add_argument('--requirements',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    import cv2
    import numpy as np
    detector=YoloOnnx(args.model,args.model_sha256)
    with args.requirements.open('rb') as f:raw=f.read(32769)
    if len(raw)>32768:raise ValueError('Requirements file too large')
    requirements=load_json(raw)
    total={k:dict(tp=0,fp=0,fn=0,ground_truth=0) for k in CLASSES}
    acceptance(metrics(total),0,requirements) # Validate thresholds before inference.
    base=args.dataset.resolve().parent;latencies=[];errors=[];digest=hashlib.sha256()
    with args.dataset.open('rb') as source:
        while True:
            line=source.readline(262145)
            if not line:break
            if len(line)>262144 or not line.endswith(b'\n') or len(latencies)>=10000:raise ValueError('Dataset exceeds bounds')
            digest.update(line);record=load_json(line)
            if not isinstance(record,dict) or set(record)!={'image','annotations'} or not isinstance(record['image'],str):raise ValueError('Dataset record mismatch')
            path=(base/record['image']).resolve()
            if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size>64*1024**2:raise ValueError('Invalid dataset image path/size')
            if not isinstance(record['annotations'],list) or len(record['annotations'])>2000:raise ValueError('Annotation bound exceeded')
            expected=[annotation(item) for item in record['annotations']]
            with path.open('rb') as image_file:image_bytes=image_file.read(64*1024**2+1)
            if len(image_bytes)>64*1024**2:raise ValueError('Image exceeds size bound')
            image=cv2.imdecode(np.frombuffer(image_bytes,dtype=np.uint8),cv2.IMREAD_COLOR)
            if image is None:raise ValueError('Dataset image could not be decoded')
            height,width=image.shape[:2]
            if any(g.x2>width or g.y2>height for g in expected):raise ValueError('Annotation outside image')
            digest.update(hashlib.sha256(image_bytes).digest())
            started=time.perf_counter();predicted=detector.detect(image);latencies.append((time.perf_counter()-started)*1000)
            counts,error=score_frame(expected,predicted);errors.append(error)
            for cls in CLASSES:
                for key in total[cls]:total[cls][key]+=counts[cls][key]
    measured=metrics(total);result=acceptance(measured,len(latencies),requirements)
    report={**result,'frames':len(latencies),'iou_threshold':.5,'confidence_threshold':.35,'metrics':measured,
            'vehicle_count_mean_absolute_error':sum(errors)/len(errors) if errors else None,
            'max_inference_ms':max(latencies) if latencies else None,'model_sha256':args.model_sha256,
            'dataset_digest':digest.hexdigest(),'raw_frames_or_boxes_exported':False,
            'limits':'Dataset-specific evaluation only; labels/split quality, calibration, camera timing, hardware and road acceptance remain separate.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as output_file:json.dump(report,output_file,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='metrics'},indent=2))
    raise SystemExit(0 if report['requirements_met'] else 1)

if __name__=='__main__':main()

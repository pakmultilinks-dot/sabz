"""Explicit local-camera sensor runner. Observe-only unless --publish is set.
Requires an approved local model and surveyed calibration; no model downloads.
"""
import argparse
import json
import os
from pathlib import Path
import time
from .client import CameraClient
from .core import APPROACHES,number
from .server import load_json
from .sensor_ingest import producer_from_file
from .vision import YoloOnnx,RoadTracker
from .capture import ProcessCapture


def independent_state(path,wall_now):
    with Path(path).open('rb') as f:raw=f.read(8193)
    if len(raw)>8192:raise ValueError('Independent sensor state too large')
    state=load_json(raw)
    required={'captured_at','conflict_clear','healthy','downstream_counts','downstream_capacity'}
    if not isinstance(state,dict) or set(state)!=required:raise ValueError('Independent sensor contract mismatch')
    stamp=number(state['captured_at'],'sensor timestamp',0,1e12)
    if not -.05<=wall_now-stamp<=.15:raise ValueError('Independent sensor state expired or future-dated')
    if type(state['healthy']) is not bool or type(state['conflict_clear']) is not bool:raise ValueError('Invalid sensor flags')
    for key in ('downstream_counts','downstream_capacity'):
        if not isinstance(state[key],dict) or set(state[key])!=set(APPROACHES):raise ValueError('Invalid downstream state')
    for a in APPROACHES:
        cap=number(state['downstream_capacity'][a],'capacity',1,500)
        number(state['downstream_counts'][a],'count',0,cap)
    return state


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device',type=int,required=True,help='Explicit authorized LOCAL camera index; no default webcam access')
    p.add_argument('--model',required=True)
    p.add_argument('--model-sha256',required=True)
    p.add_argument('--calibration',required=True)
    p.add_argument('--sensor-state',required=True,help='Fresh independently produced clearance/receiving-state JSON')
    p.add_argument('--capture-age-bound-ms',type=float,required=True,help='Externally measured worst-case exposure-to-read-return age, not an assumed zero')
    p.add_argument('--publish',action='store_true')
    p.add_argument('--endpoint',default='http://127.0.0.1:8099')
    p.add_argument('--ca-file')
    p.add_argument('--sequence-state',default='data/camera-sender.sqlite3')
    p.add_argument('--seconds',type=float,default=60)
    args=p.parse_args()
    if not 0<=args.device<=32:p.error('Device index must be 0..32')
    bound=number(args.capture_age_bound_ms,'capture age bound ms',0,1000)/1000
    number(args.seconds,'run duration',1,86400)
    producer=producer_from_file(args.calibration)
    tracker=RoadTracker(producer.calibrations)
    detector=YoloOnnx(args.model,args.model_sha256)
    client=None;capture=None;previous=0;started=time.monotonic();last_report=started
    try:
        # Spawn before opening SQLite: native database handles must not be
        # inherited through platform process launchers.
        capture=ProcessCapture(args.device)
        if args.publish:client=CameraClient(args.endpoint,os.environ['SABZ_CAMERA_TOKEN'],args.sequence_state,ca_file=args.ca_file)
        while time.monotonic()-started<args.seconds:
            cycle=time.monotonic();sample=capture.take(previous)
            try:
                if sample is None:raise ValueError('No fresh frame')
                previous,read_at,read_wall,image=sample
                # This backdating is conservative ONLY if the externally measured
                # bound is valid. VideoCapture provides no exposure guarantee.
                boxes=detector.detect(image)
                detections,pedestrians=tracker.update(boxes,read_at)
                if time.monotonic()-read_at+bound>.15:raise ValueError('Inference/capture age budget exceeded')
                state=independent_state(args.sensor_state,time.time())
                data=producer.update(detections,monotonic_now=read_at,captured_at=read_wall-bound,
                    conflict_clear=state['conflict_clear'],downstream_counts=state['downstream_counts'],
                                    downstream_capacity=state['downstream_capacity'],sensors_healthy=state['healthy'],
                                    pedestrian_queue=pedestrians)
                if time.time()-state['captured_at']>.15:
                    data['healthy']=False;data['conflict_clear']=False
                if client:client.send(**data)
                summary={'sensor_healthy':data['healthy'],'counts':data['counts'],
                         'frame_processing_ms':round((time.monotonic()-read_at)*1000,2),'publishing':bool(client)}
            except (ValueError,OSError,RuntimeError):
                if client:client.send(dict.fromkeys(APPROACHES,0),conflict_clear=False,healthy=False)
                summary={'sensor_healthy':False,'publishing':bool(client),'reason':'camera_or_independent_sensor_unavailable'}
            if time.monotonic()-last_report>=1:
                print(json.dumps(summary),flush=True);last_report=time.monotonic()
            time.sleep(max(0,.1-(time.monotonic()-cycle)))
    finally:
        try:
            if client:
                try:client.send(dict.fromkeys(APPROACHES,0),conflict_clear=False,healthy=False)
                except Exception:print('Health withdrawal was not acknowledged; receiver expiry remains necessary.',flush=True)
                finally:client.close()
        finally:
            if capture:
                if not capture.close():print('Camera worker could not be stopped; operator intervention required.',flush=True)
                elif capture.forced_termination:print('Blocked camera worker was terminated; investigate backend before restart.',flush=True)

if __name__=='__main__':main()

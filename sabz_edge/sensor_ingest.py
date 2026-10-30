"""Local JSON-lines detection bridge to authenticated observation v4.
Input is metadata from an authorized local detector, never camera images.
Calibration must be surveyed; clearance/receiving occupancy are separate inputs.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from .client import CameraClient
from .perception import Detection,MetricProducer,RoadPlane
from .server import load_json

MAX_FRAME=262144

def producer_from_file(path):
    raw=Path(path).read_bytes()
    if len(raw)>32768:raise ValueError('Calibration file too large')
    config=load_json(raw)
    if not isinstance(config,dict) or set(config)!=set('NSEW'):raise ValueError('Exactly four surveyed approach calibrations required')
    return MetricProducer({a:RoadPlane(**config[a]) for a in 'NSEW'})


def process_frame(producer,packet):
    fields={'frame_time_s','captured_at','detections','conflict_clear','downstream_counts','downstream_capacity','sensors_healthy'}
    with_peds=fields|{'pedestrian_queue'}
    if not isinstance(packet,dict) or set(packet) not in (fields,with_peds) or not isinstance(packet['detections'],list) or len(packet['detections'])>2000:
        raise ValueError('Invalid local detector frame')
    detections=[]
    for data in packet['detections']:
        if not isinstance(data,dict) or set(data)!={'track_id','approach','pixel_x','pixel_y','vehicle_class'}:raise ValueError('Invalid detection fields')
        detections.append(Detection(**data))
    return producer.update(detections,monotonic_now=packet['frame_time_s'],captured_at=packet['captured_at'],
                           conflict_clear=packet['conflict_clear'],downstream_counts=packet['downstream_counts'],
                           downstream_capacity=packet['downstream_capacity'],sensors_healthy=packet['sensors_healthy'],
                           pedestrian_queue=packet.get('pedestrian_queue'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration',required=True)
    parser.add_argument('--endpoint',default='http://127.0.0.1:8099')
    parser.add_argument('--ca-file')
    parser.add_argument('--state',default='data/metric-sensor.sqlite3')
    parser.add_argument('--validate-only',action='store_true',help='Emit aggregate observations without connecting to the service')
    args=parser.parse_args()
    producer=producer_from_file(args.calibration)
    client=None
    if not args.validate_only:client=CameraClient(args.endpoint,os.environ['SABZ_CAMERA_TOKEN'],args.state,ca_file=args.ca_file)
    try:
        while True:
            raw=sys.stdin.buffer.readline(MAX_FRAME+1)
            if not raw:break
            try:
                if len(raw)>MAX_FRAME or not raw.endswith(b'\n'):raise ValueError('Frame exceeds framing limit')
                data=process_frame(producer,load_json(raw))
            except Exception:
                # Immediately withdraw health if parsing/calibration fails;
                # never retain a previous healthy measurement silently.
                if client:client.send(dict.fromkeys('NSEW',0),conflict_clear=False,healthy=False)
                raise SystemExit('Detector frame rejected; no identifiers or raw input logged.') from None
            if client:
                print(json.dumps(client.send(**data)),flush=True)
            else:
                print(json.dumps(data,allow_nan=False),flush=True)
    finally:
        if client:client.close()

if __name__=='__main__':main()

"""Camera producer for SABZ edge. Counts alone never assert conflict clearance.

Run the edge service first; set SABZ_CAMERA_TOKEN and optionally SABZ_ENDPOINT.
This producer does not control lamps. Camera calibration and conflict-zone
sensing remain separate integration requirements.
"""
import argparse
import os
import time

from sabz_edge.client import CameraClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', default='0')
    parser.add_argument('--endpoint', default=os.environ.get('SABZ_ENDPOINT', 'http://127.0.0.1:8099'))
    parser.add_argument('--state', default='data/live-camera.sqlite3')
    args = parser.parse_args()
    from sabz_camera import LiveCameraSystem
    source = int(args.source) if args.source.isdigit() else args.source
    client = CameraClient(args.endpoint, os.environ['SABZ_CAMERA_TOKEN'], args.state)
    camera = LiveCameraSystem()
    try:
        def on_counts(counts):
            print(client.send(counts, conflict_clear=False, captured_at=time.time()), flush=True)
        camera.run_stream(source, on_counts=on_counts)
    finally:
        client.close()


if __name__ == '__main__':
    main()

"""Continuously feed synthetic bench observations through the real API."""
import argparse
import os
import time

from sabz_edge.client import CameraClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8099")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--state", default="data/bench-camera.sqlite3")
    args = parser.parse_args()
    client = CameraClient(args.endpoint, os.environ["SABZ_CAMERA_TOKEN"], args.state)
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            alternate = int((time.monotonic() - start) / 12) % 2
            counts = dict(zip("NSEW", (20, 10, 1, 1) if alternate == 0 else (1, 1, 20, 10)))
            print(client.send(counts, conflict_clear=True), flush=True)
            time.sleep(.5)
    finally:
        client.close()


if __name__ == "__main__":
    main()

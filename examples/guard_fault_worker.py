"""Disposable isolated-process fixture for killing the edge's parent process."""
import argparse
from pathlib import Path
import time

from sabz_edge.core import Timing
from sabz_edge.guard import CabinetAdapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--trace", required=True)
    args = parser.parse_args()
    timing = Timing(min_green=.1, max_green=10, yellow=.2, all_red=.1)
    adapter = CabinetAdapter(timing, trace_path=args.trace)
    seq = 0
    try:
        while True:
            seq += 1
            cmd = {"command_sequence": seq, "stage": "GREEN", "phase": "NS", "lease_s": .5,
                   "lamps": {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}}
            adapter.apply(cmd)
            if adapter.readback["stage"] == "GREEN":
                Path(args.marker).write_text("ready")
                time.sleep(60)
            time.sleep(.03)
    finally:
        adapter.close()


if __name__ == "__main__":
    main()

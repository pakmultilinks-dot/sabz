"""SABZ Live: end-to-end live video traffic control.

Connects live camera footage directly to the intelligence layer.
No simulation. No historical data. Live video in, signal decisions out.

Pipeline:
    Live video -> YOLO detect -> track -> count per approach
    -> Intelligence Layer (DQN + actuated + fixed) -> Safety -> Decision

Usage:
    python3 sabz_live.py <video_source>
    python3 sabz_live.py 0                    # webcam
    python3 sabz_live.py rtsp://cam/stream    # network camera
    python3 sabz_live.py traffic.mp4          # video file
"""
import time
import sys

from sabz_intelligence import IntelligenceLayer


class SabzLive:
    """Full live pipeline: camera -> brain -> decision."""

    def __init__(self, dqn_path="sabz_dqn_capable.npz"):
        # Intelligence layer with real trained brain
        self.brain = IntelligenceLayer(dqn_path=dqn_path)
        # Camera (imported lazily so module loads without ultralytics)
        self.camera = None
        self.phase = "NS"
        self.green_elapsed = 0.0
        self.decisions = []

    def _get_camera(self):
        if self.camera is None:
            from sabz_camera import LiveCameraSystem
            self.camera = LiveCameraSystem(frame_skip=3)
        return self.camera

    def counts_to_state(self, counts):
        """Convert live camera counts to 16-dim state vector."""
        q = [float(counts[a]) for a in ["N", "S", "E", "W"]]
        # Approaching estimated as half of queue (conservative)
        app = [c * 0.5 for c in q]
        hour = time.localtime().tm_hour + time.localtime().tm_min / 60.0
        # [queues(4), approaching(4), phase, green_elapsed,
        #  near_school, near_mosque, near_office, near_hospital,
        #  friday, hour]
        # Friday check: Monday=0 ... Sunday=6, Friday=4
        import datetime
        friday = 1.0 if datetime.datetime.now().weekday() == 4 else 0.0
        state = (q + app +
                 [1.0 if self.phase == "NS" else 0.0,
                  min(self.green_elapsed / 60.0, 1.0),
                  0.0, 0.0, 0.0, 0.0,  # location: neutral for live
                  friday, hour])
        return state

    def on_frame_counts(self, counts):
        """Called with live counts each second. Returns decision."""
        state = self.counts_to_state(counts)
        action, ctrl, regime = self.brain.decide(state)

        # Update signal phase tracking
        if action == "switch":
            self.phase = "EW" if self.phase == "NS" else "NS"
            self.green_elapsed = 0.0
        else:
            self.green_elapsed += 1.0

        result = {
            "action": action,
            "controller": ctrl,
            "regime": regime,
            "phase": self.phase,
            "counts": dict(counts),
            "ts": time.time(),
        }
        self.decisions.append(result)
        return result

    def run(self, source, max_seconds=0):
        """Run live on a video source."""
        cam = self._get_camera()
        print(f"SABZ LIVE: processing {source}")
        print("Press Ctrl+C to stop.\n")

        start = time.time()
        try:
            def on_counts(counts):
                result = self.on_frame_counts(counts)
                elapsed = time.time() - start
                print(f"[{elapsed:5.0f}s] {counts} -> "
                      f"{result['action'].upper()} "
                      f"via {result['controller']} "
                      f"({result['regime']}, phase={result['phase']})",
                      flush=True)
                if max_seconds and elapsed >= max_seconds:
                    raise StopIteration

            cam.run_stream(source, on_counts=on_counts)
        except StopIteration:
            pass
        except KeyboardInterrupt:
            print("\nstopped")

        print(f"\nDone. {len(self.decisions)} decisions made.")
        print(f"Routing: {self.brain.stats()['routed']}")
        return self.decisions


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else 0
    try:
        src = int(src)
    except ValueError:
        pass
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    live = SabzLive()
    live.run(src, max_seconds=secs)

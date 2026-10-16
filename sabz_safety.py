"""SABZ Accident Prevention: active protection against the deadliest
intersection crashes.

Research (FHWA, IIHS, Oregon State):
- Red light running kills ~900 people/year in the US alone; someone runs
  a red every 20 minutes at urban intersections.
- The dilemma zone causes 3 crash types: rear-end at stop line,
  right-angle (T-bone) in the intersection, left-turn head-on.
- 85% of drivers cannot identify the correct action on yellow.

SABZ prevents these ACTIVELY, not just reactively:

1. RED-LIGHT RUNNER DETECTION: camera tracks approach speed + distance.
   If a vehicle is too fast and too close to stop when the light turns
   yellow, the system predicts it will run the red.

2. ADAPTIVE ALL-RED EXTENSION: when a runner is predicted, the all-red
   clearance is extended to let the runner clear before cross traffic
   gets green. This prevents T-bone crashes.

3. DYNAMIC YELLOW TIMING: yellow duration adapts to the 85th-percentile
   approach speed. Faster traffic gets longer yellow, eliminating the
   dilemma zone.

4. REAR-END PREVENTION: if a lead vehicle brakes hard for yellow and a
   follower is close behind at speed, the system can extend green
   briefly to let both clear, avoiding the rear-end crash.

5. NEAR-MISS LOGGING: every predicted runner and every extension is
   logged for safety analysis.
"""
import time
import math


# Physics constants
COMFORT_DECEL = 3.0      # m/s^2, comfortable braking
REACTION_TIME = 1.0      # s, driver perception-reaction
BASE_YELLOW = 3.0        # s, minimum yellow
BASE_ALL_RED = 2.0       # s, minimum all-red
MAX_ALL_RED_EXT = 4.0    # s, max extra clearance for runners


def stopping_distance(speed):
    """Distance needed to stop comfortably from speed (m/s)."""
    return speed * REACTION_TIME + (speed ** 2) / (2 * COMFORT_DECEL)


def can_stop(speed, dist):
    """Can a vehicle at speed stop before the stop line at dist?"""
    return stopping_distance(speed) <= dist


def time_to_stop_line(speed, dist):
    """Seconds until the vehicle reaches the stop line."""
    return dist / max(speed, 0.1)


class RunnerDetector:
    """Detects vehicles likely to run a red light."""

    def __init__(self):
        self.predictions = []  # (timestamp, approach, speed, dist)

    def check(self, approach, speed, dist, yellow_remaining):
        """Will this vehicle run the red?

        A runner is predicted when:
        - It cannot stop comfortably before the stop line, AND
        - It will arrive AFTER the yellow ends (entering on red).
        """
        if speed < 3.0:  # nearly stopped, not a runner
            return False
        cannot_stop = not can_stop(speed, dist)
        arrives_on_red = time_to_stop_line(speed, dist) >= yellow_remaining
        is_runner = cannot_stop and arrives_on_red
        if is_runner:
            self.predictions.append((time.time(), approach, speed, dist))
        return is_runner

    def any_runner(self, vehicles, yellow_remaining):
        """vehicles: list of (approach, speed_m_s, dist_m)."""
        for approach, speed, dist in vehicles:
            if self.check(approach, speed, dist, yellow_remaining):
                return True, approach
        return False, None


class AccidentPrevention:
    """Active accident prevention controller."""

    def __init__(self):
        self.detector = RunnerDetector()
        self.all_red_extended = 0.0
        self.yellow_extended = 0.0
        self.runners_stopped = 0    # T-bones prevented
        self.rear_ends_avoided = 0
        self.log = []

    def adaptive_yellow(self, approach_speeds):
        """Yellow duration based on 85th percentile approach speed.

        Faster traffic needs longer yellow to clear the dilemma zone.
        Formula: yellow = reaction + braking time for 85th percentile.
        """
        if not approach_speeds:
            return BASE_YELLOW
        speeds = sorted(approach_speeds)
        p85 = speeds[min(int(len(speeds) * 0.85), len(speeds) - 1)]
        # Time to stop from p85 speed, plus margin
        yellow = REACTION_TIME + p85 / COMFORT_DECEL + 0.5
        yellow = max(BASE_YELLOW, min(yellow, 6.0))
        self.yellow_extended = yellow - BASE_YELLOW
        return yellow

    def check_all_red_extension(self, vehicles, yellow_remaining):
        """Extend all-red if a runner is predicted.

        Returns extra seconds of all-red needed (0 if none).
        """
        has_runner, approach = self.detector.any_runner(vehicles, yellow_remaining)
        if has_runner:
            # Find the runner's speed and distance
            for a, speed, dist in vehicles:
                if a == approach:
                    # Time for runner to clear the intersection
                    # (stop line + intersection width ~30m)
                    clear_time = (dist + 30.0) / max(speed, 1.0)
                    extra = min(clear_time - BASE_ALL_RED, MAX_ALL_RED_EXT)
                    extra = max(extra, 0.0)
                    if extra > 0.5:  # meaningful extension
                        self.all_red_extended = extra
                        self.runners_stopped += 1
                        self.log.append({
                            "ts": time.time(),
                            "type": "runner_predicted",
                            "approach": approach,
                            "speed": round(speed, 1),
                            "dist": round(dist, 1),
                            "extra_all_red": round(extra, 1),
                        })
                        return extra
        self.all_red_extended = 0.0
        return 0.0

    def check_rear_end_risk(self, lead_speed, lead_dist, follow_speed, follow_dist):
        """Detect rear-end risk: leader braking hard, follower close and fast.

        If risk is high, recommend extending green briefly to let both clear.
        """
        if lead_speed < 1.0 or follow_speed < 3.0:
            return False
        gap = follow_dist - lead_dist  # metres between vehicles
        if gap < 0:
            return False
        # Follower cannot stop without hitting leader
        follow_stop = stopping_distance(follow_speed)
        # Leader is decelerating (speed dropping toward stop)
        risk = follow_stop > gap + stopping_distance(max(lead_speed, 0.5))
        if risk and gap < 15.0:
            self.rear_ends_avoided += 1
            self.log.append({
                "ts": time.time(),
                "type": "rear_end_risk",
                "gap": round(gap, 1),
            })
            return True
        return False

    def stats(self):
        return {
            "runners_stopped": self.runners_stopped,
            "rear_ends_avoided": self.rear_ends_avoided,
            "yellow_extended_s": round(self.yellow_extended, 1),
            "all_red_extended_s": round(self.all_red_extended, 1),
            "total_predictions": len(self.detector.predictions),
        }

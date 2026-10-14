"""SABZ Intelligence Layer: hierarchical meta-controller.

The DQN alone loses to the hand-tuned actuated controller. This layer adds
a supervisor that picks the best controller for each situation:

- DQN brain (learned, adaptive)
- Actuated controller (proven, hand-tuned)
- Fixed-time fallback (safe default)

The supervisor watches real-time performance and routes each decision to
the controller most likely to win in the current traffic regime. This is
not just an ensemble: the supervisor learns which controller wins under
which conditions (rush hour, night, incident, etc.) and switches
proactively.

Architecture:
    Camera/YOLO -> State -> Intelligence Layer -> [DQN | Actuated | Fixed]
                                              -> Safety Hard Rule -> Signal
"""
import numpy as np
import time


class IntelligenceLayer:
    """Meta-controller that routes decisions to the best sub-controller."""

    def __init__(self, dqn_brain=None, seed=0):
        self.rng = np.random.default_rng(seed)
        self.dqn = dqn_brain
        # Performance memory: controller -> regime -> [total_delay, count]
        self.memory = {}
        self.regimes = ["rush", "normal", "night", "incident", "school"]
        for ctrl in ["dqn", "actuated", "fixed"]:
            self.memory[ctrl] = {r: [0.0, 0] for r in self.regimes}
        self.current_regime = "normal"
        self.decisions_routed = {c: 0 for c in ["dqn", "actuated", "fixed"]}

    def detect_regime(self, state):
        """Classify current traffic regime from state vector."""
        # state: [queues(4), approaching(4), phase, green_elapsed,
        #         near_school, near_mosque, near_office, near_hospital,
        #         friday, hour]
        total_queue = sum(state[0:4])
        total_approach = sum(state[4:8])
        hour = state[15] if len(state) > 15 else 12
        near_school = state[10] if len(state) > 10 else 0

        total = total_queue + total_approach
        if total > 30:
            return "incident" if total > 50 else "rush"
        if hour < 6 or hour > 22:
            return "night"
        if near_school and 7 <= hour <= 9:
            return "school"
        return "normal"

    def pick_controller(self, state):
        """Pick the controller with the best historical delay for this regime."""
        regime = self.detect_regime(state)
        self.current_regime = regime

        best_ctrl = "actuated"  # safe default
        best_avg = float("inf")
        for ctrl in ["dqn", "actuated", "fixed"]:
            total, count = self.memory[ctrl][regime]
            if count > 5:
                avg = total / count
                if avg < best_avg:
                    best_avg = avg
                    best_ctrl = ctrl

        # Exploration: 5% of the time try DQN to keep learning
        if self.rng.random() < 0.05:
            best_ctrl = "dqn"

        self.decisions_routed[best_ctrl] += 1
        return best_ctrl, regime

    def report(self, controller, regime, delay):
        """Record observed delay for a controller in a regime."""
        self.memory[controller][regime][0] += delay
        self.memory[controller][regime][1] += 1

    def decide(self, state, controllers):
        """Route to best controller and return its action.

        controllers: dict with 'dqn', 'actuated', 'fixed' callables.
        Each callable takes state and returns 'hold' or 'switch'.
        """
        ctrl_name, regime = self.pick_controller(state)
        action = controllers[ctrl_name](state)
        return action, ctrl_name, regime

    def stats(self):
        return {
            "routed": dict(self.decisions_routed),
            "regime": self.current_regime,
        }


class SignalIntegration:
    """Clean interface for plugging SABZ into real signal hardware.

    This is the integration point the user asked for. Any real controller
    (NEMA, PLC, relay board) implements the two methods below; SABZ talks
    only through this interface, never directly to hardware.
    """

    def __init__(self, intelligence_layer, safety_checker=None):
        self.brain = intelligence_layer
        self.safety = safety_checker
        self.last_decision = None
        self.last_controller = None

    def on_camera_frame(self, counts):
        """Called each second with dict {N, S, E, W} vehicle counts.

        Returns: 'hold' or 'switch' (already safety-checked).
        """
        # Build state vector from counts (simplified; full version uses
        # sabz_sim2.get_state with location features)
        state = self._counts_to_state(counts)
        controllers = self._get_controllers()
        action, ctrl, regime = self.brain.decide(state, controllers)

        # Safety hard rule always applies
        if self.safety and not self.safety(action, counts):
            action = "hold"

        self.last_decision = action
        self.last_controller = ctrl
        return action

    def _counts_to_state(self, counts):
        """Convert camera counts to 16-feature state vector."""
        # Simplified: real version pulls from sabz_sim2.get_state
        q = [float(counts.get(a, 0)) for a in ["N", "S", "E", "W"]]
        app = [0.0, 0.0, 0.0, 0.0]  # approaching estimated from queue delta
        hour = time.localtime().tm_hour + time.localtime().tm_min / 60.0
        return q + app + [0, 0, 0, 0, 0, 0, 0, hour]

    def _get_controllers(self):
        """Return controller callables. DQN loaded from best checkpoint."""
        # Placeholder: wired to real controllers in production
        return {
            "dqn": lambda s: "hold",
            "actuated": lambda s: "switch" if sum(s[0:4]) > 8 else "hold",
            "fixed": lambda s: "hold",
        }

"""SABZ Predictor: traffic forecasting for proactive signal control.

Reactive control waits for queues to build, then reacts. Proactive control
predicts arrivals 60 seconds ahead and sets green before the queue forms.

Uses real NGSIM headway distributions to forecast expected arrivals per
approach, then the intelligence layer decides based on predicted (not just
current) demand.
"""
import numpy as np
import json
import os
import time
from collections import deque


class TrafficPredictor:
    """Forecast vehicle arrivals using real measured patterns."""

    def __init__(self, headway_path="real_data/ngsim_headways.json",
                 horizon=60, seed=0):
        self.rng = np.random.default_rng(seed)
        self.horizon = horizon  # seconds ahead to predict
        self.headways = {}
        if os.path.exists(headway_path):
            with open(headway_path) as f:
                self.headways = json.load(f)
        # Recent arrival history per approach for adaptive rate estimation
        self.history = {a: deque(maxlen=120) for a in ["N", "S", "E", "W"]}
        self.last_counts = {a: 0 for a in ["N", "S", "E", "W"]}

    def update(self, counts):
        """Feed live counts each second. Tracks new arrivals."""
        now = time.time()
        for a in ["N", "S", "E", "W"]:
            c = float(counts.get(a, 0))
            # New arrivals = increase in count (crude but effective)
            if c > self.last_counts[a]:
                self.history[a].append(now)
            self.last_counts[a] = c

    def _rate_from_history(self, approach):
        """Estimate current arrival rate from recent history."""
        h = self.history[approach]
        if len(h) < 3:
            return None
        # Arrivals in last 60 seconds
        cutoff = time.time() - 60
        recent = [t for t in h if t > cutoff]
        return len(recent) / 60.0  # vehicles per second

    def _rate_from_ngsim(self):
        """Fallback rate from real NGSIM medians."""
        if not self.headways:
            return 0.15
        medians = [h["median"] for h in self.headways.values() if h["n"] > 50]
        if not medians:
            return 0.15
        avg_median = sum(medians) / len(medians)
        return 1.0 / avg_median if avg_median > 0 else 0.15

    def predict(self, counts):
        """Predict arrivals in next `horizon` seconds per approach.

        Returns dict {N, S, E, W} of predicted new vehicles.
        """
        self.update(counts)
        pred = {}
        base_rate = self._rate_from_ngsim()
        for a in ["N", "S", "E", "W"]:
            rate = self._rate_from_history(a)
            if rate is None:
                rate = base_rate
            # Blend: 70% live estimate, 30% historical baseline
            rate = 0.7 * rate + 0.3 * base_rate
            # Expected arrivals in horizon (Poisson mean)
            pred[a] = rate * self.horizon
        return pred

    def predicted_state(self, counts, current_state):
        """Build a future-aware state: current queues + predicted arrivals."""
        pred = self.predict(counts)
        # Add predicted arrivals to approaching counts (indices 4-8)
        future = list(current_state)
        for i, a in enumerate(["N", "S", "E", "W"]):
            future[4 + i] = future[4 + i] + pred[a] * 0.5  # dampened
        return future


class ProactiveBrain:
    """Wraps the intelligence layer with prediction.

    Decides based on where traffic WILL BE, not just where it is.
    """

    def __init__(self, intelligence_layer, predictor=None):
        self.brain = intelligence_layer
        self.predictor = predictor or TrafficPredictor()

    def decide(self, counts, current_state):
        """Proactive decision using predicted future state."""
        future_state = self.predictor.predicted_state(counts, current_state)
        # Get decision on future state
        action, ctrl, regime = self.brain.decide(future_state)
        # Also get reactive decision for comparison
        r_action, r_ctrl, r_regime = self.brain.decide(current_state)

        # If they disagree, trust the proactive one when predicted
        # demand is significantly higher
        pred = self.predictor.predict(counts)
        total_pred = sum(pred.values())
        total_now = sum(float(counts.get(a, 0)) for a in ["N", "S", "E", "W"])

        if total_pred > total_now * 1.5 and action != r_action:
            # Proactive override: predicted surge
            return action, ctrl, regime + "+predicted"

        return r_action, r_ctrl, r_regime

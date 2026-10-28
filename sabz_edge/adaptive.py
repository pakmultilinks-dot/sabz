"""Bounded, capacity-aware scheduling inspired by pressure-based control.

Not a SCATS/SCOOT clone or a throughput-optimal MP theorem implementation.
Safety timing and legal signal states belong to the separate kernel.
"""
PHASE_INDEX = {"NS": (0, 1), "EW": (2, 3)}


class AdaptivePolicy:
    name = "capacity-aware-adaptive-v1"
    horizon_s = 4.0
    passage_gap_s = 3.0
    hysteresis = 3.0
    fairness_wait_s = 60.0

    def __init__(self):
        self.last_demand = {"NS": None, "EW": None}
        self.details = {}
        self.last_service = {"NS": None, "EW": None}

    def inspect(self, observation, now):
        result = {}
        utilization = {}
        for phase, indexes in PHASE_INDEX.items():
            pressure = demand = wait = present = 0.0
            utilization[phase] = 0.0
            supply_available = False
            for i in indexes:
                q, down, capacity = observation.counts[i], observation.downstream_counts[i], observation.downstream_capacity[i]
                supply = max(0.0, 1.0 - down / capacity)
                if supply > 0:
                    supply_available = True
                    incoming = observation.approaching[i] + self.horizon_s * observation.arrival_rate[i]
                    present += q + observation.approaching[i]
                    utilization[phase] = max(utilization[phase], observation.arrival_rate[i] / .5)
                    demand += q + incoming
                    wait = max(wait, observation.oldest_wait_s[i] if q > 0 else 0)
                    pressure += (max(0, q - down) + .5 * incoming) * supply
            # A shared NS/EW green cannot independently stop a blocked member.
            # Require receiving space for one more vehicle on BOTH approaches.
            supply_available = all(observation.downstream_counts[i] + 1 <= observation.downstream_capacity[i]
                                   for i in indexes)
            if not supply_available:
                pressure = demand = wait = present = 0.0
            if present > 0:
                self.last_demand[phase] = now
            result[phase] = {"score": round(pressure, 4), "demand": round(demand, 4),
                             "present": present, "oldest_wait_s": wait, "supply_available": supply_available}
        # Batch service to account for the time lost at every phase change.
        # Webster-inspired cycle estimate, bounded for this through-only bench:
        # 10s lost/cycle, .5 veh/s/approach saturation, 40..100s target cycle.
        total = sum(utilization.values())
        cycle = max(40.0, min(100.0, 20.0 / max(.1, 1 - total)))
        for phase in result:
            queue_green = 2.0 + max(observation.counts[i] for i in PHASE_INDEX[phase]) / .5
            rate_green = (cycle - 10) * utilization[phase] / max(total, .01)
            result[phase]["target_green_s"] = round(max(8.0, min(45.0, max(queue_green, rate_green))), 2)
        self.details = result
        return result

    def mark_service_opportunity(self, phase, now):
        self.last_service[phase] = now

    def next_phase(self, preferred):
        candidates = [p for p, d in self.details.items() if d["supply_available"] and d["demand"] > 0]
        present = [p for p in candidates if self.details[p]["present"] > 0]
        candidates = present or candidates
        overdue = [p for p in candidates if self.details[p]["oldest_wait_s"] >= self.fairness_wait_s]
        if overdue:
            return max(overdue, key=lambda p: self.details[p]["oldest_wait_s"])
        if candidates:
            return max(candidates, key=lambda p: (self.details[p]["score"], p == preferred))
        if self.details[preferred]["supply_available"]:
            return preferred
        return next((p for p, d in self.details.items() if d["supply_available"]), None)

    def switch_reason(self, current, other, now, green_elapsed=None):
        cur, opp = self.details[current], self.details[other]
        if not cur["supply_available"]:
            return "downstream_blocked"
        if not opp["supply_available"] or opp["demand"] <= 0:
            return None
        last_service = self.last_service[other]
        if (opp["oldest_wait_s"] >= self.fairness_wait_s and
                (last_service is None or now-last_service >= self.fairness_wait_s)):
            return "waiting_time_priority"
        last = self.last_demand[current]
        if cur["present"] == 0 and opp["present"] > 0 and (last is None or now - last >= self.passage_gap_s):
            return "passage_gap"
        if green_elapsed is not None and green_elapsed < cur["target_green_s"]:
            return None
        if opp["score"] > cur["score"] + self.hysteresis:
            return "pressure_difference"
        if green_elapsed is not None and green_elapsed >= cur["target_green_s"] and opp["present"] > 0:
            return "allocated_green_complete"
        return None

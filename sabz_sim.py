"""SABZ adaptive traffic-signal simulator.

Compares a fixed-time signal plan against the SABZ adaptive controller on a
4-way intersection. Discrete-time simulation, dt = 1 s.

Controllers implement real actuated-signal logic:
- FIXED: 60 s cycle, 25 s green per phase (the user's example), 3 s yellow,
  2 s all-red. Green is served whether cars are there or not.
- SABZ: camera-based per-approach vehicle counting (with detection noise),
  min/max green, gap-out, max-out, phase skipping for empty approaches, and
  time-of-day priority plans (e.g. school-road priority in the morning).
"""
import numpy as np
from collections import deque

APPROACHES = ["N", "S", "E", "W"]
PHASES = {"NS": ["N", "S"], "EW": ["E", "W"]}
OTHER = {"NS": "EW", "EW": "NS"}

HEADWAY = 2.0        # seconds per discharged vehicle (saturation flow)
YELLOW = 3.0         # yellow clearance, s
ALLRED = 2.0         # all-red clearance, s
MIN_GREEN = 8.0      # minimum green, s
MAX_GREEN = 45.0     # maximum green, s
GAP_OUT = 3.0        # switch if no demand for this long, s
DETECT_NOISE = 0.7   # camera count noise (vehicles), std dev
IDLE_FUEL_L_PER_H = 0.6   # fuel burned idling, litres/hour/vehicle
CO2_KG_PER_L = 2.31       # petrol CO2, kg/litre


class Intersection:
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.queues = {a: deque() for a in APPROACHES}  # arrival times
        self.phase = "NS"
        self.green_elapsed = 0.0
        self.transitioning = False
        self.trans_left = 0.0
        self.next_phase = None
        self.acc = {a: 0.0 for a in APPROACHES}  # discharge accumulator
        self.last_arrival = {a: -1e9 for a in APPROACHES}
        self.delay_sum = 0.0
        self.served = 0
        self.total_arrived = 0
        self.wasted_green = 0.0
        self.green_served = {"NS": 0.0, "EW": 0.0}
        self.switches = 0
        self.max_queue = 0
        self.idle_veh_s = 0.0
        self.discharged = {a: 0 for a in APPROACHES}

    # -- sensing -----------------------------------------------------------
    def observed_queues(self):
        """Camera-based count = true queue + detection noise, clipped at 0."""
        return {a: max(0.0, len(self.queues[a]) +
                       self.rng.normal(0.0, DETECT_NOISE)) for a in APPROACHES}

    # -- stepping ----------------------------------------------------------
    def step(self, rates, decide, schedule=None, trace=None):
        dt = 1.0
        self.t += dt
        # arrivals (Poisson per approach)
        for a in APPROACHES:
            lam = rates(a, self.t)
            n = self.rng.poisson(lam * dt)
            for _ in range(n):
                self.queues[a].append(self.t)
                self.total_arrived += 1
            if n:
                self.last_arrival[a] = self.t
        q = {a: len(self.queues[a]) for a in APPROACHES}
        self.max_queue = max(self.max_queue, sum(q.values()))
        self.idle_veh_s += sum(q.values()) * dt

        if self.transitioning:
            self.trans_left -= dt
            if self.trans_left <= 0:
                self.phase = self.next_phase
                self.next_phase = None
                self.transitioning = False
                self.green_elapsed = 0.0
        else:
            self.green_elapsed += dt
            self.green_served[self.phase] += dt
            # discharge on green approaches
            moved = False
            for a in PHASES[self.phase]:
                self.acc[a] += dt
                while self.acc[a] >= HEADWAY and self.queues[a]:
                    arr = self.queues[a].popleft()
                    self.delay_sum += self.t - arr
                    self.served += 1
                    self.discharged[a] += 1
                    self.acc[a] -= HEADWAY
                    moved = True
            # wasted green: green burning while nobody moves but others wait
            other_q = sum(len(self.queues[a]) for a in PHASES[OTHER[self.phase]])
            if not moved and other_q > 0:
                self.wasted_green += dt
            # controller decision
            obs = self.observed_queues()
            prio = schedule(self.t) if schedule else None
            if decide(self, obs, q, prio) == "switch" \
                    and self.green_elapsed >= MIN_GREEN:
                self.transitioning = True
                self.trans_left = YELLOW + ALLRED
                self.next_phase = OTHER[self.phase]
                self.switches += 1
        if trace is not None:
            trace.append({
                "t": self.t, "phase": self.phase,
                "green": not self.transitioning,
                "queues": dict(q), "served": self.served,
                "wasted": self.wasted_green,
                "delay": self.delay_sum, "arrived": self.total_arrived,
            })

    def finish(self):
        for a in APPROACHES:
            for arr in self.queues[a]:
                self.delay_sum += self.t - arr
        n = self.total_arrived or 1
        fuel = self.idle_veh_s * IDLE_FUEL_L_PER_H / 3600.0
        return {
            "vehicles": self.total_arrived,
            "served": self.served,
            "avg_delay_s": self.delay_sum / n,
            "max_queue": self.max_queue,
            "throughput_per_h": self.served / (self.t / 3600.0),
            "wasted_green_s": self.wasted_green,
            "switches": self.switches,
            "idle_veh_h": self.idle_veh_s / 3600.0,
            "fuel_wasted_L": fuel,
            "co2_kg": fuel * CO2_KG_PER_L,
        }


# -- controllers -----------------------------------------------------------
def fixed_decide(sim, obs, q, prio):
    """Fixed-time plan: 25 s green per phase, exactly the user's example."""
    return "switch" if sim.green_elapsed >= 25.0 else "stay"


def sabz_decide(sim, obs, q, prio):
    """SABZ adaptive controller: actuated logic on camera counts."""
    cur = PHASES[sim.phase]
    oth = PHASES[OTHER[sim.phase]]
    cur_q = sum(q[a] for a in cur)
    oth_obs = sum(obs[a] for a in oth)
    oth_recent = any(sim.t - sim.last_arrival[a] <= GAP_OUT for a in oth)
    oth_demand = oth_obs > 0.5 or oth_recent
    # max-out: never starve the other road
    if sim.green_elapsed >= MAX_GREEN:
        return "switch"
    # time-of-day priority (e.g. school road in the morning)
    if prio and prio != sim.phase and sim.green_elapsed >= MIN_GREEN:
        if sum(obs[a] for a in PHASES[prio]) > 0.5:
            return "switch"
    # gap-out: current road is clear, give green to whoever waits
    if sim.green_elapsed >= MIN_GREEN and cur_q == 0:
        cur_recent = any(sim.t - sim.last_arrival[a] <= GAP_OUT for a in cur)
        if not cur_recent and oth_demand:
            return "switch"
    return "stay"


# -- scenarios (vehicles/second/approach) ------------------------------------
def rates_asymmetric(a, t):
    """User's example: 2-lane main road vs nearly empty side road."""
    return 0.25 if a in ("N", "S") else 0.035


def rates_balanced(a, t):
    return 0.22


def rates_school(a, t):
    """Morning rush with a school on road N, peak 07:30-08:15 mapped here."""
    if a == "N" and 1200.0 <= t < 2100.0:
        return 0.45
    return 0.12


def school_schedule(t):
    return "NS" if 1200.0 <= t < 2100.0 else None


SCENARIOS = {
    "asymmetric": (rates_asymmetric, None,
                   "2 cars vs 50 cars: empty side road, packed main road"),
    "school": (rates_school, school_schedule,
               "School morning: school road surges 07:30-08:15"),
    "balanced": (rates_balanced, None,
                 "Balanced rush hour on all four roads"),
}


def run(controller, rates, schedule=None, T=3600.0, seed=0, trace=False):
    decide = fixed_decide if controller == "fixed" else sabz_decide
    sim = Intersection(seed=seed)
    tr = [] if trace else None
    while sim.t < T:
        sim.step(rates, decide, schedule=schedule, trace=tr)
    m = sim.finish()
    m["controller"] = controller
    if trace:
        m["trace"] = tr
    return m

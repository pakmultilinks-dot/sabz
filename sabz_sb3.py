"""SABZ on Stable Baselines3: professional RL framework, our custom environment.

Uses PPO from SB3 (industry standard) wrapped around our IntersectionV2
simulator with location-aware states. This replaces the hand-rolled NumPy
DQN with a proper, reliable open-source base.
"""
import os
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from sabz_sim2 import IntersectionV2, MAX_GREEN
from sabz_rl import scenario_sampler, N_POI


class SabzEnv(gym.Env):
    """Gymnasium wrapper: 18-dim location-aware state, 2 actions."""
    metadata = {"render_modes": []}

    def __init__(self, T=450.0):
        super().__init__()
        self.T = T
        self.observation_space = spaces.Box(
            low=0, high=2, shape=(18,), dtype=np.float64)
        self.action_space = spaces.Discrete(2)
        self._rng = np.random.default_rng()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self.rates, self.sched, self.loc = scenario_sampler(self._rng)
        self.sim = IntersectionV2(
            seed=int(self._rng.integers(1e9)), safety_on=True)
        return self._get_state(), {}

    def _get_state(self):
        from sabz_rl import get_state
        return get_state(self.sim, self.loc).astype(np.float64)

    def step(self, action):
        self.sim.step(
            self.rates,
            lambda st, pr: "switch" if action == 1 else "stay",
            schedule=self.sched)
        qtot = sum(len(self.sim.queue_of(x)) for x in ("N", "S", "E", "W"))
        reward = -qtot / 40.0
        terminated = self.sim.t >= self.T
        return self._get_state(), reward, terminated, False, {}


def train_sb3(total_timesteps=500000, out="sabz_ppo.zip"):
    from stable_baselines3 import PPO
    env = SabzEnv(T=450.0)
    model = PPO("MlpPolicy", env, verbose=1,
                n_steps=2048, batch_size=64,
                learning_rate=3e-4, gamma=0.995)
    model.learn(total_timesteps=total_timesteps)
    model.save(out)
    print(f"SB3 PPO saved to {out}")


if __name__ == "__main__":
    import sys
    ts = int(sys.argv[1]) if len(sys.argv) > 1 else 500000
    train_sb3(total_timesteps=ts)

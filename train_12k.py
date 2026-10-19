"""Train the 12,026-param DQN (18-72-72-72-2) from scratch."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sabz_rl
from sabz_rl import DQN

# Verify architecture
net = DQN(seed=0)
total = sum(v.size for v in net.p.values())
print(f"Training {total}-param brain from scratch...", flush=True)
assert total >= 10000, f"Only {total} params!"

# Train from scratch - fresh checkpoint path so it doesn't load old arch
sabz_rl.train(episodes=120000, out="sabz_dqn_12k.npz",
              ckpt_path="sabz_dqn_12k_ckpt.npz",
              log_every=100, ckpt_every=500, eval_every=2000)

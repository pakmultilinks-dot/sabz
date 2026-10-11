# SABZ Brain - Model Card

## What this is
Our own Deep Q-Network (DQN) signal controller, trained from scratch inside
the SABZ kinematic traffic simulator. It decides every second whether to
hold the current green or switch phases. Safety is NOT learned: a hard
dilemma-zone rule in the environment overrides any switch decision while a
vehicle is near the stop line, so the network can never cause an unsafe
cutoff no matter what it outputs.

## Architecture
- Input: 10 features (queued vehicles per approach /20, approaching vehicles
  per approach /10, current phase one-hot, green elapsed /60)
- Hidden: 64 ReLU, 64 ReLU
- Output: 2 Q-values (stay, switch), argmax policy
- File: `models/sabz_dqn_best.npz` (numpy weights, ~41 KB)

## Training
- Behavioral-cloning warm start on 200 episodes of the actuated controller
  (86.1% imitation accuracy), then DQN refinement
- Target: 120,000 episodes across asymmetric, school-rush, and balanced
  demand scenarios with camera noise modeled
- Reward: negative total delay, collision-free by construction (safety layer)
- Checkpoints every 500 episodes, evaluation every 2,000, best kept

## Current status
Training in progress (see `rl_train_120k.log`). Best quick-evaluation so far:
12.1 s average delay on the balanced rush scenario vs 179.7 s fixed-time.

## Files
- `models/sabz_dqn_bc.npz` - behavioral-cloning warm-start weights
- `models/sabz_dqn_best.npz` - best DQN weights so far
- `models/sabz_dqn_ckpt.npz` - latest training checkpoint (resume here)
- `sabz_rl.py` - full training code (DQN + BC + evaluation)
- `sabz_brain_weights.json` - same weights as JSON, embedded in the dashboard

#!/bin/bash
# SABZ interactive live demo: real footage + AI detection + DQN brain.
cd "$(dirname "$0")"
echo "Starting SABZ live demo on http://localhost:8099 ..."
python3 server.py

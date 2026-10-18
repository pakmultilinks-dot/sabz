#!/bin/bash
# SABZ live judge demo launcher.
cd "$(dirname "$0")"
echo "Starting SABZ live demo backend on http://localhost:8099 ..."
python3 server.py

#!/bin/bash

# Orchestrator startup wrapper
cd "$(dirname "$0")"

# Ensure Python packages are available
export PYTHONPATH="${HOME}/.local/lib/python3.10/site-packages:${PYTHONPATH}"

# Start orchestrator
exec python3 orchestrator.py

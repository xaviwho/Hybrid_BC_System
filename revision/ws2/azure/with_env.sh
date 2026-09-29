#!/bin/bash
# Run a command on orbit-d with the testbed environment: with_env.sh python ...
set -a
. /opt/orbit/azure.env
set +a
cd /opt/orbit/Hybrid_BC_System
PATH=/opt/orbit-venv/bin:/opt/fabric/bin:$PATH exec "$@"

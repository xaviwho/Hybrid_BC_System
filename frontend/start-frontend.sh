#!/bin/bash

# Frontend startup wrapper
cd "$(dirname "$0")"

# Start frontend server with proper detachment
nohup node server.js </dev/null >/dev/null 2>&1 &
disown

#!/bin/bash

# Hybrid Blockchain IoT System - Server Refresh Script
# Quickly restart Node.js services for development

echo "🔄 Refreshing Hybrid Blockchain IoT System Servers..."
echo "=================================================="

# Kill all Node.js processes
echo "🛑 Stopping all Node.js services..."
pkill node
sleep 2

# Start Orchestrator Service
echo "🚀 Starting Orchestrator Service..."
cd /mnt/c/Users/sandr/Downloads/Hybrid_BC_System/orchestrator-js
node index.js &
ORCHESTRATOR_PID=$!
echo "   → Orchestrator started (PID: $ORCHESTRATOR_PID)"

# Wait a moment for orchestrator to initialize
sleep 2

# Start Frontend Server
echo "🎨 Starting Frontend Server..."
cd /mnt/c/Users/sandr/Downloads/Hybrid_BC_System/frontend
node server.js &
FRONTEND_PID=$!
echo "   → Frontend started (PID: $FRONTEND_PID)"

# Wait for services to initialize
sleep 3

echo ""
echo "✅ Server refresh completed!"
echo "=================================================="
echo "🔗 Access Points:"
echo "   → Frontend Dashboard: http://localhost:8080"
echo "   → Orchestrator API:   http://localhost:3000"
echo "   → ML Gateway Filter:  http://localhost:5000"
echo "   → ML Privacy Filter:  http://localhost:5001"
echo "   → Ethereum Node:      http://localhost:8545"
echo ""
echo "💡 Services running in background:"
echo "   → Orchestrator PID: $ORCHESTRATOR_PID"
echo "   → Frontend PID:     $FRONTEND_PID"
echo ""
echo "🔄 To refresh again, run: ./refresh-servers.sh"
echo "🛑 To stop all services, run: pkill node"

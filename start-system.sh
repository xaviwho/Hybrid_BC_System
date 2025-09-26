#!/bin/bash

# ============================================================================
# Hybrid Blockchain System - Complete Startup Script
# ============================================================================
# This single script starts all components of the hybrid blockchain system:
# - Hyperledger Fabric Network
# - Ethereum (Ganache)
# - ML Services (Gateway & Privacy Filter)
# - Orchestrator Service
# - Frontend (if available)
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
FABRIC_PATH="${PROJECT_ROOT}/blockchain/setup/hyperledger/fabric-samples"
TEST_NETWORK="${FABRIC_PATH}/test-network"
ETHEREUM_PATH="${PROJECT_ROOT}/blockchain/setup/ethereum"
LOG_DIR="${PROJECT_ROOT}/logs"

# Create log directory
mkdir -p "${LOG_DIR}"

# ASCII Art Banner
echo -e "${CYAN}"
cat << "EOF"
 _   _       _          _     _   ____  _            _        _           _       
| | | |_   _| |__  _ __(_) __| | | __ )| | ___   ___| | _____| |__   __ _(_)_ __  
| |_| | | | | '_ \| '__| |/ _` | |  _ \| |/ _ \ / __| |/ / __| '_ \ / _` | | '_ \ 
|  _  | |_| | |_) | |  | | (_| | | |_) | | (_) | (__|   < (__| | | | (_| | | | | |
|_| |_|\__, |_.__/|_|  |_|\__,_| |____/|_|\___/ \___|_|\_\___|_| |_|\__,_|_|_| |_|
       |___/                                                                       
EOF
echo -e "${NC}"

echo -e "${CYAN}Starting Hybrid Blockchain System...${NC}"
echo -e "${CYAN}=====================================\n${NC}"

# Function to check if a port is in use
check_port() {
    local port=$1
    nc -z localhost $port 2>/dev/null
}

# Function to wait for service
wait_for_service() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=0
    
    echo -ne "${YELLOW}Waiting for ${service_name}...${NC}"
    while [ $attempt -lt $max_attempts ]; do
        if check_port $port; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo -e " ${RED}✗${NC}"
    return 1
}

# Function to stop all services
stop_all_services() {
    echo -e "\n${YELLOW}Stopping all services...${NC}"
    
    # Stop Fabric
    if [ -d "${TEST_NETWORK}" ]; then
        cd "${TEST_NETWORK}"
        ./network.sh down 2>/dev/null || true
    fi
    
    # Stop Ganache
    docker stop ganache-cli 2>/dev/null || true
    docker rm ganache-cli 2>/dev/null || true
    pkill -f ganache 2>/dev/null || true
    
    # Stop ML services
    docker-compose -f "${PROJECT_ROOT}/docker-compose-hybrid.yml" down 2>/dev/null || true
    
    # Stop Orchestrator
    pkill -f orchestrator.py 2>/dev/null || true
    
    # Stop Frontend
    pkill -f "npm.*start" 2>/dev/null || true
    pkill -f "react-scripts" 2>/dev/null || true
}

# Trap to handle script interruption
trap 'echo -e "\n${RED}Script interrupted. Services may still be running.${NC}"; exit 1' INT TERM

# Parse command line arguments
ACTION=${1:-start}

if [ "$ACTION" = "stop" ]; then
    stop_all_services
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
elif [ "$ACTION" = "restart" ]; then
    stop_all_services
    sleep 3
    ACTION="start"
elif [ "$ACTION" = "status" ]; then
    echo -e "${BLUE}System Status:${NC}"
    echo -e "${BLUE}==============${NC}"
    
    # Check each service
    check_port 7051 && echo -e "${GREEN}✓ Fabric Peer${NC}" || echo -e "${RED}✗ Fabric Peer${NC}"
    check_port 8545 && echo -e "${GREEN}✓ Ethereum${NC}" || echo -e "${RED}✗ Ethereum${NC}"
    check_port 5000 && echo -e "${GREEN}✓ ML Gateway${NC}" || echo -e "${RED}✗ ML Gateway${NC}"
    check_port 5001 && echo -e "${GREEN}✓ ML Privacy${NC}" || echo -e "${RED}✗ ML Privacy${NC}"
    check_port 5002 && echo -e "${GREEN}✓ Orchestrator${NC}" || echo -e "${RED}✗ Orchestrator${NC}"
    check_port 8080 && echo -e "${GREEN}✓ Frontend${NC}" || echo -e "${RED}✗ Frontend${NC}"
    exit 0
fi

# ============================================================================
# STEP 1: Start Hyperledger Fabric
# ============================================================================
echo -e "${MAGENTA}[1/5] Starting Hyperledger Fabric Network${NC}"
echo -e "${BLUE}==========================================${NC}"

if check_port 7051; then
    echo -e "${YELLOW}Fabric appears to be running. Skipping...${NC}"
else
    cd "${TEST_NETWORK}"
    
    # Set PATH for Fabric binaries
    export PATH="${FABRIC_PATH}/bin:$PATH"
    export FABRIC_CFG_PATH="${FABRIC_PATH}/config"
    
    # Check if binaries exist
    if [ ! -f "${FABRIC_PATH}/bin/peer" ]; then
        echo -e "${RED}Error: Fabric binaries not found!${NC}"
        echo -e "${YELLOW}Run: ./install-fabric-binaries.sh${NC}"
        exit 1
    fi
    
    # Start network
    echo -e "${CYAN}Starting Fabric network...${NC}"
    ./network.sh up -s couchdb > "${LOG_DIR}/fabric.log" 2>&1
    
    # Create channel
    echo -e "${CYAN}Creating channel 'hiot'...${NC}"
    ./network.sh createChannel -c hiot >> "${LOG_DIR}/fabric.log" 2>&1
    
    echo -e "${GREEN}✓ Fabric network started${NC}"
fi

# ============================================================================
# STEP 2: Start Ethereum (Ganache)
# ============================================================================
echo -e "\n${MAGENTA}[2/5] Starting Ethereum Network (Ganache)${NC}"
echo -e "${BLUE}==========================================${NC}"

if check_port 8545; then
    echo -e "${YELLOW}Ganache appears to be running. Skipping...${NC}"
else
    # Use Docker for Ganache
    echo -e "${CYAN}Starting Ganache in Docker...${NC}"
    docker run -d \
        --name ganache-cli \
        -p 8545:8545 \
        trufflesuite/ganache:latest \
        --accounts 10 \
        --host 0.0.0.0 \
        > /dev/null 2>&1
    
    wait_for_service "Ganache" 8545
    
    # Deploy smart contracts
    echo -e "${CYAN}Deploying smart contracts...${NC}"
    cd "${ETHEREUM_PATH}"
    npx truffle migrate --network development --reset > "${LOG_DIR}/truffle.log" 2>&1
    
    echo -e "${GREEN}✓ Ethereum network started and contracts deployed${NC}"
fi

# ============================================================================
# STEP 3: Start ML Services
# ============================================================================
echo -e "\n${MAGENTA}[3/5] Starting ML Services${NC}"
echo -e "${BLUE}=========================${NC}"

if check_port 5000 && check_port 5001; then
    echo -e "${YELLOW}ML services appear to be running. Skipping...${NC}"
else
    cd "${PROJECT_ROOT}"
    
    echo -e "${CYAN}Building and starting ML services...${NC}"
    docker-compose -f docker-compose-hybrid.yml up -d --build ml-gateway ml-privacy > "${LOG_DIR}/ml-services.log" 2>&1
    
    wait_for_service "ML Gateway" 5000
    wait_for_service "ML Privacy Filter" 5001
    
    echo -e "${GREEN}✓ ML services started${NC}"
fi

# ============================================================================
# STEP 4: Start Orchestrator
# ============================================================================
echo -e "\n${MAGENTA}[4/5] Starting Orchestrator Service${NC}"
echo -e "${BLUE}===================================${NC}"

if check_port 5002; then
    echo -e "${YELLOW}Orchestrator appears to be running. Skipping...${NC}"
else
    cd "${PROJECT_ROOT}/orchestrator"
    
    # Install Python dependencies
    echo -e "${CYAN}Installing Python dependencies...${NC}"
    pip3 install --user -q Flask==2.3.0 Flask-CORS==3.0.10 web3==6.0.0 requests==2.28.0 python-dotenv==0.19.0 2>/dev/null
    
    # Start orchestrator
    echo -e "${CYAN}Starting Orchestrator...${NC}"
    nohup python3 orchestrator.py > "${LOG_DIR}/orchestrator.log" 2>&1 &
    
    wait_for_service "Orchestrator" 5002
    
    echo -e "${GREEN}✓ Orchestrator started${NC}"
fi

# ============================================================================
# STEP 5: Start Frontend (if exists)
# ============================================================================
echo -e "\n${MAGENTA}[5/5] Starting Frontend${NC}"
echo -e "${BLUE}======================${NC}"

FRONTEND_PATH="${PROJECT_ROOT}/frontend"

if [ -d "${FRONTEND_PATH}" ] && [ -f "${FRONTEND_PATH}/package.json" ]; then
    if check_port 8080; then
        echo -e "${YELLOW}Frontend appears to be running. Skipping...${NC}"
    else
        cd "${FRONTEND_PATH}"
        
        # Install dependencies if needed
        if [ ! -d "node_modules" ]; then
            echo -e "${CYAN}Installing frontend dependencies...${NC}"
            npm install > "${LOG_DIR}/frontend-install.log" 2>&1
        fi
        
        # Start frontend (runs on port 8080)
        echo -e "${CYAN}Starting frontend on port 8080...${NC}"
        nohup npm start > "${LOG_DIR}/frontend.log" 2>&1 &
        
        wait_for_service "Frontend" 8080
        
        echo -e "${GREEN}✓ Frontend started${NC}"
    fi
else
    echo -e "${YELLOW}No frontend found. Skipping...${NC}"
fi

# ============================================================================
# Final Status Check
# ============================================================================
echo -e "\n${CYAN}============================================${NC}"
echo -e "${CYAN}       System Startup Complete!${NC}"
echo -e "${CYAN}============================================${NC}"

echo -e "\n${GREEN}All services are running:${NC}"
echo -e "  ${BLUE}•${NC} Hyperledger Fabric: ${CYAN}localhost:7051${NC}"
echo -e "  ${BLUE}•${NC} Ethereum (Ganache): ${CYAN}http://localhost:8545${NC}"
echo -e "  ${BLUE}•${NC} ML Gateway: ${CYAN}http://localhost:5000${NC}"
echo -e "  ${BLUE}•${NC} ML Privacy Filter: ${CYAN}http://localhost:5001${NC}"
echo -e "  ${BLUE}•${NC} Orchestrator: ${CYAN}http://localhost:5002${NC}"

if [ -d "${FRONTEND_PATH}" ]; then
    echo -e "  ${BLUE}•${NC} Frontend: ${CYAN}http://localhost:8080${NC}"
fi

# Get contract address
if [ -f "${ETHEREUM_PATH}/build/contracts/IoTDataRegistry.json" ]; then
    CONTRACT_ADDRESS=$(grep -A 10 '"networks"' "${ETHEREUM_PATH}/build/contracts/IoTDataRegistry.json" | grep '"address"' | head -1 | cut -d'"' -f4)
    echo -e "\n${GREEN}Smart Contract:${NC}"
    echo -e "  ${BLUE}•${NC} IoTDataRegistry: ${CYAN}${CONTRACT_ADDRESS}${NC}"
fi

echo -e "\n${YELLOW}Commands:${NC}"
echo -e "  ${BLUE}•${NC} Check status: ${CYAN}./start-system.sh status${NC}"
echo -e "  ${BLUE}•${NC} Stop all: ${CYAN}./start-system.sh stop${NC}"
echo -e "  ${BLUE}•${NC} Restart all: ${CYAN}./start-system.sh restart${NC}"

echo -e "\n${YELLOW}Test the system:${NC}"
echo -e "${CYAN}curl -X POST http://localhost:5002/ingest_data \\
  -H 'Content-Type: application/json' \\
  -d '{
    \"id\": \"test_$(date +%s)\",
    \"deviceId\": \"sensor_001\",
    \"data\": {\"temperature\": 22.5, \"humidity\": 65}
  }'${NC}"

echo -e "\n${GREEN}✨ System is ready for use!${NC}"

# Keep track of running services in a PID file
echo "# PID tracking for services" > "${PROJECT_ROOT}/.running-services"
echo "FABRIC=running" >> "${PROJECT_ROOT}/.running-services"
echo "ETHEREUM=running" >> "${PROJECT_ROOT}/.running-services"
echo "ML_SERVICES=running" >> "${PROJECT_ROOT}/.running-services"
echo "ORCHESTRATOR=running" >> "${PROJECT_ROOT}/.running-services"
[ -d "${FRONTEND_PATH}" ] && echo "FRONTEND=running" >> "${PROJECT_ROOT}/.running-services"

cd "${PROJECT_ROOT}"

#!/bin/bash

# Clean startup script with better error handling and visibility

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
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

# Function to check port
check_port() {
    nc -z localhost $1 2>/dev/null
}

# Function to wait for service
wait_for_service() {
    local service=$1
    local port=$2
    local max_wait=30
    local count=0
    
    echo -ne "${YELLOW}  Waiting for ${service} on port ${port}...${NC}"
    
    while [ $count -lt $max_wait ]; do
        if check_port $port; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
        count=$((count + 1))
    done
    
    echo -e " ${RED}✗ Timeout${NC}"
    return 1
}

# Parse command
ACTION=${1:-start}

if [ "$ACTION" = "stop" ]; then
    echo -e "${YELLOW}Stopping all services...${NC}"
    
    # Stop containers
    docker stop ganache-cli 2>/dev/null && echo -e "${GREEN}  ✓ Stopped Ganache${NC}"
    docker-compose -f docker-compose-hybrid.yml down 2>/dev/null && echo -e "${GREEN}  ✓ Stopped ML services${NC}"
    pkill -f orchestrator.py 2>/dev/null && echo -e "${GREEN}  ✓ Stopped Orchestrator${NC}"
    pkill -f "npm.*start" 2>/dev/null && echo -e "${GREEN}  ✓ Stopped Frontend${NC}"
    
    echo -e "${GREEN}All services stopped${NC}"
    exit 0
fi

# Step 1: Hyperledger Fabric
echo -e "${MAGENTA}[1/5] Hyperledger Fabric${NC}"
if check_port 7051; then
    echo -e "${GREEN}  ✓ Already running${NC}"
else
    echo -e "${YELLOW}  ⚠ Not running - please start manually${NC}"
fi

# Step 2: Ethereum (Ganache)
echo -e "\n${MAGENTA}[2/5] Ethereum (Ganache)${NC}"
if check_port 8545; then
    echo -e "${GREEN}  ✓ Already running${NC}"
else
    echo -e "${CYAN}  Starting Ganache...${NC}"
    
    # Clean up old container
    docker rm -f ganache-cli 2>/dev/null
    
    # Start new container
    docker run -d \
        --name ganache-cli \
        -p 8545:8545 \
        trufflesuite/ganache:latest \
        --accounts 10 \
        --host 0.0.0.0 \
        --deterministic
    
    if [ $? -eq 0 ]; then
        wait_for_service "Ganache" 8545
        
        if check_port 8545; then
            echo -e "${GREEN}  ✓ Ganache started${NC}"
            
            # Deploy contracts
            echo -e "${CYAN}  Deploying smart contracts...${NC}"
            cd "${PROJECT_ROOT}/blockchain/setup/ethereum"
            npx truffle migrate --network development --reset > "${LOG_DIR}/truffle.log" 2>&1
            
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}  ✓ Contracts deployed${NC}"
            else
                echo -e "${YELLOW}  ⚠ Contract deployment issues (check logs)${NC}"
            fi
            cd "${PROJECT_ROOT}"
        else
            echo -e "${RED}  ✗ Ganache failed to start${NC}"
        fi
    else
        echo -e "${RED}  ✗ Failed to create Ganache container${NC}"
        echo -e "${YELLOW}  Is Docker running?${NC}"
    fi
fi

# Step 3: ML Services
echo -e "\n${MAGENTA}[3/5] ML Services${NC}"
if check_port 5000 && check_port 5001; then
    echo -e "${GREEN}  ✓ Already running${NC}"
else
    echo -e "${CYAN}  Starting ML services...${NC}"
    
    docker-compose -f docker-compose-hybrid.yml up -d ml-gateway ml-privacy 2>/dev/null
    
    if [ $? -eq 0 ]; then
        wait_for_service "ML Gateway" 5000
        wait_for_service "ML Privacy" 5001
        
        if check_port 5000 && check_port 5001; then
            echo -e "${GREEN}  ✓ ML services started${NC}"
        else
            echo -e "${YELLOW}  ⚠ Some ML services may not be ready${NC}"
        fi
    else
        echo -e "${RED}  ✗ Failed to start ML services${NC}"
    fi
fi

# Step 4: Orchestrator
echo -e "\n${MAGENTA}[4/5] Orchestrator${NC}"
if check_port 5002; then
    echo -e "${GREEN}  ✓ Already running${NC}"
else
    echo -e "${CYAN}  Starting Orchestrator...${NC}"
    
    cd "${PROJECT_ROOT}/orchestrator"
    
    # Install dependencies quietly
    pip3 install --user -q Flask Flask-CORS web3 requests python-dotenv 2>/dev/null
    
    # Start orchestrator
    nohup python3 orchestrator.py > "${LOG_DIR}/orchestrator.log" 2>&1 &
    
    wait_for_service "Orchestrator" 5002
    
    if check_port 5002; then
        echo -e "${GREEN}  ✓ Orchestrator started${NC}"
    else
        echo -e "${RED}  ✗ Orchestrator failed to start${NC}"
    fi
    
    cd "${PROJECT_ROOT}"
fi

# Step 5: Frontend
echo -e "\n${MAGENTA}[5/5] Frontend${NC}"
if check_port 8080; then
    echo -e "${GREEN}  ✓ Already running${NC}"
else
    if [ -d "${PROJECT_ROOT}/frontend" ]; then
        echo -e "${CYAN}  Starting Frontend...${NC}"
        
        cd "${PROJECT_ROOT}/frontend"
        
        # Install dependencies if needed
        if [ ! -d "node_modules" ]; then
            echo -e "${CYAN}  Installing dependencies...${NC}"
            npm install --silent > "${LOG_DIR}/frontend-install.log" 2>&1
        fi
        
        # Start frontend
        nohup npm start > "${LOG_DIR}/frontend.log" 2>&1 &
        
        wait_for_service "Frontend" 8080
        
        if check_port 8080; then
            echo -e "${GREEN}  ✓ Frontend started${NC}"
        else
            echo -e "${RED}  ✗ Frontend failed to start${NC}"
        fi
        
        cd "${PROJECT_ROOT}"
    else
        echo -e "${YELLOW}  ⚠ Frontend directory not found${NC}"
    fi
fi

# Summary
echo -e "\n${CYAN}================================================${NC}"
echo -e "${CYAN}              System Status${NC}"
echo -e "${CYAN}================================================${NC}"

echo -e "\n${BLUE}Services:${NC}"
check_port 7051 && echo -e "  ${GREEN}✓${NC} Fabric (7051)" || echo -e "  ${RED}✗${NC} Fabric (7051)"
check_port 8545 && echo -e "  ${GREEN}✓${NC} Ethereum (8545)" || echo -e "  ${RED}✗${NC} Ethereum (8545)"
check_port 5000 && echo -e "  ${GREEN}✓${NC} ML Gateway (5000)" || echo -e "  ${RED}✗${NC} ML Gateway (5000)"
check_port 5001 && echo -e "  ${GREEN}✓${NC} ML Privacy (5001)" || echo -e "  ${RED}✗${NC} ML Privacy (5001)"
check_port 5002 && echo -e "  ${GREEN}✓${NC} Orchestrator (5002)" || echo -e "  ${RED}✗${NC} Orchestrator (5002)"
check_port 8080 && echo -e "  ${GREEN}✓${NC} Frontend (8080)" || echo -e "  ${RED}✗${NC} Frontend (8080)"

echo -e "\n${BLUE}Access Points:${NC}"
echo -e "  Frontend: ${CYAN}http://localhost:8080${NC}"
echo -e "  API: ${CYAN}http://localhost:5002${NC}"

echo -e "\n${BLUE}Commands:${NC}"
echo -e "  Stop all: ${CYAN}./start-clean.sh stop${NC}"
echo -e "  View logs: ${CYAN}tail -f logs/*.log${NC}"

echo -e "\n${GREEN}✨ System startup complete!${NC}"
echo -e "${CYAN}================================================${NC}"

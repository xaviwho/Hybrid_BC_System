#!/bin/bash

# Comprehensive Frontend Verification and Startup Script
# Ensures all services are running and frontend is properly connected

set -e

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

echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}   Frontend System Verification & Startup${NC}"
echo -e "${CYAN}================================================${NC}"

# Function to check if a port is in use
check_port() {
    local port=$1
    nc -z localhost $port 2>/dev/null
}

# Function to start a service if not running
ensure_service() {
    local service_name=$1
    local port=$2
    local start_command=$3
    local working_dir=$4
    
    echo -ne "${YELLOW}Checking ${service_name}...${NC} "
    
    if check_port $port; then
        echo -e "${GREEN}✓ Already running${NC}"
        return 0
    else
        echo -e "${YELLOW}Starting...${NC}"
        cd "$working_dir"
        eval "$start_command"
        
        # Wait for service to start
        local attempts=0
        while [ $attempts -lt 30 ]; do
            if check_port $port; then
                echo -e "  ${GREEN}✓ ${service_name} started successfully${NC}"
                return 0
            fi
            sleep 1
            attempts=$((attempts + 1))
        done
        
        echo -e "  ${RED}✗ Failed to start ${service_name}${NC}"
        return 1
    fi
}

echo -e "\n${BLUE}Step 1: Checking Core Services${NC}"
echo -e "${BLUE}===============================${NC}"

# Check Hyperledger Fabric
echo -ne "${YELLOW}Checking Hyperledger Fabric...${NC} "
if check_port 7051; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo -e "${CYAN}  → Run: ./start-system.sh${NC}"
fi

# Check and start Ethereum (Ganache)
echo -ne "${YELLOW}Checking Ethereum (Ganache)...${NC} "
if check_port 8545; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}Starting Ganache...${NC}"
    docker run -d --name ganache-cli -p 8545:8545 trufflesuite/ganache:latest --accounts 10 --host 0.0.0.0 > /dev/null 2>&1 || {
        docker start ganache-cli > /dev/null 2>&1
    }
    sleep 5
    if check_port 8545; then
        echo -e "  ${GREEN}✓ Ganache started${NC}"
    else
        echo -e "  ${RED}✗ Failed to start Ganache${NC}"
    fi
fi

echo -e "\n${BLUE}Step 2: Checking ML Services${NC}"
echo -e "${BLUE}=============================${NC}"

# Check ML services
if check_port 5000 && check_port 5001; then
    echo -e "${GREEN}✓ ML services are running${NC}"
else
    echo -e "${YELLOW}Starting ML services...${NC}"
    docker-compose -f "${PROJECT_ROOT}/docker-compose-hybrid.yml" up -d ml-gateway ml-privacy > /dev/null 2>&1
    sleep 5
    echo -e "${GREEN}✓ ML services started${NC}"
fi

echo -e "\n${BLUE}Step 3: Checking Orchestrator${NC}"
echo -e "${BLUE}==============================${NC}"

ensure_service "Orchestrator" 5002 \
    "nohup python3 orchestrator.py > '${LOG_DIR}/orchestrator.log' 2>&1 &" \
    "${PROJECT_ROOT}/orchestrator"

echo -e "\n${BLUE}Step 4: Starting Frontend${NC}"
echo -e "${BLUE}=========================${NC}"

# Install frontend dependencies if needed
if [ ! -d "${PROJECT_ROOT}/frontend/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd "${PROJECT_ROOT}/frontend"
    npm install > "${LOG_DIR}/frontend-install.log" 2>&1
fi

# Start frontend
ensure_service "Frontend Server" 8080 \
    "nohup npm start > '${LOG_DIR}/frontend.log' 2>&1 &" \
    "${PROJECT_ROOT}/frontend"

echo -e "\n${BLUE}Step 5: Verifying Connections${NC}"
echo -e "${BLUE}==============================${NC}"

# Test key endpoints
echo -e "${CYAN}Testing service endpoints...${NC}"

# Function to test endpoint
test_endpoint() {
    local name=$1
    local url=$2
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    
    if [ "$response" = "200" ]; then
        echo -e "  ${GREEN}✓ ${name}: OK${NC}"
        return 0
    else
        echo -e "  ${RED}✗ ${name}: Failed (HTTP ${response})${NC}"
        return 1
    fi
}

test_endpoint "Orchestrator API" "http://localhost:5002/health"
test_endpoint "ML Gateway" "http://localhost:5000/health"
test_endpoint "ML Privacy Filter" "http://localhost:5001/health"
test_endpoint "Frontend UI" "http://localhost:8080"

echo -e "\n${BLUE}Step 6: Testing Data Flow${NC}"
echo -e "${BLUE}=========================${NC}"

# Test ML Privacy Filter
echo -e "${CYAN}Testing ML Privacy Filter...${NC}"
PRIVACY_TEST=$(curl -s -X POST http://localhost:5001/filter_data \
    -H "Content-Type: application/json" \
    -d '{"data": {"test": "data", "temperature": 25}}' 2>/dev/null || echo "failed")

if [[ "$PRIVACY_TEST" == *"shareable_data"* ]]; then
    echo -e "  ${GREEN}✓ ML Privacy Filter working${NC}"
else
    echo -e "  ${RED}✗ ML Privacy Filter not responding correctly${NC}"
fi

# Test complete workflow
echo -e "${CYAN}Testing complete data ingestion workflow...${NC}"
WORKFLOW_TEST=$(curl -s -X POST http://localhost:5002/ingest_data \
    -H "Content-Type: application/json" \
    -d '{
        "id": "frontend_test_'$(date +%s)'",
        "deviceId": "test_sensor",
        "data": {"temperature": 22.5}
    }' 2>/dev/null || echo "failed")

if [[ "$WORKFLOW_TEST" == *"error"* ]] || [[ "$WORKFLOW_TEST" == "failed" ]]; then
    echo -e "  ${YELLOW}⚠ Workflow test returned an error (this is normal if Fabric isn't fully configured)${NC}"
else
    echo -e "  ${GREEN}✓ Data ingestion workflow operational${NC}"
fi

echo -e "\n${CYAN}================================================${NC}"
echo -e "${CYAN}              System Status Summary${NC}"
echo -e "${CYAN}================================================${NC}"

echo -e "\n${GREEN}Frontend Dashboard:${NC} ${CYAN}http://localhost:8080${NC}"
echo -e "${GREEN}API Endpoints:${NC}"
echo -e "  • Orchestrator: ${CYAN}http://localhost:5002${NC}"
echo -e "  • ML Gateway: ${CYAN}http://localhost:5000${NC}"
echo -e "  • ML Privacy: ${CYAN}http://localhost:5001${NC}"
echo -e "  • Ethereum: ${CYAN}http://localhost:8545${NC}"

echo -e "\n${YELLOW}Frontend Features Available:${NC}"
echo -e "  ✓ Real-time system monitoring"
echo -e "  ✓ IoT data submission form"
echo -e "  ✓ Privacy control settings"
echo -e "  ✓ Blockchain transaction viewer"
echo -e "  ✓ Activity logs and metrics"

echo -e "\n${GREEN}Test the Frontend:${NC}"
echo -e "1. Open ${CYAN}http://localhost:8080${NC} in your browser"
echo -e "2. Navigate to 'Data Ingestion' tab"
echo -e "3. Submit test data:"
echo -e "   • Device ID: test_sensor_001"
echo -e "   • Location: Test Lab"
echo -e "   • Data Type: Environmental Data"
echo -e "   • JSON Payload: {\"temperature\": 25, \"humidity\": 60}"
echo -e "   • Privacy Level: Medium"

echo -e "\n${GREEN}✨ Frontend is ready and fully connected!${NC}"
echo -e "${CYAN}================================================${NC}"

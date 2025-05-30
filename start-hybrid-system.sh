#!/bin/bash
# Master control script for Hybrid Blockchain-based Incognito Data Sharing System
# Uses existing Hyperledger Fabric network

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}       HYBRID BLOCKCHAIN IOT DATA SHARING SYSTEM          ${NC}"
echo -e "${BLUE}          with Quantum Security & ML Filtering            ${NC}"
echo -e "${BLUE}==========================================================${NC}"

# Check Docker is running
echo -e "${YELLOW}Checking Docker status...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running! Please start Docker and try again.${NC}"
    exit 1
fi

# Stop any running containers from previous attempts
echo -e "${YELLOW}Cleaning up any previous deployments...${NC}"
docker-compose -f docker-compose-hybrid.yml down &>/dev/null

# Check if Hyperledger Fabric is already running
echo -e "${YELLOW}Checking Hyperledger Fabric status...${NC}"
if ! docker ps | grep -q "hybrid-peer0.org1.example.com"; then
    echo -e "${YELLOW}Starting Hyperledger Fabric private blockchain...${NC}"
    cd blockchain/setup/hyperledger/fabric-samples/hybrid-bc-network
    export COMPOSE_PROJECT_NAME=hybridbc
    ./network.sh up
    ./network.sh createChannel -c hiot
    ./network.sh deployCC -c hiot -ccn iot-data -ccp ../chaincode/iot-data/go/ -ccl go
    cd ../../../../.. # Return to project root
else
    echo -e "${GREEN}Hyperledger Fabric is already running.${NC}"
    
    # Fix chaincode if needed
    cd blockchain/setup/hyperledger/fabric-samples/chaincode/iot-data/go
    if [ ! -f "go.sum" ]; then
        echo -e "${YELLOW}Fixing chaincode dependencies...${NC}"
        go mod tidy
        go mod download github.com/hyperledger/fabric-contract-api-go
    fi
    cd ../../../../../../.. # Return to project root
fi

# Now start the rest of the system with Docker Compose
echo -e "${YELLOW}Starting Ethereum and ML components...${NC}"
docker-compose -f docker-compose-hybrid.yml up -d

# Wait for system initialization
echo -e "${YELLOW}Waiting for all services to be ready...${NC}"
for i in {1..15}; do
    if docker ps | grep -q "system-orchestrator"; then
        # Check if system orchestrator is running correctly
        if docker logs system-orchestrator 2>&1 | grep -q "System Orchestrator API is running"; then
            echo -e "${GREEN}System orchestrator is running!${NC}"
            break
        fi
    fi
    echo -n "."
    sleep 2
done
echo ""

# Display system status and access points
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}      Hybrid Blockchain IoT System is now running!        ${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo -e "Access points:"
echo -e "  - System Orchestrator API: ${BLUE}http://localhost:8000${NC}"
echo -e "  - ML Gateway Filter API: ${BLUE}http://localhost:5000${NC}"
echo -e "  - ML Privacy Filter API: ${BLUE}http://localhost:5001${NC}"
echo -e "  - Ethereum JSON-RPC: ${BLUE}http://localhost:8545${NC}"
echo -e "  - Hyperledger Fabric Peer: ${BLUE}localhost:7051${NC}"
echo -e ""
echo -e "You can monitor the system with: ${YELLOW}docker ps${NC}"
echo -e "To stop the system, run: ${YELLOW}./stop-hybrid-system.sh${NC}"

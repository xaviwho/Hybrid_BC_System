#!/bin/bash
# Reset script for Hybrid Blockchain System to fix network visibility

# Colors for readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}       RESETTING HYBRID BLOCKCHAIN SYSTEM                 ${NC}"
echo -e "${BLUE}==========================================================${NC}"

# Stop the components but keep Hyperledger running
echo -e "${YELLOW}Stopping current containers...${NC}"
docker-compose -f docker-compose-hybrid.yml down

# Verify Hyperledger containers are still running
echo -e "${YELLOW}Verifying Hyperledger Fabric status...${NC}"
if docker ps | grep -q "hybrid-peer0.org1.example.com"; then
    echo -e "${GREEN}Hyperledger Fabric is running.${NC}"
else
    echo -e "${RED}Hyperledger Fabric is not running! Please start it first.${NC}"
    exit 1
fi

# Get the Hyperledger network name
FABRIC_NETWORK=$(docker network ls | grep fabric_test | awk '{print $2}')
if [ -z "$FABRIC_NETWORK" ]; then
    echo -e "${RED}Could not find fabric_test network. Creating external network reference...${NC}"
    FABRIC_NETWORK=$(docker network ls | grep hybridbc | awk '{print $2}')
    if [ -z "$FABRIC_NETWORK" ]; then
        echo -e "${RED}Could not find any Hyperledger network! Please ensure Hyperledger is running.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}Using Hyperledger network: ${FABRIC_NETWORK}${NC}"

# Start the components with the updated configuration
echo -e "${YELLOW}Starting hybrid system components...${NC}"
docker-compose -f docker-compose-hybrid.yml up -d || {
    echo -e "${RED}Error starting containers. Running with verbose output...${NC}"
    docker-compose -f docker-compose-hybrid.yml up
    exit 1
}

echo -e "${YELLOW}Waiting for components to stabilize...${NC}"
sleep 10

# Display running containers
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}      Hybrid Blockchain System Containers                 ${NC}"
echo -e "${GREEN}==========================================================${NC}"
docker ps

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}  Your hybrid blockchain system should now be visible      ${NC}"
echo -e "${BLUE}  in Docker Desktop and all components connected.          ${NC}"
echo -e "${BLUE}==========================================================${NC}"
echo -e "Access points:"
echo -e "  - System Orchestrator API: ${BLUE}http://localhost:8000${NC}"
echo -e "  - ML Gateway Filter API: ${BLUE}http://localhost:5000${NC}"
echo -e "  - ML Privacy Filter API: ${BLUE}http://localhost:5001${NC}"
echo -e "  - Ethereum JSON-RPC: ${BLUE}http://localhost:8545${NC}"
echo -e "  - Hyperledger Fabric Peer: ${BLUE}localhost:7051${NC}"

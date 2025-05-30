#!/bin/bash
# Stop script for Hybrid Blockchain-based Incognito Data Sharing System
# Preserves the existing Hyperledger Fabric network

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Stopping Hybrid Blockchain IoT System...${NC}"

# Stop Docker Compose services first (ML, Ethereum, and orchestrator)
echo -e "${YELLOW}Stopping ML, Ethereum, and orchestrator services...${NC}"
docker-compose -f docker-compose-hybrid.yml down

# Ask about stopping Hyperledger Fabric
echo -e "${YELLOW}Do you want to stop the Hyperledger Fabric network too? (y/N)${NC}"
read -r STOP_FABRIC

if [[ $STOP_FABRIC =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Shutting down Hyperledger Fabric network...${NC}"
    cd blockchain/setup/hyperledger/fabric-samples/hybrid-bc-network
    export COMPOSE_PROJECT_NAME=hybridbc
    ./network.sh down
    cd ../../../../..
    echo -e "${GREEN}Hyperledger Fabric network shutdown complete.${NC}"
else
    echo -e "${GREEN}Keeping Hyperledger Fabric network running.${NC}"
fi

echo -e "${GREEN}System shutdown complete.${NC}"
echo -e "To restart the system: ${YELLOW}./start-hybrid-system.sh${NC}"

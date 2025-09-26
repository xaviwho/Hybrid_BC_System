#!/bin/bash
set -e

# Get the script's directory to ensure we can return to the project root
PROJECT_ROOT=$(pwd)

# Set the path to Fabric binaries
FABRIC_SAMPLES_DIR="${PROJECT_ROOT}/blockchain/setup/hyperledger/fabric-samples"
export PATH="${FABRIC_SAMPLES_DIR}/bin:$PATH"
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

# Shut down and rebuild the Docker Compose services (Ethereum, ML, etc.)
echo -e "${YELLOW}Cleaning up and rebuilding Docker Compose services...${NC}"
docker-compose -f docker-compose-hybrid.yml down --volumes --remove-orphans
docker-compose -f docker-compose-hybrid.yml build

# Now build and start the rest of the system with Docker Compose
echo -e "${YELLOW}Building Ethereum and ML components...${NC}"
docker-compose -f docker-compose-hybrid.yml build
echo -e "${YELLOW}Starting Ethereum and ML components...${NC}"
docker-compose -f docker-compose-hybrid.yml up -d


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

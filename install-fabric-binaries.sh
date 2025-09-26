#!/bin/bash

# Install Hyperledger Fabric Binaries and Docker Images
# This script downloads the necessary binaries for running Fabric network

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fabric version configuration
FABRIC_VERSION="2.5.0"
CA_VERSION="1.5.5"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Installing Hyperledger Fabric Binaries${NC}"
echo -e "${BLUE}========================================${NC}"

# Navigate to the fabric-samples directory
cd "$(dirname "$0")/blockchain/setup/hyperledger/fabric-samples"

echo -e "${YELLOW}Current directory: $(pwd)${NC}"

# Download binaries using the Fabric bootstrap script
echo -e "${BLUE}Downloading Fabric binaries version ${FABRIC_VERSION}...${NC}"

# Create bin and config directories if they don't exist
mkdir -p bin config

# Download the bootstrap script
echo -e "${BLUE}Downloading Fabric bootstrap script...${NC}"
curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/bootstrap.sh -o bootstrap.sh
chmod +x bootstrap.sh

# Run bootstrap script to download binaries and docker images
# -d flag skips clone of fabric-samples (we already have it)
# -s flag skips clone of fabric-samples
echo -e "${BLUE}Running bootstrap script to download binaries...${NC}"
./bootstrap.sh ${FABRIC_VERSION} ${CA_VERSION} -d -s

# Alternative method if bootstrap fails
if [ ! -f "bin/peer" ]; then
    echo -e "${YELLOW}Bootstrap script failed. Trying direct download...${NC}"
    
    # Determine OS and architecture
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    
    if [ "$ARCH" = "x86_64" ]; then
        ARCH="amd64"
    fi
    
    BINARY_FILE="hyperledger-fabric-${OS}-${ARCH}-${FABRIC_VERSION}.tar.gz"
    CA_BINARY_FILE="hyperledger-fabric-ca-${OS}-${ARCH}-${CA_VERSION}.tar.gz"
    
    echo -e "${BLUE}Downloading Fabric binaries for ${OS}-${ARCH}...${NC}"
    
    # Download Fabric binaries
    curl -sSL https://github.com/hyperledger/fabric/releases/download/v${FABRIC_VERSION}/${BINARY_FILE} -o ${BINARY_FILE}
    
    # Extract binaries
    echo -e "${BLUE}Extracting Fabric binaries...${NC}"
    tar xzf ${BINARY_FILE} -C .
    rm ${BINARY_FILE}
    
    # Download CA binaries
    echo -e "${BLUE}Downloading Fabric CA binaries...${NC}"
    curl -sSL https://github.com/hyperledger/fabric-ca/releases/download/v${CA_VERSION}/${CA_BINARY_FILE} -o ${CA_BINARY_FILE}
    
    # Extract CA binaries
    echo -e "${BLUE}Extracting Fabric CA binaries...${NC}"
    tar xzf ${CA_BINARY_FILE} -C .
    rm ${CA_BINARY_FILE}
fi

# Verify installation
echo -e "${BLUE}Verifying installation...${NC}"

if [ -f "bin/peer" ]; then
    echo -e "${GREEN}✓ Peer binary installed${NC}"
    ./bin/peer version
else
    echo -e "${RED}✗ Peer binary not found${NC}"
    exit 1
fi

if [ -f "bin/orderer" ]; then
    echo -e "${GREEN}✓ Orderer binary installed${NC}"
    ./bin/orderer version
else
    echo -e "${RED}✗ Orderer binary not found${NC}"
    exit 1
fi

if [ -f "bin/fabric-ca-client" ]; then
    echo -e "${GREEN}✓ Fabric CA client installed${NC}"
    ./bin/fabric-ca-client version
else
    echo -e "${YELLOW}⚠ Fabric CA client not found (optional)${NC}"
fi

# Pull Docker images
echo -e "${BLUE}Pulling Hyperledger Fabric Docker images...${NC}"

FABRIC_IMAGES=(
    "hyperledger/fabric-peer:${FABRIC_VERSION}"
    "hyperledger/fabric-orderer:${FABRIC_VERSION}"
    "hyperledger/fabric-ccenv:${FABRIC_VERSION}"
    "hyperledger/fabric-tools:${FABRIC_VERSION}"
    "hyperledger/fabric-ca:${CA_VERSION}"
    "hyperledger/fabric-couchdb:latest"
)

for image in "${FABRIC_IMAGES[@]}"; do
    echo -e "${BLUE}Pulling ${image}...${NC}"
    docker pull ${image}
done

# Tag images for compatibility
echo -e "${BLUE}Tagging Docker images...${NC}"
docker tag hyperledger/fabric-peer:${FABRIC_VERSION} hyperledger/fabric-peer:latest
docker tag hyperledger/fabric-orderer:${FABRIC_VERSION} hyperledger/fabric-orderer:latest
docker tag hyperledger/fabric-tools:${FABRIC_VERSION} hyperledger/fabric-tools:latest
docker tag hyperledger/fabric-ca:${CA_VERSION} hyperledger/fabric-ca:latest

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Fabric binaries installation complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Installed components:${NC}"
echo -e "  • Fabric version: ${FABRIC_VERSION}"
echo -e "  • CA version: ${CA_VERSION}"
echo -e "  • Binaries location: $(pwd)/bin"
echo -e "  • Config location: $(pwd)/config"

echo -e "\n${YELLOW}Next steps:${NC}"
echo -e "1. Return to project root: cd $(dirname "$0")"
echo -e "2. Run the deployment script: ./deploy-hybrid-fabric.sh"
echo -e "3. Or run the complete system: ./start-complete-system.sh"

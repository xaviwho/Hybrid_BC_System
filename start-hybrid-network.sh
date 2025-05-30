#!/bin/bash
# Hybrid Blockchain IoT System Network Startup Script
# This script manages the Hyperledger Fabric network for the hybrid blockchain system

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Navigate to the test-network directory
cd "$(dirname "$0")/blockchain/setup/hyperledger/fabric-samples/test-network"

# Display header
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}      Hybrid Blockchain IoT System Network Manager        ${NC}"
echo -e "${GREEN}==========================================================${NC}"

# Set the project name for docker-compose
export COMPOSE_PROJECT_NAME="hybridbc"

# Function to check if the network is already running
check_network() {
    if docker ps | grep "hybrid-orderer" > /dev/null; then
        echo -e "${YELLOW}Network is already running.${NC}"
        return 0
    else
        return 1
    fi
}

# Function to start the network
start_network() {
    echo -e "${GREEN}Starting Hybrid Blockchain Network...${NC}"
    ./network.sh up
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Network started successfully!${NC}"
        return 0
    else
        echo -e "${RED}Failed to start network.${NC}"
        return 1
    fi
}

# Function to create the hiot channel
create_channel() {
    echo -e "${GREEN}Creating 'hiot' channel...${NC}"
    ./network.sh createChannel -c hiot
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Channel 'hiot' created successfully!${NC}"
        return 0
    else
        echo -e "${RED}Failed to create channel.${NC}"
        return 1
    fi
}

# Function to deploy the IoT Data chaincode
deploy_chaincode() {
    echo -e "${GREEN}Deploying IoT Data chaincode...${NC}"
    ./network.sh deployCC -c hiot -ccn iot-data -ccp ../chaincode/iot-data/go/ -ccl go
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}IoT Data chaincode deployed successfully!${NC}"
        return 0
    else
        echo -e "${RED}Failed to deploy chaincode.${NC}"
        return 1
    fi
}

# Function to stop the network
stop_network() {
    echo -e "${YELLOW}Stopping Hybrid Blockchain Network...${NC}"
    
    # First try the normal way
    ./network.sh down
    
    # If containers are still around, force remove them
    if docker ps -a | grep hybrid > /dev/null; then
        echo -e "${YELLOW}Some containers still exist. Force removing them...${NC}"
        docker rm -f $(docker ps -a | grep hybrid | awk '{print $1}') 2>/dev/null || true
    fi
    
    # Check if the network was stopped successfully
    if ! docker ps | grep hybrid > /dev/null; then
        echo -e "${GREEN}Network stopped successfully!${NC}"
        return 0
    else
        echo -e "${RED}Failed to stop network.${NC}"
        return 1
    fi
}

# Function to display help
show_help() {
    echo -e "${GREEN}Hybrid Blockchain IoT System Network Manager${NC}"
    echo "Usage: $0 [OPTION]"
    echo "Options:"
    echo "  start       - Start the network"
    echo "  channel     - Create the 'hiot' channel"
    echo "  chaincode   - Deploy the IoT Data chaincode"
    echo "  restart     - Restart the network (down and up)"
    echo "  stop        - Stop the network"
    echo "  status      - Check network status"
    echo "  all         - Perform all steps (start, channel, chaincode)"
    echo "  help        - Show this help message"
}

# Function to check network status
check_status() {
    echo -e "${GREEN}Checking Hybrid Blockchain Network status...${NC}"
    
    if check_network; then
        echo -e "${GREEN}Network components:${NC}"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep hybrid
    else
        echo -e "${YELLOW}Hybrid Blockchain Network is not running.${NC}"
    fi
}

# Process command line arguments
case "$1" in
    start)
        if ! check_network; then
            start_network
        fi
        ;;
    channel)
        if check_network; then
            create_channel
        else
            echo -e "${RED}Network is not running. Start it first with '$0 start'${NC}"
        fi
        ;;
    chaincode)
        if check_network; then
            deploy_chaincode
        else
            echo -e "${RED}Network is not running. Start it first with '$0 start'${NC}"
        fi
        ;;
    restart)
        stop_network
        sleep 3
        start_network
        ;;
    stop)
        stop_network
        ;;
    status)
        check_status
        ;;
    all)
        if ! check_network; then
            start_network
        fi
        create_channel
        deploy_chaincode
        echo -e "${GREEN}==========================================================${NC}"
        echo -e "${GREEN}      Hybrid Blockchain IoT System is now ready!          ${NC}"
        echo -e "${GREEN}==========================================================${NC}"
        ;;
    help|*)
        show_help
        ;;
esac

exit 0

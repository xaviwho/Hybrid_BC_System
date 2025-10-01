#!/bin/bash

# Diagnostic script to check why services aren't starting

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}   System Startup Diagnostics${NC}"
echo -e "${CYAN}================================================${NC}"

# Check Docker
echo -e "\n${BLUE}1. Docker Status:${NC}"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker is installed${NC}"
    
    # Check if Docker daemon is running
    if docker info > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Docker daemon is running${NC}"
        
        # Check Docker version
        DOCKER_VERSION=$(docker --version)
        echo -e "  Version: $DOCKER_VERSION"
        
        # List running containers
        echo -e "\n  Running containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -10
    else
        echo -e "${RED}✗ Docker daemon is not running${NC}"
        echo -e "${YELLOW}Please start Docker Desktop or Docker service${NC}"
    fi
else
    echo -e "${RED}✗ Docker is not installed${NC}"
fi

# Check Docker Compose
echo -e "\n${BLUE}2. Docker Compose Status:${NC}"
if command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✓ Docker Compose is installed${NC}"
    COMPOSE_VERSION=$(docker-compose --version)
    echo -e "  Version: $COMPOSE_VERSION"
else
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
fi

# Check Python
echo -e "\n${BLUE}3. Python Status:${NC}"
if command -v python3 &> /dev/null; then
    echo -e "${GREEN}✓ Python3 is installed${NC}"
    PYTHON_VERSION=$(python3 --version)
    echo -e "  Version: $PYTHON_VERSION"
else
    echo -e "${RED}✗ Python3 is not installed${NC}"
fi

# Check Node.js
echo -e "\n${BLUE}4. Node.js Status:${NC}"
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓ Node.js is installed${NC}"
    NODE_VERSION=$(node --version)
    echo -e "  Version: $NODE_VERSION"
else
    echo -e "${RED}✗ Node.js is not installed${NC}"
fi

# Check npm
echo -e "\n${BLUE}5. NPM Status:${NC}"
if command -v npm &> /dev/null; then
    echo -e "${GREEN}✓ NPM is installed${NC}"
    NPM_VERSION=$(npm --version)
    echo -e "  Version: $NPM_VERSION"
else
    echo -e "${RED}✗ NPM is not installed${NC}"
fi

# Check port availability
echo -e "\n${BLUE}6. Port Availability:${NC}"
PORTS=(7051 8545 5000 5001 5002 8080)
for port in "${PORTS[@]}"; do
    if nc -z localhost $port 2>/dev/null; then
        echo -e "${YELLOW}Port $port: IN USE${NC}"
        # Try to identify what's using it
        if command -v lsof &> /dev/null; then
            PROCESS=$(lsof -i :$port 2>/dev/null | grep LISTEN | awk '{print $1}' | head -1)
            if [ ! -z "$PROCESS" ]; then
                echo -e "  Used by: $PROCESS"
            fi
        fi
    else
        echo -e "${GREEN}Port $port: AVAILABLE${NC}"
    fi
done

# Check for existing Ganache container
echo -e "\n${BLUE}7. Ganache Container Status:${NC}"
if docker ps -a | grep -q ganache-cli; then
    echo -e "${YELLOW}Ganache container exists${NC}"
    GANACHE_STATUS=$(docker inspect ganache-cli --format='{{.State.Status}}' 2>/dev/null)
    echo -e "  Status: $GANACHE_STATUS"
    
    if [ "$GANACHE_STATUS" = "exited" ]; then
        echo -e "${YELLOW}Container is stopped. Checking logs...${NC}"
        echo -e "  Last 5 lines of logs:"
        docker logs ganache-cli --tail 5 2>&1 | sed 's/^/    /'
    fi
else
    echo -e "${GREEN}No existing Ganache container${NC}"
fi

# Check log files
echo -e "\n${BLUE}8. Log Files:${NC}"
LOG_DIR="./logs"
if [ -d "$LOG_DIR" ]; then
    echo -e "${GREEN}Log directory exists${NC}"
    
    # Check for recent errors in logs
    for log_file in "$LOG_DIR"/*.log; do
        if [ -f "$log_file" ]; then
            filename=$(basename "$log_file")
            echo -e "\n  Checking $filename:"
            
            # Check if file has content
            if [ -s "$log_file" ]; then
                # Show last 3 lines
                tail -3 "$log_file" | sed 's/^/    /'
            else
                echo -e "    (empty)"
            fi
        fi
    done
else
    echo -e "${YELLOW}No log directory found${NC}"
fi

# Recommendations
echo -e "\n${CYAN}================================================${NC}"
echo -e "${CYAN}   Recommendations${NC}"
echo -e "${CYAN}================================================${NC}"

ISSUES_FOUND=false

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    ISSUES_FOUND=true
    echo -e "\n${RED}Issue: Docker is not running${NC}"
    echo -e "${YELLOW}Solution:${NC}"
    echo -e "  1. Start Docker Desktop (Windows)"
    echo -e "  2. Wait for Docker to fully start"
    echo -e "  3. Run ./start-system.sh again"
fi

# Check if ports are blocked
if nc -z localhost 8545 2>/dev/null; then
    if ! docker ps | grep -q ganache-cli; then
        ISSUES_FOUND=true
        echo -e "\n${RED}Issue: Port 8545 is in use but not by Ganache container${NC}"
        echo -e "${YELLOW}Solution:${NC}"
        echo -e "  1. Kill the process using port 8545"
        echo -e "  2. Or use: docker stop ganache-cli && docker rm ganache-cli"
    fi
fi

if [ "$ISSUES_FOUND" = false ]; then
    echo -e "\n${GREEN}No major issues detected!${NC}"
    echo -e "${YELLOW}Try running:${NC}"
    echo -e "  ./start-system.sh"
fi

echo -e "\n${CYAN}================================================${NC}"

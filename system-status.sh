#!/bin/bash

# System Status Check Script

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}   Hybrid Blockchain System - Status Check     ${NC}"
echo -e "${CYAN}================================================${NC}"

echo -e "\n${BLUE}Service Status:${NC}"
echo -e "${BLUE}---------------${NC}"

# Check Hyperledger Fabric
if docker ps | grep -q "peer0.org1.example.com"; then
    echo -e "${GREEN}✓ Hyperledger Fabric${NC}"
    echo -e "  • Peer Org1: $(docker ps --format 'table {{.Status}}' --filter name=peer0.org1 | tail -1)"
    echo -e "  • Orderer: $(docker ps --format 'table {{.Status}}' --filter name=orderer | tail -1)"
    echo -e "  • CouchDB: $(docker ps --format 'table {{.Status}}' --filter name=couchdb0 | tail -1)"
else
    echo -e "${RED}✗ Hyperledger Fabric - NOT RUNNING${NC}"
fi

# Check Ethereum (Ganache)
if nc -z localhost 8545 2>/dev/null; then
    echo -e "${GREEN}✓ Ethereum (Ganache)${NC}"
    # Get latest block number
    BLOCK=$(curl -s -X POST -H "Content-Type: application/json" \
        --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
        http://localhost:8545 | python3 -c "import sys, json; print(int(json.load(sys.stdin)['result'], 16))" 2>/dev/null)
    echo -e "  • Latest block: #${BLOCK}"
    echo -e "  • RPC endpoint: http://localhost:8545"
else
    echo -e "${RED}✗ Ethereum (Ganache) - NOT RUNNING${NC}"
fi

# Check ML Gateway
if docker ps | grep -q "ml-gateway" && nc -z localhost 5000 2>/dev/null; then
    echo -e "${GREEN}✓ ML Gateway${NC}"
    HEALTH=$(curl -s http://localhost:5000/health 2>/dev/null || echo "N/A")
    echo -e "  • Status: Running on port 5000"
else
    echo -e "${RED}✗ ML Gateway - NOT RUNNING${NC}"
fi

# Check ML Privacy Filter
if docker ps | grep -q "ml-privacy" && nc -z localhost 5001 2>/dev/null; then
    echo -e "${GREEN}✓ ML Privacy Filter${NC}"
    echo -e "  • Status: Running on port 5001"
else
    echo -e "${RED}✗ ML Privacy Filter - NOT RUNNING${NC}"
fi

# Check Orchestrator
if nc -z localhost 5002 2>/dev/null; then
    ORCH_HEALTH=$(curl -s http://localhost:5002/health 2>/dev/null)
    if [ ! -z "$ORCH_HEALTH" ]; then
        ETH_CONNECTED=$(echo $ORCH_HEALTH | python3 -c "import sys, json; print(json.load(sys.stdin)['ethereum_connected'])" 2>/dev/null)
        echo -e "${GREEN}✓ Orchestrator${NC}"
        echo -e "  • Status: Running on port 5002"
        echo -e "  • Ethereum connected: ${ETH_CONNECTED}"
    else
        echo -e "${YELLOW}⚠ Orchestrator running but health check failed${NC}"
    fi
else
    echo -e "${RED}✗ Orchestrator - NOT RUNNING${NC}"
fi

echo -e "\n${BLUE}Smart Contract Addresses:${NC}"
echo -e "${BLUE}------------------------${NC}"
if [ -f "blockchain/setup/ethereum/build/contracts/IoTDataRegistry.json" ]; then
    CONTRACT_ADDRESS=$(grep -A 10 '"networks"' blockchain/setup/ethereum/build/contracts/IoTDataRegistry.json | grep '"address"' | head -1 | cut -d'"' -f4)
    echo -e "IoTDataRegistry: ${CYAN}${CONTRACT_ADDRESS}${NC}"
fi

echo -e "\n${BLUE}Test Commands:${NC}"
echo -e "${BLUE}-------------${NC}"
echo -e "${YELLOW}1. Test ML Privacy Filter:${NC}"
echo -e "   curl -X POST http://localhost:5001/filter_data \\"
echo -e "     -H 'Content-Type: application/json' \\"
echo -e "     -d '{\"data\": {\"temperature\": 25.5, \"location\": \"Lab A\"}}'"

echo -e "\n${YELLOW}2. Test Complete Workflow:${NC}"
echo -e "   curl -X POST http://localhost:5002/ingest_data \\"
echo -e "     -H 'Content-Type: application/json' \\"
echo -e "     -d '{"
echo -e "       \"id\": \"test_$(date +%s)\","
echo -e "       \"deviceId\": \"sensor_001\","
echo -e "       \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
echo -e "       \"dataType\": \"environmental\","
echo -e "       \"data\": {"
echo -e "         \"temperature\": 22.5,"
echo -e "         \"humidity\": 65,"
echo -e "         \"location\": \"Lab A\","
echo -e "         \"pressure\": 1013.25"
echo -e "       }"
echo -e "     }'"

echo -e "\n${CYAN}================================================${NC}"

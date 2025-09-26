#!/bin/bash

# Frontend Integration Test Script
# Tests all connections between frontend and backend services

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}   Frontend Integration Test Suite${NC}"
echo -e "${CYAN}================================================${NC}"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=""

# Function to test endpoint
test_endpoint() {
    local name=$1
    local url=$2
    local method=${3:-GET}
    local data=${4:-}
    
    echo -ne "${YELLOW}Testing ${name}...${NC} "
    
    if [ "$method" = "POST" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$url" 2>/dev/null || echo "000")
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    fi
    
    if [ "$response" = "200" ] || [ "$response" = "201" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $response)"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP $response)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS="${FAILED_TESTS}\n  - ${name}: HTTP ${response}"
        return 1
    fi
}

# Function to test WebSocket or real-time features
test_realtime() {
    local name=$1
    local url=$2
    
    echo -ne "${YELLOW}Testing ${name} connectivity...${NC} "
    
    # Simple connectivity test
    if nc -z -w 2 $(echo $url | sed 's/.*:\/\/\([^:]*\).*/\1/') $(echo $url | sed 's/.*:\([0-9]*\).*/\1/') 2>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS="${FAILED_TESTS}\n  - ${name}: Connection failed"
        return 1
    fi
}

echo -e "\n${BLUE}1. Testing Backend Services${NC}"
echo -e "${BLUE}============================${NC}"

# Test Orchestrator
test_endpoint "Orchestrator Health" "http://localhost:5002/health"

# Test ML Services
test_endpoint "ML Gateway Health" "http://localhost:5000/health"
test_endpoint "ML Privacy Filter Health" "http://localhost:5001/health"

# Test Frontend Server
test_endpoint "Frontend Server" "http://localhost:8080/health"
test_endpoint "Frontend UI" "http://localhost:8080"

echo -e "\n${BLUE}2. Testing Service Connectivity${NC}"
echo -e "${BLUE}================================${NC}"

# Test Ethereum connectivity
test_realtime "Ethereum (Ganache)" "localhost:8545"

# Test Fabric connectivity
test_realtime "Hyperledger Fabric" "localhost:7051"

echo -e "\n${BLUE}3. Testing Data Flow Integration${NC}"
echo -e "${BLUE}=================================${NC}"

# Test ML Privacy Filter endpoint
TEST_DATA='{"data": {"temperature": 25.5, "humidity": 60, "location": "Test Lab"}}'
test_endpoint "ML Privacy Filter Processing" "http://localhost:5001/filter_data" "POST" "$TEST_DATA"

# Test complete data ingestion workflow
INGESTION_DATA='{
    "id": "test_'$(date +%s)'",
    "deviceId": "test_sensor_001",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "dataType": "environmental",
    "data": {
        "temperature": 22.5,
        "humidity": 65,
        "pressure": 1013.25,
        "location": "Integration Test"
    }
}'

test_endpoint "Data Ingestion Workflow" "http://localhost:5002/ingest_data" "POST" "$INGESTION_DATA"

echo -e "\n${BLUE}4. Testing Frontend API Calls${NC}"
echo -e "${BLUE}==============================${NC}"

# Test if frontend can reach all required endpoints
echo -e "${CYAN}Simulating frontend API calls...${NC}"

# Test CORS headers
echo -ne "${YELLOW}Testing CORS configuration...${NC} "
cors_test=$(curl -s -I -X OPTIONS \
    -H "Origin: http://localhost:8080" \
    -H "Access-Control-Request-Method: POST" \
    http://localhost:5002/ingest_data 2>/dev/null | grep -i "access-control-allow-origin" || echo "")

if [ ! -z "$cors_test" ]; then
    echo -e "${GREEN}✓ PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${YELLOW}⚠ WARNING${NC} - CORS might not be configured"
fi

echo -e "\n${BLUE}5. Testing Frontend Components${NC}"
echo -e "${BLUE}===============================${NC}"

# Check if frontend files are accessible
echo -ne "${YELLOW}Checking frontend static files...${NC} "
static_files=("styles.css" "script.js")
all_static_ok=true

for file in "${static_files[@]}"; do
    response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/$file" 2>/dev/null)
    if [ "$response" != "200" ]; then
        all_static_ok=false
        break
    fi
done

if [ "$all_static_ok" = true ]; then
    echo -e "${GREEN}✓ PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}✗ FAIL${NC} - Some static files not accessible"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo -e "\n${BLUE}6. Performance Tests${NC}"
echo -e "${BLUE}====================${NC}"

# Test response times
echo -ne "${YELLOW}Testing API response time...${NC} "
start_time=$(date +%s%N)
curl -s "http://localhost:5002/health" > /dev/null 2>&1
end_time=$(date +%s%N)
response_time=$(( ($end_time - $start_time) / 1000000 ))

if [ $response_time -lt 1000 ]; then
    echo -e "${GREEN}✓ PASS${NC} (${response_time}ms)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${YELLOW}⚠ SLOW${NC} (${response_time}ms)"
fi

# Summary
echo -e "\n${CYAN}================================================${NC}"
echo -e "${CYAN}                Test Summary${NC}"
echo -e "${CYAN}================================================${NC}"

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
echo -e "${BLUE}Total Tests:${NC} $TOTAL_TESTS"
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"

if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "\n${RED}Failed Tests:${NC}$FAILED_TESTS"
fi

# Calculate success rate
if [ $TOTAL_TESTS -gt 0 ]; then
    SUCCESS_RATE=$(( (TESTS_PASSED * 100) / TOTAL_TESTS ))
    echo -e "\n${BLUE}Success Rate:${NC} ${SUCCESS_RATE}%"
    
    if [ $SUCCESS_RATE -eq 100 ]; then
        echo -e "${GREEN}✅ All tests passed! Frontend is fully integrated.${NC}"
    elif [ $SUCCESS_RATE -ge 80 ]; then
        echo -e "${YELLOW}⚠ Most tests passed, but some components need attention.${NC}"
    else
        echo -e "${RED}❌ Multiple integration issues detected.${NC}"
    fi
fi

echo -e "\n${CYAN}================================================${NC}"

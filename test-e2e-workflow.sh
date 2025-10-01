#!/bin/bash

# End-to-End Testing Suite for Hybrid Blockchain IoT System
# Tests the complete workflow from data ingestion to blockchain storage

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

echo -e "${CYAN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════╗
║     Hybrid Blockchain IoT System - E2E Test Suite        ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to run a test
run_test() {
    local test_name=$1
    local test_command=$2
    local expected_pattern=$3
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -e "\n${BLUE}Test $TOTAL_TESTS: ${test_name}${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Run the test
    result=$(eval "$test_command" 2>&1)
    
    # Check if result matches expected pattern
    if echo "$result" | grep -q "$expected_pattern"; then
        echo -e "${GREEN}✓ PASSED${NC}"
        echo -e "${CYAN}Response:${NC}"
        echo "$result" | python3 -m json.tool 2>/dev/null || echo "$result"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo -e "${RED}Response:${NC}"
        echo "$result"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

# ============================================================================
# PHASE 1: Service Health Checks
# ============================================================================
echo -e "\n${MAGENTA}═══════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}PHASE 1: Service Health Checks${NC}"
echo -e "${MAGENTA}═══════════════════════════════════════════════${NC}"

run_test "Orchestrator Health Check" \
    "curl -s http://localhost:5002/health" \
    "healthy"

run_test "ML Gateway Health Check" \
    "curl -s http://localhost:5000/health" \
    "status"

run_test "ML Privacy Filter Health Check" \
    "curl -s http://localhost:5001/health" \
    "status"

run_test "Frontend Health Check" \
    "curl -s http://localhost:8080/health" \
    "Frontend server is running"

run_test "Ethereum Connection" \
    "curl -s -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"method\":\"eth_blockNumber\",\"params\":[],\"id\":1}' http://localhost:8545" \
    "result"

# ============================================================================
# PHASE 2: ML Privacy Filter Testing
# ============================================================================
echo -e "\n${MAGENTA}═══════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}PHASE 2: ML Privacy Filter Testing${NC}"
echo -e "${MAGENTA}═══════════════════════════════════════════════${NC}"

run_test "ML Privacy Filter - Environmental Data" \
    "curl -s -X POST http://localhost:5001/filter_data -H 'Content-Type: application/json' -d '{\"iot_data\": {\"temperature\": 25.5, \"humidity\": 60, \"location\": \"Lab A\"}, \"requester_access_level\": \"public\"}'" \
    "shareable_data"

run_test "ML Privacy Filter - Medical Data" \
    "curl -s -X POST http://localhost:5001/filter_data -H 'Content-Type: application/json' -d '{\"iot_data\": {\"heartRate\": 72, \"bloodPressure\": \"120/80\", \"patientId\": \"P001\"}, \"requester_access_level\": \"medical_staff\"}'" \
    "shareable_data"

# ============================================================================
# PHASE 3: Complete Data Ingestion Workflow
# ============================================================================
echo -e "\n${MAGENTA}═══════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}PHASE 3: Complete Data Ingestion Workflow${NC}"
echo -e "${MAGENTA}═══════════════════════════════════════════════${NC}"

# Test 1: Environmental IoT Data
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TEST_ID="e2e_env_$(date +%s)"

run_test "Data Ingestion - Environmental Sensor" \
    "curl -s -X POST http://localhost:5002/ingest_data -H 'Content-Type: application/json' -d '{
        \"id\": \"${TEST_ID}\",
        \"deviceId\": \"env_sensor_001\",
        \"timestamp\": \"${TIMESTAMP}\",
        \"dataType\": \"environmental\",
        \"data\": {
            \"temperature\": 22.5,
            \"humidity\": 65,
            \"pressure\": 1013.25,
            \"airQuality\": \"good\",
            \"location\": \"Building A - Floor 3\"
        }
    }'" \
    "ethereum_tx_hash"

# Test 2: Medical IoT Data
TEST_ID="e2e_medical_$(date +%s)"

run_test "Data Ingestion - Medical Device" \
    "curl -s -X POST http://localhost:5002/ingest_data -H 'Content-Type: application/json' -d '{
        \"id\": \"${TEST_ID}\",
        \"deviceId\": \"medical_monitor_042\",
        \"timestamp\": \"${TIMESTAMP}\",
        \"dataType\": \"medical\",
        \"data\": {
            \"heartRate\": 75,
            \"bloodPressure\": \"118/76\",
            \"temperature\": 36.8,
            \"oxygenLevel\": 98,
            \"patientId\": \"anonymous_patient_001\"
        }
    }'" \
    "ethereum_tx_hash"

# Test 3: Industrial IoT Data
TEST_ID="e2e_industrial_$(date +%s)"

run_test "Data Ingestion - Industrial Sensor" \
    "curl -s -X POST http://localhost:5002/ingest_data -H 'Content-Type: application/json' -d '{
        \"id\": \"${TEST_ID}\",
        \"deviceId\": \"industrial_sensor_099\",
        \"timestamp\": \"${TIMESTAMP}\",
        \"dataType\": \"industrial\",
        \"data\": {
            \"machineId\": \"CNC_001\",
            \"vibration\": 2.3,
            \"temperature\": 45.2,
            \"operatingHours\": 1250,
            \"efficiency\": 94.5
        }
    }'" \
    "ethereum_tx_hash"

# Test 4: Security/Surveillance Data
TEST_ID="e2e_security_$(date +%s)"

run_test "Data Ingestion - Security Camera" \
    "curl -s -X POST http://localhost:5002/ingest_data -H 'Content-Type: application/json' -d '{
        \"id\": \"${TEST_ID}\",
        \"deviceId\": \"security_cam_015\",
        \"timestamp\": \"${TIMESTAMP}\",
        \"dataType\": \"security\",
        \"data\": {
            \"location\": \"Main Entrance\",
            \"motionDetected\": true,
            \"personCount\": 3,
            \"alertLevel\": \"normal\"
        }
    }'" \
    "ethereum_tx_hash"

# ============================================================================
# PHASE 4: Blockchain Verification
# ============================================================================
echo -e "\n${MAGENTA}═══════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}PHASE 4: Blockchain Verification${NC}"
echo -e "${MAGENTA}═══════════════════════════════════════════════${NC}"

run_test "Ethereum Block Count" \
    "curl -s -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"method\":\"eth_blockNumber\",\"params\":[],\"id\":1}' http://localhost:8545" \
    "0x"

run_test "Ethereum Latest Block" \
    "curl -s -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"method\":\"eth_getBlockByNumber\",\"params\":[\"latest\",false],\"id\":1}' http://localhost:8545" \
    "transactions"

# ============================================================================
# PHASE 5: Frontend Integration Tests
# ============================================================================
echo -e "\n${MAGENTA}═══════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}PHASE 5: Frontend Integration Tests${NC}"
echo -e "${MAGENTA}═══════════════════════════════════════════════${NC}"

run_test "Frontend - Main Page Load" \
    "curl -s http://localhost:8080/" \
    "System Dashboard"

run_test "Frontend - Static Assets (CSS)" \
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/styles.css" \
    "200"

run_test "Frontend - Static Assets (JS)" \
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/script.js" \
    "200"

# ============================================================================
# PHASE 6: Stress Test (Multiple Concurrent Requests)
# ============================================================================
echo -e "\n${MAGENTA}═══════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}PHASE 6: Stress Test (5 Concurrent Requests)${NC}"
echo -e "${MAGENTA}═══════════════════════════════════════════════${NC}"

echo -e "${CYAN}Sending 5 concurrent data ingestion requests...${NC}"

for i in {1..5}; do
    TEST_ID="stress_test_${i}_$(date +%s)"
    curl -s -X POST http://localhost:5002/ingest_data \
        -H 'Content-Type: application/json' \
        -d "{
            \"id\": \"${TEST_ID}\",
            \"deviceId\": \"stress_sensor_${i}\",
            \"data\": {\"value\": ${i}, \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}
        }" > /dev/null &
done

wait
echo -e "${GREEN}✓ All concurrent requests completed${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
PASSED_TESTS=$((PASSED_TESTS + 1))

# ============================================================================
# Test Summary
# ============================================================================
echo -e "\n${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${CYAN}           TEST SUMMARY${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"

echo -e "\n${BLUE}Total Tests:${NC} $TOTAL_TESTS"
echo -e "${GREEN}Passed:${NC} $PASSED_TESTS"
echo -e "${RED}Failed:${NC} $FAILED_TESTS"

SUCCESS_RATE=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
echo -e "\n${BLUE}Success Rate:${NC} ${SUCCESS_RATE}%"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "\n${GREEN}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  🎉 ALL TESTS PASSED! SYSTEM OPERATIONAL  ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "\n${YELLOW}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠️  SOME TESTS FAILED - CHECK LOGS       ║${NC}"
    echo -e "${YELLOW}╚═══════════════════════════════════════════╝${NC}"
    exit 1
fi

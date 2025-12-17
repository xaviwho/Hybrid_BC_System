#!/bin/bash

# Interactive Testing Script
# Use this while testing the frontend to understand what's happening

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m'

clear

echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Interactive Testing - Understanding the System       ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Menu
while true; do
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}What would you like to test?${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${GREEN}1${NC} - Check System Status (Are all services running?)"
    echo -e "  ${GREEN}2${NC} - Submit Medical Data (See privacy protection)"
    echo -e "  ${GREEN}3${NC} - Submit Environmental Data (See public sharing)"
    echo -e "  ${GREEN}4${NC} - Submit Industrial Data (See trade secret protection)"
    echo -e "  ${GREEN}5${NC} - View Recent Blockchain Transactions"
    echo -e "  ${GREEN}6${NC} - Test ML Privacy Filter Directly"
    echo -e "  ${GREEN}7${NC} - Compare Public vs Private Data"
    echo -e "  ${GREEN}8${NC} - Run Full E2E Test Suite"
    echo -e "  ${GREEN}9${NC} - Watch Live Logs"
    echo -e "  ${GREEN}0${NC} - Exit"
    echo ""
    echo -ne "${YELLOW}Enter your choice: ${NC}"
    read choice

    case $choice in
        1)
            echo -e "\n${CYAN}Checking System Status...${NC}\n"
            
            echo -e "${BLUE}Service Health Checks:${NC}"
            
            # Orchestrator
            if curl -s http://localhost:5002/health | grep -q "healthy"; then
                echo -e "  ${GREEN}✓${NC} Orchestrator: Online"
            else
                echo -e "  ${YELLOW}✗${NC} Orchestrator: Offline"
            fi
            
            # ML Gateway
            if curl -s http://localhost:5000/health | grep -q "ok"; then
                echo -e "  ${GREEN}✓${NC} ML Gateway: Online"
            else
                echo -e "  ${YELLOW}✗${NC} ML Gateway: Offline"
            fi
            
            # ML Privacy
            if curl -s http://localhost:5001/health | grep -q "ok"; then
                echo -e "  ${GREEN}✓${NC} ML Privacy Filter: Online"
            else
                echo -e "  ${YELLOW}✗${NC} ML Privacy Filter: Offline"
            fi
            
            # Frontend
            if curl -s http://localhost:8080/health | grep -q "ok"; then
                echo -e "  ${GREEN}✓${NC} Frontend: Online"
            else
                echo -e "  ${YELLOW}✗${NC} Frontend: Offline"
            fi
            
            # Ethereum
            if curl -s -X POST http://localhost:8545 -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' | grep -q "result"; then
                echo -e "  ${GREEN}✓${NC} Ethereum: Online"
            else
                echo -e "  ${YELLOW}✗${NC} Ethereum: Offline"
            fi
            
            echo ""
            ;;
            
        2)
            echo -e "\n${CYAN}Submitting Medical Data...${NC}"
            echo -e "${YELLOW}This demonstrates privacy protection for sensitive health data${NC}\n"
            
            RESPONSE=$(curl -s -X POST http://localhost:5002/ingest_data \
              -H "Content-Type: application/json" \
              -d '{
                "id": "medical_test_'$(date +%s)'",
                "deviceId": "heart_monitor_001",
                "dataType": "medical",
                "data": {
                  "heartRate": 72,
                  "bloodPressure": "120/80",
                  "patientId": "CONFIDENTIAL_P12345",
                  "diagnosis": "Normal checkup"
                }
              }')
            
            echo -e "${GREEN}Response:${NC}"
            echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
            
            echo -e "\n${BLUE}What happened:${NC}"
            echo -e "  • ML detected MEDICAL data (high sensitivity)"
            echo -e "  • Sensitive fields (patientId, diagnosis) stored PRIVATELY"
            echo -e "  • Only metadata stored PUBLICLY on Ethereum"
            echo -e "  • Transaction hash proves data integrity"
            echo ""
            ;;
            
        3)
            echo -e "\n${CYAN}Submitting Environmental Data...${NC}"
            echo -e "${YELLOW}This demonstrates public data sharing for transparency${NC}\n"
            
            RESPONSE=$(curl -s -X POST http://localhost:5002/ingest_data \
              -H "Content-Type: application/json" \
              -d '{
                "id": "env_test_'$(date +%s)'",
                "deviceId": "weather_station_01",
                "dataType": "environmental",
                "data": {
                  "temperature": 22.5,
                  "humidity": 65,
                  "airQuality": "good",
                  "pm25": 12
                }
              }')
            
            echo -e "${GREEN}Response:${NC}"
            echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
            
            echo -e "\n${BLUE}What happened:${NC}"
            echo -e "  • ML detected ENVIRONMENTAL data (low-medium sensitivity)"
            echo -e "  • Most data safe to share publicly"
            echo -e "  • Useful for citizen awareness and research"
            echo -e "  • Blockchain ensures data authenticity"
            echo ""
            ;;
            
        4)
            echo -e "\n${CYAN}Submitting Industrial Data...${NC}"
            echo -e "${YELLOW}This demonstrates trade secret protection${NC}\n"
            
            RESPONSE=$(curl -s -X POST http://localhost:5002/ingest_data \
              -H "Content-Type: application/json" \
              -d '{
                "id": "industrial_test_'$(date +%s)'",
                "deviceId": "cnc_machine_05",
                "dataType": "industrial",
                "data": {
                  "productQuality": "Grade A",
                  "defectRate": 0.02,
                  "proprietaryProcess": "SECRET_FORMULA_X"
                }
              }')
            
            echo -e "${GREEN}Response:${NC}"
            echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
            
            echo -e "\n${BLUE}What happened:${NC}"
            echo -e "  • ML detected INDUSTRIAL data"
            echo -e "  • Quality metrics shared publicly (customer trust)"
            echo -e "  • Proprietary processes kept private (competitive advantage)"
            echo -e "  • Blockchain proves quality claims"
            echo ""
            ;;
            
        5)
            echo -e "\n${CYAN}Recent Blockchain Transactions...${NC}\n"
            
            BLOCK_NUM=$(curl -s -X POST http://localhost:8545 \
              -H "Content-Type: application/json" \
              -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
              | grep -o '"result":"[^"]*' | cut -d'"' -f4)
            
            DECIMAL=$((16#${BLOCK_NUM:2}))
            
            echo -e "${GREEN}Current Block Number:${NC} $DECIMAL"
            echo -e "${GREEN}Total Transactions:${NC} $DECIMAL (approximately)"
            
            echo -e "\n${BLUE}Latest Block Details:${NC}"
            curl -s -X POST http://localhost:8545 \
              -H "Content-Type: application/json" \
              -d '{"jsonrpc":"2.0","method":"eth_getBlockByNumber","params":["latest",false],"id":1}' \
              | python3 -m json.tool 2>/dev/null | head -30
            
            echo ""
            ;;
            
        6)
            echo -e "\n${CYAN}Testing ML Privacy Filter Directly...${NC}\n"
            
            echo -e "${YELLOW}Sending test data to privacy filter...${NC}"
            
            RESPONSE=$(curl -s -X POST http://localhost:5001/filter_data \
              -H "Content-Type: application/json" \
              -d '{
                "iot_data": {
                  "temperature": 25,
                  "patientId": "P12345",
                  "heartRate": 72,
                  "location": "Room 101"
                },
                "requester_access_level": "public"
              }')
            
            echo -e "${GREEN}Filter Response:${NC}"
            echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
            
            echo -e "\n${BLUE}Notice:${NC}"
            echo -e "  • Sensitive fields are identified"
            echo -e "  • Public version has redacted data"
            echo -e "  • This is automatic - no manual configuration!"
            echo ""
            ;;
            
        7)
            echo -e "\n${CYAN}Comparing Public vs Private Data Storage...${NC}\n"
            
            echo -e "${BLUE}Scenario:${NC} Medical device sends patient data"
            echo -e ""
            echo -e "${YELLOW}Original Data (from IoT device):${NC}"
            cat << 'EOF'
{
  "heartRate": 72,
  "bloodPressure": "120/80",
  "temperature": 36.7,
  "patientId": "P12345",
  "patientName": "John Doe",
  "diagnosis": "Recovering well"
}
EOF
            
            echo -e "\n${GREEN}After ML Privacy Filter:${NC}"
            echo -e ""
            echo -e "${MAGENTA}PRIVATE Blockchain (Hyperledger Fabric):${NC}"
            echo -e "  ✓ Full data including all sensitive fields"
            echo -e "  ✓ Only accessible to authorized medical staff"
            echo -e "  ✓ Used for treatment and internal records"
            echo -e ""
            echo -e "${MAGENTA}PUBLIC Blockchain (Ethereum):${NC}"
            cat << 'EOF'
{
  "dataType": "medical",
  "deviceId": "heart_monitor_001",
  "timestamp": "2025-10-21T06:47:39Z",
  "fabricTxId": "abc123...",
  "dataHash": "0x..."
}
EOF
            echo -e "  ✓ No patient identity"
            echo -e "  ✓ Anyone can verify data exists"
            echo -e "  ✓ Useful for research and statistics"
            echo ""
            ;;
            
        8)
            echo -e "\n${CYAN}Running Full E2E Test Suite...${NC}\n"
            ./test-e2e-workflow.sh
            ;;
            
        9)
            echo -e "\n${CYAN}Live Log Monitoring${NC}"
            echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
            tail -f logs/orchestrator.log
            ;;
            
        0)
            echo -e "\n${GREEN}Thank you for testing!${NC}\n"
            exit 0
            ;;
            
        *)
            echo -e "\n${YELLOW}Invalid choice. Please try again.${NC}\n"
            ;;
    esac
    
    echo -e "${YELLOW}Press ENTER to continue...${NC}"
    read
    clear
    
    echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Interactive Testing - Understanding the System       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
done

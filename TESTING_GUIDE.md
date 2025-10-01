# 🧪 Hybrid Blockchain IoT System - Testing Guide

## Overview
This guide provides comprehensive end-to-end testing procedures for the Hybrid Blockchain IoT System, covering all components from data ingestion to blockchain storage.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Automated E2E Tests](#automated-e2e-tests)
3. [Manual Testing Procedures](#manual-testing-procedures)
4. [Frontend Testing](#frontend-testing)
5. [Performance Testing](#performance-testing)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- All services running (Fabric, Ethereum, ML Services, Orchestrator, Frontend)
- curl installed for API testing
- Web browser for frontend testing

### Start the System
```bash
./start-system.sh
```

### Verify All Services
```bash
./start-system.sh status
```

Expected output: All services showing ✓ (green checkmark)

---

## Automated E2E Tests

### Run Complete Test Suite
```bash
chmod +x test-e2e-workflow.sh
./test-e2e-workflow.sh
```

### What the E2E Test Covers:
1. **Service Health Checks** - Verifies all services are responding
2. **ML Privacy Filter** - Tests data sensitivity analysis
3. **Data Ingestion** - Tests complete workflow for 4 data types:
   - Environmental sensors
   - Medical devices
   - Industrial IoT
   - Security cameras
4. **Blockchain Verification** - Confirms Ethereum transactions
5. **Frontend Integration** - Tests UI endpoints
6. **Stress Test** - 5 concurrent requests

### Expected Results:
- **Success Rate**: 100%
- **All Tests**: Should show ✓ PASSED
- **Ethereum TX Hashes**: Should be returned for each ingestion

---

## Manual Testing Procedures

### Test 1: Service Health Checks

#### Orchestrator
```bash
curl http://localhost:5002/health
```
**Expected**: `{"status": "healthy", "ethereum_connected": true}`

#### ML Gateway
```bash
curl http://localhost:5000/health
```
**Expected**: `{"status": "ok"}`

#### ML Privacy Filter
```bash
curl http://localhost:5001/health
```
**Expected**: `{"status": "ok"}`

#### Frontend
```bash
curl http://localhost:8080/health
```
**Expected**: `{"status": "ok", "message": "Frontend server is running"}`

---

### Test 2: ML Privacy Filter

#### Test Environmental Data
```bash
curl -X POST http://localhost:5001/filter_data \
  -H "Content-Type: application/json" \
  -d '{
    "iot_data": {
      "temperature": 25.5,
      "humidity": 60,
      "location": "Lab A"
    }
  }'
```

**Expected Response**:
```json
{
  "sensitivity_level": "low",
  "shareable_data": {
    "temperature": 25.5,
    "humidity": 60
  },
  "redacted_fields": ["location"]
}
```

#### Test Medical Data (High Sensitivity)
```bash
curl -X POST http://localhost:5001/filter_data \
  -H "Content-Type: application/json" \
  -d '{
    "iot_data": {
      "heartRate": 72,
      "bloodPressure": "120/80",
      "patientId": "P001"
    }
  }'
```

**Expected**: Higher sensitivity level, more fields redacted

---

### Test 3: Complete Data Ingestion Workflow

#### Environmental Sensor Data
```bash
curl -X POST http://localhost:5002/ingest_data \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test_env_001",
    "deviceId": "env_sensor_001",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "dataType": "environmental",
    "data": {
      "temperature": 22.5,
      "humidity": 65,
      "pressure": 1013.25,
      "airQuality": "good"
    }
  }'
```

**Expected Response**:
```json
{
  "status": "success",
  "data_id": "test_env_001",
  "ethereum_tx_hash": "0x...",
  "fabric_tx_id": "...",
  "message": "Data processed and registered on the blockchain."
}
```

#### Medical Device Data
```bash
curl -X POST http://localhost:5002/ingest_data \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test_medical_001",
    "deviceId": "medical_monitor_042",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "dataType": "medical",
    "data": {
      "heartRate": 75,
      "bloodPressure": "118/76",
      "temperature": 36.8,
      "oxygenLevel": 98
    }
  }'
```

#### Industrial IoT Data
```bash
curl -X POST http://localhost:5002/ingest_data \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test_industrial_001",
    "deviceId": "industrial_sensor_099",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "dataType": "industrial",
    "data": {
      "machineId": "CNC_001",
      "vibration": 2.3,
      "temperature": 45.2,
      "efficiency": 94.5
    }
  }'
```

---

### Test 4: Blockchain Verification

#### Check Ethereum Block Number
```bash
curl -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "eth_blockNumber",
    "params": [],
    "id": 1
  }'
```

**Expected**: Returns current block number in hex

#### Get Latest Block
```bash
curl -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "eth_getBlockByNumber",
    "params": ["latest", false],
    "id": 1
  }'
```

**Expected**: Returns block details with transactions

---

## Frontend Testing

### Access the Dashboard
1. Open browser: `http://localhost:8080`
2. Verify all status cards show "ONLINE"
3. Check Data Flow Architecture diagram displays

### Test Data Ingestion via UI

#### Step 1: Navigate to Data Ingestion
- Click "Data Ingestion" in navigation menu
- Form should be visible

#### Step 2: Use Quick Test Data
- Click "Environmental" button
- Form should auto-fill with sample data
- Verify preview updates

#### Step 3: Submit Data
- Click "Submit Data" button
- Wait for processing (spinner should show)
- Verify success message appears
- Check transaction hash is displayed

#### Step 4: Verify in Dashboard
- Return to Dashboard
- Check "Data Processed" counter increased
- Check "Blockchain Txs" counter increased

### Test All Data Types
Repeat the above process for:
- ✅ Environmental
- ✅ Medical
- ✅ Industrial
- ✅ Security

### Test Privacy Controls
1. Navigate to "Privacy Controls" tab
2. Adjust ML Gateway threshold slider
3. Click "Test Gateway" button
4. Verify response message

### Test Blockchain Section
1. Navigate to "Blockchain" tab
2. Verify Hyperledger Fabric status
3. Verify Ethereum status
4. Check transaction history displays

---

## Performance Testing

### Concurrent Request Test
```bash
# Send 10 concurrent requests
for i in {1..10}; do
  curl -X POST http://localhost:5002/ingest_data \
    -H "Content-Type: application/json" \
    -d "{
      \"id\": \"perf_test_${i}\",
      \"deviceId\": \"perf_sensor_${i}\",
      \"data\": {\"value\": ${i}}
    }" &
done
wait
```

**Expected**: All requests complete successfully within 10 seconds

### Load Test with Apache Bench (if installed)
```bash
ab -n 100 -c 10 http://localhost:5002/health
```

**Expected**: 
- Requests per second: > 50
- Failed requests: 0

---

## Troubleshooting

### Test Failures

#### Service Not Responding
```bash
# Check service logs
tail -f logs/orchestrator.log
tail -f logs/frontend.log
```

#### Ethereum Connection Failed
```bash
# Verify Ganache is running
docker ps | grep ganache

# Restart Ganache
docker restart ganache-cli
```

#### ML Services Not Responding
```bash
# Check ML service logs
docker logs ml-gateway
docker logs ml-privacy

# Restart ML services
docker-compose -f docker-compose-hybrid.yml restart ml-gateway ml-privacy
```

### Common Issues

#### Port Already in Use
```bash
# Find process using port
lsof -i :5002

# Kill process
kill -9 <PID>
```

#### Frontend Not Loading
```bash
# Check if port 8080 is available
nc -z localhost 8080

# Restart frontend
cd frontend && node server.js
```

---

## Test Data Examples

### Environmental Sensor
```json
{
  "id": "env_001",
  "deviceId": "env_sensor_001",
  "dataType": "environmental",
  "data": {
    "temperature": 22.5,
    "humidity": 65,
    "pressure": 1013.25,
    "airQuality": "good",
    "co2Level": 400
  }
}
```

### Medical Device
```json
{
  "id": "med_001",
  "deviceId": "medical_monitor_042",
  "dataType": "medical",
  "data": {
    "heartRate": 75,
    "bloodPressure": "118/76",
    "temperature": 36.8,
    "oxygenLevel": 98,
    "patientId": "anonymous_001"
  }
}
```

### Industrial IoT
```json
{
  "id": "ind_001",
  "deviceId": "industrial_sensor_099",
  "dataType": "industrial",
  "data": {
    "machineId": "CNC_001",
    "vibration": 2.3,
    "temperature": 45.2,
    "operatingHours": 1250,
    "efficiency": 94.5
  }
}
```

---

## Success Criteria

### System is Working Correctly When:
- ✅ All automated tests pass (100% success rate)
- ✅ All services respond to health checks
- ✅ Data ingestion returns Ethereum transaction hash
- ✅ Frontend displays real-time status updates
- ✅ Privacy filter processes data correctly
- ✅ Blockchain transactions are recorded
- ✅ No errors in service logs

---

## Next Steps

After successful testing:
1. **Monitor Performance**: Check logs regularly
2. **Scale Testing**: Increase concurrent requests
3. **Security Audit**: Review access controls
4. **Documentation**: Update based on findings
5. **Production Deployment**: Prepare deployment checklist

---

## Support

For issues or questions:
- Check `TROUBLESHOOTING.md`
- Review service logs in `logs/` directory
- Run diagnostic: `./diagnose-startup.sh`

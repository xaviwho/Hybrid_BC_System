# Hybrid Blockchain System - Troubleshooting Guide

## Common Issues and Solutions

### 1. Hyperledger Fabric Issues

#### Issue: "Failed to start the network"
**Symptoms:**
- Network.sh fails with permission errors
- Docker containers don't start

**Solutions:**
```bash
# Clean up existing containers and volumes
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker volume prune -f
docker network prune -f

# Ensure Docker daemon is running
sudo service docker start  # On Linux/WSL

# Re-run the deployment
./deploy-hybrid-fabric.sh
```

#### Issue: "Chaincode installation failed"
**Symptoms:**
- Package ID not found
- Endorsement failure

**Solutions:**
```bash
# Check if chaincode source exists
ls -la simple-iot-chaincode/

# Ensure Go dependencies are vendored
cd simple-iot-chaincode
go mod vendor
cd ..

# Retry deployment
./deploy-hybrid-fabric.sh
```

#### Issue: "Channel 'hiot' already exists"
**Symptoms:**
- Channel creation fails
- "Channel already exists" error

**Solution:**
This is usually fine - the channel is already created. Continue with chaincode deployment.

### 2. Ethereum/Ganache Issues

#### Issue: "Connection refused on port 8545"
**Symptoms:**
- Orchestrator can't connect to Ganache
- Web3 connection errors

**Solutions:**
```bash
# Check if Ganache is running
ps aux | grep ganache

# Kill existing Ganache process
pkill -f ganache

# Restart Ganache with correct settings
cd blockchain/setup/ethereum
npx ganache --host 0.0.0.0 --accounts 10 --deterministic
```

#### Issue: "Contract not deployed"
**Symptoms:**
- IoTDataRegistry address is undefined
- Truffle migration fails

**Solutions:**
```bash
cd blockchain/setup/ethereum

# Clean build artifacts
rm -rf build/

# Recompile and deploy
npx truffle compile
npx truffle migrate --network development --reset
```

### 3. ML Services Issues

#### Issue: "ML services not starting"
**Symptoms:**
- Ports 5000/5001 not accessible
- Docker container exits immediately

**Solutions:**
```bash
# Check Docker logs
docker logs ml-gateway
docker logs ml-privacy

# Rebuild containers
docker-compose -f docker-compose-hybrid.yml build ml-gateway ml-privacy

# Start with verbose output
docker-compose -f docker-compose-hybrid.yml up ml-gateway ml-privacy
```

#### Issue: "Sensitivity model not found"
**Symptoms:**
- FileNotFoundError for sensitivity_model.joblib
- ML service returns 500 error

**Solution:**
The services will auto-create a dummy model on first run. This is expected behavior.

### 4. Orchestrator Issues

#### Issue: "fabric_sdk_py not found"
**Symptoms:**
- ImportError when starting orchestrator
- Module not found error

**Solutions:**
```bash
cd orchestrator

# Create/activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# OR
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Issue: "Connection to Fabric failed"
**Symptoms:**
- Can't connect to peer
- Certificate errors

**Solutions:**
1. Check connection profile matches your network:
```bash
# Verify peer is running
docker ps | grep peer0.org1

# Check TLS certificates exist
ls blockchain/setup/hyperledger/fabric-samples/test-network/organizations/
```

2. Update connection-org1.json with correct paths and certificates

### 5. Integration Issues

#### Issue: "End-to-end test fails"
**Symptoms:**
- Data not stored in Fabric
- Ethereum transaction fails

**Solutions:**
1. Test each component individually:
```bash
# Test Fabric
docker exec cli peer chaincode query -C hiot -n iot-data -c '{"function":"GetAllIoTData","Args":[]}'

# Test Ethereum
curl -X POST -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  http://localhost:8545

# Test ML Gateway
curl http://localhost:5000/health

# Test ML Privacy Filter
curl http://localhost:5001/health

# Test Orchestrator
curl http://localhost:5002/health
```

2. Check logs for specific errors:
```bash
tail -f logs/orchestrator.log
tail -f logs/fabric-deployment.log
tail -f logs/ganache.log
```

### 6. WSL-Specific Issues (Windows)

#### Issue: "Cannot connect to Docker daemon"
**Solutions:**
```bash
# Ensure Docker Desktop is running and WSL integration is enabled
# In Docker Desktop: Settings > Resources > WSL Integration

# Restart WSL
wsl --shutdown
# Then reopen WSL terminal
```

#### Issue: "Path translation issues"
**Solutions:**
- Use `/mnt/c/` instead of `C:\` in WSL
- Ensure scripts have Unix line endings:
```bash
dos2unix *.sh
```

## Quick Diagnostic Commands

```bash
# Check all services status
./start-complete-system.sh

# View all Docker containers
docker ps -a

# Check network connectivity
nc -zv localhost 7051  # Fabric peer
nc -zv localhost 8545  # Ganache
nc -zv localhost 5000  # ML Gateway
nc -zv localhost 5001  # ML Privacy
nc -zv localhost 5002  # Orchestrator

# View recent logs
tail -n 50 logs/*.log

# Clean everything and start fresh
./stop-hybrid-system.sh
docker system prune -a --volumes
./start-complete-system.sh
```

## Getting Help

If issues persist:

1. Check the detailed logs in the `logs/` directory
2. Verify all prerequisites are installed:
   - Docker & Docker Compose
   - Node.js & npm
   - Python 3.8+
   - Go 1.19+ (for chaincode)

3. Ensure sufficient system resources:
   - At least 8GB RAM
   - 10GB free disk space
   - Stable internet connection (for downloading Docker images)

4. Review the system architecture in README.md
5. Check that all configuration files are consistent (channel names, ports, etc.)

# Fixing Hyperledger Fabric Setup

## Current Issues
1. Channel name mismatch (hiot vs medicalchannel)
2. Chaincode path issues
3. Network connectivity problems
4. Complex dependency on fabric-samples

## Step-by-Step Fix

### 1. Simplify the Network Setup

Instead of using the complex fabric-samples test-network, let's create a minimal Fabric network:

```bash
# Stop any existing Fabric containers
docker stop $(docker ps -aq --filter name=hyperledger)
docker rm $(docker ps -aq --filter name=hyperledger)
docker stop $(docker ps -aq --filter name=hybrid)
docker rm $(docker ps -aq --filter name=hybrid)

# Clean up volumes
docker volume prune -f
```

### 2. Fix Configuration Consistency

Update the following files to use consistent channel name:

**orchestrator/orchestrator.py** - Line 95:
```python
FABRIC_CHANNEL_NAME = os.getenv('FABRIC_CHANNEL_NAME', 'hiot')  # Changed from 'medicalchannel'
```

### 3. Create Simple Docker-Based Fabric Network

Create a new file `docker-compose-fabric-simple.yml`:

```yaml
version: '3.7'

networks:
  fabric_test:
    name: fabric_test

services:
  orderer.example.com:
    container_name: orderer.example.com
    image: hyperledger/fabric-orderer:2.5
    environment:
      - FABRIC_LOGGING_SPEC=INFO
      - ORDERER_GENERAL_LISTENADDRESS=0.0.0.0
      - ORDERER_GENERAL_LISTENPORT=7050
      - ORDERER_GENERAL_LOCALMSPID=OrdererMSP
      - ORDERER_GENERAL_LOCALMSPDIR=/var/hyperledger/orderer/msp
      - ORDERER_GENERAL_TLS_ENABLED=false
      - ORDERER_GENERAL_BOOTSTRAPMETHOD=file
      - ORDERER_GENERAL_BOOTSTRAPFILE=/var/hyperledger/orderer/orderer.genesis.block
    working_dir: /opt/gopath/src/github.com/hyperledger/fabric
    command: orderer
    volumes:
      - ./blockchain/setup/hyperledger/config/genesis.block:/var/hyperledger/orderer/orderer.genesis.block
      - ./blockchain/setup/hyperledger/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/msp:/var/hyperledger/orderer/msp
    ports:
      - 7050:7050
    networks:
      - fabric_test

  peer0.org1.example.com:
    container_name: peer0.org1.example.com
    image: hyperledger/fabric-peer:2.5
    environment:
      - CORE_VM_ENDPOINT=unix:///host/var/run/docker.sock
      - CORE_PEER_ID=peer0.org1.example.com
      - CORE_PEER_ADDRESS=peer0.org1.example.com:7051
      - CORE_PEER_LISTENADDRESS=0.0.0.0:7051
      - CORE_PEER_CHAINCODEADDRESS=peer0.org1.example.com:7052
      - CORE_PEER_CHAINCODELISTENADDRESS=0.0.0.0:7052
      - CORE_PEER_GOSSIP_BOOTSTRAP=peer0.org1.example.com:7051
      - CORE_PEER_GOSSIP_EXTERNALENDPOINT=peer0.org1.example.com:7051
      - CORE_PEER_LOCALMSPID=Org1MSP
      - CORE_PEER_MSPCONFIGPATH=/etc/hyperledger/fabric/msp
      - CORE_PEER_TLS_ENABLED=false
      - FABRIC_LOGGING_SPEC=INFO
    volumes:
      - /var/run/docker.sock:/host/var/run/docker.sock
      - ./blockchain/setup/hyperledger/crypto-config/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/msp:/etc/hyperledger/fabric/msp
    working_dir: /opt/gopath/src/github.com/hyperledger/fabric/peer
    command: peer node start
    ports:
      - 7051:7051
    networks:
      - fabric_test
    depends_on:
      - orderer.example.com

  cli:
    container_name: cli
    image: hyperledger/fabric-tools:2.5
    tty: true
    stdin_open: true
    environment:
      - GOPATH=/opt/gopath
      - CORE_VM_ENDPOINT=unix:///host/var/run/docker.sock
      - FABRIC_LOGGING_SPEC=INFO
      - CORE_PEER_ID=cli
      - CORE_PEER_ADDRESS=peer0.org1.example.com:7051
      - CORE_PEER_LOCALMSPID=Org1MSP
      - CORE_PEER_TLS_ENABLED=false
      - CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
    working_dir: /opt/gopath/src/github.com/hyperledger/fabric/peer
    command: /bin/bash
    volumes:
      - /var/run/docker.sock:/host/var/run/docker.sock
      - ./simple-iot-chaincode:/opt/gopath/src/github.com/chaincode
      - ./blockchain/setup/hyperledger/crypto-config:/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/
    networks:
      - fabric_test
    depends_on:
      - orderer.example.com
      - peer0.org1.example.com
```

### 4. Alternative: Use Mock Fabric for Development

Since Hyperledger Fabric is complex and you're frustrated with it, consider creating a mock service that simulates Fabric's behavior for development:

Create `mock-fabric-service.py`:

```python
from flask import Flask, request, jsonify
import json
import hashlib
from datetime import datetime

app = Flask(__name__)

# In-memory storage simulating Fabric ledger
ledger = {}

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mock-fabric"}), 200

@app.route('/store', methods=['POST'])
def store_data():
    """Simulates storing data on Fabric"""
    data = request.json
    data_id = data.get('id', hashlib.sha256(json.dumps(data).encode()).hexdigest()[:8])
    
    # Simulate Fabric storage
    ledger[data_id] = {
        'data': data,
        'timestamp': datetime.now().isoformat(),
        'transaction_id': f"tx_{hashlib.sha256(json.dumps(data).encode()).hexdigest()[:16]}"
    }
    
    return jsonify({
        'status': 'success',
        'data_id': data_id,
        'transaction_id': ledger[data_id]['transaction_id']
    }), 200

@app.route('/query/<data_id>', methods=['GET'])
def query_data(data_id):
    """Simulates querying data from Fabric"""
    if data_id in ledger:
        return jsonify(ledger[data_id]), 200
    return jsonify({'error': 'Data not found'}), 404

@app.route('/query_all', methods=['GET'])
def query_all():
    """Returns all data in the ledger"""
    return jsonify(list(ledger.values())), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7054, debug=True)
```

### 5. Update Orchestrator to Use Mock Service (for testing)

Update `orchestrator/orchestrator.py` to optionally use the mock service:

```python
# Add environment variable to switch between real and mock Fabric
USE_MOCK_FABRIC = os.getenv('USE_MOCK_FABRIC', 'true').lower() == 'true'

if USE_MOCK_FABRIC:
    FABRIC_MOCK_URL = "http://localhost:7054"
    
    def store_on_fabric_mock(data):
        """Store data on mock Fabric service"""
        response = requests.post(f"{FABRIC_MOCK_URL}/store", json=data)
        return response.json()
```

## Recommended Approach

Given your frustration with Hyperledger Fabric, I recommend:

1. **Start with the Mock Service**: Get the entire system working end-to-end with the mock Fabric service
2. **Test the Complete Workflow**: Ensure ML services, Ethereum, and Orchestrator work correctly
3. **Return to Fabric Later**: Once everything else works, tackle Fabric setup with a clearer mind

## Quick Start Commands

```bash
# 1. Start Mock Fabric Service
python mock-fabric-service.py

# 2. Start Ethereum (Ganache)
cd blockchain/setup/ethereum
npm install
npx ganache --host 0.0.0.0

# 3. Deploy Ethereum Contracts
npx truffle migrate --network development

# 4. Start ML Services
docker-compose -f docker-compose-hybrid.yml up ml-gateway ml-privacy

# 5. Start Orchestrator with Mock Fabric
export USE_MOCK_FABRIC=true
python orchestrator/orchestrator.py

# 6. Test the system
node test-end-to-end-workflow.js
```

This approach lets you make progress on the overall system while temporarily sidestepping the Hyperledger complexity.

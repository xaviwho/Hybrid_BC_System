# Hybrid Blockchain System - Complete Guide

## 🎯 Overview
A production-ready hybrid blockchain system combining Hyperledger Fabric (private) and Ethereum (public) with ML-powered privacy filtering for secure IoT data management.

## 🚀 Single Command Management

Everything is now managed through **one script**: `start-system.sh`

### Commands:
```bash
# First-time setup (only needed once)
./install-fabric-binaries.sh

# Start everything
./start-system.sh

# Check status
./start-system.sh status

# Stop everything
./start-system.sh stop

# Restart everything
./start-system.sh restart
```

## 📋 What Gets Started

The `start-system.sh` script automatically starts:

1. **Hyperledger Fabric Network**
   - Peer nodes, Orderer, CouchDB
   - Channel: `hiot`
   - Port: 7051

2. **Ethereum (Ganache)**
   - Local blockchain for development
   - Smart contracts auto-deployed
   - Port: 8545

3. **ML Services**
   - Gateway (Port 5000)
   - Privacy Filter (Port 5001)

4. **Orchestrator**
   - Central coordination service
   - Port: 5002

5. **Frontend** (if available)
   - Web interface
   - Port: 3000

## 🔄 System Workflow

```
IoT Device → Orchestrator → ML Privacy Filter
                ↓
        [Sensitive Data?]
           ↙        ↘
    Hyperledger   Ethereum
     (Private)    (Public)
```

## 🧪 Test the System

Once started, test with:

```bash
curl -X POST http://localhost:5002/ingest_data \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "test_001",
    "deviceId": "sensor_001",
    "data": {
      "temperature": 22.5,
      "humidity": 65,
      "location": "Lab A"
    }
  }'
```

## 📁 Clean File Structure

```
Hybrid_BC_System/
├── start-system.sh           # Main control script
├── install-fabric-binaries.sh # One-time Fabric setup
├── system-status.sh          # Quick status check
├── TROUBLESHOOTING.md        # Help guide
├── README.md                 # Project overview
├── blockchain/               # Blockchain components
├── ml/                      # ML services
├── orchestrator/            # Coordination service
└── logs/                    # System logs
```

## 🛠️ Troubleshooting

### If services don't start:
1. Check logs in `logs/` directory
2. Ensure Docker is running
3. Check port availability
4. Run `./start-system.sh status`

### Common Issues:
- **Port in use**: Stop conflicting services
- **Docker not running**: Start Docker Desktop
- **Permission denied**: Run `chmod +x start-system.sh`

## 🔒 Security Features

- **Data Segregation**: Sensitive data stays in private blockchain
- **ML Privacy Filter**: Automatic sensitivity detection
- **Access Control**: Smart contract-based permissions
- **Audit Trail**: Complete transaction history

## 📊 Monitoring

Check individual service health:
- Fabric: `docker logs peer0.org1.example.com`
- Ethereum: Check block number at http://localhost:8545
- ML Services: `curl http://localhost:5000/health`
- Orchestrator: `curl http://localhost:5002/health`

## 🚦 Production Deployment

For production:
1. Replace Ganache with actual Ethereum network
2. Configure proper TLS certificates for Fabric
3. Set up proper authentication for services
4. Use environment variables for configuration
5. Deploy ML services with proper scaling

## 📝 License

This system is designed for government/enterprise use with appropriate security measures.

---

**Note**: All unnecessary scripts have been removed. The system is now managed entirely through `start-system.sh` for simplicity and maintainability.

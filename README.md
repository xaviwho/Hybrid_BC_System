# Hybrid Blockchain System for IoT Data Management

##  Quick Start

This system combines Hyperledger Fabric (private blockchain) and Ethereum (public blockchain) with ML-powered privacy filtering for secure IoT data management.

### Start Everything with One Command:

```bash
# First time setup (install Fabric binaries)
./install-fabric-binaries.sh

# Start all services
./start-system.sh

# Check status
./start-system.sh status

# Stop all services
./start-system.sh stop

# Restart all services
./start-system.sh restart
```
## System Architecture

### Components Started by `start-system.sh`:

1. **Hyperledger Fabric** (Port 7051)
   - Private blockchain for sensitive data
   - Channel: `hiot`
   - Includes CouchDB for state database

2. **Ethereum/Ganache** (Port 8545)
   - Public blockchain for metadata
   - Smart Contract: `IoTDataRegistry`

3. **ML Services**
   - **Gateway** (Port 5000): Initial data filtering
   - **Privacy Filter** (Port 5001): Sensitivity analysis

4. **Orchestrator** (Port 5002)
   - Central coordination service
   - Manages workflow between all components

5. **Frontend** (Port 3000) - *Optional*
   - Web interface (if frontend/ directory exists)

## Test the System

Once all services are running, test the complete workflow:

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

## Workflow

1. **Data Ingestion**: IoT device sends data to Orchestrator
2. **ML Analysis**: Privacy Filter analyzes data sensitivity
3. **Data Segregation**: Sensitive data → Hyperledger Fabric, Metadata → Ethereum
4. **Access Control**: Public can query Ethereum for metadata, authorized users access Fabric

## Project Structure

```
Hybrid_BC_System/
├── data/                      # Sample IoT data and datasets
├── ml/                        # Machine learning components
│   ├── preprocessing/         # Data preprocessing modules
│   ├── classification/        # Data classification models
│   └── inference/             # Inference modules for real-time decisions
├── blockchain/
│   ├── private/               # Private blockchain implementation
│   ├── public/                # Public blockchain implementation
│   └── smart_contracts/       # Smart contracts for data access and management
├── quantum/                   # Quantum security components
│   ├── key_distribution/      # Quantum key distribution modules
│   └── encryption/            # Post-quantum cryptography implementation
├── api/                       # API layer for system interaction
├── config/                    # Configuration files
├── tests/                     # Test suites
└── docs/                      # Documentation
```

## Getting Started

[Installation and setup instructions will be added once the initial implementation is complete]

## License

[TBD]

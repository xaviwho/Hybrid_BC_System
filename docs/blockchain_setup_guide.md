# Blockchain Setup Guide for Hybrid Blockchain System

This guide provides detailed instructions for setting up both Hyperledger Fabric (private blockchain) and Ethereum (public blockchain) for your Hybrid Blockchain-based Incognito Data Sharing system.

## 1. Hyperledger Fabric Setup (Private Blockchain)

### Prerequisites

Before setting up Hyperledger Fabric, ensure you have the following prerequisites installed:

- **Docker Desktop for Windows** (https://www.docker.com/products/docker-desktop)
- **Git** (https://git-scm.com/downloads)
- **Go** version 1.14.x or higher (https://golang.org/dl/)
- **Node.js** and npm version 12.x or higher (https://nodejs.org/)
- **Python** version 3.7 or higher (https://www.python.org/downloads/)
- **Visual Studio Code** with Hyperledger Fabric extension (optional but recommended)

### Step 1: Download Fabric Samples and Binaries

1. Open PowerShell with administrator privileges
2. Create a directory for your Hyperledger setup:

```powershell
mkdir -p c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\hyperledger
cd c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\hyperledger
```

3. Download the Fabric samples and binaries:

```powershell
curl -sSL https://bit.ly/2ysbOFE | bash -s -- 2.2.0 1.4.9
```

This command will download:
- Fabric sample applications
- Fabric Docker images
- Fabric binaries (cryptogen, configtxgen, etc.)

### Step 2: Start a Test Network

1. Navigate to the test-network directory:

```powershell
cd fabric-samples/test-network
```

2. Bring up the test network:

```powershell
./network.sh up
```

3. Create a channel for medical data:

```powershell
./network.sh createChannel -c medicalchannel
```

### Step 3: Develop and Deploy Custom Chaincode

1. Create a custom chaincode for medical data storage:

```powershell
mkdir -p c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\hyperledger\chaincode\medical-data\go
```

2. Create a basic chaincode for medical data:

```powershell
cd c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\hyperledger\chaincode\medical-data\go
```

3. Create a `medical-data.go` file with the following content:

```go
package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// MedicalDataContract defines the smart contract structure
type MedicalDataContract struct {
	contractapi.Contract
}

// MedicalData represents a medical data record
type MedicalData struct {
	ID            string    `json:"id"`
	PatientID     string    `json:"patientId"`
	DeviceID      string    `json:"deviceId"`
	DataType      string    `json:"dataType"`
	Field         string    `json:"field"`
	Value         string    `json:"value"`
	Priority      string    `json:"priority"`
	Timestamp     time.Time `json:"timestamp"`
	EncryptedData string    `json:"encryptedData,omitempty"`
	PublicKey     string    `json:"publicKey,omitempty"`
}

// InitLedger initializes the ledger with sample data
func (c *MedicalDataContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	// Initial setup logic (if needed)
	return nil
}

// CreateMedicalData adds a new medical data record to the ledger
func (c *MedicalDataContract) CreateMedicalData(ctx contractapi.TransactionContextInterface, id string, data string) error {
	exists, err := c.MedicalDataExists(ctx, id)
	if err != nil {
		return fmt.Errorf("failed to check if medical data exists: %v", err)
	}
	if exists {
		return fmt.Errorf("medical data %s already exists", id)
	}

	var medicalData MedicalData
	err = json.Unmarshal([]byte(data), &medicalData)
	if err != nil {
		return fmt.Errorf("failed to unmarshal medical data: %v", err)
	}

	medicalDataJSON, err := json.Marshal(medicalData)
	if err != nil {
		return fmt.Errorf("failed to marshal medical data: %v", err)
	}

	return ctx.GetStub().PutState(id, medicalDataJSON)
}

// ReadMedicalData returns a medical data record by ID
func (c *MedicalDataContract) ReadMedicalData(ctx contractapi.TransactionContextInterface, id string) (*MedicalData, error) {
	medicalDataJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if medicalDataJSON == nil {
		return nil, fmt.Errorf("medical data %s does not exist", id)
	}

	var medicalData MedicalData
	err = json.Unmarshal(medicalDataJSON, &medicalData)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal medical data: %v", err)
	}

	return &medicalData, nil
}

// QueryMedicalDataByPatient queries for medical data based on patient ID
func (c *MedicalDataContract) QueryMedicalDataByPatient(ctx contractapi.TransactionContextInterface, patientID string) ([]*MedicalData, error) {
	queryString := fmt.Sprintf(`{"selector":{"patientId":"%s"}}`, patientID)
	return c.queryMedicalData(ctx, queryString)
}

// QueryMedicalDataByType queries for medical data based on data type
func (c *MedicalDataContract) QueryMedicalDataByType(ctx contractapi.TransactionContextInterface, dataType string) ([]*MedicalData, error) {
	queryString := fmt.Sprintf(`{"selector":{"dataType":"%s"}}`, dataType)
	return c.queryMedicalData(ctx, queryString)
}

// Helper function for querying medical data
func (c *MedicalDataContract) queryMedicalData(ctx contractapi.TransactionContextInterface, queryString string) ([]*MedicalData, error) {
	resultsIterator, err := ctx.GetStub().GetQueryResult(queryString)
	if err != nil {
		return nil, fmt.Errorf("failed to get query result: %v", err)
	}
	defer resultsIterator.Close()

	var results []*MedicalData
	for resultsIterator.HasNext() {
		queryResult, err := resultsIterator.Next()
		if err != nil {
			return nil, fmt.Errorf("failed to get next result: %v", err)
		}

		var medicalData MedicalData
		err = json.Unmarshal(queryResult.Value, &medicalData)
		if err != nil {
			return nil, fmt.Errorf("failed to unmarshal medical data: %v", err)
		}
		results = append(results, &medicalData)
	}

	return results, nil
}

// MedicalDataExists returns true if the medical data with given ID exists
func (c *MedicalDataContract) MedicalDataExists(ctx contractapi.TransactionContextInterface, id string) (bool, error) {
	medicalDataJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return false, fmt.Errorf("failed to read from world state: %v", err)
	}
	return medicalDataJSON != nil, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&MedicalDataContract{})
	if err != nil {
		fmt.Printf("Error creating medical data chaincode: %v", err)
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting medical data chaincode: %v", err)
	}
}
```

4. Create `go.mod` file:

```go
module github.com/hyperledger/fabric-samples/chaincode/medical-data/go

go 1.14

require (
	github.com/hyperledger/fabric-contract-api-go v1.1.0
)
```

5. Deploy the chaincode to your test network:

```powershell
cd fabric-samples/test-network
./network.sh deployCC -c medicalchannel -ccn medical-data -ccp ../../chaincode/medical-data/go/ -ccl go
```

### Step 4: Integrate with Your System

1. Modify your `hyperledger_fabric.py` file to use the Fabric SDK Python:

```powershell
pip install fabric-sdk-py
```

2. Update your implementation to connect to the real Hyperledger Fabric network.

## 2. Ethereum Setup (Public Blockchain)

### Prerequisites

- **Node.js** and npm (v12.x or higher)
- **Truffle Framework** for development and testing
- **Ganache** for local blockchain development
- **MetaMask** browser extension for testing
- **Solidity compiler** version 0.8.0 or higher

### Step 1: Set Up Local Development Environment

1. Install Truffle and Ganache CLI:

```powershell
npm install -g truffle
npm install -g ganache-cli
```

2. Create a Truffle project structure:

```powershell
mkdir -p c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\ethereum
cd c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\ethereum
truffle init
```

3. Start Ganache (local Ethereum blockchain):

```powershell
ganache-cli --deterministic
```

This will start a local Ethereum blockchain with predefined accounts and private keys.

### Step 2: Configure Truffle for Deployment

1. Create a `truffle-config.js` file:

```javascript
module.exports = {
  networks: {
    development: {
      host: "127.0.0.1",
      port: 8545,
      network_id: "*"
    },
    // For testnet deployment (e.g., Goerli or Sepolia)
    testnet: {
      provider: () => new HDWalletProvider(MNEMONIC, `https://goerli.infura.io/v3/${INFURA_PROJECT_ID}`),
      network_id: 5,       // Goerli's id
      gas: 5500000,        
      confirmations: 2,    // # of confirmations to wait between deployments
      timeoutBlocks: 200,  
      skipDryRun: true     
    }
  },
  compilers: {
    solc: {
      version: "0.8.0",
      settings: {
        optimizer: {
          enabled: true,
          runs: 200
        }
      }
    }
  }
};
```

2. Copy your smart contracts to the contracts folder:

```powershell
cp c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\smart_contracts\*.sol c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\ethereum\contracts\
```

### Step 3: Deploy Your Smart Contracts

1. Compile your contracts:

```powershell
cd c:\Users\Victor\Downloads\Hybrid_BC_System\blockchain\setup\ethereum
truffle compile
```

2. Deploy to the local Ganache network:

```powershell
truffle migrate --network development
```

3. Make note of the contract addresses for later use.

### Step 4: Integrate with Your System

1. Install Web3.py to interact with Ethereum from Python:

```powershell
pip install web3
```

2. Update your `ethereum_client.py` to connect to the real Ethereum network using Web3.py.

## 3. Updating Your System to Use Real Blockchains

1. Update the configuration files:

```python
# In config/system_config.py

PRIVATE_BLOCKCHAIN_CONFIG = {
    'type': 'hyperledger_fabric',
    'network': {
        'channel': 'medicalchannel',
        'chaincode': 'medical-data',
        'org1_connection_profile': './blockchain/setup/hyperledger/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/connection-org1.json',
        'user_name': 'Admin',
        'org_name': 'org1.example.com'
    }
}

PUBLIC_BLOCKCHAIN_CONFIG = {
    'type': 'ethereum',
    'network': 'development',  # or 'testnet' for Goerli/Sepolia
    'provider_url': 'http://127.0.0.1:8545',  # Ganache URL
    'contract_addresses': {
        'data_request': '0x...your contract address here...',  # From truffle migrate
        'access_control': '0x...your contract address here...'  # From truffle migrate
    },
    'account': {
        'address': '0x...your account address here...',  # From Ganache
        'private_key': '0x...your private key here...'  # From Ganache (be careful with private keys!)
    }
}
```

2. Update your blockchain interfaces to use the real implementations:

- Modify `hyperledger_fabric.py` to use the Fabric SDK
- Modify `ethereum_client.py` to use Web3.py

## 4. Testing Your Real Blockchain Integration

1. Create test scripts to verify connectivity to both blockchains
2. Test data storage and retrieval on the private blockchain
3. Test data requests and access control on the public blockchain
4. Test the full workflow from end to end

## 5. Next Steps for Production Deployment

1. **Hyperledger Fabric**:
   - Set up a multi-organization network
   - Implement proper identity management
   - Configure TLS for secure communication
   - Set up proper endorsement policies

2. **Ethereum**:
   - Deploy to a testnet (Goerli, Sepolia)
   - Implement proper key management
   - Consider layer 2 solutions for scalability
   - Optimize gas usage

3. **Security Considerations**:
   - Securely manage private keys
   - Implement proper access controls
   - Regularly audit smart contracts
   - Consider formal verification for critical contracts

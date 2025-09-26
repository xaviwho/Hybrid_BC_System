package main

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// SmartContract provides functions for managing IoT data
type SmartContract struct {
	contractapi.Contract
}

// IoTData describes basic details of IoT data
type IoTData struct {
	ID        string `json:"id"`
	Timestamp string `json:"timestamp"`
	Device    string `json:"device"`
	Value     string `json:"value"`
}

// InitLedger adds a base set of data to the ledger
func (s *SmartContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	fmt.Println("IoT Data chaincode initialized")
	return nil
}

// StoreIoTData stores IoT data on the ledger
func (s *SmartContract) StoreIoTData(ctx contractapi.TransactionContextInterface, id string, payload string) error {
	// Check if data already exists
	existingData, err := ctx.GetStub().GetState(id)
	if err != nil {
		return fmt.Errorf("failed to read from world state: %v", err)
	}
	if existingData != nil {
		return fmt.Errorf("data %s already exists", id)
	}

	// Parse the payload
	var data IoTData
	err = json.Unmarshal([]byte(payload), &data)
	if err != nil {
		return fmt.Errorf("failed to unmarshal IoT data: %v", err)
	}

	// Set the ID from parameter
	data.ID = id

	// Marshal and store
	dataJSON, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal IoT data: %v", err)
	}

	return ctx.GetStub().PutState(id, dataJSON)
}

// ReadIoTData returns the IoT data stored in the world state with given id
func (s *SmartContract) ReadIoTData(ctx contractapi.TransactionContextInterface, id string) (*IoTData, error) {
	dataJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if dataJSON == nil {
		return nil, fmt.Errorf("data %s does not exist", id)
	}

	var data IoTData
	err = json.Unmarshal(dataJSON, &data)
	if err != nil {
		return nil, err
	}

	return &data, nil
}

// GetAllIoTData returns all IoT data found in world state
func (s *SmartContract) GetAllIoTData(ctx contractapi.TransactionContextInterface) ([]*IoTData, error) {
	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var data []*IoTData
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var iotData IoTData
		err = json.Unmarshal(queryResponse.Value, &iotData)
		if err != nil {
			return nil, err
		}
		data = append(data, &iotData)
	}

	return data, nil
}

func main() {
	iotChaincode, err := contractapi.NewChaincode(&SmartContract{})
	if err != nil {
		log.Panicf("Error creating IoT chaincode: %v", err)
	}

	if err := iotChaincode.Start(); err != nil {
		log.Panicf("Error starting IoT chaincode: %v", err)
	}
}

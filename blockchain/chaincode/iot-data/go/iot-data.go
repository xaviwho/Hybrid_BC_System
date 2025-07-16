package main

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// SmartContract provides functions for managing IoT data
type SmartContract struct {
	contractapi.Contract
}

// IoTData describes basic details of what makes up a simple IoT data point
type IoTData struct {
	ID          string `json:"id"`
	Timestamp   string `json:"timestamp"`
	Device      string `json:"device"`
	Value       string `json:"value"`
}

// InitLedger adds a base set of data to the ledger
func (s *SmartContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	// This is a sample initialization, can be left empty if not needed
	fmt.Println("IoTData chaincode is initialized")
	return nil
}

// StoreIoTData adds a new data entry to the ledger
func (s *SmartContract) StoreIoTData(ctx contractapi.TransactionContextInterface, id string, payload string) error {
	// Check if data with the given ID already exists
	existingData, err := ctx.GetStub().GetState(id)
	if err != nil {
		return fmt.Errorf("failed to read from world state: %v", err)
	}
	if existingData != nil {
		return fmt.Errorf("the data %s already exists", id)
	}

	var data IoTData
	err = json.Unmarshal([]byte(payload), &data)
	if err != nil {
		return fmt.Errorf("failed to unmarshal iot data: %v", err)
	}

	dataJSON, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal iot data: %v", err)
	}

	return ctx.GetStub().PutState(id, dataJSON)
}

// ReadIoTData returns the data stored in the world state with given id.
func (s *SmartContract) ReadIoTData(ctx contractapi.TransactionContextInterface, id string) (*IoTData, error) {
	dataJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if dataJSON == nil {
		return nil, fmt.Errorf("the data %s does not exist", id)
	}

	var data IoTData
	err = json.Unmarshal(dataJSON, &data)
	if err != nil {
		return nil, err
	}

	return &data, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&SmartContract{})
	if err != nil {
		fmt.Printf("Error creating new chaincode: %s", err)
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting chaincode: %s", err)
	}
}

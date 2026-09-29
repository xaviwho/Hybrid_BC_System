package main

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// SmartContract stores OrBIT records on the permissioned ledger.
type SmartContract struct {
	contractapi.Contract
}

// Record is the world-state value for key k.
//
// Envelope holds the orchestrator's canonical record bytes (full payload x,
// public metadata m, H(m), ingress time t0) as a JSON *string*. It is kept as a
// string rather than embedded as an object because the CouchDB state database
// re-serialises JSON documents on read; a string value round-trips byte for
// byte, which is what lets an auditor recompute H(m) from the ledger alone.
//
// TxID is the transaction that created the record. It is the version nu in the
// relay tuple sigma = <id, k, nu, tau, H(m)> (manuscript Eq. 22).
type Record struct {
	Envelope string `json:"envelope"`
	TxID     string `json:"txid"`
}

// InitLedger is required by the lifecycle but has nothing to seed.
func (s *SmartContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	return nil
}

// StoreIoTData writes envelope under key id and returns the stored record.
//
// Idempotent: if id already exists, nothing is written and the existing record
// is returned unchanged. A retry after a crash between the Fabric commit and the
// outbox write therefore converges on the first commit instead of failing. The
// caller reads the record back and decides whether the stored envelope matches
// the request (same x) or is a genuine key conflict.
func (s *SmartContract) StoreIoTData(ctx contractapi.TransactionContextInterface, id string, envelope string) (string, error) {
	existing, err := ctx.GetStub().GetState(id)
	if err != nil {
		return "", fmt.Errorf("failed to read from world state: %v", err)
	}
	if existing != nil {
		return string(existing), nil
	}
	if !json.Valid([]byte(envelope)) {
		return "", fmt.Errorf("envelope for %s is not valid JSON", id)
	}
	rec, err := json.Marshal(Record{Envelope: envelope, TxID: ctx.GetStub().GetTxID()})
	if err != nil {
		return "", fmt.Errorf("failed to marshal record: %v", err)
	}
	if err := ctx.GetStub().PutState(id, rec); err != nil {
		return "", err
	}
	return string(rec), nil
}

// ReadIoTData returns the stored record for id as JSON.
func (s *SmartContract) ReadIoTData(ctx contractapi.TransactionContextInterface, id string) (string, error) {
	rec, err := ctx.GetStub().GetState(id)
	if err != nil {
		return "", fmt.Errorf("failed to read from world state: %v", err)
	}
	if rec == nil {
		return "", fmt.Errorf("the data %s does not exist", id)
	}
	return string(rec), nil
}

// KeyedRecord is one entry of a ListRecords page.
type KeyedRecord struct {
	Key      string `json:"key"`
	Envelope string `json:"envelope"`
	TxID     string `json:"txid"`
}

// RecordPage is a page of records plus the bookmark to fetch the next one.
type RecordPage struct {
	Records  []KeyedRecord `json:"records"`
	Bookmark string        `json:"bookmark"`
}

// ListRecords returns up to pageSize records after bookmark, in key order.
//
// Read-only: range queries with pagination run only in query (evaluate)
// transactions. Used by the reconciliation sweep and the auditor (revision
// WS5): a record committed privately whose process died before the outbox
// write exists nowhere but here, so finding it requires enumerating the ledger.
func (s *SmartContract) ListRecords(ctx contractapi.TransactionContextInterface, pageSize int32, bookmark string) (string, error) {
	it, meta, err := ctx.GetStub().GetStateByRangeWithPagination("", "", pageSize, bookmark)
	if err != nil {
		return "", fmt.Errorf("range query failed: %v", err)
	}
	defer it.Close()
	page := RecordPage{Records: []KeyedRecord{}}
	for it.HasNext() {
		kv, err := it.Next()
		if err != nil {
			return "", err
		}
		var rec Record
		if err := json.Unmarshal(kv.Value, &rec); err != nil {
			// Not a v2 record; report the key with an empty envelope.
			page.Records = append(page.Records, KeyedRecord{Key: kv.Key})
			continue
		}
		page.Records = append(page.Records, KeyedRecord{Key: kv.Key, Envelope: rec.Envelope, TxID: rec.TxID})
	}
	page.Bookmark = meta.GetBookmark()
	out, err := json.Marshal(page)
	if err != nil {
		return "", err
	}
	return string(out), nil
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

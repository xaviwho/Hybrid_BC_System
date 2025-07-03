// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IoTDataRegistry
 * @dev This contract manages the registration of IoT data metadata on the public blockchain.
 * The actual data is stored off-chain on a private Hyperledger Fabric network.
 */
contract IoTDataRegistry {

    struct DataRecord {
        bytes32 id; // Using bytes32 for gas efficiency
        address owner;
        string dataHash; // Hash of the data stored on Fabric
        string metadata; // Publicly visible metadata
        uint256 registrationTime;
    }

    // Mapping from data ID to the data record
    mapping(bytes32 => DataRecord) public dataRecords;
    // Mapping from data ID to owner
    mapping(bytes32 => address) public dataOwners;

    // Event emitted when new data is registered
    event DataRegistered(
        bytes32 indexed id,
        address indexed owner,
        string dataHash,
        uint256 registrationTime
    );

    /**
     * @dev Registers a new piece of IoT data.
     * @param _dataId The unique identifier for the data.
     * @param _dataHash The hash of the data stored off-chain.
     * @param _metadata Publicly visible metadata for the data.
     */
    function registerData(bytes32 _dataId, string memory _dataHash, string memory _metadata) public {
        require(dataOwners[_dataId] == address(0), "Data ID already registered");

        dataRecords[_dataId] = DataRecord({
            id: _dataId,
            owner: msg.sender,
            dataHash: _dataHash,
            metadata: _metadata,
            registrationTime: block.timestamp
        });
        dataOwners[_dataId] = msg.sender;

        emit DataRegistered(_dataId, msg.sender, _dataHash, block.timestamp);
    }

    /**
     * @dev Retrieves the owner of a given data ID.
     * @param _dataId The unique identifier of the data.
     * @return The address of the data owner.
     */
    function getDataOwner(bytes32 _dataId) public view returns (address) {
        return dataOwners[_dataId];
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IoTDataRegistry
 * @dev Public anchor registry for OrBIT. The full record lives on Hyperledger
 * Fabric; this contract holds the commitment c = H(sigma) per record id.
 *
 * v2 (revision WS0.5): registerData is gated by Auth(caller) (manuscript
 * Eq. 27), an owner-managed allowlist of relay accounts. The uniqueness revert
 * (Eq. 15) and the registerData signature are unchanged. A rejected duplicate
 * reverts, so it cannot emit an event; duplicate attempts are counted from
 * reverted receipts instead.
 */
contract IoTDataRegistry {

    struct DataRecord {
        bytes32 id; // Using bytes32 for gas efficiency
        address owner;
        string dataHash; // Commitment c = H(sigma), hex
        string metadata; // Publicly visible metadata m (canonical JSON)
        uint256 registrationTime;
    }

    // Mapping from data ID to the data record
    mapping(bytes32 => DataRecord) public dataRecords;
    // Mapping from data ID to owner
    mapping(bytes32 => address) public dataOwners;

    address public owner;
    mapping(address => bool) public isRelay;

    // Event emitted when new data is registered
    event DataRegistered(
        bytes32 indexed id,
        address indexed owner,
        string dataHash,
        uint256 registrationTime
    );
    event RelayAdded(address indexed relay);
    event RelayRemoved(address indexed relay);

    modifier onlyOwner() {
        require(msg.sender == owner, "caller is not the owner");
        _;
    }

    modifier onlyRelay() {
        require(isRelay[msg.sender], "caller is not an authorized relay");
        _;
    }

    constructor() {
        owner = msg.sender;
        isRelay[msg.sender] = true;
        emit RelayAdded(msg.sender);
    }

    function addRelay(address relay) external onlyOwner {
        require(relay != address(0), "zero address");
        require(!isRelay[relay], "already a relay");
        isRelay[relay] = true;
        emit RelayAdded(relay);
    }

    function removeRelay(address relay) external onlyOwner {
        require(isRelay[relay], "not a relay");
        isRelay[relay] = false;
        emit RelayRemoved(relay);
    }

    /**
     * @dev Registers a new piece of IoT data.
     * @param _dataId The unique identifier for the data.
     * @param _dataHash The commitment c = H(sigma).
     * @param _metadata Publicly visible metadata for the data.
     */
    function registerData(bytes32 _dataId, string memory _dataHash, string memory _metadata) public onlyRelay {
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

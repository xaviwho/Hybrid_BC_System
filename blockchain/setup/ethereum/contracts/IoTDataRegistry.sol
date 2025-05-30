// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./AccessToken.sol";
import "./DataAccessRequest.sol";

/**
 * @title IoTDataRegistry
 * @dev Registry for IoT data references on the public blockchain
 * Part of the Hybrid Blockchain-based Incognito Data Sharing system
 */
contract IoTDataRegistry {
    // Reference to the access token contract
    AccessToken public accessToken;
    
    // Reference to the data access request contract
    DataAccessRequest public dataAccessRequest;
    
    // Structure for IoT data reference
    struct DataReference {
        string dataId;           // Unique identifier for the data
        string dataType;         // Type of IoT data (temperature, humidity, etc.)
        string metadataHash;     // IPFS hash or other reference to metadata
        uint8 sensitivityLevel;  // 1=Public, 2=Restricted, 3=Confidential, 4=Critical
        uint256 timestamp;       // When the data was registered
        bool exists;             // Flag to check if a reference exists
    }
    
    // Mapping from data ID to DataReference
    mapping(string => DataReference) private dataReferences;
    
    // Array to store all data IDs
    string[] private dataIds;
    
    // Mapping from data type to array of data IDs
    mapping(string => string[]) private dataTypeIndex;
    
    // Owner of the contract
    address public owner;
    
    // Events
    event DataReferenceRegistered(string dataId, string dataType, uint8 sensitivityLevel);
    event DataReferenceUpdated(string dataId, string metadataHash);
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only the owner can call this function");
        _;
    }
    
    modifier dataExists(string memory _dataId) {
        require(dataReferences[_dataId].exists, "Data reference does not exist");
        _;
    }
    
    /**
     * @dev Constructor to initialize the contract with token and request contract addresses
     * @param _accessTokenAddress Address of the AccessToken contract
     * @param _dataAccessRequestAddress Address of the DataAccessRequest contract
     */
    constructor(address _accessTokenAddress, address _dataAccessRequestAddress) {
        owner = msg.sender;
        accessToken = AccessToken(_accessTokenAddress);
        dataAccessRequest = DataAccessRequest(_dataAccessRequestAddress);
    }
    
    /**
     * @dev Register a new IoT data reference
     * @param _dataId Unique identifier for the data
     * @param _dataType Type of IoT data
     * @param _metadataHash IPFS hash or other reference to metadata
     * @param _sensitivityLevel Sensitivity level of the data
     */
    function registerDataReference(
        string memory _dataId,
        string memory _dataType,
        string memory _metadataHash,
        uint8 _sensitivityLevel
    ) public onlyOwner {
        require(!dataReferences[_dataId].exists, "Data reference already exists");
        require(_sensitivityLevel >= 1 && _sensitivityLevel <= 4, "Invalid sensitivity level");
        
        dataReferences[_dataId] = DataReference({
            dataId: _dataId,
            dataType: _dataType,
            metadataHash: _metadataHash,
            sensitivityLevel: _sensitivityLevel,
            timestamp: block.timestamp,
            exists: true
        });
        
        dataIds.push(_dataId);
        dataTypeIndex[_dataType].push(_dataId);
        
        emit DataReferenceRegistered(_dataId, _dataType, _sensitivityLevel);
    }
    
    /**
     * @dev Update the metadata hash for an existing data reference
     * @param _dataId ID of the data reference to update
     * @param _metadataHash New IPFS hash or reference
     */
    function updateMetadata(string memory _dataId, string memory _metadataHash) 
        public 
        onlyOwner 
        dataExists(_dataId) 
    {
        dataReferences[_dataId].metadataHash = _metadataHash;
        
        emit DataReferenceUpdated(_dataId, _metadataHash);
    }
    
    /**
     * @dev Get data reference details if user has appropriate access level
     * @param _dataId ID of the data reference
     * @return Full data reference details if authorized, limited details otherwise
     */
    function getDataReference(string memory _dataId) 
        public 
        view 
        dataExists(_dataId) 
        returns (
            string memory dataId,
            string memory dataType,
            string memory metadataHash,
            uint8 sensitivityLevel,
            uint256 timestamp
        ) 
    {
        DataReference storage ref = dataReferences[_dataId];
        uint8 userAccessLevel = accessToken.getAccessLevel(msg.sender);
        
        // If user doesn't have sufficient access level, return limited information
        if (userAccessLevel < ref.sensitivityLevel - 1) {
            return (
                ref.dataId,
                ref.dataType,
                "",  // No metadata hash for unauthorized users
                ref.sensitivityLevel,
                ref.timestamp
            );
        }
        
        // Return full details for authorized users
        return (
            ref.dataId,
            ref.dataType,
            ref.metadataHash,
            ref.sensitivityLevel,
            ref.timestamp
        );
    }
    
    /**
     * @dev Get all data IDs
     * @return Array of all registered data IDs
     */
    function getAllDataIds() public view returns (string[] memory) {
        return dataIds;
    }
    
    /**
     * @dev Get data IDs by type
     * @param _dataType Type of data to query
     * @return Array of data IDs matching the specified type
     */
    function getDataIdsByType(string memory _dataType) public view returns (string[] memory) {
        return dataTypeIndex[_dataType];
    }
    
    /**
     * @dev Check if user has access to a specific data reference
     * @param _dataId ID of the data reference
     * @param _user Address of the user to check
     * @return Whether the user has access to the data
     */
    function hasAccess(string memory _dataId, address _user) 
        public 
        view 
        dataExists(_dataId) 
        returns (bool) 
    {
        DataReference storage ref = dataReferences[_dataId];
        uint8 userAccessLevel = accessToken.getAccessLevel(_user);
        
        // Access is granted if user access level is at least data sensitivity level - 1
        // This allows some flexibility while still protecting highly sensitive data
        return userAccessLevel >= ref.sensitivityLevel - 1;
    }
    
    /**
     * @dev Get data references that a user has access to
     * @param _user Address of the user
     * @return Array of data IDs the user has access to
     */
    function getAccessibleDataIds(address _user) public view returns (string[] memory) {
        uint8 userAccessLevel = accessToken.getAccessLevel(_user);
        uint256 count = 0;
        
        // First, count how many items the user can access
        for (uint256 i = 0; i < dataIds.length; i++) {
            DataReference storage ref = dataReferences[dataIds[i]];
            if (userAccessLevel >= ref.sensitivityLevel - 1) {
                count++;
            }
        }
        
        // Create an array of the right size and fill it
        string[] memory result = new string[](count);
        uint256 index = 0;
        
        for (uint256 i = 0; i < dataIds.length; i++) {
            DataReference storage ref = dataReferences[dataIds[i]];
            if (userAccessLevel >= ref.sensitivityLevel - 1) {
                result[index] = dataIds[i];
                index++;
            }
        }
        
        return result;
    }
    
    /**
     * @dev Transfer ownership of the contract
     * @param _newOwner Address of the new owner
     */
    function transferOwnership(address _newOwner) public onlyOwner {
        require(_newOwner != address(0), "New owner cannot be the zero address");
        owner = _newOwner;
    }
}

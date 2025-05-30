// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title AccessControlContract
 * @dev Manages access control for the hybrid blockchain data sharing system
 */
contract AccessControlContract {
    // Access level definition
    enum AccessLevel {
        None,       // No access
        Public,     // Public access level (minimal data)
        Researcher, // Researcher access (anonymized data)
        Doctor,     // Doctor or healthcare professional (most patient data)
        Admin       // Full access to all data
    }
    
    // Entity structure
    struct Entity {
        string entityId;       // Unique identifier for the entity
        string entityType;     // Type of entity (individual, organization, etc.)
        address walletAddress; // Ethereum wallet address
        AccessLevel level;     // Default access level
        bool isActive;         // Whether the entity is active
        uint256 createdAt;     // When the entity was created
    }
    
    // Special permission structure (for specific data types)
    struct SpecialPermission {
        string dataType;       // Type of data
        AccessLevel level;     // Special access level for this data type
        uint256 expirationTime; // When this special permission expires
    }
    
    // Events
    event EntityRegistered(string entityId, address indexed walletAddress);
    event EntityDeactivated(string entityId);
    event EntityReactivated(string entityId);
    event AccessLevelChanged(string entityId, AccessLevel level);
    event SpecialPermissionGranted(string entityId, string dataType, AccessLevel level, uint256 expirationTime);
    event SpecialPermissionRevoked(string entityId, string dataType);
    
    // State variables
    mapping(string => Entity) public entities;              // entityId => Entity
    mapping(address => string) public addressToEntityId;    // walletAddress => entityId
    mapping(string => mapping(string => SpecialPermission)) public specialPermissions; // entityId => dataType => SpecialPermission
    
    address public admin;
    
    // Modifiers
    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can perform this action");
        _;
    }
    
    modifier entityExists(string memory entityId) {
        require(bytes(entities[entityId].entityId).length > 0, "Entity does not exist");
        _;
    }
    
    modifier entityActive(string memory entityId) {
        require(entities[entityId].isActive, "Entity is not active");
        _;
    }
    
    /**
     * @dev Constructor sets the admin address
     */
    constructor() {
        admin = msg.sender;
    }
    
    /**
     * @dev Register a new entity
     * @param entityId Unique identifier for the entity
     * @param entityType Type of entity
     * @param walletAddress Ethereum wallet address of the entity
     * @param level Default access level
     * @return success Boolean indicating success
     */
    function registerEntity(
        string memory entityId,
        string memory entityType,
        address walletAddress,
        AccessLevel level
    ) public onlyAdmin returns (bool success) {
        // Ensure entity ID doesn't already exist
        require(bytes(entities[entityId].entityId).length == 0, "Entity ID already exists");
        
        // Ensure wallet address isn't already associated with an entity
        require(bytes(addressToEntityId[walletAddress]).length == 0, "Wallet address already registered");
        
        // Create entity
        Entity memory newEntity = Entity({
            entityId: entityId,
            entityType: entityType,
            walletAddress: walletAddress,
            level: level,
            isActive: true,
            createdAt: block.timestamp
        });
        
        // Store entity
        entities[entityId] = newEntity;
        addressToEntityId[walletAddress] = entityId;
        
        // Emit event
        emit EntityRegistered(entityId, walletAddress);
        
        return true;
    }
    
    /**
     * @dev Deactivate an entity
     * @param entityId ID of the entity to deactivate
     * @return success Boolean indicating success
     */
    function deactivateEntity(string memory entityId) 
        public
        onlyAdmin
        entityExists(entityId)
        returns (bool success) 
    {
        // Set entity as inactive
        entities[entityId].isActive = false;
        
        // Emit event
        emit EntityDeactivated(entityId);
        
        return true;
    }
    
    /**
     * @dev Reactivate an entity
     * @param entityId ID of the entity to reactivate
     * @return success Boolean indicating success
     */
    function reactivateEntity(string memory entityId) 
        public
        onlyAdmin
        entityExists(entityId)
        returns (bool success) 
    {
        // Set entity as active
        entities[entityId].isActive = true;
        
        // Emit event
        emit EntityReactivated(entityId);
        
        return true;
    }
    
    /**
     * @dev Change an entity's default access level
     * @param entityId ID of the entity
     * @param level New access level
     * @return success Boolean indicating success
     */
    function changeAccessLevel(string memory entityId, AccessLevel level) 
        public
        onlyAdmin
        entityExists(entityId)
        returns (bool success) 
    {
        // Update access level
        entities[entityId].level = level;
        
        // Emit event
        emit AccessLevelChanged(entityId, level);
        
        return true;
    }
    
    /**
     * @dev Grant special permission for a specific data type
     * @param entityId ID of the entity
     * @param dataType Type of data
     * @param level Special access level
     * @param expirationDays Number of days until permission expires
     * @return success Boolean indicating success
     */
    function grantSpecialPermission(
        string memory entityId,
        string memory dataType,
        AccessLevel level,
        uint256 expirationDays
    ) 
        public
        onlyAdmin
        entityExists(entityId)
        entityActive(entityId)
        returns (bool success) 
    {
        // Calculate expiration time
        uint256 expirationTime = block.timestamp + (expirationDays * 1 days);
        
        // Create special permission
        SpecialPermission memory permission = SpecialPermission({
            dataType: dataType,
            level: level,
            expirationTime: expirationTime
        });
        
        // Store permission
        specialPermissions[entityId][dataType] = permission;
        
        // Emit event
        emit SpecialPermissionGranted(entityId, dataType, level, expirationTime);
        
        return true;
    }
    
    /**
     * @dev Revoke special permission for a specific data type
     * @param entityId ID of the entity
     * @param dataType Type of data
     * @return success Boolean indicating success
     */
    function revokeSpecialPermission(string memory entityId, string memory dataType) 
        public
        onlyAdmin
        entityExists(entityId)
        returns (bool success) 
    {
        // Ensure special permission exists
        require(bytes(specialPermissions[entityId][dataType].dataType).length > 0, "Special permission does not exist");
        
        // Delete special permission
        delete specialPermissions[entityId][dataType];
        
        // Emit event
        emit SpecialPermissionRevoked(entityId, dataType);
        
        return true;
    }
    
    /**
     * @dev Check if an entity has access to a specific data type at a certain level
     * @param entityId ID of the entity
     * @param dataType Type of data
     * @param requiredLevel Minimum required access level
     * @return hasAccess Boolean indicating if the entity has sufficient access
     */
    function checkAccess(string memory entityId, string memory dataType, AccessLevel requiredLevel) 
        public
        view
        returns (bool hasAccess) 
    {
        // Ensure entity exists and is active
        if (bytes(entities[entityId].entityId).length == 0 || !entities[entityId].isActive) {
            return false;
        }
        
        // Check if entity has special permission for this data type
        if (bytes(specialPermissions[entityId][dataType].dataType).length > 0) {
            // Check if special permission has expired
            if (block.timestamp > specialPermissions[entityId][dataType].expirationTime) {
                // Special permission expired, fall back to default level
                return uint(entities[entityId].level) >= uint(requiredLevel);
            }
            
            // Check if special permission grants sufficient access
            return uint(specialPermissions[entityId][dataType].level) >= uint(requiredLevel);
        }
        
        // No special permission, check default level
        return uint(entities[entityId].level) >= uint(requiredLevel);
    }
    
    /**
     * @dev Get entity details by ID
     * @param entityId ID of the entity
     * @return entity The entity details
     */
    function getEntityById(string memory entityId) 
        public
        view
        entityExists(entityId)
        returns (Entity memory) 
    {
        return entities[entityId];
    }
    
    /**
     * @dev Get entity details by wallet address
     * @param walletAddress Wallet address of the entity
     * @return entity The entity details
     */
    function getEntityByAddress(address walletAddress) 
        public
        view
        returns (Entity memory) 
    {
        string memory entityId = addressToEntityId[walletAddress];
        require(bytes(entityId).length > 0, "No entity associated with this address");
        
        return entities[entityId];
    }
    
    /**
     * @dev Change the admin address
     * @param newAdmin New admin address
     */
    function changeAdmin(address newAdmin) public onlyAdmin {
        admin = newAdmin;
    }
}

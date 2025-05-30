// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title DataRequestContract
 * @dev Handles data access requests on the public blockchain
 */
contract DataRequestContract {
    // Data request structure
    struct DataRequest {
        address requester;
        string requesterId;
        string dataType;
        string purpose;
        string accessLevel;
        uint256 timestamp;
        uint256 expirationTime;
        RequestStatus status;
        string responseDataId;  // IPFS or other storage reference
    }
    
    // Request status enum
    enum RequestStatus {
        Pending,
        Approved,
        Rejected,
        Fulfilled,
        Expired
    }
    
    // Events
    event RequestCreated(string requestId, address requester, string dataType);
    event RequestStatusUpdated(string requestId, RequestStatus status);
    event RequestFulfilled(string requestId, string responseDataId);
    
    // State variables
    mapping(string => DataRequest) public requests;
    string[] public requestIds;
    address public admin;
    mapping(address => bool) public authorizedRequesters;
    
    // Modifiers
    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can perform this action");
        _;
    }
    
    modifier onlyAuthorized() {
        require(msg.sender == admin || authorizedRequesters[msg.sender], "Not authorized");
        _;
    }
    
    /**
     * @dev Constructor sets the admin address
     */
    constructor() {
        admin = msg.sender;
    }
    
    /**
     * @dev Create a new data access request
     * @param requestId Unique identifier for the request
     * @param requesterId ID of the requester (organization or individual)
     * @param dataType Type of data being requested
     * @param purpose Purpose of the data request
     * @param accessLevel Requested access level
     * @param expirationDays Number of days until request expires
     * @return success Boolean indicating success
     */
    function createDataRequest(
        string memory requestId,
        string memory requesterId,
        string memory dataType,
        string memory purpose,
        string memory accessLevel,
        uint256 expirationDays
    ) public returns (bool success) {
        // Ensure request ID doesn't already exist
        require(requests[requestId].timestamp == 0, "Request ID already exists");
        
        // Create request
        DataRequest memory newRequest = DataRequest({
            requester: msg.sender,
            requesterId: requesterId,
            dataType: dataType,
            purpose: purpose,
            accessLevel: accessLevel,
            timestamp: block.timestamp,
            expirationTime: block.timestamp + (expirationDays * 1 days),
            status: RequestStatus.Pending,
            responseDataId: ""
        });
        
        // Store request
        requests[requestId] = newRequest;
        requestIds.push(requestId);
        
        // Emit event
        emit RequestCreated(requestId, msg.sender, dataType);
        
        return true;
    }
    
    /**
     * @dev Update the status of a data request
     * @param requestId ID of the request to update
     * @param status New status
     * @return success Boolean indicating success
     */
    function updateRequestStatus(string memory requestId, RequestStatus status) 
        public
        onlyAuthorized
        returns (bool success) 
    {
        // Ensure request exists
        require(requests[requestId].timestamp > 0, "Request does not exist");
        
        // Update status
        requests[requestId].status = status;
        
        // Emit event
        emit RequestStatusUpdated(requestId, status);
        
        return true;
    }
    
    /**
     * @dev Fulfill a data request with response data
     * @param requestId ID of the request to fulfill
     * @param responseDataId Reference to the response data (IPFS hash or other identifier)
     * @return success Boolean indicating success
     */
    function fulfillRequest(string memory requestId, string memory responseDataId) 
        public
        onlyAuthorized
        returns (bool success) 
    {
        // Ensure request exists and is approved
        require(requests[requestId].timestamp > 0, "Request does not exist");
        require(requests[requestId].status == RequestStatus.Approved, "Request not approved");
        require(block.timestamp < requests[requestId].expirationTime, "Request has expired");
        
        // Update request
        requests[requestId].responseDataId = responseDataId;
        requests[requestId].status = RequestStatus.Fulfilled;
        
        // Emit event
        emit RequestFulfilled(requestId, responseDataId);
        
        return true;
    }
    
    /**
     * @dev Get details of a specific request
     * @param requestId ID of the request
     * @return request The request details
     */
    function getRequestDetails(string memory requestId) 
        public
        view
        returns (DataRequest memory) 
    {
        require(requests[requestId].timestamp > 0, "Request does not exist");
        return requests[requestId];
    }
    
    /**
     * @dev Get all request IDs
     * @return ids Array of request IDs
     */
    function getAllRequestIds() public view returns (string[] memory) {
        return requestIds;
    }
    
    /**
     * @dev Add an authorized requester
     * @param requester Address to authorize
     */
    function addAuthorizedRequester(address requester) public onlyAdmin {
        authorizedRequesters[requester] = true;
    }
    
    /**
     * @dev Remove an authorized requester
     * @param requester Address to deauthorize
     */
    function removeAuthorizedRequester(address requester) public onlyAdmin {
        authorizedRequesters[requester] = false;
    }
    
    /**
     * @dev Change the admin address
     * @param newAdmin New admin address
     */
    function changeAdmin(address newAdmin) public onlyAdmin {
        admin = newAdmin;
    }
}

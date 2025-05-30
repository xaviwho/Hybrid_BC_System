// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title DataAccessRequest
 * @dev Smart contract for requesting access to IoT data from the private blockchain
 * Part of the Hybrid Blockchain-based Incognito Data Sharing with Quantum Computing system
 */
contract DataAccessRequest {
    // Access level definitions
    enum AccessLevel { Public, User, Researcher, Admin }
    
    // Request status definitions
    enum RequestStatus { Pending, Approved, Rejected, Fulfilled }
    
    // Structure for data access requests
    struct Request {
        uint256 id;
        address requester;
        string dataType;
        string purpose;
        AccessLevel accessLevel;
        RequestStatus status;
        uint256 timestamp;
        uint256 expirationTime;
        string responseDataHash;  // IPFS hash or other reference to the filtered data
        bool quantumSecured;      // Flag indicating if quantum security was used
    }
    
    // Mapping from request ID to Request
    mapping(uint256 => Request) public requests;
    
    // Array to keep track of all request IDs
    uint256[] public requestIds;
    
    // Mapping from user address to their request IDs
    mapping(address => uint256[]) public userRequests;
    
    // Counter for generating unique request IDs
    uint256 private requestIdCounter;
    
    // Owner of the contract (system administrator)
    address public owner;
    
    // Events
    event RequestCreated(uint256 indexed requestId, address indexed requester, string dataType, AccessLevel accessLevel);
    event RequestStatusChanged(uint256 indexed requestId, RequestStatus status);
    event RequestFulfilled(uint256 indexed requestId, string responseDataHash);
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only the owner can call this function");
        _;
    }
    
    modifier validRequestId(uint256 _requestId) {
        require(_requestId < requestIdCounter, "Invalid request ID");
        _;
    }
    
    modifier onlyRequester(uint256 _requestId) {
        require(msg.sender == requests[_requestId].requester, "Only the requester can call this function");
        _;
    }
    
    // Constructor
    constructor() {
        owner = msg.sender;
        requestIdCounter = 0;
    }
    
    /**
     * @dev Create a new data access request
     * @param _dataType Type of data being requested (e.g., "temperature", "humidity")
     * @param _purpose Purpose of the data access request
     * @param _accessLevel Required access level for the request
     * @param _expirationTime Time when the request expires (unix timestamp)
     * @return The ID of the newly created request
     */
    function createRequest(
        string memory _dataType,
        string memory _purpose,
        AccessLevel _accessLevel,
        uint256 _expirationTime
    ) public returns (uint256) {
        uint256 requestId = requestIdCounter++;
        
        requests[requestId] = Request({
            id: requestId,
            requester: msg.sender,
            dataType: _dataType,
            purpose: _purpose,
            accessLevel: _accessLevel,
            status: RequestStatus.Pending,
            timestamp: block.timestamp,
            expirationTime: _expirationTime,
            responseDataHash: "",
            quantumSecured: false
        });
        
        requestIds.push(requestId);
        userRequests[msg.sender].push(requestId);
        
        emit RequestCreated(requestId, msg.sender, _dataType, _accessLevel);
        
        return requestId;
    }
    
    /**
     * @dev Update the status of a request
     * @param _requestId ID of the request to update
     * @param _status New status for the request
     */
    function updateRequestStatus(uint256 _requestId, RequestStatus _status) 
        public 
        onlyOwner 
        validRequestId(_requestId) 
    {
        Request storage request = requests[_requestId];
        request.status = _status;
        
        emit RequestStatusChanged(_requestId, _status);
    }
    
    /**
     * @dev Fulfill a data access request with the response data hash
     * @param _requestId ID of the request to fulfill
     * @param _responseDataHash Hash or reference to the response data
     * @param _quantumSecured Whether quantum security was used
     */
    function fulfillRequest(
        uint256 _requestId,
        string memory _responseDataHash,
        bool _quantumSecured
    ) 
        public 
        onlyOwner 
        validRequestId(_requestId) 
    {
        Request storage request = requests[_requestId];
        
        // Request must be approved and not expired
        require(request.status == RequestStatus.Approved, "Request must be approved first");
        require(block.timestamp <= request.expirationTime, "Request has expired");
        
        request.status = RequestStatus.Fulfilled;
        request.responseDataHash = _responseDataHash;
        request.quantumSecured = _quantumSecured;
        
        emit RequestFulfilled(_requestId, _responseDataHash);
    }
    
    /**
     * @dev Get all requests made by a specific user
     * @param _user Address of the user
     * @return Array of request IDs belonging to the user
     */
    function getRequestsByUser(address _user) public view returns (uint256[] memory) {
        return userRequests[_user];
    }
    
    /**
     * @dev Get all request IDs
     * @return Array of all request IDs
     */
    function getAllRequestIds() public view returns (uint256[] memory) {
        return requestIds;
    }
    
    /**
     * @dev Get request details by ID
     * @param _requestId ID of the request
     * @return Request details as a tuple
     */
    function getRequestDetails(uint256 _requestId) 
        public 
        view 
        validRequestId(_requestId) 
        returns (
            uint256 id,
            address requester,
            string memory dataType,
            string memory purpose,
            AccessLevel accessLevel,
            RequestStatus status,
            uint256 timestamp,
            uint256 expirationTime,
            string memory responseDataHash,
            bool quantumSecured
        ) 
    {
        Request storage request = requests[_requestId];
        
        return (
            request.id,
            request.requester,
            request.dataType,
            request.purpose,
            request.accessLevel,
            request.status,
            request.timestamp,
            request.expirationTime,
            request.responseDataHash,
            request.quantumSecured
        );
    }
    
    /**
     * @dev Cancel a pending request (only the requester can cancel their own requests)
     * @param _requestId ID of the request to cancel
     */
    function cancelRequest(uint256 _requestId) 
        public 
        onlyRequester(_requestId) 
        validRequestId(_requestId) 
    {
        Request storage request = requests[_requestId];
        
        // Can only cancel pending requests
        require(request.status == RequestStatus.Pending, "Only pending requests can be cancelled");
        
        request.status = RequestStatus.Rejected;
        
        emit RequestStatusChanged(_requestId, RequestStatus.Rejected);
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

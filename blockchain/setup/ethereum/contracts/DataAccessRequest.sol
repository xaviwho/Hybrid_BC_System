// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./IoTDataRegistry.sol";
import "./AccessToken.sol";

/**
 * @title DataAccessRequest
 * @dev Manages requests from users to access specific IoT data.
 * Interacts with IoTDataRegistry to verify data ownership and AccessToken to mint NFTs upon approval.
 */
contract DataAccessRequest {

    struct Request {
        address requester;
        address dataOwner;
        bytes32 dataId;
        string justification;
        RequestStatus status;
    }

    enum RequestStatus { Pending, Approved, Rejected }

    event RequestCreated(uint256 indexed requestId, bytes32 indexed dataId, address indexed requester);
    event RequestApproved(uint256 indexed requestId, bytes32 indexed dataId, address indexed requester);
    event RequestRejected(uint256 indexed requestId, bytes32 indexed dataId, address indexed requester);

    IoTDataRegistry public iotDataRegistry;
    AccessToken public accessTokenContract;

    mapping(uint256 => Request) public requests;
    uint256 private _requestIdCounter;

    /**
     * @dev Sets the addresses of the dependent contracts.
     * @param _registryAddress The address of the IoTDataRegistry contract.
     * @param _accessTokenAddress The address of the AccessToken contract.
     */
    constructor(address _registryAddress, address _accessTokenAddress) {
        iotDataRegistry = IoTDataRegistry(_registryAddress);
        accessTokenContract = AccessToken(_accessTokenAddress);
    }

    /**
     * @dev Creates a new request to access a piece of data.
     * @param _dataId The unique identifier of the data.
     * @param _justification A string explaining the reason for the request.
     */
    function createRequest(bytes32 _dataId, string memory _justification) public {
        address dataOwner = iotDataRegistry.getDataOwner(_dataId);
        require(dataOwner != address(0), "Data not registered");

        uint256 newRequestId = _requestIdCounter;
        requests[newRequestId] = Request({
            requester: msg.sender,
            dataOwner: dataOwner,
            dataId: _dataId,
            justification: _justification,
            status: RequestStatus.Pending
        });

        _requestIdCounter++;
        emit RequestCreated(newRequestId, _dataId, msg.sender);
    }

    /**
     * @dev Allows the data owner to approve an access request and mints an access token.
     * @param _requestId The ID of the request to approve.
     */
    function approveRequest(uint256 _requestId) public {
        Request storage requestToApprove = requests[_requestId];
        require(requestToApprove.dataOwner == msg.sender, "Only data owner can approve");
        require(requestToApprove.status == RequestStatus.Pending, "Request not pending");

        requestToApprove.status = RequestStatus.Approved;

        // A real implementation would generate a more descriptive URI
        string memory tokenURI = "https://example.com/tokens/access_token_for_request_id"; 
        accessTokenContract.mintAccessToken(requestToApprove.requester, tokenURI);

        emit RequestApproved(_requestId, requestToApprove.dataId, requestToApprove.requester);
    }

    /**
     * @dev Allows the data owner to reject an access request.
     * @param _requestId The ID of the request to reject.
     */
    function rejectRequest(uint256 _requestId) public {
        Request storage requestToReject = requests[_requestId];
        require(requestToReject.dataOwner == msg.sender, "Only data owner can reject");
        require(requestToReject.status == RequestStatus.Pending, "Request not pending");

        requestToReject.status = RequestStatus.Rejected;
        emit RequestRejected(_requestId, requestToReject.dataId, requestToReject.requester);
    }

    /**
     * @dev Retrieves the details of a specific request.
     * @param _requestId The ID of the request to retrieve.
     */
    function getRequest(uint256 _requestId) public view returns (address, address, bytes32, string memory, RequestStatus) {
        Request storage r = requests[_requestId];
        return (r.requester, r.dataOwner, r.dataId, r.justification, r.status);
    }
}

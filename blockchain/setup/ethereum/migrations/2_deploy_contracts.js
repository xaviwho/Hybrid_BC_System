const AccessToken = artifacts.require("AccessToken");
const DataAccessRequest = artifacts.require("DataAccessRequest");
const IoTDataRegistry = artifacts.require("IoTDataRegistry");

module.exports = function(deployer) {
  // Deploy AccessToken first
  deployer.deploy(AccessToken).then(() => {
    // Then deploy DataAccessRequest
    return deployer.deploy(DataAccessRequest);
  }).then(() => {
    // Finally deploy IoTDataRegistry with the addresses of the other contracts
    return deployer.deploy(
      IoTDataRegistry, 
      AccessToken.address, 
      DataAccessRequest.address
    );
  });
};

const DataRequestContract = artifacts.require("DataRequestContract");
const AccessControlContract = artifacts.require("AccessControlContract");

module.exports = function(deployer) {
  // Deploy the AccessControlContract first
  deployer.deploy(AccessControlContract).then(() => {
    // Then deploy the DataRequestContract
    return deployer.deploy(DataRequestContract);
  });
};

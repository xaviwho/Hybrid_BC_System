const IoTDataRegistry = artifacts.require("IoTDataRegistry");
const DataAccessRequest = artifacts.require("DataAccessRequest");
const AccessToken = artifacts.require("AccessToken");

module.exports = async function (deployer) {
  // 1. Deploy IoTDataRegistry
  await deployer.deploy(IoTDataRegistry);
  const registryInstance = await IoTDataRegistry.deployed();

  // 2. Deploy AccessToken
  await deployer.deploy(AccessToken);
  const tokenInstance = await AccessToken.deployed();

  // 3. Deploy DataAccessRequest with the addresses of the other contracts
  await deployer.deploy(
    DataAccessRequest,
    registryInstance.address,
    tokenInstance.address
  );
  const requestInstance = await DataAccessRequest.deployed();

  // 4. Authorize the DataAccessRequest contract to mint tokens
  await tokenInstance.setMinter(requestInstance.address);
};

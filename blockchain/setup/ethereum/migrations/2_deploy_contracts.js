const IoTDataRegistry = artifacts.require("IoTDataRegistry");
const DataAccessRequest = artifacts.require("DataAccessRequest");
const AccessToken = artifacts.require("AccessToken");

// Relay accounts allowlisted at deployment (revision WS0.5). accounts[0] is the
// deployer and is allowlisted by the constructor; accounts[1..3] are the
// independent relays of WS3. Doing it here keeps every v2 experiment on ONE
// deployment: adding relays later is a transaction, not a redeploy, but fixing
// the set now means the allowlist is part of the recorded deployment.
const RELAY_ACCOUNT_INDICES = [1, 2, 3];

module.exports = async function (deployer, network, accounts) {
  // 1. Deploy IoTDataRegistry
  await deployer.deploy(IoTDataRegistry);
  const registryInstance = await IoTDataRegistry.deployed();
  for (const i of RELAY_ACCOUNT_INDICES) {
    await registryInstance.addRelay(accounts[i]);
  }

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

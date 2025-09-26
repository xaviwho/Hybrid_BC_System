module.exports = {
  /**
   * This specifies the directory where Truffle will store your compiled contracts.
   */
  contracts_build_directory: "./build/contracts",

  /**
   * This specifies the directory where Truffle will look for your Solidity contracts.
   */
  contracts_directory: "./contracts",

  /**
   * Networks define how you connect to your ethereum client and let you set the
   * defaults web3 uses to send transactions. You can configure different networks
   * for development, testing, and production.
   */
  networks: {
    development: {
      host: "127.0.0.1",     // Localhost for local development
      port: 8545,            // Standard Ethereum client port
      network_id: "*",       // Any network (default: none)
    },
  },

  // Configure your compilers
  compilers: {
    solc: {
      version: "0.8.20",    // Fetch exact version from solc-bin
      settings: {         // See the Solidity docs for optimizer and other settings
        optimizer: {
          enabled: true,
          runs: 200
        },
      }
    }
  }
};

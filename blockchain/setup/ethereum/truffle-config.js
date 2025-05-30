/**
 * Truffle configuration for the Ethereum component of the 
 * Hybrid Blockchain-based Incognito Data Sharing system
 */

module.exports = {
  networks: {
    // Development network (local)
    development: {
      host: "127.0.0.1",
      port: 8545,
      network_id: "*", // Match any network id
    },
    
    // For connecting to Ganache UI
    ganache: {
      host: "127.0.0.1",
      port: 7545,
      network_id: "*",
    },
    
    // Test network (Sepolia)
    sepolia: {
      provider: () => {
        // You would need to add HDWalletProvider and API key here for deployment
        // const HDWalletProvider = require('@truffle/hdwallet-provider');
        // return new HDWalletProvider(process.env.MNEMONIC, `https://sepolia.infura.io/v3/${process.env.INFURA_API_KEY}`);
      },
      network_id: 11155111,
      gas: 5500000,
      confirmations: 2,
      timeoutBlocks: 200,
      skipDryRun: true,
    },
  },

  // Set default mocha options here, use special reporters, etc.
  mocha: {
    timeout: 100000
  },

  // Configure your compilers
  compilers: {
    solc: {
      version: "0.8.17",
      settings: {
        optimizer: {
          enabled: true,
          runs: 200
        },
      }
    }
  },
  
  // Plugins
  plugins: [
    'truffle-plugin-verify'
  ],
  
  // API keys for verification
  api_keys: {
    // Add API keys for verification services like Etherscan
    // etherscan: process.env.ETHERSCAN_API_KEY
  }
};

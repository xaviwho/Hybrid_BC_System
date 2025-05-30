"""
System configuration for the Hybrid Blockchain-based Incognito Data Sharing System.

This file contains all configuration parameters for the various components of the system.
"""

# ML Gateway Filter Configuration
ML_CONFIG = {
    'gateway_filter': {
        'model_path': '/app/gateway_filter/gateway_filter_model.joblib',
        'api_endpoint': 'http://ml-gateway:5000',
        'threshold': 0.7  # Threshold for classification
    },
    'privacy_filter': {
        'model_path': '/app/privacy_filter/sensitivity_model.joblib',
        'api_endpoint': 'http://ml-privacy:5001',
        'sensitivity_levels': ['public', 'restricted', 'confidential']
    }
}

# Hyperledger Fabric (Private Blockchain) Configuration
PRIVATE_BLOCKCHAIN_CONFIG = {
    'peer_endpoint': 'http://hybrid-peer0.org1.example.com:7051',
    'orderer_endpoint': 'http://hybrid-orderer.example.com:7050',
    'channel_name': 'hiot',
    'chaincode_name': 'iot-data',
    'org_name': 'Org1MSP',
    'user_name': 'Admin'
}

# Ethereum (Public Blockchain) Configuration
PUBLIC_BLOCKCHAIN_CONFIG = {
    'rpc_endpoint': 'http://ethereum-node:8545',
    'contracts': {
        'AccessToken': {
            'address': '0x5FbDB2315678afecb367f032d93F642f64180aa3'
        },
        'DataAccessRequest': {
            'address': '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512'
        },
        'IoTDataRegistry': {
            'address': '0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0'
        }
    },
    'gas_limit': 6000000
}

# Quantum Security Configuration
QUANTUM_CONFIG = {
    'enabled': True,
    'key_size': 256,
    'algorithm': 'SPHINCS+',
    'encryption_level': 'high'
}

# General System Configuration
SYSTEM_CONFIG = {
    'log_level': 'INFO',
    'log_file_path': './logs/system.log',
    'api_port': 8000,
    'debug_mode': False,
    'default_sensitivity': 'restricted'
}

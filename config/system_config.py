"""
Configuration settings for the Hybrid Blockchain-based Incognito Data Sharing System with Quantum Computing.
"""

# IoT Data Collection Configuration
IOT_CONFIG = {
    'data_sources': ['medical_sensors', 'environmental_sensors', 'wearable_devices'],
    'collection_interval_seconds': 60,
    'buffer_size': 1000,  # Number of data points to buffer before processing
}

# Machine Learning Configuration
ML_CONFIG = {
    # Gateway Filter (determines what data enters private blockchain)
    'gateway_filter': {
        'model_path': './ml/models/gateway_filter.pkl',
        'threshold': 0.75,  # Confidence threshold for accepting data
        'update_interval_hours': 24,  # How often to retrain/update the model
    },
    
    # Privacy Filter (determines what data can be shared when requested)
    'privacy_filter': {
        'model_path': './ml/models/privacy_filter.pkl',
        'sensitivity_levels': ['public', 'restricted', 'confidential', 'critical'],
        'default_level': 'critical',  # Default sensitivity if classification fails
    },
    
    # Anomaly Detection
    'anomaly_detection': {
        'model_path': './ml/models/anomaly_detector.pkl',
        'threshold': 0.95,  # Threshold for anomaly detection
    }
}

# Private Blockchain Configuration
PRIVATE_BLOCKCHAIN_CONFIG = {
    'type': 'hyperledger_fabric',  # Blockchain implementation
    'version': '2.2',
    'channels': ['medical_data', 'critical_sensors'],
    'organizations': ['hospital', 'research_lab', 'device_manufacturers'],
    'endorsement_policy': {
        'medical_data': {'min_endorsements': 2},
        'critical_sensors': {'min_endorsements': 3},
    },
    'world_state_db': 'couchdb',
    'max_transaction_size': 1024 * 1024,  # 1 MB
}

# Public Blockchain Configuration
PUBLIC_BLOCKCHAIN_CONFIG = {
    'type': 'ethereum',  # Blockchain implementation
    'version': '1.0',
    'network': 'testnet',  # 'mainnet', 'testnet', or 'private'
    'gas_limit': 6721975,
    'gas_price': '20000000000',  # in wei
    'contract_addresses': {
        'data_request': '0x0000000000000000000000000000000000000000',  # Placeholder
        'access_control': '0x0000000000000000000000000000000000000000',  # Placeholder
    }
}

# Quantum Security Configuration
QUANTUM_CONFIG = {
    'encryption': {
        'algorithm': 'CRYSTALS-Kyber',  # Post-quantum key encapsulation mechanism
        'key_size': 1024,
    },
    'key_distribution': {
        'protocol': 'BB84',  # Bennett-Brassard 1984 quantum key distribution protocol
        'refresh_interval_minutes': 60,
    },
    'signature': {
        'algorithm': 'CRYSTALS-Dilithium',  # Post-quantum digital signature algorithm
        'security_level': 3,  # Higher means more secure but slower
    }
}

# System-wide settings
SYSTEM_CONFIG = {
    'log_level': 'INFO',  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    'log_file_path': './logs/system.log',
    'admin_email': 'admin@example.com',
    'max_cache_size_mb': 100,
    'api_rate_limit': 100,  # Requests per minute
    'enable_quantum_security': True,
}

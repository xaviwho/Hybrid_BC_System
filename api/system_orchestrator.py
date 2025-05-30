"""
System orchestrator for the Hybrid Blockchain-based Incognito Data Sharing System.

This module integrates all system components (ML, blockchains, quantum security)
and orchestrates the data flow between them.
"""

import logging
import os
import sys
import time
from typing import Dict, Any, List, Optional, Union

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import system components
from config.system_config import (
    ML_CONFIG, PRIVATE_BLOCKCHAIN_CONFIG, PUBLIC_BLOCKCHAIN_CONFIG, 
    QUANTUM_CONFIG, SYSTEM_CONFIG
)
from ml.preprocessing.data_processor import IoTDataProcessor
from ml.classification.gateway_filter import GatewayFilter
from ml.classification.privacy_filter import PrivacyFilter
from blockchain.private.hyperledger_fabric import HyperledgerFabricClient
from blockchain.public.ethereum_client import EthereumClient
from quantum.encryption.post_quantum_crypto import PostQuantumCrypto
from quantum.key_distribution.quantum_key_distribution import QuantumKeyDistribution

# Configure logging
logging.basicConfig(
    level=getattr(logging, SYSTEM_CONFIG.get('log_level', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(SYSTEM_CONFIG.get('log_file_path', './logs/system.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SystemOrchestrator:
    """
    Orchestrates data flow and interactions between all system components.
    """
    
    def __init__(self):
        """Initialize the system orchestrator and all components."""
        logger.info("Initializing Hybrid Blockchain System components")
        
        # Initialize ML components
        self.data_processor = IoTDataProcessor({})
        self.gateway_filter = GatewayFilter(ML_CONFIG['gateway_filter'])
        self.privacy_filter = PrivacyFilter(ML_CONFIG['privacy_filter'])
        
        # Initialize blockchain components
        self.private_blockchain = HyperledgerFabricClient(PRIVATE_BLOCKCHAIN_CONFIG)
        self.public_blockchain = EthereumClient(PUBLIC_BLOCKCHAIN_CONFIG)
        
        # Initialize quantum security components
        self.quantum_crypto = PostQuantumCrypto(QUANTUM_CONFIG['encryption'])
        self.quantum_key_dist = QuantumKeyDistribution(QUANTUM_CONFIG['key_distribution'])
        
        # Connect to blockchains
        self._initialize_connections()
        
        logger.info("System initialization complete")
    
    def _initialize_connections(self):
        """Establish connections to blockchain networks."""
        # Connect to private blockchain
        if not self.private_blockchain.connect():
            logger.error("Failed to connect to private blockchain")
        
        # Connect to public blockchain
        if not self.public_blockchain.connect():
            logger.error("Failed to connect to public blockchain")
    
    def process_iot_data(self, data: Union[Dict, List[Dict]]) -> Dict[str, Any]:
        """
        Process incoming IoT data through the full pipeline.
        
        Args:
            data: Raw IoT data (single record or batch)
            
        Returns:
            Processing results and status
        """
        try:
            logger.info(f"Processing IoT data: {len(data) if isinstance(data, list) else 1} records")
            
            # Convert to list if single record
            data_list = data if isinstance(data, list) else [data]
            
            # Step 1: Preprocess the data
            preprocessed_data = [self.data_processor.process(item) for item in data_list]
            
            # Step 2: Filter data through the gateway ML model
            # Only data deemed necessary will enter the private blockchain
            filtered_data = []
            for item in preprocessed_data:
                is_needed, confidence = self.gateway_filter.is_data_needed(item)
                if is_needed:
                    filtered_data.append({
                        'data': item,
                        'confidence': confidence
                    })
            
            # Step 3: Store necessary data in private blockchain with quantum security
            stored_items = []
            for item in filtered_data:
                # Generate a unique key for the data
                data_key = f"iot_data_{int(time.time())}_{len(stored_items)}"
                
                # Apply quantum encryption before storage
                if SYSTEM_CONFIG.get('enable_quantum_security', True):
                    # Get or generate encryption keys
                    sender_id = item['data'].get('device_id', 'unknown_device')
                    receiver_id = 'private_blockchain'
                    
                    # Ensure quantum key is established
                    qkd_key_id = self.quantum_key_dist.establish_key(sender_id, receiver_id)
                    if not qkd_key_id:
                        logger.warning(f"Could not establish quantum key for {sender_id}")
                        # Proceed without quantum security as fallback
                    else:
                        # Get the shared key
                        shared_key = self.quantum_key_dist.get_shared_key(sender_id, receiver_id)
                        
                        # Generate keypair for this transaction
                        public_key, private_key = self.quantum_crypto.generate_keypair(f"{sender_id}_{data_key}")
                        
                        # Encrypt the data
                        encrypted_data = self.quantum_crypto.encrypt(str(item['data']), public_key)
                        
                        # Store the encrypted data
                        self.private_blockchain.store_data(
                            channel='medical_data',  # Assuming medical data for this example
                            key=data_key,
                            data={
                                'encrypted_data': encrypted_data.hex(),
                                'public_key': public_key,
                                'metadata': {
                                    'device_id': sender_id,
                                    'timestamp': time.time(),
                                    'confidence': item['confidence']
                                }
                            }
                        )
                else:
                    # Store unencrypted data if quantum security is disabled
                    self.private_blockchain.store_data(
                        channel='medical_data',
                        key=data_key,
                        data=item['data']
                    )
                
                stored_items.append(data_key)
            
            return {
                'status': 'success',
                'total_records': len(data_list),
                'filtered_records': len(filtered_data),
                'stored_records': len(stored_items),
                'stored_keys': stored_items
            }
        except Exception as e:
            logger.error(f"Error processing IoT data: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def handle_data_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a data access request from the public blockchain.
        
        Args:
            request: Data request details
            
        Returns:
            Response with filtered data or error
        """
        try:
            logger.info(f"Handling data request: {request.get('request_id', 'unknown')}")
            
            # Step 1: Validate the request
            requester_id = request.get('requester_id')
            data_type = request.get('data_type')
            purpose = request.get('purpose')
            access_level = request.get('access_level', 'public')
            
            if not all([requester_id, data_type]):
                return {
                    'status': 'error',
                    'message': 'Missing required request parameters'
                }
            
            # Step 2: Create a request record on the public blockchain
            request_id = self.public_blockchain.request_data_access(
                requester_id=requester_id,
                data_type=data_type,
                purpose=purpose,
                access_level=access_level
            )
            
            if not request_id:
                return {
                    'status': 'error',
                    'message': 'Failed to register data request on public blockchain'
                }
            
            # Step 3: Query relevant data from private blockchain
            query_params = {'data_type': data_type}
            if 'filters' in request:
                # Add additional filters from the request
                query_params.update(request['filters'])
                
            private_data = self.private_blockchain.query_data(
                channel='medical_data',  # Assuming medical data channel
                query=query_params
            )
            
            if not private_data:
                return {
                    'status': 'success',
                    'message': 'No matching data found',
                    'request_id': request_id,
                    'data': []
                }
            
            # Step 4: Use ML privacy filter to determine what data can be shared
            request_context = {
                'requester_id': requester_id,
                'purpose': purpose,
                'access_level': access_level,
                'request_id': request_id
            }
            
            shareable_data = self.privacy_filter.filter_shareable_data(
                data=private_data,
                request_context=request_context
            )
            
            # Step 5: Store the filtered data on the public blockchain
            shared_data_id = self.public_blockchain.store_non_critical_data(
                data_type=data_type,
                data={
                    'request_id': request_id,
                    'filtered_data': shareable_data.to_dict(orient='records'),
                    'timestamp': time.time()
                }
            )
            
            return {
                'status': 'success',
                'request_id': request_id,
                'data_id': shared_data_id,
                'record_count': len(shareable_data)
            }
        except Exception as e:
            logger.error(f"Error handling data request: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def simulate_full_workflow(self, sample_data: List[Dict[str, Any]], 
                              sample_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate the full system workflow for demonstration purposes.
        
        Args:
            sample_data: Sample IoT data
            sample_request: Sample data access request
            
        Returns:
            Results of the simulation
        """
        results = {
            'iot_processing': None,
            'data_request': None
        }
        
        # Step 1: Process IoT data
        logger.info("Starting simulation: Processing IoT data")
        iot_result = self.process_iot_data(sample_data)
        results['iot_processing'] = iot_result
        
        # Step 2: Handle data access request
        logger.info("Simulation continuing: Handling data access request")
        request_result = self.handle_data_request(sample_request)
        results['data_request'] = request_result
        
        logger.info("Simulation complete")
        return results


# If running as main script, initialize the system
if __name__ == "__main__":
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(SYSTEM_CONFIG.get('log_file_path', './logs/system.log'))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    logger.info("Initializing Hybrid Blockchain System")
    
    # Initialize the system
    system = SystemOrchestrator()
    
    # Run a simple test if desired
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        logger.info("Running system test")
        
        # Sample IoT data (medical)
        sample_data = [
            {
                'device_id': 'med-sensor-001',
                'data_type': 'medical',
                'timestamp': time.time(),
                'field': 'heart_rate',
                'value': 72,
                'patient_id': 'P12345',
                'priority': 'normal'
            },
            {
                'device_id': 'med-sensor-002',
                'data_type': 'medical',
                'timestamp': time.time(),
                'field': 'blood_pressure',
                'value': '120/80',
                'patient_id': 'P12345',
                'priority': 'normal'
            },
            {
                'device_id': 'med-sensor-003',
                'data_type': 'medical',
                'timestamp': time.time(),
                'field': 'hiv_status',
                'value': 'positive',
                'patient_id': 'P12345',
                'priority': 'critical'
            }
        ]
        
        # Sample data request
        sample_request = {
            'requester_id': 'research_lab_123',
            'data_type': 'medical',
            'purpose': 'anonymized research',
            'access_level': 'researcher',
            'filters': {
                'patient_id': 'P12345'
            }
        }
        
        # Run the simulation
        results = system.simulate_full_workflow(sample_data, sample_request)
        
        # Print results
        logger.info(f"Test results: {results}")

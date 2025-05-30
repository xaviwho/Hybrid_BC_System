"""
System test script for the Hybrid Blockchain-based Incognito Data Sharing System.

This script tests the core functionality of the system with real data.
"""

import os
import sys
import json
import time
import logging
import pandas as pd
from typing import Dict, Any, List

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import system components
from api.system_orchestrator import SystemOrchestrator
from config.system_config import SYSTEM_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_test_data(file_path: str) -> List[Dict[str, Any]]:
    """
    Load test data from a file.
    
    Args:
        file_path: Path to the test data file
        
    Returns:
        List of data records
    """
    if file_path.endswith('.json'):
        with open(file_path, 'r') as f:
            return json.load(f)
    elif file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
        return df.to_dict(orient='records')
    else:
        raise ValueError(f"Unsupported file format: {file_path}")


def test_iot_data_processing(system: SystemOrchestrator, test_data: List[Dict[str, Any]]):
    """
    Test IoT data processing functionality.
    
    Args:
        system: SystemOrchestrator instance
        test_data: Test data records
    """
    logger.info("Testing IoT data processing...")
    
    # Process the test data
    result = system.process_iot_data(test_data)
    
    # Log results
    logger.info(f"IoT processing results: {result}")
    
    # Validate results
    if result['status'] == 'success':
        logger.info(f"Successfully processed {result['total_records']} records")
        logger.info(f"Filtered records: {result['filtered_records']}")
        logger.info(f"Stored records: {result['stored_records']}")
        
        if result['stored_records'] > 0:
            logger.info("IoT data processing test: PASSED")
        else:
            logger.warning("No records were stored in the blockchain")
            logger.info("IoT data processing test: PARTIAL PASS")
    else:
        logger.error(f"Failed to process IoT data: {result.get('message', 'Unknown error')}")
        logger.info("IoT data processing test: FAILED")


def test_data_request(system: SystemOrchestrator, test_request: Dict[str, Any]):
    """
    Test data request functionality.
    
    Args:
        system: SystemOrchestrator instance
        test_request: Test request parameters
    """
    logger.info("Testing data request handling...")
    
    # Handle the test request
    result = system.handle_data_request(test_request)
    
    # Log results
    logger.info(f"Data request results: {result}")
    
    # Validate results
    if result['status'] == 'success':
        logger.info(f"Successfully created request {result['request_id']}")
        
        if 'data_id' in result:
            logger.info(f"Data shared with ID: {result['data_id']}")
            logger.info(f"Records shared: {result.get('record_count', 0)}")
            logger.info("Data request test: PASSED")
        else:
            logger.warning("Request created but no data was shared")
            logger.info("Data request test: PARTIAL PASS")
    else:
        logger.error(f"Failed to handle data request: {result.get('message', 'Unknown error')}")
        logger.info("Data request test: FAILED")


def test_full_workflow(system: SystemOrchestrator, test_data: List[Dict[str, Any]], test_request: Dict[str, Any]):
    """
    Test the full system workflow.
    
    Args:
        system: SystemOrchestrator instance
        test_data: Test data records
        test_request: Test request parameters
    """
    logger.info("Testing full system workflow...")
    
    # Run the full workflow simulation
    result = system.simulate_full_workflow(test_data, test_request)
    
    # Log results
    logger.info("Full workflow results:")
    logger.info(f"IoT processing: {result['iot_processing']}")
    logger.info(f"Data request: {result['data_request']}")
    
    # Validate results
    iot_success = result['iot_processing']['status'] == 'success'
    request_success = result['data_request']['status'] == 'success'
    
    if iot_success and request_success:
        logger.info("Full system workflow test: PASSED")
    elif iot_success or request_success:
        logger.info("Full system workflow test: PARTIAL PASS")
    else:
        logger.info("Full system workflow test: FAILED")


def main():
    """Main test function."""
    logger.info("Starting system tests...")
    
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(SYSTEM_CONFIG.get('log_file_path', './logs/system.log'))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Create test data directory if it doesn't exist
    test_data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(test_data_dir):
        os.makedirs(test_data_dir)
        logger.info(f"Created test data directory: {test_data_dir}")
        logger.info("Please add test data files to this directory")
        return
    
    # Check for test data files
    test_files = [f for f in os.listdir(test_data_dir) if f.endswith(('.json', '.csv'))]
    
    if not test_files:
        logger.error(f"No test data files found in {test_data_dir}")
        logger.info("Please add test data files (JSON or CSV) to run tests")
        return
    
    # Initialize the system
    system = SystemOrchestrator()
    
    # Choose a test file
    test_file = os.path.join(test_data_dir, test_files[0])
    logger.info(f"Using test data from: {test_file}")
    
    # Load test data
    try:
        test_data = load_test_data(test_file)
        logger.info(f"Loaded {len(test_data)} test records")
    except Exception as e:
        logger.error(f"Failed to load test data: {str(e)}")
        return
    
    # Create a test request
    test_request = {
        'requester_id': 'test_requester',
        'data_type': 'medical',
        'purpose': 'system testing',
        'access_level': 'researcher'
    }
    
    # Run tests
    try:
        # Test IoT data processing
        test_iot_data_processing(system, test_data)
        
        # Test data request
        test_data_request(system, test_request)
        
        # Test full workflow
        test_full_workflow(system, test_data, test_request)
        
        logger.info("All tests completed")
    except Exception as e:
        logger.error(f"Test execution failed: {str(e)}")


if __name__ == "__main__":
    main()

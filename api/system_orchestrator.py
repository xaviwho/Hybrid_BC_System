"""System orchestrator for the Hybrid Blockchain-based Incognito Data Sharing System.

This module integrates all system components (ML, blockchains, quantum security)
and orchestrates the data flow between them."""

import logging
import os
import sys
import time
import json
import requests
import uuid
from typing import Dict, Any, List, Optional, Union

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import system configuration
from config.system_config import (
    ML_CONFIG, PRIVATE_BLOCKCHAIN_CONFIG, PUBLIC_BLOCKCHAIN_CONFIG, 
    QUANTUM_CONFIG, SYSTEM_CONFIG
)

# For web server
from flask import Flask, request, jsonify

# Configure logging
os.makedirs('logs', exist_ok=True)  # Create logs directory if it doesn't exist
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create Flask application
app = Flask(__name__)

# Simulated data storage for demonstration
iot_data_store = {}
data_access_requests = {}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify the service is running."""
    logger.info("Health check requested")
    return jsonify({
        "status": "healthy",
        "components": {
            "ml_gateway": check_service_health(ML_CONFIG['gateway_filter']['api_endpoint']),
            "ml_privacy": check_service_health(ML_CONFIG['privacy_filter']['api_endpoint']),
            "ethereum": check_ethereum_health(),
            "hyperledger": "connected",  # Simplified check
            "quantum_security": QUANTUM_CONFIG['enabled']
        },
        "version": "1.0.0"
    })

@app.route('/submit-iot-data', methods=['POST'])
def submit_iot_data():
    """Submit IoT data to the system for processing and storage."""
    try:
        data = request.json
        logger.info(f"Received IoT data submission: {data}")
        
        # Generate a unique ID for this data
        data_id = str(uuid.uuid4())
        
        # Store the data temporarily
        iot_data_store[data_id] = {
            "data": data,
            "timestamp": time.time(),
            "status": "received"
        }
        
        # Simulate ML gateway filter processing
        sensitivity = classify_data_sensitivity(data)
        
        # Update data record with classification results
        iot_data_store[data_id]["sensitivity_level"] = sensitivity
        iot_data_store[data_id]["status"] = "classified"
        
        # Simulate storing in Hyperledger Fabric (private blockchain)
        hyperledger_response = store_in_hyperledger(data_id, data, sensitivity)
        
        # Simulate registering a reference in Ethereum (public blockchain)
        ethereum_response = register_in_ethereum(data_id, sensitivity)
        
        return jsonify({
            "status": "success",
            "data_id": data_id,
            "sensitivity": sensitivity,
            "storage_status": {
                "hyperledger": hyperledger_response,
                "ethereum": ethereum_response
            }
        })
    except Exception as e:
        logger.error(f"Error processing IoT data: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/request-data-access', methods=['POST'])
def request_data_access():
    """Create a data access request via the public blockchain."""
    try:
        request_data = request.json
        logger.info(f"Received data access request: {request_data}")
        
        # Generate a request ID
        request_id = str(uuid.uuid4())
        
        # Store the request
        data_access_requests[request_id] = {
            "requester": request_data.get("requester", "unknown"),
            "data_type": request_data.get("data_type", "all"),
            "purpose": request_data.get("purpose", ""),
            "access_level": request_data.get("access_level", "public"),
            "status": "pending",
            "timestamp": time.time()
        }
        
        # Simulate creating a request on Ethereum
        ethereum_request = create_ethereum_request(request_id, request_data)
        
        # Simulate ML privacy filter evaluation
        evaluation_result = evaluate_access_request(request_id, request_data)
        
        # Update request status based on evaluation
        data_access_requests[request_id]["status"] = evaluation_result["decision"]
        data_access_requests[request_id]["evaluation"] = evaluation_result
        
        return jsonify({
            "status": "success",
            "request_id": request_id,
            "evaluation": evaluation_result,
            "ethereum_tx": ethereum_request
        })
    except Exception as e:
        logger.error(f"Error processing access request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/system-status', methods=['GET'])
def system_status():
    """Get the status of the entire hybrid blockchain system."""
    return jsonify({
        "status": "operational",
        "components": {
            "ml_gateway": {
                "status": "running",
                "endpoint": ML_CONFIG['gateway_filter']['api_endpoint']
            },
            "ml_privacy": {
                "status": "running",
                "endpoint": ML_CONFIG['privacy_filter']['api_endpoint']
            },
            "ethereum": {
                "status": "connected",
                "endpoint": PUBLIC_BLOCKCHAIN_CONFIG['rpc_endpoint']
            },
            "hyperledger": {
                "status": "connected",
                "endpoint": PRIVATE_BLOCKCHAIN_CONFIG['peer_endpoint']
            },
            "quantum_security": {
                "status": "enabled" if QUANTUM_CONFIG['enabled'] else "disabled",
                "algorithm": QUANTUM_CONFIG['algorithm']
            }
        },
        "data_stats": {
            "total_iot_data": len(iot_data_store),
            "access_requests": len(data_access_requests)
        }
    })

# Helper functions
def check_service_health(endpoint):
    """Check if a service is healthy by making a request to its health endpoint."""
    try:
        response = requests.get(f"{endpoint}/health", timeout=2)
        if response.status_code == 200:
            return "healthy"
        return "unhealthy"
    except:
        return "unreachable"

def check_ethereum_health():
    """Check if Ethereum node is reachable."""
    try:
        # Simple RPC call to check if node is responding
        response = requests.post(
            PUBLIC_BLOCKCHAIN_CONFIG['rpc_endpoint'],
            json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
            timeout=2
        )
        if response.status_code == 200:
            return "connected"
        return "error"
    except:
        return "unreachable"

def classify_data_sensitivity(data):
    """Simulate ML classification of data sensitivity."""
    # In a real implementation, this would call the ML gateway filter API
    sensitivities = ["public", "restricted", "confidential"]
    # Simple mock classification based on data content
    if "medical" in str(data).lower() or "health" in str(data).lower():
        return "confidential"
    elif "personal" in str(data).lower() or "private" in str(data).lower():
        return "restricted"
    return "public"

def store_in_hyperledger(data_id, data, sensitivity):
    """Simulate storing data in Hyperledger Fabric."""
    # In a real implementation, this would call the Hyperledger Fabric API
    return {
        "status": "success",
        "blockchain": "hyperledger",
        "tx_id": f"hlf_{data_id[:8]}"
    }

def register_in_ethereum(data_id, sensitivity):
    """Simulate registering a data reference in Ethereum."""
    # In a real implementation, this would call the Ethereum API
    return {
        "status": "success",
        "blockchain": "ethereum",
        "tx_hash": f"0x{data_id.replace('-', '')}{'0'*20}"
    }

def create_ethereum_request(request_id, request_data):
    """Simulate creating a data access request on Ethereum."""
    # In a real implementation, this would call the Ethereum API
    return {
        "status": "submitted",
        "tx_hash": f"0x{request_id.replace('-', '')}{'0'*20}"
    }

def evaluate_access_request(request_id, request_data):
    """Simulate ML privacy filter evaluation of an access request."""
    # In a real implementation, this would call the ML privacy filter API
    requester = request_data.get("requester", "unknown")
    access_level = request_data.get("access_level", "public")
    purpose = request_data.get("purpose", "")
    
    # Simple mock decision logic
    if access_level == "public":
        decision = "approved"
        confidence = 0.95
    elif "research" in purpose.lower() and access_level == "restricted":
        decision = "approved"
        confidence = 0.85
    elif access_level == "confidential":
        decision = "denied"
        confidence = 0.90
    else:
        decision = "pending_review"
        confidence = 0.60
        
    return {
        "decision": decision,
        "confidence": confidence,
        "requester_validated": True,
        "data_availability": "available"
    }

# Start the application
if __name__ == "__main__":
    logger.info("System Orchestrator API is running")
    app.run(host='0.0.0.0', port=8000, debug=False)

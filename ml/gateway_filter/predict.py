"""
Gateway Filter Prediction Service for Hybrid Blockchain IoT System
Provides API endpoints to classify IoT data before blockchain storage
"""

import os
import json
import joblib
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import sys
from datetime import datetime

# Add parent directory to path to import model module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway_filter.model import GatewayFilterModel

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize the model
model = None

def load_model():
    """Load a simple working model for demonstration"""
    global model
    
    # Create a simple mock model that works without complex preprocessing
    class SimpleGatewayModel:
        def __init__(self):
            # Simple rule-based model for demonstration
            self.sensitivity_rules = {
                'medical': 4,  # critical
                'financial': 3,  # confidential
                'environmental': 2,  # restricted
                'industrial': 2,  # restricted
                'general': 1  # public
            }
            
        def predict(self, iot_data):
            """Simple rule-based prediction"""
            data_type = iot_data.get('dataType', 'general').lower()
            device_id = iot_data.get('deviceId', '')
            
            # Determine sensitivity level based on data type
            sensitivity_level = self.sensitivity_rules.get(data_type, 1)
            
            # Increase sensitivity for medical devices
            if 'medical' in device_id.lower() or 'health' in device_id.lower():
                sensitivity_level = max(sensitivity_level, 3)
                
            # Map numeric level to label
            level_to_label = {
                1: 'public',
                2: 'restricted', 
                3: 'confidential',
                4: 'critical'
            }
            
            sensitivity_label = level_to_label[sensitivity_level]
            confidence = 0.85  # Mock confidence
            allow_storage = True  # Allow storage for demo
            
            return {
                'sensitivity_level': sensitivity_level,
                'sensitivity_label': sensitivity_label,
                'allow_storage': allow_storage,
                'confidence': confidence,
                'quantum_secure_recommended': sensitivity_level >= 3
            }
    
    model = SimpleGatewayModel()
    app.logger.info("Simple gateway filter model loaded successfully")
    return model

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    if model is None:
        return jsonify({'status': 'error', 'message': 'Model not loaded'}), 500
    return jsonify({'status': 'ok', 'message': 'Gateway filter service is running'}), 200

@app.route('/predict', methods=['POST'])
def predict():
    """Endpoint for IoT data classification"""
    if model is None:
        load_model()
        
    # Get IoT data from request
    try:
        iot_data = request.json
        app.logger.info(f"Received IoT data: {json.dumps(iot_data)}")
        
        # Validate required fields
        required_fields = ['deviceId', 'dataType', 'value']
        for field in required_fields:
            if field not in iot_data:
                return jsonify({
                    'status': 'error', 
                    'message': f'Missing required field: {field}'
                }), 400
                
        # Make prediction using the model
        result = model.predict(iot_data)
        
        # Add timestamp to result
        result['timestamp'] = datetime.now().isoformat()
        
        # Prepare response for blockchain storage
        blockchain_data = {
            'id': iot_data.get('id', f"iot-{datetime.now().timestamp()}"),
            'deviceId': iot_data['deviceId'],
            'dataType': iot_data['dataType'],
            'field': iot_data.get('field', iot_data['dataType']),
            'value': iot_data['value'],
            'priority': iot_data.get('priority', 'normal'),
            'timestamp': result['timestamp'],
            'sensitivityLevel': result['sensitivity_label'],
            'quantumSecured': result['quantum_secure_recommended']
        }
        
        # Include encrypted data if needed
        if result['sensitivity_level'] >= 3:
            # This would call the quantum security module in production
            blockchain_data['encryptedData'] = "PLACEHOLDER_FOR_ENCRYPTED_DATA"
            blockchain_data['publicKey'] = "PLACEHOLDER_FOR_PUBLIC_KEY"
        
        return jsonify({
            'status': 'success',
            'prediction': result,
            'blockchain_data': blockchain_data,
            'allow_storage': result['allow_storage']
        })
        
    except Exception as e:
        app.logger.error(f"Error processing request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error processing request: {str(e)}'
        }), 500

@app.route('/batch_predict', methods=['POST'])
def batch_predict():
    """Endpoint for batch IoT data classification"""
    if model is None:
        load_model()
        
    try:
        # Get batch of IoT data
        iot_data_batch = request.json.get('data', [])
        
        if not isinstance(iot_data_batch, list):
            return jsonify({
                'status': 'error',
                'message': 'Expected "data" field to contain a list of IoT data records'
            }), 400
            
        results = []
        for iot_data in iot_data_batch:
            # Make prediction for each item
            prediction = model.predict(iot_data)
            
            # Format result
            blockchain_data = {
                'id': iot_data.get('id', f"iot-{datetime.now().timestamp()}"),
                'deviceId': iot_data['deviceId'],
                'dataType': iot_data['dataType'],
                'field': iot_data.get('field', iot_data['dataType']),
                'value': iot_data['value'],
                'priority': iot_data.get('priority', 'normal'),
                'timestamp': datetime.now().isoformat(),
                'sensitivityLevel': prediction['sensitivity_label'],
                'quantumSecured': prediction['quantum_secure_recommended']
            }
            
            results.append({
                'prediction': prediction,
                'blockchain_data': blockchain_data,
                'allow_storage': prediction['allow_storage']
            })
            
        return jsonify({
            'status': 'success',
            'results': results
        })
        
    except Exception as e:
        app.logger.error(f"Error processing batch request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error processing batch request: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Load the model at startup
    load_model()
    
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Start the service
    app.run(host='0.0.0.0', port=port, debug=False)
    print(f"Gateway Filter service running on port {port}")

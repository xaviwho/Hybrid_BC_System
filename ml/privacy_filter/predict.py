"""
Privacy Filter Prediction Service for Hybrid Blockchain IoT System
Handles data access requests from the public blockchain and determines what data can be shared
"""

import os
import json
import joblib
from flask import Flask, request, jsonify
import pandas as pd
import numpy as np
import sys
from datetime import datetime

# Add parent directory to path to import sensitivity classifier
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from privacy_filter.sensitivity_classifier import SensitivityClassifier

app = Flask(__name__)

# Initialize the classifier
classifier = None

def load_classifier():
    """Load the trained sensitivity classifier"""
    global classifier
    classifier = SensitivityClassifier()
    classifier.load()
    app.logger.info("Privacy filter classifier loaded successfully")
    return classifier

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    if classifier is None:
        return jsonify({'status': 'error', 'message': 'Classifier not loaded'}), 500
    return jsonify({'status': 'ok', 'message': 'Privacy filter service is running'}), 200

@app.route('/filter_data', methods=['POST'])
def filter_data():
    """Filter IoT data based on sensitivity and requester access level"""
    if classifier is None:
        load_classifier()
        
    try:
        # Get request data
        request_data = request.json
        
        # Validate required fields
        required_fields = ['iot_data', 'requester_access_level']
        for field in required_fields:
            if field not in request_data:
                return jsonify({
                    'status': 'error', 
                    'message': f'Missing required field: {field}'
                }), 400
                
        iot_data = request_data['iot_data']
        access_level = request_data['requester_access_level']
        
        # Determine shareable fields
        shareable_data = classifier.determine_shareable_fields(iot_data, access_level)
        
        # Add request metadata
        result = {
            'request_id': request_data.get('request_id', f"req-{datetime.now().timestamp()}"),
            'timestamp': datetime.now().isoformat(),
            'requester_access_level': access_level,
            'data_sensitivity': iot_data.get('sensitivityLevel', 'unknown'),
            'shareable_data': shareable_data
        }
        
        return jsonify({
            'status': 'success',
            'result': result
        })
        
    except Exception as e:
        app.logger.error(f"Error processing request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error processing request: {str(e)}'
        }), 500

@app.route('/batch_filter', methods=['POST'])
def batch_filter():
    """Filter multiple IoT data records based on sensitivity and requester access level"""
    if classifier is None:
        load_classifier()
        
    try:
        # Get batch request data
        request_data = request.json
        
        # Validate required fields
        required_fields = ['iot_data_batch', 'requester_access_level']
        for field in required_fields:
            if field not in request_data:
                return jsonify({
                    'status': 'error', 
                    'message': f'Missing required field: {field}'
                }), 400
                
        iot_data_batch = request_data['iot_data_batch']
        access_level = request_data['requester_access_level']
        
        # Process each item in batch
        results = []
        for iot_data in iot_data_batch:
            # Determine shareable fields
            shareable_data = classifier.determine_shareable_fields(iot_data, access_level)
            
            # Add to results
            results.append({
                'data_id': iot_data.get('id', ''),
                'data_sensitivity': iot_data.get('sensitivityLevel', 'unknown'),
                'shareable_data': shareable_data
            })
        
        # Add batch request metadata
        response = {
            'request_id': request_data.get('request_id', f"batch-{datetime.now().timestamp()}"),
            'timestamp': datetime.now().isoformat(),
            'requester_access_level': access_level,
            'total_records': len(results),
            'results': results
        }
        
        return jsonify({
            'status': 'success',
            'response': response
        })
        
    except Exception as e:
        app.logger.error(f"Error processing batch request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error processing batch request: {str(e)}'
        }), 500

@app.route('/analyze_request', methods=['POST'])
def analyze_request():
    """Analyze a data access request from the public blockchain"""
    if classifier is None:
        load_classifier()
        
    try:
        # Get request data
        request_data = request.json
        
        # Validate required fields
        required_fields = ['request_type', 'requester_id', 'access_level', 'data_query']
        for field in required_fields:
            if field not in request_data:
                return jsonify({
                    'status': 'error', 
                    'message': f'Missing required field: {field}'
                }), 400
                
        # Extract request details
        request_type = request_data['request_type']
        requester_id = request_data['requester_id']
        access_level = request_data['access_level']
        data_query = request_data['data_query']
        
        # Analyze the request
        # In a production system, this would implement more sophisticated logic
        # to detect suspicious or potentially malicious requests
        
        risk_score = 0
        risk_factors = []
        
        # Check for suspicious requester IDs
        if requester_id.startswith('anonymous'):
            risk_score += 20
            risk_factors.append('Anonymous requester')
            
        # Check for suspicious query patterns
        if 'all' in data_query.lower():
            risk_score += 15
            risk_factors.append('Broad data request')
            
        # Check access level vs request type
        if access_level == 'public' and request_type == 'batch':
            risk_score += 10
            risk_factors.append('Public access requesting batch data')
            
        # Final risk assessment
        risk_assessment = 'low'
        if risk_score > 30:
            risk_assessment = 'high'
        elif risk_score > 15:
            risk_assessment = 'medium'
            
        # Recommendation
        recommendation = 'approve'
        if risk_assessment == 'high':
            recommendation = 'reject'
        elif risk_assessment == 'medium':
            recommendation = 'review'
            
        # Prepare response
        analysis = {
            'request_id': request_data.get('request_id', f"analysis-{datetime.now().timestamp()}"),
            'timestamp': datetime.now().isoformat(),
            'risk_score': risk_score,
            'risk_assessment': risk_assessment,
            'risk_factors': risk_factors,
            'recommendation': recommendation,
            'max_sensitivity_to_share': 'public' if risk_assessment == 'high' else 
                                        'restricted' if risk_assessment == 'medium' else
                                        access_level
        }
        
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
        
    except Exception as e:
        app.logger.error(f"Error analyzing request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error analyzing request: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Load the classifier at startup
    load_classifier()
    
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5001))
    
    # Start the service
    app.run(host='0.0.0.0', port=port, debug=False)
    print(f"Privacy Filter service running on port {port}")

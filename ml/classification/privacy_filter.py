"""
Privacy filter module for data sharing.

This module classifies data from the private blockchain to determine
what can be shared when requested through the public blockchain.
"""

import numpy as np
import pandas as pd
import joblib
import os
import logging
from typing import Dict, Any, Union, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PrivacyFilter:
    """
    Privacy filter that determines which private blockchain data can be shared
    when requested through the public blockchain interface.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the privacy filter.
        
        Args:
            config: Configuration dictionary with model parameters
        """
        self.config = config
        self.model_path = config.get('model_path', './models/privacy_filter.pkl')
        self.sensitivity_levels = config.get('sensitivity_levels', 
                                           ['public', 'restricted', 'confidential', 'critical'])
        self.default_level = config.get('default_level', 'critical')
        self.model = None
        
        # Load model if it exists
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                logger.info(f"Loaded privacy filter model from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load model: {str(e)}")
        else:
            logger.warning(f"Model file not found at {self.model_path}. Using fallback rules.")
    
    def classify_data_sensitivity(self, data: Union[pd.DataFrame, Dict, List]) -> Tuple[str, float]:
        """
        Classify the sensitivity level of data.
        
        Args:
            data: Data to classify
            
        Returns:
            Tuple of (sensitivity_level: str, confidence: float)
        """
        # Convert to DataFrame if not already
        if not isinstance(data, pd.DataFrame):
            data_df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)
        else:
            data_df = data.copy()
            
        # If model exists, use it for prediction
        if self.model is not None:
            try:
                # Predict sensitivity level
                predicted_class = self.model.predict(data_df)[0]
                probabilities = self.model.predict_proba(data_df)[0]
                confidence = max(probabilities)
                
                # Map the predicted class index to sensitivity level
                sensitivity_level = self.sensitivity_levels[predicted_class] \
                                   if predicted_class < len(self.sensitivity_levels) \
                                   else self.default_level
                
                return sensitivity_level, float(confidence)
            except Exception as e:
                logger.error(f"Prediction error: {str(e)}")
                # Fallback to rule-based classification
                return self._rule_based_classification(data_df)
        else:
            # Fallback to rule-based classification
            return self._rule_based_classification(data_df)
    
    def _rule_based_classification(self, data: pd.DataFrame) -> Tuple[str, float]:
        """
        Rule-based fallback when model is not available.
        
        Args:
            data: Data to classify
            
        Returns:
            Tuple of (sensitivity_level: str, confidence: float)
        """
        # Default to the most restrictive level with medium confidence
        sensitivity_level = self.default_level
        confidence = 0.7
        
        # Example rules for medical data
        if 'data_type' in data.columns:
            data_type = str(data['data_type'].iloc[0]).lower()
            
            if data_type == 'medical':
                # Medical data specific rules
                if 'field' in data.columns:
                    field = str(data['field'].iloc[0]).lower()
                    
                    if field in ['heart_rate', 'steps', 'temperature', 'oxygen_level']:
                        sensitivity_level = 'public'
                        confidence = 0.9
                    elif field in ['medication', 'diagnosis_general']:
                        sensitivity_level = 'restricted'
                        confidence = 0.85
                    elif field in ['genetic', 'hiv_status', 'mental_health']:
                        sensitivity_level = 'critical'
                        confidence = 0.95
                    else:
                        sensitivity_level = 'confidential'
                        confidence = 0.8
            
            # Add more rules for different data types
            elif data_type == 'environmental':
                sensitivity_level = 'public'
                confidence = 0.95
                
            elif data_type == 'financial':
                sensitivity_level = 'confidential'
                confidence = 0.9
                
        # Add more sophisticated rules based on your domain knowledge
                
        return sensitivity_level, confidence
    
    def filter_shareable_data(self, data: pd.DataFrame, request_context: Dict[str, Any]) -> pd.DataFrame:
        """
        Filter the data to only include shareable fields based on request context.
        
        Args:
            data: Data from private blockchain to be potentially shared
            request_context: Information about the request and requester
            
        Returns:
            DataFrame with only shareable data
        """
        # Make a copy to avoid modifying the original
        result = data.copy()
        
        # Get the access level of the requester
        requester_access_level = request_context.get('access_level', 'public')
        
        # Define which levels can access which sensitivity levels
        access_permissions = {
            'public': ['public'],
            'researcher': ['public', 'restricted'],
            'doctor': ['public', 'restricted', 'confidential'],
            'admin': ['public', 'restricted', 'confidential', 'critical']
        }
        
        allowed_sensitivity_levels = access_permissions.get(requester_access_level, ['public'])
        
        # Process each row to determine which fields can be shared
        redacted_rows = []
        for idx, row in result.iterrows():
            redacted_row = {}
            
            # Process each field in the row
            for field_name, field_value in row.items():
                # Classify the sensitivity of this specific field
                field_data = {'field': field_name, 'value': field_value}
                if 'data_type' in row:
                    field_data['data_type'] = row['data_type']
                    
                sensitivity, _ = self.classify_data_sensitivity(field_data)
                
                # Include field if its sensitivity level is allowed
                if sensitivity in allowed_sensitivity_levels:
                    redacted_row[field_name] = field_value
                else:
                    redacted_row[field_name] = "[REDACTED]"
                    
            redacted_rows.append(redacted_row)
            
        return pd.DataFrame(redacted_rows)
    
    def update_model(self, training_data: pd.DataFrame, labels: List[str]):
        """
        Update the model with new training data.
        
        Args:
            training_data: Features for training
            labels: Target labels (sensitivity levels)
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import LabelEncoder
        
        logger.info("Training new privacy filter model")
        
        # Convert string labels to numeric
        label_encoder = LabelEncoder()
        label_encoder.fit(self.sensitivity_levels)
        numeric_labels = label_encoder.transform(labels)
        
        # Create a new model
        model = RandomForestClassifier(
            n_estimators=100, 
            max_depth=10, 
            random_state=42
        )
        
        # Train the model
        model.fit(training_data, numeric_labels)
        
        # Save the model
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(model, self.model_path)
        
        # Update the current model
        self.model = model
        
        logger.info(f"Model updated and saved to {self.model_path}")

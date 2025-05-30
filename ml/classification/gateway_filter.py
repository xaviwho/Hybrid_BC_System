"""
Gateway filter module for IoT data.

This module provides the functionality to classify incoming IoT data and 
determine which data should be stored in the private blockchain.
"""

import numpy as np
import pandas as pd
import joblib
from typing import Dict, Any, Union, List, Tuple
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GatewayFilter:
    """
    Gateway filter that determines which IoT data should enter the private blockchain.
    Acts as the first layer of security in the system.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the gateway filter.
        
        Args:
            config: Configuration dictionary with model parameters
        """
        self.config = config
        self.threshold = config.get('threshold', 0.75)
        self.model_path = config.get('model_path', './models/gateway_filter.pkl')
        self.model = None
        
        # Load model if it exists
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                logger.info(f"Loaded gateway filter model from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load model: {str(e)}")
        else:
            logger.warning(f"Model file not found at {self.model_path}. Using fallback rules.")
    
    def is_data_needed(self, data: Union[pd.DataFrame, Dict, List]) -> Tuple[bool, float]:
        """
        Determine if the data is needed for the private blockchain.
        
        Args:
            data: IoT data to evaluate
            
        Returns:
            Tuple of (is_needed: bool, confidence: float)
        """
        # Convert to DataFrame if not already
        if not isinstance(data, pd.DataFrame):
            data_df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)
        else:
            data_df = data.copy()
            
        # If model exists, use it for prediction
        if self.model is not None:
            try:
                # Get probability of being needed
                probabilities = self.model.predict_proba(data_df)
                # Assuming binary classification where class 1 is "needed"
                needed_probability = probabilities[:, 1] if probabilities.shape[1] > 1 else probabilities
                
                # Decision based on threshold
                is_needed = needed_probability >= self.threshold
                
                # Return boolean decision and confidence
                return bool(is_needed[0]), float(needed_probability[0])
            except Exception as e:
                logger.error(f"Prediction error: {str(e)}")
                # Fallback to rule-based decision
                return self._rule_based_decision(data_df)
        else:
            # Fallback to rule-based decision
            return self._rule_based_decision(data_df)
    
    def _rule_based_decision(self, data: pd.DataFrame) -> Tuple[bool, float]:
        """
        Rule-based fallback when model is not available.
        
        Args:
            data: IoT data to evaluate
            
        Returns:
            Tuple of (is_needed: bool, confidence: float)
        """
        # Check for indicators of critical data
        is_needed = False
        confidence = 0.5  # Default medium confidence
        
        # Example rules - customize based on your IoT data structure
        if 'priority' in data.columns and data['priority'].iloc[0] in ['high', 'critical']:
            is_needed = True
            confidence = 0.9
        
        if 'data_type' in data.columns and data['data_type'].iloc[0] in ['medical', 'security']:
            is_needed = True
            confidence = 0.95
            
        # Add more rules here based on your domain knowledge
            
        return is_needed, confidence
    
    def batch_filter(self, data_batch: pd.DataFrame) -> pd.DataFrame:
        """
        Filter a batch of IoT data and return only the data needed for private blockchain.
        
        Args:
            data_batch: Batch of IoT data
            
        Returns:
            DataFrame containing only the needed data
        """
        # Create a copy of the input data to avoid modifying the original
        result = data_batch.copy()
        
        # Add a column to store decisions and confidence
        result['is_needed'] = False
        result['confidence'] = 0.0
        
        # Process each row
        for idx, row in result.iterrows():
            is_needed, confidence = self.is_data_needed(row.to_dict())
            result.at[idx, 'is_needed'] = is_needed
            result.at[idx, 'confidence'] = confidence
            
        # Filter to keep only needed data
        filtered_data = result[result['is_needed']]
        
        logger.info(f"Filtered batch: {len(filtered_data)} out of {len(data_batch)} records were needed")
        return filtered_data
    
    def update_model(self, training_data: pd.DataFrame, labels: np.ndarray):
        """
        Update the model with new training data.
        
        Args:
            training_data: Features for training
            labels: Target labels (1 for needed, 0 for not needed)
        """
        from sklearn.ensemble import RandomForestClassifier
        
        logger.info("Training new gateway filter model")
        
        # Create a new model
        model = RandomForestClassifier(
            n_estimators=100, 
            max_depth=10, 
            random_state=42
        )
        
        # Train the model
        model.fit(training_data, labels)
        
        # Save the model
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(model, self.model_path)
        
        # Update the current model
        self.model = model
        
        logger.info(f"Model updated and saved to {self.model_path}")

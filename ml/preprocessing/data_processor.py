"""
Data preprocessing module for IoT data.

This module handles preprocessing of raw IoT data before it's passed to the ML models.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Union


class IoTDataProcessor:
    """Processes raw IoT data for machine learning models."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the data processor.
        
        Args:
            config: Configuration dictionary with preprocessing parameters
        """
        self.config = config
        self.supported_sensors = config.get('supported_sensors', [])
        
    def normalize_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize numerical data to a standard scale.
        
        Args:
            data: Input DataFrame with IoT sensor data
            
        Returns:
            Normalized DataFrame
        """
        # Copy the input data to avoid modifying the original
        result = data.copy()
        
        # Select only numeric columns for normalization
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        
        # Apply min-max scaling to numeric columns
        for col in numeric_cols:
            col_min = result[col].min()
            col_max = result[col].max()
            if col_max > col_min:  # Avoid division by zero
                result[col] = (result[col] - col_min) / (col_max - col_min)
                
        return result
    
    def handle_missing_values(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Handle missing values in the dataset.
        
        Args:
            data: Input DataFrame with potentially missing values
            
        Returns:
            DataFrame with missing values handled
        """
        result = data.copy()
        
        # For numerical columns, use median imputation
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            result[col].fillna(result[col].median(), inplace=True)
            
        # For categorical columns, use mode imputation
        categorical_cols = result.select_dtypes(include=['object', 'category']).columns
        for col in categorical_cols:
            result[col].fillna(result[col].mode()[0] if not result[col].mode().empty else "unknown", inplace=True)
            
        return result
    
    def extract_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Extract features from the raw data.
        
        Args:
            data: Input DataFrame with preprocessed IoT data
            
        Returns:
            DataFrame with extracted features
        """
        result = data.copy()
        
        # Add timestamp features if a timestamp column exists
        if 'timestamp' in result.columns:
            result['timestamp'] = pd.to_datetime(result['timestamp'])
            result['hour'] = result['timestamp'].dt.hour
            result['day_of_week'] = result['timestamp'].dt.dayofweek
            result['month'] = result['timestamp'].dt.month
            
        # Add device-specific features if device_id column exists
        if 'device_id' in result.columns:
            result['device_type'] = result['device_id'].apply(
                lambda x: str(x).split('-')[0] if '-' in str(x) else 'unknown'
            )
            
        return result
    
    def process(self, raw_data: Union[pd.DataFrame, Dict, List]) -> pd.DataFrame:
        """
        Main processing pipeline for IoT data.
        
        Args:
            raw_data: Raw IoT data (DataFrame, dict, or list)
            
        Returns:
            Processed DataFrame ready for ML models
        """
        # Convert to DataFrame if not already
        if not isinstance(raw_data, pd.DataFrame):
            data = pd.DataFrame(raw_data)
        else:
            data = raw_data.copy()
            
        # Apply processing steps
        data = self.handle_missing_values(data)
        data = self.normalize_data(data)
        data = self.extract_features(data)
        
        return data

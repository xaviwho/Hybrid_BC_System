"""
NSL KDD Dataset Preprocessor for Gateway Filter
This module transforms NSL KDD data for use in IoT traffic filtering
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import joblib
import os

class NSLKDDPreprocessor:
    def __init__(self):
        self.categorical_features = [1, 2, 3]  # protocol_type, service, flag (0-indexed)
        self.numeric_features = [0, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40]
        self.feature_names = self._load_feature_names()
        self.preprocessor = None
        self.label_mapping = {
            'normal': 'public',
            'back': 'restricted',
            'land': 'restricted',
            'neptune': 'restricted',
            'pod': 'restricted',
            'smurf': 'restricted',
            'teardrop': 'restricted',
            'ipsweep': 'confidential',
            'nmap': 'confidential',
            'portsweep': 'confidential', 
            'satan': 'confidential',
            'ftp_write': 'critical',
            'guess_passwd': 'critical',
            'imap': 'critical',
            'multihop': 'critical',
            'phf': 'critical',
            'spy': 'critical',
            'warezclient': 'critical',
            'warezmaster': 'critical',
            'buffer_overflow': 'critical',
            'loadmodule': 'critical',
            'perl': 'critical',
            'rootkit': 'critical'
        }
        self.sensitivity_levels = {
            'public': 1,
            'restricted': 2,
            'confidential': 3,
            'critical': 4
        }
        
    def _load_feature_names(self):
        """Load feature names from the feature_names.txt file"""
        file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'feature_names.txt')
        features = []
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    features.append(parts[1])
        return features
    
    def fit(self, data_path):
        """Fit preprocessor on the training data"""
        # Load data - assumes CSV format with no header
        df = pd.read_csv(data_path, header=None)
        
        # Keep only the needed columns for IoT gateway filtering
        # Focus on connection basics and traffic patterns
        key_columns = [0, 1, 2, 3, 4, 5, 22, 23, 24, 25, 31, 32, 41]  # duration, protocol, service, flag, bytes, traffic counts, etc.
        
        # Set up the preprocessing steps
        categorical_transformer = Pipeline(steps=[
            ('onehot', OneHotEncoder(handle_unknown='ignore'))
        ])
        
        numeric_transformer = Pipeline(steps=[
            ('scaler', StandardScaler())
        ])
        
        # Create preprocessor pipeline
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, [i for i in self.numeric_features if i in key_columns]),
                ('cat', categorical_transformer, [i for i in self.categorical_features if i in key_columns])
            ])
        
        # Fit the preprocessor
        self.preprocessor.fit(df.iloc[:, :-1])  # Exclude the class column
        
        return self
    
    def transform(self, data):
        """Transform NSL KDD data to features for model training/prediction"""
        if isinstance(data, str):
            # If a file path is provided
            df = pd.read_csv(data, header=None)
        else:
            # If a DataFrame is provided
            df = data
            
        # Apply the preprocessing transformations
        X_transformed = self.preprocessor.transform(df.iloc[:, :-1])
        
        # Get the class labels
        y = df.iloc[:, -1].values
        
        # Map attack types to sensitivity levels
        sensitivity_labels = np.array([self.label_mapping.get(label, 'public') for label in y])
        sensitivity_values = np.array([self.sensitivity_levels[label] for label in sensitivity_labels])
        
        return X_transformed, sensitivity_values, sensitivity_labels
    
    def transform_iot_data(self, iot_data):
        """Transform IoT data to match the NSL KDD feature space"""
        # Convert IoT data format to match NSL KDD features
        # This would extract relevant information from IoT payloads
        
        # Example mapping (this would need to be customized for actual IoT data):
        nsl_kdd_format = {
            0: iot_data.get('duration', 0),  # duration
            1: iot_data.get('protocol', 'tcp'),  # protocol_type
            2: iot_data.get('service', 'http'),  # service
            3: iot_data.get('flag', 'SF'),  # flag
            4: iot_data.get('src_bytes', 0),  # src_bytes
            5: iot_data.get('dst_bytes', 0),  # dst_bytes
            # Fill in other needed features with defaults
        }
        
        # Convert to DataFrame in NSL KDD format
        df = pd.DataFrame([nsl_kdd_format])
        
        # Apply same preprocessing as for training data
        X_transformed = self.preprocessor.transform(df)
        
        return X_transformed
    
    def save(self, path='preprocessor.joblib'):
        """Save the preprocessor to disk"""
        joblib.dump(self.preprocessor, path)
        
    def load(self, path='preprocessor.joblib'):
        """Load the preprocessor from disk"""
        self.preprocessor = joblib.load(path)
        return self

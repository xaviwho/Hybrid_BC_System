"""
Sensitivity Classifier for Hybrid Blockchain IoT System
Classifies data sensitivity and determines what can be shared
between private and public blockchains
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
import joblib
import os
import sys

class SensitivityClassifier:
    def __init__(self):
        self.categorical_features = [1, 2, 3]  # protocol_type, service, flag (0-indexed)
        self.numeric_features = [0, 4, 5, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]  # focus on content features
        self.model = None
        self.preprocessor = None
        self.sensitivity_levels = {
            'public': 1,      # Can be freely shared
            'restricted': 2,  # Can be shared with authorized parties
            'confidential': 3, # Can be shared with limited info
            'critical': 4     # Cannot be shared, highly sensitive
        }
        self.access_levels = {
            'public': 1,      # Anonymous access
            'user': 2,        # Registered users
            'researcher': 3,  # Researchers/analysts
            'admin': 4        # System administrators
        }
        
    def build_preprocessor(self):
        """Build the preprocessing pipeline"""
        categorical_transformer = Pipeline(steps=[
            ('onehot', OneHotEncoder(handle_unknown='ignore'))
        ])
        
        numeric_transformer = Pipeline(steps=[
            ('scaler', StandardScaler())
        ])
        
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, self.numeric_features),
                ('cat', categorical_transformer, self.categorical_features)
            ])
        
        return self
    
    def build_model(self):
        """Build the classification model"""
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=15,
            min_samples_split=10,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
        
        return self
    
    def load_data(self, data_path):
        """Load NSL KDD data and convert labels to sensitivity levels"""
        # Load data - assumes CSV format with no header
        df = pd.read_csv(data_path, header=None)
        
        # Extract features and labels
        X = df.iloc[:, :-1]
        y = df.iloc[:, -1]
        
        # Convert attack labels to sensitivity levels
        sensitivity_map = {
            'normal': 'public',
            # DoS attacks - restricted level
            'back': 'restricted',
            'land': 'restricted',
            'neptune': 'restricted',
            'pod': 'restricted',
            'smurf': 'restricted',
            'teardrop': 'restricted',
            # Probe attacks - confidential level
            'ipsweep': 'confidential',
            'nmap': 'confidential',
            'portsweep': 'confidential',
            'satan': 'confidential',
            # R2L attacks - critical level
            'ftp_write': 'critical',
            'guess_passwd': 'critical',
            'imap': 'critical',
            'multihop': 'critical',
            'phf': 'critical',
            'spy': 'critical',
            'warezclient': 'critical',
            'warezmaster': 'critical',
            # U2R attacks - critical level
            'buffer_overflow': 'critical',
            'loadmodule': 'critical',
            'perl': 'critical',
            'rootkit': 'critical'
        }
        
        # Map text labels to sensitivity levels
        y_sensitivity = y.map(lambda x: sensitivity_map.get(x, 'critical'))
        # Convert to numeric sensitivity levels
        y_numeric = y_sensitivity.map(self.sensitivity_levels)
        
        return X, y_numeric
    
    def train(self, train_data_path, test_data_path=None, save_model=True):
        """Train the sensitivity classifier model"""
        print("Loading and preprocessing training data...")
        
        # Load and transform training data
        X_train, y_train = self.load_data(train_data_path)
        
        # Build preprocessor if not already built
        if self.preprocessor is None:
            self.build_preprocessor()
            
        # Fit preprocessor on training data
        self.preprocessor.fit(X_train)
        
        # Transform training data
        X_train_processed = self.preprocessor.transform(X_train)
        
        # Build model if not already built
        if self.model is None:
            self.build_model()
        
        print("Training sensitivity classification model...")
        # Train the model
        self.model.fit(X_train_processed, y_train)
        
        # Evaluate on training data
        train_predictions = self.model.predict(X_train_processed)
        train_accuracy = np.mean(train_predictions == y_train)
        print(f"Training accuracy: {train_accuracy:.4f}")
        
        # Evaluate on test data if provided
        if test_data_path:
            print("Evaluating on test data...")
            X_test, y_test = self.load_data(test_data_path)
            X_test_processed = self.preprocessor.transform(X_test)
            test_predictions = self.model.predict(X_test_processed)
            test_accuracy = np.mean(test_predictions == y_test)
            print(f"Test accuracy: {test_accuracy:.4f}")
        
        # Save the model if requested
        if save_model:
            self.save()
            
        return self
    
    def determine_shareable_fields(self, data, requester_access_level):
        """Determine which fields from the data can be shared based on sensitivity and access level
        
        Args:
            data: Dictionary of IoT data with sensitivity level
            requester_access_level: Access level of the requester ('public', 'user', 'researcher', 'admin')
            
        Returns:
            Dictionary with fields that can be shared
        """
        # Convert access level to numeric
        if isinstance(requester_access_level, str):
            access_level_num = self.access_levels.get(requester_access_level.lower(), 1)
        else:
            access_level_num = requester_access_level
            
        # Get data sensitivity level
        if 'sensitivityLevel' in data and isinstance(data['sensitivityLevel'], str):
            sensitivity_level = self.sensitivity_levels.get(data['sensitivityLevel'].lower(), 4)
        else:
            sensitivity_level = data.get('sensitivityLevel', 4)
            
        # Basic sharing rules:
        # - Public data (1): Share all non-sensitive fields with everyone
        # - Restricted data (2): Share basic info with users+ access
        # - Confidential data (3): Share limited info with researchers+ access
        # - Critical data (4): Share minimal info with admins only
        
        shareable_data = {}
        
        # Always shareable fields
        shareable_data['id'] = data.get('id', '')
        shareable_data['timestamp'] = data.get('timestamp', '')
        
        # Conditionally shareable fields based on sensitivity vs access level
        if access_level_num >= sensitivity_level:
            # Full access
            for key, value in data.items():
                if key not in ['encryptedData', 'publicKey']:
                    shareable_data[key] = value
        elif access_level_num == 3 and sensitivity_level == 4:
            # Researcher access to critical data
            shareable_data['deviceId'] = data.get('deviceId', '')
            shareable_data['dataType'] = data.get('dataType', '')
            # Provide sanitized/aggregated values
            if 'value' in data:
                shareable_data['value'] = 'SANITIZED'
        elif access_level_num == 2 and sensitivity_level >= 3:
            # User access to confidential/critical data
            shareable_data['deviceId'] = data.get('deviceId', '')
            shareable_data['dataType'] = data.get('dataType', '')
            # No values provided
        elif access_level_num == 1:
            # Public access gets minimal info regardless of sensitivity
            shareable_data['dataType'] = data.get('dataType', '')
            
        return shareable_data
    
    def save(self, model_path=None, preprocessor_path=None):
        """Save the model and preprocessor"""
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitivity_model.joblib')
            
        if preprocessor_path is None:
            preprocessor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitivity_preprocessor.joblib')
        
        print(f"Saving sensitivity model to {model_path}")
        joblib.dump(self.model, model_path)
        
        print(f"Saving preprocessor to {preprocessor_path}")
        joblib.dump(self.preprocessor, preprocessor_path)
    
    def load(self, model_path=None, preprocessor_path=None):
        """Load the model and preprocessor"""
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitivity_model.joblib')
            
        if preprocessor_path is None:
            preprocessor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitivity_preprocessor.joblib')
        
        print(f"Loading sensitivity model from {model_path}")
        self.model = joblib.load(model_path)
        
        print(f"Loading preprocessor from {preprocessor_path}")
        self.preprocessor = joblib.load(preprocessor_path)
        
        return self


if __name__ == "__main__":
    # Example usage
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    train_path = os.path.join(data_dir, 'KDDTrain+.txt')
    test_path = os.path.join(data_dir, 'KDDTest+.txt')
    
    print("Training Sensitivity Classifier for Hybrid Blockchain IoT System")
    classifier = SensitivityClassifier()
    classifier.train(train_path, test_path)
    
    print("\nModel training complete. The sensitivity classifier is ready for integration.")

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
            Dictionary with fields that can be shared (non-sensitive fields)
        """
        # Define sensitive field patterns (fields that should be REMOVED from public metadata)
        sensitive_field_patterns = [
            'patientid', 'patient_id', 'patient',
            'ssn', 'social_security', 'socialsecurity',
            'email', 'phone', 'address', 'location',
            'password', 'secret', 'key', 'token', 'credential',
            'creditcard', 'credit_card', 'cardnumber',
            'diagnosis', 'prescription', 'medication', 'medical',
            'salary', 'income', 'financial', 'bank', 'account',
            'confidential', 'private', 'restricted', 'classified',
            'proprietary', 'formula', 'catalyst', 'machinesettings',
            'exactgps', 'gps', 'coordinates'
        ]
        
        # Sensitive value patterns (check in string values)
        sensitive_value_patterns = [
            'patient', 'p12345', 'ssn', 'confidential', 'secret',
            'private', 'classified', 'proprietary', 'formula'
        ]
        
        # Start with all data
        shareable_data = {}
        
        # Determine data sensitivity
        data_sensitivity = 'public'
        has_sensitive_fields = False
        confidence = 0.5  # Base confidence
        
        # Check if data explicitly declares sensitivity level
        explicit_sensitivity = data.get('sensitivityLevel', '').lower()
        if explicit_sensitivity in ['sensitive', 'restricted', 'confidential', 'critical', 'private']:
            has_sensitive_fields = True
            confidence = 0.95  # High confidence when explicitly marked
        
        # Check privacyLevel field (common in IoT data)
        privacy_level = data.get('privacyLevel', '').lower()
        if privacy_level in ['high', 'sensitive', 'restricted', 'confidential']:
            has_sensitive_fields = True
            confidence = max(confidence, 0.90)
        
        # Check dataType for sensitive categories
        data_type = data.get('dataType', '').lower()
        if data_type in ['medical', 'health', 'financial', 'personal', 'industrial']:
            has_sensitive_fields = True
            confidence = max(confidence, 0.85)
        
        # Check each field for sensitive patterns
        sensitive_field_count = 0
        total_fields = len(data)
        
        for key, value in data.items():
            key_lower = key.lower().replace('_', '').replace('-', '')
            
            # Check if this field matches any sensitive pattern
            is_sensitive = any(pattern in key_lower for pattern in sensitive_field_patterns)
            
            # Also check value content for sensitive patterns
            if isinstance(value, str):
                value_lower = value.lower()
                if any(pattern in value_lower for pattern in sensitive_value_patterns):
                    is_sensitive = True
            
            # Check nested data objects
            if isinstance(value, dict):
                for nested_key in value.keys():
                    nested_lower = nested_key.lower().replace('_', '').replace('-', '')
                    if any(pattern in nested_lower for pattern in sensitive_field_patterns):
                        is_sensitive = True
                        break
            
            if is_sensitive:
                has_sensitive_fields = True
                sensitive_field_count += 1
                # Skip this field - don't add to shareable data
                continue
            else:
                # This field is safe to share
                shareable_data[key] = value
        
        # Calculate confidence based on sensitive field ratio
        if total_fields > 0 and sensitive_field_count > 0:
            field_ratio = sensitive_field_count / total_fields
            confidence = max(confidence, 0.5 + field_ratio * 0.5)
        
        # Determine overall sensitivity
        if has_sensitive_fields:
            data_sensitivity = 'sensitive'
        else:
            data_sensitivity = 'public'
            confidence = 1.0 - confidence  # Invert for public classification
        
        # Add data sensitivity and confidence to result
        shareable_data['data_sensitivity'] = data_sensitivity
        shareable_data['confidence'] = round(confidence, 4)
        
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

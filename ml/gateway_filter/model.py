"""
Gateway Filter Model for Hybrid Blockchain IoT System
Trains and evaluates machine learning models using NSL KDD dataset
for detecting malicious traffic and classifying IoT data sensitivity
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.model_selection import train_test_split
import joblib
import os
import sys
from datetime import datetime

# Add parent directory to path to import preprocess module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway_filter.preprocess import NSLKDDPreprocessor

class GatewayFilterModel:
    def __init__(self, model_type='rf'):
        """Initialize the gateway filter model
        
        Args:
            model_type: Type of model to use ('rf' for Random Forest, 'svm' for Support Vector Machine)
        """
        self.model_type = model_type
        self.model = None
        self.preprocessor = NSLKDDPreprocessor()
        
    def build_model(self):
        """Create the ML model for gateway filtering"""
        if self.model_type == 'rf':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=20,
                min_samples_split=10,
                class_weight='balanced',
                random_state=42,
                n_jobs=-1
            )
        elif self.model_type == 'svm':
            self.model = SVC(
                kernel='rbf',
                C=10,
                gamma='scale',
                class_weight='balanced',
                probability=True,
                random_state=42
            )
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
        
        return self
        
    def train(self, train_data_path, test_data_path=None, save_model=True):
        """Train the gateway filter model
        
        Args:
            train_data_path: Path to the NSL KDD training data
            test_data_path: Path to the NSL KDD test data (optional)
            save_model: Whether to save the trained model
        """
        print(f"[{datetime.now()}] Loading and preprocessing training data...")
        
        # Fit preprocessor on training data
        self.preprocessor.fit(train_data_path)
        
        # Transform training data
        X_train, y_train, _ = self.preprocessor.transform(train_data_path)
        
        # Build the model if not already built
        if self.model is None:
            self.build_model()
        
        print(f"[{datetime.now()}] Training {self.model_type.upper()} model...")
        # Train the model
        self.model.fit(X_train, y_train)
        
        # Evaluate on training data
        train_predictions = self.model.predict(X_train)
        train_accuracy = accuracy_score(y_train, train_predictions)
        print(f"Training accuracy: {train_accuracy:.4f}")
        
        # Evaluate on test data if provided
        if test_data_path:
            print(f"[{datetime.now()}] Evaluating on test data...")
            X_test, y_test, _ = self.preprocessor.transform(test_data_path)
            test_predictions = self.model.predict(X_test)
            test_accuracy = accuracy_score(y_test, test_predictions)
            print(f"Test accuracy: {test_accuracy:.4f}")
            
            # Print detailed metrics
            print("\nClassification Report:")
            print(classification_report(y_test, test_predictions))
        
        # Save the model if requested
        if save_model:
            self.save()
            
        return self
    
    def predict(self, iot_data):
        """Predict sensitivity level and filtering decision for IoT data
        
        Args:
            iot_data: Dictionary containing IoT data fields
        
        Returns:
            Dictionary with prediction results including:
            - sensitivity_level: Numeric level (1-4)
            - sensitivity_label: Text label (public, restricted, confidential, critical)
            - allow_storage: Boolean indicating if data should be stored in private blockchain
            - confidence: Model confidence score
        """
        # Transform IoT data to match model input format
        X = self.preprocessor.transform_iot_data(iot_data)
        
        # Make prediction
        sensitivity_level = self.model.predict(X)[0]
        
        # Get prediction probability/confidence
        confidence = np.max(self.model.predict_proba(X)[0])
        
        # Map numeric level back to label
        level_to_label = {
            1: 'public',
            2: 'restricted',
            3: 'confidential',
            4: 'critical'
        }
        sensitivity_label = level_to_label[sensitivity_level]
        
        # Determine if data should be stored in blockchain
        # Logic: Store all data except potentially malicious data with high confidence
        allow_storage = True
        if sensitivity_level >= 3 and confidence > 0.8:
            # Check additional security features in the data
            # For example, check if suspicious port patterns or payloads exist
            if self._has_suspicious_patterns(iot_data):
                allow_storage = False
        
        return {
            'sensitivity_level': int(sensitivity_level),
            'sensitivity_label': sensitivity_label,
            'allow_storage': allow_storage,
            'confidence': float(confidence),
            'quantum_secure_recommended': sensitivity_level >= 3
        }
    
    def _has_suspicious_patterns(self, iot_data):
        """Check for suspicious patterns in IoT data
        
        This is a placeholder for more sophisticated detection logic
        """
        # Example check for suspicious patterns
        suspicious = False
        
        # Check for unusual port usage
        if iot_data.get('dst_port') in [22, 23, 445, 1433, 3389]:
            suspicious = True
            
        # Check for unusually large payloads
        if iot_data.get('src_bytes', 0) > 10000:
            suspicious = True
            
        return suspicious
    
    def save(self, model_path=None, preprocessor_path=None):
        """Save the model and preprocessor
        
        Args:
            model_path: Path to save the model
            preprocessor_path: Path to save the preprocessor
        """
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gateway_filter_model.joblib')
            
        if preprocessor_path is None:
            preprocessor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gateway_preprocessor.joblib')
        
        print(f"Saving model to {model_path}")
        joblib.dump(self.model, model_path)
        
        print(f"Saving preprocessor to {preprocessor_path}")
        self.preprocessor.save(preprocessor_path)
    
    def load(self, model_path=None, preprocessor_path=None):
        """Load the model and preprocessor
        
        Args:
            model_path: Path to load the model from
            preprocessor_path: Path to load the preprocessor from
        """
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gateway_filter_model.joblib')
            
        if preprocessor_path is None:
            preprocessor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gateway_preprocessor.joblib')
        
        print(f"Loading model from {model_path}")
        self.model = joblib.load(model_path)
        
        print(f"Loading preprocessor from {preprocessor_path}")
        self.preprocessor.load(preprocessor_path)
        
        return self


if __name__ == "__main__":
    # Example usage
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    train_path = os.path.join(data_dir, 'KDDTrain+.txt')
    test_path = os.path.join(data_dir, 'KDDTest+.txt')
    
    print("Training Gateway Filter Model for Hybrid Blockchain IoT System")
    model = GatewayFilterModel(model_type='rf')
    model.train(train_path, test_path)
    
    print("\nModel training complete. The gateway filter is ready for integration.")

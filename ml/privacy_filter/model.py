"""
Privacy Filter Model for Hybrid Blockchain IoT System
Trains models to classify data sensitivity and determine sharing policies
"""

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.model_selection import train_test_split
import joblib
import sys
from datetime import datetime

# Add parent directory to path to import sensitivity classifier
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from privacy_filter.sensitivity_classifier import SensitivityClassifier

class PrivacyFilterModel:
    def __init__(self):
        """Initialize the privacy filter model"""
        self.classifier = SensitivityClassifier()
        
    def train(self, train_data_path, test_data_path=None, save_model=True):
        """Train the privacy filter model
        
        Args:
            train_data_path: Path to the NSL KDD training data
            test_data_path: Path to the NSL KDD test data (optional)
            save_model: Whether to save the trained model
        """
        print(f"[{datetime.now()}] Training Privacy Filter Model for Hybrid Blockchain IoT System")
        
        # Train the sensitivity classifier
        self.classifier.train(train_data_path, test_data_path, save_model)
        
        print(f"[{datetime.now()}] Privacy Filter Model training complete")
        
        return self
    
    def evaluate_sharing_policies(self, test_data_path):
        """Evaluate the effectiveness of sharing policies
        
        Args:
            test_data_path: Path to test data
        """
        print(f"[{datetime.now()}] Evaluating sharing policies...")
        
        # Load test data
        X_test, y_test = self.classifier.load_data(test_data_path)
        
        # Create test records with sensitivity levels
        test_records = []
        for i in range(min(100, len(X_test))):
            sensitivity_level = int(y_test.iloc[i])
            level_to_label = {1: 'public', 2: 'restricted', 3: 'confidential', 4: 'critical'}
            
            record = {
                'id': f'test-{i}',
                'deviceId': f'device-{i}',
                'dataType': 'temperature',
                'field': 'temperature',
                'value': f'{20 + i % 10}',
                'sensitivityLevel': level_to_label[sensitivity_level],
                'timestamp': '2023-01-01T12:00:00Z'
            }
            test_records.append(record)
        
        # Test sharing policies for different access levels
        access_levels = ['public', 'user', 'researcher', 'admin']
        results = {}
        
        for access_level in access_levels:
            print(f"Testing sharing policy for access level: {access_level}")
            
            shared_fields = []
            for record in test_records:
                shareable = self.classifier.determine_shareable_fields(record, access_level)
                shared_fields.append(set(shareable.keys()))
            
            # Analyze sharing patterns
            field_frequencies = {}
            for fields in shared_fields:
                for field in fields:
                    if field not in field_frequencies:
                        field_frequencies[field] = 0
                    field_frequencies[field] += 1
            
            # Calculate sharing percentages
            total_records = len(test_records)
            field_percentages = {field: (count / total_records) * 100 
                               for field, count in field_frequencies.items()}
            
            results[access_level] = {
                'field_percentages': field_percentages,
                'avg_fields_shared': sum(len(fields) for fields in shared_fields) / len(shared_fields)
            }
            
            print(f"Average fields shared: {results[access_level]['avg_fields_shared']:.2f}")
            print(f"Field sharing percentages: {field_percentages}")
            
        return results
    
    def save(self):
        """Save the model components"""
        self.classifier.save()
    
    def load(self):
        """Load the model components"""
        self.classifier.load()
        return self


if __name__ == "__main__":
    # Example usage
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    train_path = os.path.join(data_dir, 'KDDTrain+.txt')
    test_path = os.path.join(data_dir, 'KDDTest+.txt')
    
    print("Training Privacy Filter Model for Hybrid Blockchain IoT System")
    model = PrivacyFilterModel()
    model.train(train_path, test_path)
    
    # Evaluate sharing policies
    model.evaluate_sharing_policies(test_path)
    
    print("\nPrivacy filter is ready for integration with your hybrid blockchain system.")

#!/usr/bin/env python3
"""
Real-Time Data Streaming Test Script
Simulates IoT devices sending continuous data to the orchestrator
"""

import requests
import time
import random
import json
from datetime import datetime

ORCHESTRATOR_URL = "http://localhost:5002"

# Simulated device data generators
def generate_industrial_data(device_id):
    return {
        "deviceId": device_id,
        "timestamp": datetime.now().isoformat(),
        "dataType": "manufacturing",
        "Vibration": round(random.uniform(0.1, 1.0), 2),
        "Temperature": round(random.uniform(60, 120), 2),
        "Pressure": round(random.uniform(7, 10), 2),
        "RMS_Vibration": round(random.uniform(0.5, 0.8), 2),
        "Mean_Temp": round(random.uniform(85, 95), 2),
        "Fault_Label": random.choice([0, 1])
    }

def generate_environmental_data(device_id):
    return {
        "deviceId": device_id,
        "timestamp": datetime.now().isoformat(),
        "dataType": "environmental",
        "temperature": round(random.uniform(18, 28), 1),
        "humidity": round(random.uniform(40, 70), 1),
        "pressure": round(random.uniform(1010, 1020), 2),
        "airQuality": random.choice(["good", "moderate", "poor"]),
        "co2Level": random.randint(350, 600)
    }

def generate_medical_data(device_id):
    return {
        "deviceId": device_id,
        "timestamp": datetime.now().isoformat(),
        "dataType": "medical",
        "heartRate": random.randint(60, 100),
        "bloodPressure": f"{random.randint(110, 140)}/{random.randint(70, 90)}",
        "oxygenLevel": random.randint(95, 100),
        "temperature": round(random.uniform(36.0, 37.5), 1)
    }

def stream_data(device_id, data_generator, interval=2):
    """Stream data from a device at specified interval"""
    print(f"Starting data stream for {device_id}...")
    
    while True:
        try:
            data = data_generator(device_id)
            
            # Send to orchestrator's stream endpoint
            response = requests.post(
                f"{ORCHESTRATOR_URL}/stream_data",
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ {device_id}: Streamed to {result.get('clients_notified', 0)} clients")
            else:
                print(f"✗ {device_id}: Failed ({response.status_code})")
                
        except requests.exceptions.ConnectionError:
            print(f"✗ {device_id}: Connection failed. Is orchestrator running?")
        except Exception as e:
            print(f"✗ {device_id}: Error - {e}")
        
        time.sleep(interval)

def main():
    print("=" * 60)
    print("Real-Time Digital Twin Data Streaming Test")
    print("=" * 60)
    print(f"Target: {ORCHESTRATOR_URL}")
    print("Press Ctrl+C to stop\n")
    
    # Check if orchestrator is running
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✓ Orchestrator is online\n")
        else:
            print("✗ Orchestrator returned error\n")
            return
    except:
        print("✗ Cannot connect to orchestrator. Please start it first.\n")
        print("Run: cd orchestrator && python orchestrator.py\n")
        return
    
    # Simulate multiple devices
    devices = [
        ("machine_001", generate_industrial_data, 3),
        ("machine_002", generate_industrial_data, 4),
        ("env_sensor_001", generate_environmental_data, 5),
        ("heart_monitor_001", generate_medical_data, 2),
    ]
    
    print("Simulating devices:")
    for device_id, _, interval in devices:
        print(f"  - {device_id} (every {interval}s)")
    print("\n" + "=" * 60 + "\n")
    
    # Start streaming (sequential for simplicity)
    # In production, use threading for parallel streams
    import threading
    
    threads = []
    for device_id, generator, interval in devices:
        thread = threading.Thread(
            target=stream_data,
            args=(device_id, generator, interval),
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping data streams...")
        print("Goodbye!")

if __name__ == "__main__":
    main()

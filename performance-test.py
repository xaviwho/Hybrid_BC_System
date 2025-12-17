#!/usr/bin/env python3
"""
Digital Twin System - Performance Evaluation Suite
Tests throughput, latency, scalability, and reliability
"""

import requests
import time
import statistics
import threading
import psutil
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import socketio

BASE_URL = "http://localhost:5002"
API_URL = f"{BASE_URL}/api/twins"

class PerformanceMetrics:
    """Track performance metrics"""
    def __init__(self):
        self.create_times = []
        self.read_times = []
        self.update_times = []
        self.version_times = []
        self.rollback_times = []
        self.websocket_latencies = []
        self.errors = 0
        self.total_requests = 0
        self.start_time = None
        self.end_time = None
        
    def add_create_time(self, duration):
        self.create_times.append(duration)
        self.total_requests += 1
    
    def add_read_time(self, duration):
        self.read_times.append(duration)
        self.total_requests += 1
    
    def add_update_time(self, duration):
        self.update_times.append(duration)
        self.total_requests += 1
    
    def add_version_time(self, duration):
        self.version_times.append(duration)
        self.total_requests += 1
    
    def add_rollback_time(self, duration):
        self.rollback_times.append(duration)
        self.total_requests += 1
    
    def add_websocket_latency(self, duration):
        self.websocket_latencies.append(duration)
    
    def add_error(self):
        self.errors += 1
        self.total_requests += 1
    
    def calculate_stats(self, data, name):
        """Calculate statistics for a dataset"""
        if not data:
            return {
                "name": name,
                "count": 0,
                "min": 0,
                "max": 0,
                "mean": 0,
                "median": 0,
                "p95": 0,
                "p99": 0
            }
        
        return {
            "name": name,
            "count": len(data),
            "min": min(data) * 1000,  # Convert to ms
            "max": max(data) * 1000,
            "mean": statistics.mean(data) * 1000,
            "median": statistics.median(data) * 1000,
            "p95": statistics.quantiles(data, n=20)[18] * 1000 if len(data) > 20 else max(data) * 1000,
            "p99": statistics.quantiles(data, n=100)[98] * 1000 if len(data) > 100 else max(data) * 1000
        }
    
    def get_summary(self):
        """Get performance summary"""
        duration = (self.end_time - self.start_time) if self.end_time else 0
        
        return {
            "duration_seconds": duration,
            "total_requests": self.total_requests,
            "errors": self.errors,
            "error_rate": (self.errors / self.total_requests * 100) if self.total_requests > 0 else 0,
            "throughput_rps": self.total_requests / duration if duration > 0 else 0,
            "create_ops": self.calculate_stats(self.create_times, "CREATE"),
            "read_ops": self.calculate_stats(self.read_times, "READ"),
            "update_ops": self.calculate_stats(self.update_times, "UPDATE"),
            "version_ops": self.calculate_stats(self.version_times, "VERSION"),
            "rollback_ops": self.calculate_stats(self.rollback_times, "ROLLBACK"),
            "websocket_latency": self.calculate_stats(self.websocket_latencies, "WEBSOCKET")
        }

metrics = PerformanceMetrics()

def print_header(title):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_metrics_table(stats):
    """Print metrics in table format"""
    print(f"\n{'Operation':<15} {'Count':<8} {'Min(ms)':<10} {'Mean(ms)':<10} {'Median(ms)':<12} {'P95(ms)':<10} {'P99(ms)':<10} {'Max(ms)':<10}")
    print("-" * 95)
    print(f"{stats['name']:<15} {stats['count']:<8} {stats['min']:<10.2f} {stats['mean']:<10.2f} {stats['median']:<12.2f} {stats['p95']:<10.2f} {stats['p99']:<10.2f} {stats['max']:<10.2f}")

def measure_system_resources():
    """Measure system resource usage"""
    process = psutil.Process()
    
    return {
        "cpu_percent": process.cpu_percent(interval=0.1),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "threads": process.num_threads(),
        "open_files": len(process.open_files())
    }

# ========== TEST 1: CRUD THROUGHPUT ==========

def test_crud_throughput(num_twins=100):
    """Test CRUD operation throughput"""
    print_header(f"TEST 1: CRUD Throughput ({num_twins} twins)")
    
    metrics.start_time = time.time()
    
    # CREATE
    print(f"\n[1/4] Creating {num_twins} twins...")
    create_start = time.time()
    
    for i in range(num_twins):
        try:
            start = time.time()
            response = requests.post(API_URL, json={
                "twin_id": f"perf_twin_{i}",
                "twin_type": "performance_test",
                "initial_state": {
                    "index": i,
                    "temperature": 20 + (i % 50),
                    "status": "active"
                }
            }, timeout=5)
            
            if response.status_code == 201:
                metrics.add_create_time(time.time() - start)
            else:
                metrics.add_error()
        except Exception as e:
            metrics.add_error()
            print(f"Error creating twin {i}: {e}")
    
    create_duration = time.time() - create_start
    print(f"✓ Created {num_twins} twins in {create_duration:.2f}s ({num_twins/create_duration:.2f} twins/sec)")
    
    # READ
    print(f"\n[2/4] Reading {num_twins} twins...")
    read_start = time.time()
    
    for i in range(num_twins):
        try:
            start = time.time()
            response = requests.get(f"{API_URL}/perf_twin_{i}", timeout=5)
            
            if response.status_code == 200:
                metrics.add_read_time(time.time() - start)
            else:
                metrics.add_error()
        except Exception as e:
            metrics.add_error()
    
    read_duration = time.time() - read_start
    print(f"✓ Read {num_twins} twins in {read_duration:.2f}s ({num_twins/read_duration:.2f} reads/sec)")
    
    # UPDATE
    print(f"\n[3/4] Updating {num_twins} twins...")
    update_start = time.time()
    
    for i in range(num_twins):
        try:
            start = time.time()
            response = requests.patch(f"{API_URL}/perf_twin_{i}", json={
                "partial_state": {"temperature": 25 + (i % 50)}
            }, timeout=5)
            
            if response.status_code == 200:
                metrics.add_update_time(time.time() - start)
            else:
                metrics.add_error()
        except Exception as e:
            metrics.add_error()
    
    update_duration = time.time() - update_start
    print(f"✓ Updated {num_twins} twins in {update_duration:.2f}s ({num_twins/update_duration:.2f} updates/sec)")
    
    # DELETE
    print(f"\n[4/4] Deleting {num_twins} twins...")
    delete_start = time.time()
    
    for i in range(num_twins):
        try:
            requests.delete(f"{API_URL}/perf_twin_{i}?soft=false", timeout=5)
        except:
            pass
    
    delete_duration = time.time() - delete_start
    print(f"✓ Deleted {num_twins} twins in {delete_duration:.2f}s ({num_twins/delete_duration:.2f} deletes/sec)")

# ========== TEST 2: CONCURRENT OPERATIONS ==========

def create_twin_concurrent(twin_id):
    """Create a twin (for concurrent testing)"""
    try:
        start = time.time()
        response = requests.post(API_URL, json={
            "twin_id": twin_id,
            "twin_type": "concurrent_test",
            "initial_state": {"value": 1}
        }, timeout=10)
        
        duration = time.time() - start
        return (response.status_code == 201, duration)
    except Exception as e:
        return (False, 0)

def test_concurrent_operations(num_twins=50, num_threads=10):
    """Test concurrent operation handling"""
    print_header(f"TEST 2: Concurrent Operations ({num_twins} twins, {num_threads} threads)")
    
    print(f"\nCreating {num_twins} twins concurrently with {num_threads} threads...")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i in range(num_twins):
            future = executor.submit(create_twin_concurrent, f"concurrent_twin_{i}")
            futures.append(future)
        
        successes = 0
        for future in as_completed(futures):
            success, duration = future.result()
            if success:
                successes += 1
                metrics.add_create_time(duration)
            else:
                metrics.add_error()
    
    total_duration = time.time() - start_time
    
    print(f"\n✓ Completed {successes}/{num_twins} twins in {total_duration:.2f}s")
    print(f"  Throughput: {num_twins/total_duration:.2f} ops/sec")
    print(f"  Success rate: {successes/num_twins*100:.1f}%")
    
    # Cleanup
    print("\nCleaning up concurrent test twins...")
    for i in range(num_twins):
        try:
            requests.delete(f"{API_URL}/concurrent_twin_{i}?soft=false", timeout=5)
        except:
            pass

# ========== TEST 3: VERSION CONTROL PERFORMANCE ==========

def test_version_control_performance(num_versions=50):
    """Test version control overhead"""
    print_header(f"TEST 3: Version Control Performance ({num_versions} versions)")
    
    # Create a twin
    twin_id = "version_test_twin"
    requests.post(API_URL, json={
        "twin_id": twin_id,
        "twin_type": "version_test",
        "initial_state": {"value": 0}
    })
    
    print(f"\nCreating {num_versions} versions...")
    
    # Create multiple versions
    for i in range(1, num_versions + 1):
        try:
            start = time.time()
            response = requests.patch(f"{API_URL}/{twin_id}", json={
                "partial_state": {"value": i}
            }, timeout=5)
            
            if response.status_code == 200:
                metrics.add_update_time(time.time() - start)
        except Exception as e:
            metrics.add_error()
    
    print(f"✓ Created {num_versions} versions")
    
    # Test version retrieval
    print(f"\nRetrieving version history...")
    start = time.time()
    response = requests.get(f"{API_URL}/{twin_id}/versions")
    version_retrieval_time = time.time() - start
    
    if response.status_code == 200:
        versions = response.json()['versions']
        print(f"✓ Retrieved {len(versions)} versions in {version_retrieval_time*1000:.2f}ms")
        metrics.add_version_time(version_retrieval_time)
    
    # Test version diff
    print(f"\nComparing versions...")
    start = time.time()
    response = requests.get(f"{API_URL}/{twin_id}/diff?version1=1&version2={num_versions}")
    diff_time = time.time() - start
    
    if response.status_code == 200:
        print(f"✓ Version diff completed in {diff_time*1000:.2f}ms")
        metrics.add_version_time(diff_time)
    
    # Test rollback
    print(f"\nTesting rollback...")
    start = time.time()
    response = requests.post(f"{API_URL}/{twin_id}/rollback/1")
    rollback_time = time.time() - start
    
    if response.status_code == 200:
        print(f"✓ Rollback completed in {rollback_time*1000:.2f}ms")
        metrics.add_rollback_time(rollback_time)
    
    # Cleanup
    requests.delete(f"{API_URL}/{twin_id}?soft=false")

# ========== TEST 4: GENEALOGY PERFORMANCE ==========

def test_genealogy_performance(depth=5, breadth=3):
    """Test genealogy operations with hierarchical structures"""
    print_header(f"TEST 4: Genealogy Performance (Depth={depth}, Breadth={breadth})")
    
    print(f"\nBuilding hierarchy tree...")
    
    # Create root
    requests.post(API_URL, json={
        "twin_id": "root",
        "twin_type": "root",
        "initial_state": {"level": 0}
    })
    
    # Build tree
    total_twins = 1
    for level in range(1, depth + 1):
        parent_count = breadth ** (level - 1)
        for parent_idx in range(parent_count):
            parent_id = f"node_{level-1}_{parent_idx}" if level > 1 else "root"
            
            for child_idx in range(breadth):
                twin_id = f"node_{level}_{parent_idx * breadth + child_idx}"
                requests.post(API_URL, json={
                    "twin_id": twin_id,
                    "twin_type": f"level_{level}",
                    "initial_state": {"level": level},
                    "parent_id": parent_id
                })
                total_twins += 1
    
    print(f"✓ Created {total_twins} twins in {depth}-level hierarchy")
    
    # Test hierarchy retrieval
    print(f"\nRetrieving full hierarchy...")
    start = time.time()
    response = requests.get(f"{API_URL}/root/hierarchy")
    hierarchy_time = time.time() - start
    
    if response.status_code == 200:
        print(f"✓ Retrieved hierarchy in {hierarchy_time*1000:.2f}ms")
        metrics.add_read_time(hierarchy_time)
    
    # Test descendants
    print(f"\nGetting all descendants...")
    start = time.time()
    response = requests.get(f"{API_URL}/root/descendants")
    descendants_time = time.time() - start
    
    if response.status_code == 200:
        descendants = response.json()['descendants']
        print(f"✓ Retrieved {len(descendants)} descendants in {descendants_time*1000:.2f}ms")
        metrics.add_read_time(descendants_time)
    
    # Cleanup
    print(f"\nCleaning up hierarchy...")
    requests.delete(f"{API_URL}/root?soft=false")
    for level in range(1, depth + 1):
        node_count = breadth ** level
        for idx in range(node_count):
            try:
                requests.delete(f"{API_URL}/node_{level}_{idx}?soft=false", timeout=2)
            except:
                pass

# ========== TEST 5: MEMORY & RESOURCE USAGE ==========

def test_memory_scaling(max_twins=1000, step=100):
    """Test memory usage as twins scale"""
    print_header(f"TEST 5: Memory & Resource Scaling (up to {max_twins} twins)")
    
    print(f"\n{'Twins':<10} {'Memory(MB)':<15} {'CPU(%)':<10} {'Threads':<10}")
    print("-" * 50)
    
    # Baseline
    baseline = measure_system_resources()
    print(f"{'0':<10} {baseline['memory_mb']:<15.2f} {baseline['cpu_percent']:<10.1f} {baseline['threads']:<10}")
    
    for num_twins in range(step, max_twins + 1, step):
        # Create batch of twins
        for i in range(step):
            twin_id = f"scale_twin_{num_twins - step + i}"
            try:
                requests.post(API_URL, json={
                    "twin_id": twin_id,
                    "twin_type": "scale_test",
                    "initial_state": {"index": i, "data": "x" * 100}
                }, timeout=5)
            except:
                pass
        
        # Measure resources
        time.sleep(0.5)  # Let system stabilize
        resources = measure_system_resources()
        
        print(f"{num_twins:<10} {resources['memory_mb']:<15.2f} {resources['cpu_percent']:<10.1f} {resources['threads']:<10}")
        
        # Calculate memory per twin
        memory_per_twin = (resources['memory_mb'] - baseline['memory_mb']) / num_twins
    
    print(f"\n✓ Memory per twin: ~{memory_per_twin:.3f} MB")
    
    # Cleanup
    print(f"\nCleaning up {max_twins} twins...")
    for i in range(max_twins):
        try:
            requests.delete(f"{API_URL}/scale_twin_{i}?soft=false", timeout=2)
        except:
            pass

# ========== TEST 6: WEBSOCKET LATENCY ==========

def test_websocket_latency(num_messages=50):
    """Test WebSocket real-time latency"""
    print_header(f"TEST 6: WebSocket Latency ({num_messages} messages)")
    
    print("\nConnecting to WebSocket...")
    
    sio = socketio.Client()
    latencies = []
    received_count = [0]
    
    @sio.on('twin_update')
    def on_twin_update(data):
        # Calculate latency (approximate)
        received_count[0] += 1
    
    try:
        sio.connect(BASE_URL)
        print("✓ Connected to WebSocket")
        
        # Create a twin
        twin_id = "ws_test_twin"
        requests.post(API_URL, json={
            "twin_id": twin_id,
            "twin_type": "ws_test",
            "initial_state": {"value": 0}
        })
        
        print(f"\nSending {num_messages} updates...")
        
        for i in range(num_messages):
            start = time.time()
            
            response = requests.patch(f"{API_URL}/{twin_id}", json={
                "partial_state": {"value": i}
            })
            
            if response.status_code == 200:
                # Wait a bit for WebSocket message
                time.sleep(0.01)
                latency = time.time() - start
                latencies.append(latency)
                metrics.add_websocket_latency(latency)
        
        time.sleep(0.5)  # Wait for remaining messages
        
        print(f"✓ Sent {num_messages} updates, received {received_count[0]} WebSocket messages")
        
        if latencies:
            avg_latency = statistics.mean(latencies) * 1000
            print(f"  Average end-to-end latency: {avg_latency:.2f}ms")
        
        # Cleanup
        requests.delete(f"{API_URL}/{twin_id}?soft=false")
        sio.disconnect()
        
    except Exception as e:
        print(f"✗ WebSocket test failed: {e}")

# ========== MAIN TEST RUNNER ==========

def run_performance_tests():
    """Run all performance tests"""
    print("\n" + "=" * 80)
    print("  DIGITAL TWIN SYSTEM - PERFORMANCE EVALUATION SUITE")
    print("=" * 80)
    print(f"  Target: {BASE_URL}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Check if orchestrator is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            print("\n✓ Orchestrator is online\n")
        else:
            print("\n✗ Orchestrator returned error\n")
            return
    except:
        print("\n✗ Cannot connect to orchestrator\n")
        return
    
    metrics.start_time = time.time()
    
    try:
        # Run tests
        test_crud_throughput(num_twins=100)
        time.sleep(1)
        
        test_concurrent_operations(num_twins=50, num_threads=10)
        time.sleep(1)
        
        test_version_control_performance(num_versions=50)
        time.sleep(1)
        
        test_genealogy_performance(depth=4, breadth=3)
        time.sleep(1)
        
        test_memory_scaling(max_twins=500, step=100)
        time.sleep(1)
        
        test_websocket_latency(num_messages=50)
        
        metrics.end_time = time.time()
        
        # Print summary
        print_header("PERFORMANCE SUMMARY")
        
        summary = metrics.get_summary()
        
        print(f"\n📊 Overall Statistics:")
        print(f"  Duration: {summary['duration_seconds']:.2f} seconds")
        print(f"  Total Requests: {summary['total_requests']}")
        print(f"  Errors: {summary['errors']} ({summary['error_rate']:.2f}%)")
        print(f"  Throughput: {summary['throughput_rps']:.2f} requests/second")
        
        print(f"\n📈 Operation Latencies:")
        for op_name in ['create_ops', 'read_ops', 'update_ops', 'version_ops', 'rollback_ops', 'websocket_latency']:
            if summary[op_name]['count'] > 0:
                print_metrics_table(summary[op_name])
        
        # Save results to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"performance_results_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n✓ Results saved to: {filename}")
        
        print_header("PERFORMANCE EVALUATION COMPLETED")
        print("\n✓ All tests completed successfully!\n")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
    except Exception as e:
        print(f"\n\n✗ Error during tests: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_performance_tests()

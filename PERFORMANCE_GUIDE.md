# 📊 Digital Twin System - Performance Evaluation Guide

## 🎯 **What We Measure**

### **1. Throughput Metrics**
- **Twins Created/Second** - System capacity for new twin creation
- **Reads/Second** - Query processing rate
- **Updates/Second** - State modification throughput
- **Deletes/Second** - Cleanup operation speed

### **2. Latency Metrics**
- **API Response Time** - Time from request to response
  - Min, Max, Mean, Median, P95, P99
- **Version Creation Overhead** - Cost of maintaining history
- **Rollback Time** - Speed of state restoration
- **WebSocket Latency** - Real-time notification delay

### **3. Scalability Metrics**
- **Memory per Twin** - RAM consumption
- **CPU Usage** - Processing overhead
- **Concurrent Operations** - Multi-threaded performance
- **Hierarchy Depth** - Genealogy traversal cost

### **4. Reliability Metrics**
- **Error Rate** - Failed operations percentage
- **Success Rate** - Successful operations percentage
- **Data Integrity** - Checksum verification

---

## 🚀 **Running Performance Tests**

### **Prerequisites:**

```bash
# Install required packages
pip install psutil python-socketio requests
```

### **Run Full Test Suite:**

```bash
python3 performance-test.py
```

### **Test Configuration:**

The script runs 6 comprehensive tests:

1. **CRUD Throughput** (100 twins)
   - Create, Read, Update, Delete operations
   - Sequential execution
   - Measures individual operation latency

2. **Concurrent Operations** (50 twins, 10 threads)
   - Parallel twin creation
   - Tests thread safety
   - Measures throughput under load

3. **Version Control** (50 versions)
   - Multiple state updates
   - Version retrieval
   - Diff comparison
   - Rollback performance

4. **Genealogy** (5 levels deep, 3 children per node)
   - Hierarchical structure creation
   - Tree traversal
   - Ancestor/descendant queries

5. **Memory Scaling** (up to 1000 twins)
   - Memory consumption tracking
   - CPU usage monitoring
   - Resource efficiency

6. **WebSocket Latency** (50 messages)
   - Real-time notification delay
   - End-to-end latency

---

## 📈 **Expected Performance Baselines**

### **Development Environment (Laptop/Desktop):**

| Metric | Expected Value | Good | Excellent |
|--------|---------------|------|-----------|
| **Create Throughput** | 50-100 twins/sec | >100 | >200 |
| **Read Throughput** | 200-500 reads/sec | >500 | >1000 |
| **Update Throughput** | 50-100 updates/sec | >100 | >200 |
| **API Latency (Mean)** | 10-50ms | <10ms | <5ms |
| **API Latency (P95)** | 50-100ms | <50ms | <20ms |
| **Rollback Time** | 10-50ms | <10ms | <5ms |
| **WebSocket Latency** | 20-100ms | <20ms | <10ms |
| **Memory per Twin** | 1-5 KB | <1KB | <500B |
| **Error Rate** | <1% | <0.1% | 0% |

### **Production Environment (Server):**

| Metric | Expected Value | Good | Excellent |
|--------|---------------|------|-----------|
| **Create Throughput** | 200-500 twins/sec | >500 | >1000 |
| **Read Throughput** | 1000-2000 reads/sec | >2000 | >5000 |
| **Update Throughput** | 200-500 updates/sec | >500 | >1000 |
| **API Latency (Mean)** | 5-20ms | <5ms | <2ms |
| **API Latency (P95)** | 20-50ms | <20ms | <10ms |
| **Concurrent Connections** | 100-500 | >500 | >1000 |

---

## 🔍 **Interpreting Results**

### **Sample Output:**

```
Operation       Count    Min(ms)    Mean(ms)   Median(ms)    P95(ms)    P99(ms)    Max(ms)
-----------------------------------------------------------------------------------------------
CREATE          100      8.45       12.34      11.23         18.67      22.45      35.12
READ            100      2.34       4.56       4.12          7.89       9.23       12.45
UPDATE          100      9.12       13.45      12.78         19.34      24.56      38.90
VERSION         52       3.45       5.67       5.23          8.90       11.23      15.67
ROLLBACK        1        8.90       8.90       8.90          8.90       8.90       8.90
WEBSOCKET       50       15.67      23.45      22.12         35.67      42.34      56.78
```

### **What to Look For:**

**✅ Good Performance:**
- Mean latency < 20ms for CRUD operations
- P95 latency < 50ms
- Error rate < 1%
- Memory per twin < 5KB
- Throughput > 100 ops/sec

**⚠️ Warning Signs:**
- Mean latency > 50ms
- P95 latency > 100ms
- Error rate > 5%
- Memory per twin > 10KB
- Throughput < 50 ops/sec

**❌ Poor Performance:**
- Mean latency > 100ms
- P95 latency > 500ms
- Error rate > 10%
- Memory per twin > 50KB
- Frequent timeouts

---

## 🎯 **Performance Optimization Tips**

### **1. Database Optimization**
Currently using in-memory storage. For production:
- Add Redis for caching
- Use PostgreSQL with indexes
- Implement connection pooling

### **2. API Optimization**
- Enable gzip compression
- Implement request batching
- Add caching headers
- Use async/await for I/O

### **3. WebSocket Optimization**
- Use Redis pub/sub for scaling
- Implement message batching
- Add backpressure handling
- Use binary protocols (MessagePack)

### **4. Version Control Optimization**
- Compress old versions
- Archive historical data
- Implement version pruning
- Use incremental diffs

### **5. Genealogy Optimization**
- Cache hierarchy trees
- Use adjacency lists
- Implement lazy loading
- Add depth limits

---

## 📊 **Custom Performance Tests**

### **Test Specific Scenarios:**

```python
import requests
import time

BASE_URL = "http://localhost:5002/api/twins"

# Test 1: Rapid Updates
def test_rapid_updates(twin_id, num_updates=100):
    start = time.time()
    for i in range(num_updates):
        requests.patch(f"{BASE_URL}/{twin_id}", json={
            "partial_state": {"value": i}
        })
    duration = time.time() - start
    print(f"Updates/sec: {num_updates/duration:.2f}")

# Test 2: Large Payload
def test_large_payload():
    large_data = {"data": "x" * 10000}  # 10KB payload
    start = time.time()
    requests.post(BASE_URL, json={
        "twin_id": "large_twin",
        "twin_type": "test",
        "initial_state": large_data
    })
    duration = time.time() - start
    print(f"Large payload time: {duration*1000:.2f}ms")

# Test 3: Deep Hierarchy
def test_deep_hierarchy(depth=10):
    parent_id = None
    for i in range(depth):
        twin_id = f"level_{i}"
        requests.post(BASE_URL, json={
            "twin_id": twin_id,
            "twin_type": "hierarchy",
            "initial_state": {"level": i},
            "parent_id": parent_id
        })
        parent_id = twin_id
    
    # Measure hierarchy retrieval
    start = time.time()
    requests.get(f"{BASE_URL}/level_0/hierarchy")
    duration = time.time() - start
    print(f"Hierarchy retrieval ({depth} levels): {duration*1000:.2f}ms")
```

---

## 🔬 **Load Testing**

### **Using Apache Bench:**

```bash
# Test create endpoint
ab -n 1000 -c 10 -p twin.json -T application/json \
   http://localhost:5002/api/twins

# Test read endpoint
ab -n 10000 -c 50 \
   http://localhost:5002/api/twins
```

### **Using wrk:**

```bash
# Install wrk
# Ubuntu: sudo apt install wrk
# Mac: brew install wrk

# Run load test
wrk -t4 -c100 -d30s http://localhost:5002/api/twins
```

### **Using Locust:**

```python
# locustfile.py
from locust import HttpUser, task, between

class TwinUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def create_twin(self):
        self.client.post("/api/twins", json={
            "twin_id": f"twin_{self.environment.stats.num_requests}",
            "twin_type": "load_test",
            "initial_state": {"value": 1}
        })
    
    @task(5)
    def read_twins(self):
        self.client.get("/api/twins")
    
    @task(2)
    def update_twin(self):
        self.client.patch("/api/twins/twin_1", json={
            "partial_state": {"value": 2}
        })

# Run: locust -f locustfile.py
```

---

## 📝 **Performance Report Template**

### **System Under Test:**
- **Date:** 2025-11-12
- **Environment:** Development / Staging / Production
- **Hardware:** CPU, RAM, Disk
- **Software:** Python version, OS

### **Test Configuration:**
- **Number of Twins:** 1000
- **Concurrent Users:** 50
- **Test Duration:** 5 minutes
- **Operations:** CRUD, Version Control, Genealogy

### **Results:**

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Throughput (ops/sec) | 150 | >100 | ✅ Pass |
| Mean Latency (ms) | 15 | <20 | ✅ Pass |
| P95 Latency (ms) | 45 | <50 | ✅ Pass |
| Error Rate (%) | 0.5 | <1 | ✅ Pass |
| Memory per Twin (KB) | 2.5 | <5 | ✅ Pass |

### **Bottlenecks Identified:**
1. Version retrieval slows with >100 versions
2. Hierarchy traversal O(n) complexity
3. WebSocket broadcast scales linearly

### **Recommendations:**
1. Implement version pagination
2. Cache hierarchy trees
3. Use Redis pub/sub for WebSocket scaling

---

## 🎯 **Performance Goals**

### **Short-term (Current):**
- ✅ Handle 100 twins/sec creation
- ✅ Support 100 concurrent connections
- ✅ Maintain <50ms P95 latency
- ✅ Keep error rate <1%

### **Medium-term (Next Quarter):**
- 🎯 Handle 500 twins/sec creation
- 🎯 Support 500 concurrent connections
- 🎯 Maintain <20ms P95 latency
- 🎯 Scale to 10,000 twins

### **Long-term (Production):**
- 🎯 Handle 1000+ twins/sec creation
- 🎯 Support 1000+ concurrent connections
- 🎯 Maintain <10ms P95 latency
- 🎯 Scale to 100,000+ twins
- 🎯 Multi-region deployment

---

## 🔧 **Troubleshooting Performance Issues**

### **High Latency:**
1. Check system resources (CPU, memory)
2. Enable profiling: `python -m cProfile orchestrator.py`
3. Check network latency
4. Review database query performance

### **High Memory Usage:**
1. Check for memory leaks
2. Implement version pruning
3. Use object pooling
4. Enable garbage collection tuning

### **Low Throughput:**
1. Enable async operations
2. Increase worker threads
3. Optimize database queries
4. Add caching layer

### **WebSocket Issues:**
1. Check connection limits
2. Monitor message queue size
3. Implement backpressure
4. Use sticky sessions for load balancing

---

## 📚 **Additional Resources**

- **Profiling:** `python -m cProfile -o profile.stats orchestrator.py`
- **Memory Profiling:** `pip install memory_profiler`
- **Load Testing:** Apache Bench, wrk, Locust
- **Monitoring:** Prometheus, Grafana
- **APM:** New Relic, Datadog, AppDynamics

---

## 🎉 **Summary**

The performance test suite provides comprehensive evaluation of:
- ✅ CRUD operation throughput and latency
- ✅ Concurrent operation handling
- ✅ Version control overhead
- ✅ Genealogy performance
- ✅ Memory and resource scaling
- ✅ Real-time WebSocket latency

**Run the tests regularly to track performance over time and identify regressions early!**

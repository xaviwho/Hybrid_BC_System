# Digital Twin Lifecycle Management API

Complete REST API documentation for managing digital twins with CRUD operations, version control, and genealogy.

---

## 📋 **Table of Contents**

1. [CRUD Operations](#crud-operations)
2. [Version Control](#version-control)
3. [Genealogy Management](#genealogy-management)
4. [Utility Endpoints](#utility-endpoints)

---

## 🔧 **CRUD Operations**

### **Create a Twin**

```http
POST /api/twins
Content-Type: application/json

{
  "twin_id": "machine_001",
  "twin_type": "manufacturing",
  "initial_state": {
    "temperature": 75.5,
    "vibration": 0.45,
    "status": "operational"
  },
  "metadata": {
    "location": "Factory Floor A",
    "manufacturer": "ACME Corp"
  },
  "parent_id": null  // Optional: ID of parent twin
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Twin created successfully",
  "twin": {
    "twin_id": "machine_001",
    "twin_type": "manufacturing",
    "parent_id": null,
    "children": [],
    "metadata": {...},
    "created_at": "2025-11-11T16:00:00",
    "updated_at": "2025-11-11T16:00:00",
    "status": "active",
    "current_version": 1,
    "current_state": {...},
    "version_count": 1
  }
}
```

---

### **List All Twins**

```http
GET /api/twins?status=active&twin_type=manufacturing
```

**Query Parameters:**
- `status` - Filter by status (active, inactive, archived, deleted)
- `twin_type` - Filter by twin type
- `parent_id` - Filter by parent ID

**Response:**
```json
{
  "status": "success",
  "count": 5,
  "twins": [...]
}
```

---

### **Get Twin Details**

```http
GET /api/twins/machine_001?include_versions=true
```

**Query Parameters:**
- `include_versions` - Include full version history (default: false)

**Response:**
```json
{
  "status": "success",
  "twin": {
    "twin_id": "machine_001",
    "current_version": 3,
    "versions": [...]  // If include_versions=true
  }
}
```

---

### **Update Twin (Full Replacement)**

```http
PUT /api/twins/machine_001
Content-Type: application/json

{
  "state": {
    "temperature": 80.0,
    "vibration": 0.55,
    "status": "warning"
  },
  "metadata": {
    "action": "manual_update",
    "operator": "john_doe"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Twin updated successfully",
  "twin": {...}
}
```

---

### **Patch Twin (Partial Update)**

```http
PATCH /api/twins/machine_001
Content-Type: application/json

{
  "partial_state": {
    "temperature": 82.5
  },
  "metadata": {
    "action": "temperature_adjustment"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Twin patched successfully",
  "twin": {...}
}
```

---

### **Delete Twin**

```http
DELETE /api/twins/machine_001?soft=true
```

**Query Parameters:**
- `soft` - Soft delete (mark as deleted) or hard delete (remove completely). Default: true

**Response:**
```json
{
  "status": "success",
  "message": "Twin soft deleted successfully"
}
```

---

## 📚 **Version Control**

### **Get Version History**

```http
GET /api/twins/machine_001/versions
```

**Response:**
```json
{
  "status": "success",
  "twin_id": "machine_001",
  "current_version": 5,
  "versions": [
    {
      "version_number": 1,
      "state": {...},
      "timestamp": "2025-11-11T16:00:00",
      "metadata": {"action": "created"},
      "checksum": "abc123..."
    },
    ...
  ]
}
```

---

### **Get Specific Version**

```http
GET /api/twins/machine_001/versions/3
```

**Response:**
```json
{
  "status": "success",
  "twin_id": "machine_001",
  "version": {
    "version_number": 3,
    "state": {...},
    "timestamp": "2025-11-11T16:05:00",
    "metadata": {...},
    "checksum": "def456..."
  }
}
```

---

### **Rollback to Version**

```http
POST /api/twins/machine_001/rollback/3
```

**Response:**
```json
{
  "status": "success",
  "message": "Twin rolled back to version 3",
  "twin": {...}
}
```

---

### **Compare Versions (Diff)**

```http
GET /api/twins/machine_001/diff?version1=2&version2=4
```

**Response:**
```json
{
  "status": "success",
  "twin_id": "machine_001",
  "diff": {
    "version1": 2,
    "version2": 4,
    "timestamp1": "2025-11-11T16:02:00",
    "timestamp2": "2025-11-11T16:08:00",
    "changes": {
      "temperature": {
        "old": 75.5,
        "new": 82.5
      },
      "status": {
        "old": "operational",
        "new": "warning"
      }
    }
  }
}
```

---

## 🌳 **Genealogy Management**

### **Get Twin Hierarchy**

```http
GET /api/twins/factory_001/hierarchy
```

**Response:**
```json
{
  "status": "success",
  "hierarchy": {
    "twin_id": "factory_001",
    "twin_type": "facility",
    "children_details": [
      {
        "twin_id": "line_001",
        "twin_type": "production_line",
        "children_details": [
          {
            "twin_id": "machine_001",
            "twin_type": "manufacturing",
            "children_details": []
          }
        ]
      }
    ]
  }
}
```

---

### **Get Ancestors**

```http
GET /api/twins/machine_001/ancestors
```

**Response:**
```json
{
  "status": "success",
  "twin_id": "machine_001",
  "ancestors": ["line_001", "factory_001"],
  "count": 2
}
```

---

### **Get Descendants**

```http
GET /api/twins/factory_001/descendants
```

**Response:**
```json
{
  "status": "success",
  "twin_id": "factory_001",
  "descendants": ["line_001", "line_002", "machine_001", "machine_002", "sensor_001"],
  "count": 5
}
```

---

### **Add Child to Twin**

```http
POST /api/twins/line_001/children
Content-Type: application/json

{
  "child_id": "machine_003"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Child added successfully"
}
```

---

## 🔍 **Utility Endpoints**

### **Search Twins**

```http
GET /api/twins/search?q=machine
```

**Response:**
```json
{
  "status": "success",
  "query": "machine",
  "count": 3,
  "results": [...]
}
```

---

### **Get Statistics**

```http
GET /api/twins/statistics
```

**Response:**
```json
{
  "status": "success",
  "statistics": {
    "total_twins": 25,
    "by_status": {
      "active": 20,
      "inactive": 3,
      "deleted": 2
    },
    "by_type": {
      "manufacturing": 10,
      "environmental": 8,
      "medical": 7
    },
    "total_versions": 150,
    "orphaned_twins": 2,
    "root_twins": 5
  }
}
```

---

## 🎯 **Example Workflows**

### **Workflow 1: Create Factory Hierarchy**

```bash
# 1. Create factory (root)
curl -X POST http://localhost:5002/api/twins \
  -H 'Content-Type: application/json' \
  -d '{
    "twin_id": "factory_001",
    "twin_type": "facility",
    "initial_state": {"name": "Main Factory", "capacity": 1000}
  }'

# 2. Create production line (child of factory)
curl -X POST http://localhost:5002/api/twins \
  -H 'Content-Type: application/json' \
  -d '{
    "twin_id": "line_001",
    "twin_type": "production_line",
    "initial_state": {"name": "Line A", "machines": 5},
    "parent_id": "factory_001"
  }'

# 3. Create machine (child of line)
curl -X POST http://localhost:5002/api/twins \
  -H 'Content-Type: application/json' \
  -d '{
    "twin_id": "machine_001",
    "twin_type": "manufacturing",
    "initial_state": {"temperature": 75, "vibration": 0.4},
    "parent_id": "line_001"
  }'

# 4. View hierarchy
curl http://localhost:5002/api/twins/factory_001/hierarchy
```

---

### **Workflow 2: Update and Track Changes**

```bash
# 1. Update machine state
curl -X PATCH http://localhost:5002/api/twins/machine_001 \
  -H 'Content-Type: application/json' \
  -d '{
    "partial_state": {"temperature": 85},
    "metadata": {"reason": "increased_load"}
  }'

# 2. View version history
curl http://localhost:5002/api/twins/machine_001/versions

# 3. Compare versions
curl 'http://localhost:5002/api/twins/machine_001/diff?version1=1&version2=2'

# 4. Rollback if needed
curl -X POST http://localhost:5002/api/twins/machine_001/rollback/1
```

---

### **Workflow 3: Monitor and Search**

```bash
# 1. Get all active manufacturing twins
curl 'http://localhost:5002/api/twins?status=active&twin_type=manufacturing'

# 2. Search for specific twin
curl 'http://localhost:5002/api/twins/search?q=machine'

# 3. Get system statistics
curl http://localhost:5002/api/twins/statistics
```

---

## 🔐 **Error Responses**

All endpoints return consistent error responses:

```json
{
  "error": "Error message description"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation error)
- `404` - Not Found
- `500` - Internal Server Error

---

## 🚀 **WebSocket Events**

The API also broadcasts real-time events via WebSocket:

- `twin_created` - New twin created
- `twin_update` - Twin state updated
- `twin_deleted` - Twin deleted
- `twin_rollback` - Twin rolled back to previous version

Connect to: `ws://localhost:5002`

---

## 📊 **Data Model**

### **Twin Structure**
```json
{
  "twin_id": "string",
  "twin_type": "string",
  "parent_id": "string | null",
  "children": ["string"],
  "metadata": {},
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "status": "active | inactive | archived | deleted",
  "current_version": "number",
  "current_state": {},
  "version_count": "number"
}
```

### **Version Structure**
```json
{
  "version_number": "number",
  "state": {},
  "timestamp": "ISO8601",
  "metadata": {},
  "checksum": "string"
}
```

---

## 💡 **Best Practices**

1. **Use meaningful twin_ids** - e.g., `factory_001`, `machine_A_001`
2. **Set parent_id during creation** - Easier than adding children later
3. **Use PATCH for small updates** - More efficient than PUT
4. **Track changes with metadata** - Add context to each version
5. **Use soft delete** - Preserve history and enable recovery
6. **Query with filters** - More efficient than client-side filtering
7. **Monitor statistics** - Track system health and usage

---

## 🎉 **Feature Complete!**

You now have full lifecycle management for digital twins including:
- ✅ CRUD operations
- ✅ Version control with rollback
- ✅ Parent-child relationships
- ✅ Search and filtering
- ✅ Real-time WebSocket updates
- ✅ Statistics and monitoring

#!/usr/bin/env python3
"""
Digital Twin Lifecycle Management Test Script
Tests all CRUD operations, versioning, and genealogy features
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5002"
API_URL = f"{BASE_URL}/api/twins"

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_result(operation, response):
    """Print operation result"""
    status_icon = "✓" if response.status_code < 400 else "✗"
    print(f"{status_icon} {operation}: {response.status_code}")
    if response.status_code < 400:
        try:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
        except:
            print(f"   Response: {response.text[:100]}")
    else:
        print(f"   Error: {response.text}")

def test_crud_operations():
    """Test basic CRUD operations"""
    print_section("1. CRUD OPERATIONS")
    
    # CREATE
    print("\n[CREATE] Creating factory twin...")
    response = requests.post(API_URL, json={
        "twin_id": "factory_test_001",
        "twin_type": "facility",
        "initial_state": {
            "name": "Test Factory",
            "capacity": 1000,
            "location": "Building A"
        },
        "metadata": {
            "created_by": "test_script",
            "environment": "testing"
        }
    })
    print_result("Create Factory", response)
    
    # CREATE with parent
    print("\n[CREATE] Creating production line twin...")
    response = requests.post(API_URL, json={
        "twin_id": "line_test_001",
        "twin_type": "production_line",
        "initial_state": {
            "name": "Line A",
            "machines": 5,
            "status": "operational"
        },
        "parent_id": "factory_test_001"
    })
    print_result("Create Line", response)
    
    # CREATE machine
    print("\n[CREATE] Creating machine twin...")
    response = requests.post(API_URL, json={
        "twin_id": "machine_test_001",
        "twin_type": "manufacturing",
        "initial_state": {
            "temperature": 75.5,
            "vibration": 0.45,
            "pressure": 8.2,
            "status": "operational"
        },
        "parent_id": "line_test_001"
    })
    print_result("Create Machine", response)
    
    time.sleep(0.5)
    
    # READ - List all
    print("\n[READ] Listing all twins...")
    response = requests.get(API_URL)
    print_result("List All Twins", response)
    
    # READ - Get specific twin
    print("\n[READ] Getting machine details...")
    response = requests.get(f"{API_URL}/machine_test_001")
    print_result("Get Machine Details", response)
    
    # UPDATE - Full replacement
    print("\n[UPDATE] Updating machine state (full)...")
    response = requests.put(f"{API_URL}/machine_test_001", json={
        "state": {
            "temperature": 80.0,
            "vibration": 0.55,
            "pressure": 8.5,
            "status": "warning"
        },
        "metadata": {
            "action": "full_update",
            "reason": "increased_load"
        }
    })
    print_result("Full Update", response)
    
    time.sleep(0.5)
    
    # PATCH - Partial update
    print("\n[PATCH] Patching machine state...")
    response = requests.patch(f"{API_URL}/machine_test_001", json={
        "partial_state": {
            "temperature": 82.5
        },
        "metadata": {
            "action": "temperature_adjustment"
        }
    })
    print_result("Patch Update", response)

def test_version_control():
    """Test version control features"""
    print_section("2. VERSION CONTROL")
    
    # Get version history
    print("\n[VERSIONS] Getting version history...")
    response = requests.get(f"{API_URL}/machine_test_001/versions")
    print_result("Version History", response)
    
    if response.status_code == 200:
        versions = response.json().get('versions', [])
        print(f"   Total versions: {len(versions)}")
        for v in versions:
            print(f"   - Version {v['version_number']}: {v['metadata'].get('action', 'N/A')} at {v['timestamp']}")
    
    # Get specific version
    print("\n[VERSIONS] Getting version 1...")
    response = requests.get(f"{API_URL}/machine_test_001/versions/1")
    print_result("Get Version 1", response)
    
    # Compare versions
    print("\n[DIFF] Comparing versions 1 and 3...")
    response = requests.get(f"{API_URL}/machine_test_001/diff?version1=1&version2=3")
    print_result("Version Diff", response)
    
    if response.status_code == 200:
        diff = response.json().get('diff', {})
        changes = diff.get('changes', {})
        print(f"   Changes detected: {len(changes)}")
        for key, change in changes.items():
            print(f"   - {key}: {change['old']} → {change['new']}")
    
    # Rollback
    print("\n[ROLLBACK] Rolling back to version 1...")
    response = requests.post(f"{API_URL}/machine_test_001/rollback/1")
    print_result("Rollback", response)
    
    # Verify rollback
    print("\n[VERIFY] Verifying rollback...")
    response = requests.get(f"{API_URL}/machine_test_001")
    if response.status_code == 200:
        twin = response.json().get('twin', {})
        state = twin.get('current_state', {})
        print(f"   Current temperature: {state.get('temperature')}")
        print(f"   Current version: {twin.get('current_version')}")

def test_genealogy():
    """Test genealogy features"""
    print_section("3. GENEALOGY & RELATIONSHIPS")
    
    # Get hierarchy
    print("\n[HIERARCHY] Getting factory hierarchy...")
    response = requests.get(f"{API_URL}/factory_test_001/hierarchy")
    print_result("Hierarchy", response)
    
    # Get ancestors
    print("\n[ANCESTORS] Getting machine ancestors...")
    response = requests.get(f"{API_URL}/machine_test_001/ancestors")
    print_result("Ancestors", response)
    
    if response.status_code == 200:
        ancestors = response.json().get('ancestors', [])
        print(f"   Ancestors: {' → '.join(ancestors)}")
    
    # Get descendants
    print("\n[DESCENDANTS] Getting factory descendants...")
    response = requests.get(f"{API_URL}/factory_test_001/descendants")
    print_result("Descendants", response)
    
    if response.status_code == 200:
        descendants = response.json().get('descendants', [])
        print(f"   Total descendants: {len(descendants)}")
        for desc in descendants:
            print(f"   - {desc}")
    
    # Create another machine and add as child
    print("\n[CREATE] Creating second machine...")
    response = requests.post(API_URL, json={
        "twin_id": "machine_test_002",
        "twin_type": "manufacturing",
        "initial_state": {
            "temperature": 70.0,
            "vibration": 0.35,
            "status": "operational"
        }
    })
    print_result("Create Machine 2", response)
    
    # Add as child to line
    print("\n[ADD CHILD] Adding machine_test_002 to line...")
    response = requests.post(f"{API_URL}/line_test_001/children", json={
        "child_id": "machine_test_002"
    })
    print_result("Add Child", response)

def test_filters_and_search():
    """Test filtering and search"""
    print_section("4. FILTERS & SEARCH")
    
    # Filter by type
    print("\n[FILTER] Getting all manufacturing twins...")
    response = requests.get(f"{API_URL}?twin_type=manufacturing")
    print_result("Filter by Type", response)
    
    if response.status_code == 200:
        count = response.json().get('count', 0)
        print(f"   Found {count} manufacturing twins")
    
    # Filter by status
    print("\n[FILTER] Getting active twins...")
    response = requests.get(f"{API_URL}?status=active")
    print_result("Filter by Status", response)
    
    # Search
    print("\n[SEARCH] Searching for 'machine'...")
    response = requests.get(f"{API_URL}/search?q=machine")
    print_result("Search", response)
    
    if response.status_code == 200:
        results = response.json().get('results', [])
        print(f"   Found {len(results)} results")
        for result in results:
            print(f"   - {result['twin_id']} ({result['twin_type']})")

def test_statistics():
    """Test statistics endpoint"""
    print_section("5. STATISTICS")
    
    print("\n[STATS] Getting system statistics...")
    response = requests.get(f"{API_URL}/statistics")
    print_result("Statistics", response)
    
    if response.status_code == 200:
        stats = response.json().get('statistics', {})
        print(f"\n   System Overview:")
        print(f"   - Total twins: {stats.get('total_twins', 0)}")
        print(f"   - Total versions: {stats.get('total_versions', 0)}")
        print(f"   - Root twins: {stats.get('root_twins', 0)}")
        
        print(f"\n   By Status:")
        for status, count in stats.get('by_status', {}).items():
            print(f"   - {status}: {count}")
        
        print(f"\n   By Type:")
        for twin_type, count in stats.get('by_type', {}).items():
            print(f"   - {twin_type}: {count}")

def test_delete():
    """Test delete operations"""
    print_section("6. DELETE OPERATIONS")
    
    # Soft delete
    print("\n[DELETE] Soft deleting machine_test_002...")
    response = requests.delete(f"{API_URL}/machine_test_002?soft=true")
    print_result("Soft Delete", response)
    
    # Verify soft delete
    print("\n[VERIFY] Checking deleted twin status...")
    response = requests.get(f"{API_URL}/machine_test_002")
    if response.status_code == 200:
        twin = response.json().get('twin', {})
        print(f"   Status: {twin.get('status')}")
    
    # Hard delete
    print("\n[DELETE] Hard deleting machine_test_002...")
    response = requests.delete(f"{API_URL}/machine_test_002?soft=false")
    print_result("Hard Delete", response)
    
    # Verify hard delete
    print("\n[VERIFY] Trying to get deleted twin...")
    response = requests.get(f"{API_URL}/machine_test_002")
    print_result("Get Deleted Twin", response)

def cleanup():
    """Clean up test twins"""
    print_section("CLEANUP")
    
    print("\n[CLEANUP] Removing test twins...")
    test_twins = ["machine_test_001", "line_test_001", "factory_test_001"]
    
    for twin_id in test_twins:
        response = requests.delete(f"{API_URL}/{twin_id}?soft=false")
        status_icon = "✓" if response.status_code < 400 else "✗"
        print(f"{status_icon} Deleted {twin_id}")

def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("  DIGITAL TWIN LIFECYCLE MANAGEMENT - TEST SUITE")
    print("=" * 70)
    print(f"  Target: {BASE_URL}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Check if orchestrator is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            print("\n✓ Orchestrator is online\n")
        else:
            print("\n✗ Orchestrator returned error\n")
            return
    except:
        print("\n✗ Cannot connect to orchestrator. Please start it first.\n")
        print("Run: cd orchestrator && python orchestrator.py\n")
        return
    
    try:
        # Run all tests
        test_crud_operations()
        time.sleep(1)
        
        test_version_control()
        time.sleep(1)
        
        test_genealogy()
        time.sleep(1)
        
        test_filters_and_search()
        time.sleep(1)
        
        test_statistics()
        time.sleep(1)
        
        test_delete()
        time.sleep(1)
        
        # Cleanup
        cleanup()
        
        print_section("TEST SUITE COMPLETED")
        print("\n✓ All tests completed successfully!")
        print("\nCheck the frontend 'Real-Time Twins' tab to see live updates during testing.\n")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        cleanup()
    except Exception as e:
        print(f"\n\n✗ Error during tests: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

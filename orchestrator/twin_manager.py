"""
Digital Twin Lifecycle Management Module
Handles CRUD operations, versioning, and genealogy for digital twins
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from copy import deepcopy

class TwinVersion:
    """Represents a version of a digital twin's state"""
    
    def __init__(self, version_number: int, state: Dict, metadata: Dict = None):
        self.version_number = version_number
        self.state = state
        self.timestamp = datetime.now().isoformat()
        self.metadata = metadata or {}
        self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        """Calculate SHA256 checksum of the state"""
        state_str = json.dumps(self.state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Convert version to dictionary"""
        return {
            'version_number': self.version_number,
            'state': self.state,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
            'checksum': self.checksum
        }


class DigitalTwin:
    """Represents a digital twin with full lifecycle management"""
    
    def __init__(self, twin_id: str, twin_type: str, initial_state: Dict, 
                 metadata: Dict = None, parent_id: Optional[str] = None):
        self.twin_id = twin_id
        self.twin_type = twin_type
        self.parent_id = parent_id
        self.children = []  # List of child twin IDs
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.status = 'active'  # active, inactive, archived, deleted
        
        # Version control
        self.current_version = 1
        self.versions = []
        self._add_version(initial_state, {'action': 'created'})
        
        # Current state (for quick access)
        self.current_state = deepcopy(initial_state)
    
    def _add_version(self, state: Dict, metadata: Dict = None):
        """Add a new version to history"""
        version = TwinVersion(self.current_version, state, metadata)
        self.versions.append(version)
        self.current_version += 1
        self.updated_at = datetime.now().isoformat()
    
    def update_state(self, new_state: Dict, metadata: Dict = None):
        """Update twin state and create new version"""
        self.current_state = deepcopy(new_state)
        self._add_version(new_state, metadata or {'action': 'updated'})
        self.updated_at = datetime.now().isoformat()
    
    def patch_state(self, partial_state: Dict, metadata: Dict = None):
        """Partially update twin state (merge with existing)"""
        self.current_state.update(partial_state)
        self._add_version(self.current_state, metadata or {'action': 'patched'})
        self.updated_at = datetime.now().isoformat()
    
    def get_version(self, version_number: int) -> Optional[TwinVersion]:
        """Get a specific version"""
        for version in self.versions:
            if version.version_number == version_number:
                return version
        return None
    
    def get_version_history(self) -> List[Dict]:
        """Get all version history"""
        return [v.to_dict() for v in self.versions]
    
    def rollback_to_version(self, version_number: int) -> bool:
        """Rollback to a specific version"""
        version = self.get_version(version_number)
        if version:
            self.current_state = deepcopy(version.state)
            self._add_version(version.state, {
                'action': 'rollback',
                'rollback_to': version_number
            })
            return True
        return False
    
    def add_child(self, child_id: str):
        """Add a child twin"""
        if child_id not in self.children:
            self.children.append(child_id)
            self.updated_at = datetime.now().isoformat()
    
    def remove_child(self, child_id: str):
        """Remove a child twin"""
        if child_id in self.children:
            self.children.remove(child_id)
            self.updated_at = datetime.now().isoformat()
    
    def set_status(self, status: str, metadata: Dict = None):
        """Change twin status"""
        self.status = status
        self.updated_at = datetime.now().isoformat()
        self._add_version(self.current_state, {
            'action': 'status_change',
            'new_status': status,
            **(metadata or {})
        })
    
    def to_dict(self, include_versions: bool = False) -> Dict:
        """Convert twin to dictionary"""
        result = {
            'twin_id': self.twin_id,
            'twin_type': self.twin_type,
            'parent_id': self.parent_id,
            'children': self.children,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'status': self.status,
            'current_version': self.current_version - 1,
            'current_state': self.current_state,
            'version_count': len(self.versions)
        }
        
        if include_versions:
            result['versions'] = self.get_version_history()
        
        return result


class TwinManager:
    """Manages all digital twins with CRUD operations"""
    
    def __init__(self):
        self.twins: Dict[str, DigitalTwin] = {}
    
    def create_twin(self, twin_id: str, twin_type: str, initial_state: Dict,
                   metadata: Dict = None, parent_id: Optional[str] = None) -> DigitalTwin:
        """Create a new digital twin"""
        if twin_id in self.twins:
            raise ValueError(f"Twin with ID '{twin_id}' already exists")
        
        # If parent specified, validate it exists
        if parent_id and parent_id not in self.twins:
            raise ValueError(f"Parent twin '{parent_id}' does not exist")
        
        twin = DigitalTwin(twin_id, twin_type, initial_state, metadata, parent_id)
        self.twins[twin_id] = twin
        
        # Add to parent's children
        if parent_id:
            self.twins[parent_id].add_child(twin_id)
        
        return twin
    
    def get_twin(self, twin_id: str) -> Optional[DigitalTwin]:
        """Get a twin by ID"""
        return self.twins.get(twin_id)
    
    def update_twin(self, twin_id: str, new_state: Dict, metadata: Dict = None) -> bool:
        """Update a twin's state (full replacement)"""
        twin = self.get_twin(twin_id)
        if twin:
            twin.update_state(new_state, metadata)
            return True
        return False
    
    def patch_twin(self, twin_id: str, partial_state: Dict, metadata: Dict = None) -> bool:
        """Partially update a twin's state"""
        twin = self.get_twin(twin_id)
        if twin:
            twin.patch_state(partial_state, metadata)
            return True
        return False
    
    def delete_twin(self, twin_id: str, soft_delete: bool = True) -> bool:
        """Delete a twin (soft or hard delete)"""
        twin = self.get_twin(twin_id)
        if not twin:
            return False
        
        if soft_delete:
            # Soft delete: mark as deleted
            twin.set_status('deleted', {'action': 'soft_delete'})
        else:
            # Hard delete: remove from manager
            # Remove from parent's children
            if twin.parent_id:
                parent = self.get_twin(twin.parent_id)
                if parent:
                    parent.remove_child(twin_id)
            
            # Handle children (orphan or cascade delete)
            for child_id in twin.children[:]:
                child = self.get_twin(child_id)
                if child:
                    child.parent_id = None  # Orphan the child
            
            del self.twins[twin_id]
        
        return True
    
    def list_twins(self, filters: Dict = None) -> List[Dict]:
        """List all twins with optional filters"""
        result = []
        for twin in self.twins.values():
            # Apply filters
            if filters:
                if 'status' in filters and twin.status != filters['status']:
                    continue
                if 'twin_type' in filters and twin.twin_type != filters['twin_type']:
                    continue
                if 'parent_id' in filters and twin.parent_id != filters['parent_id']:
                    continue
            
            result.append(twin.to_dict())
        
        return result
    
    def get_twin_hierarchy(self, twin_id: str) -> Dict:
        """Get full hierarchy tree for a twin"""
        twin = self.get_twin(twin_id)
        if not twin:
            return None
        
        def build_tree(tid: str) -> Dict:
            t = self.get_twin(tid)
            if not t:
                return None
            
            tree = t.to_dict()
            tree['children_details'] = [build_tree(cid) for cid in t.children]
            return tree
        
        return build_tree(twin_id)
    
    def get_twin_ancestors(self, twin_id: str) -> List[str]:
        """Get all ancestors of a twin (parent, grandparent, etc.)"""
        ancestors = []
        twin = self.get_twin(twin_id)
        
        while twin and twin.parent_id:
            ancestors.append(twin.parent_id)
            twin = self.get_twin(twin.parent_id)
        
        return ancestors
    
    def get_twin_descendants(self, twin_id: str) -> List[str]:
        """Get all descendants of a twin (children, grandchildren, etc.)"""
        descendants = []
        twin = self.get_twin(twin_id)
        
        if not twin:
            return descendants
        
        def collect_descendants(tid: str):
            t = self.get_twin(tid)
            if t:
                for child_id in t.children:
                    descendants.append(child_id)
                    collect_descendants(child_id)
        
        collect_descendants(twin_id)
        return descendants
    
    def get_version_diff(self, twin_id: str, version1: int, version2: int) -> Dict:
        """Compare two versions of a twin"""
        twin = self.get_twin(twin_id)
        if not twin:
            return None
        
        v1 = twin.get_version(version1)
        v2 = twin.get_version(version2)
        
        if not v1 or not v2:
            return None
        
        # Simple diff: show what changed
        diff = {
            'version1': version1,
            'version2': version2,
            'timestamp1': v1.timestamp,
            'timestamp2': v2.timestamp,
            'changes': {}
        }
        
        # Find differences
        all_keys = set(v1.state.keys()) | set(v2.state.keys())
        for key in all_keys:
            val1 = v1.state.get(key)
            val2 = v2.state.get(key)
            if val1 != val2:
                diff['changes'][key] = {
                    'old': val1,
                    'new': val2
                }
        
        return diff
    
    def search_twins(self, query: str) -> List[Dict]:
        """Search twins by ID, type, or state content"""
        results = []
        query_lower = query.lower()
        
        for twin in self.twins.values():
            # Search in ID, type, and state
            if (query_lower in twin.twin_id.lower() or
                query_lower in twin.twin_type.lower() or
                query_lower in json.dumps(twin.current_state).lower()):
                results.append(twin.to_dict())
        
        return results
    
    def get_statistics(self) -> Dict:
        """Get statistics about all twins"""
        stats = {
            'total_twins': len(self.twins),
            'by_status': {},
            'by_type': {},
            'total_versions': 0,
            'orphaned_twins': 0,
            'root_twins': 0
        }
        
        for twin in self.twins.values():
            # Count by status
            stats['by_status'][twin.status] = stats['by_status'].get(twin.status, 0) + 1
            
            # Count by type
            stats['by_type'][twin.twin_type] = stats['by_type'].get(twin.twin_type, 0) + 1
            
            # Total versions
            stats['total_versions'] += len(twin.versions)
            
            # Count orphaned and root twins
            if not twin.parent_id:
                stats['root_twins'] += 1
        
        return stats

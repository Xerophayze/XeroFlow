# node_registry.py

import os
import importlib
from pathlib import Path

NODE_REGISTRY = {}

# Runtime registry of live node instances (for cross-node communication).
# Persistent nodes register themselves here when they start so other nodes
# (e.g. WhatsAppWebNode) can discover and call them directly.
RUNNING_INSTANCES = {}  # node_type -> node_instance


def register_running_instance(node_type: str, instance):
    """Register a live node instance so other nodes can discover it."""
    RUNNING_INSTANCES[node_type] = instance


def get_running_instance(node_type: str):
    """Get a live node instance by type, or None if not running."""
    return RUNNING_INSTANCES.get(node_type)


def unregister_running_instance(node_type: str):
    """Remove a node instance from the running registry."""
    RUNNING_INSTANCES.pop(node_type, None)


def get_node_catalog():
    """Return metadata about registered nodes for agent tool selection."""
    catalog = []
    for node_type, node_cls in NODE_REGISTRY.items():
        description = (node_cls.__doc__ or '').strip() or None
        inputs = []
        outputs = []
        try:
            instance = node_cls(node_id=f"_catalog_{node_type}", config={})
            inputs = instance.define_inputs()
            outputs = instance.define_outputs()
            props = instance.define_properties()
            prop_desc = None
            if isinstance(props, dict):
                prop_desc = props.get('description', {}).get('default')
            if prop_desc:
                description = prop_desc
        except Exception:
            pass
        catalog.append({
            'type': node_type,
            'description': description or 'No description available.',
            'inputs': inputs,
            'outputs': outputs
        })
    return catalog

def register_node(node_type):
    """
    Decorator to register node classes with a unique type identifier.
    """
    def decorator(cls):
        if node_type in NODE_REGISTRY:
            # Instead of raising an error, just return the existing registration
            print(f"Node type '{node_type}' is already registered, skipping duplicate registration.")
            return NODE_REGISTRY[node_type]
        NODE_REGISTRY[node_type] = cls
        print(f"Registered node type: {node_type}")  # Debug statement
        return cls
    return decorator

def reload_nodes():
    """
    Reload all node modules from the 'nodes' directory and update NODE_REGISTRY.
    """
    global NODE_REGISTRY
    NODE_REGISTRY.clear()
    print("Cleared NODE_REGISTRY for reloading nodes.")

    # Get the project root directory
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    nodes_dir = os.path.join(project_root, "nodes")
    
    for filename in os.listdir(nodes_dir):
        if filename.endswith('.py') and filename not in ('__init__.py', 'base_node.py', 'missing_node.py'):
            module_name = filename[:-3]
            module_path = f'nodes.{module_name}'
            try:
                module = importlib.import_module(module_path)
                importlib.reload(module)  # Always reload to get fresh registrations
                print(f"Reloaded node module: {module_path}")
            except Exception as e:
                print(f"Failed to reload/import node module '{module_path}': {e}")

# Automatically import all node modules in the 'nodes' directory upon initial load
def initial_load_nodes():
    """Load all nodes from the nodes directory on first import."""
    # Get the project root directory (where main.py is located)
    # This file is at src/workflows/node_registry.py, so go up 2 levels to get to root
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    nodes_dir = os.path.join(project_root, "nodes")
    
    if not os.path.exists(nodes_dir):
        print(f"Warning: nodes directory not found at {nodes_dir}")
        return
    
    for filename in os.listdir(nodes_dir):
        if filename.endswith('.py') and filename not in ('__init__.py', 'base_node.py', 'missing_node.py'):
            module_name = filename[:-3]
            module_path = f'nodes.{module_name}'
            try:
                importlib.import_module(module_path)
                print(f"Imported node module: {module_path}")
            except Exception as e:
                print(f"Failed to import node module '{module_path}': {e}")

# Perform the initial loading of nodes
initial_load_nodes()

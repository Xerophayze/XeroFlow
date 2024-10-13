# node_registry.py

import os
import importlib
from pathlib import Path

NODE_REGISTRY = {}

def register_node(node_type):
    """
    Decorator to register node classes with a unique type identifier.
    """
    def decorator(cls):
        if node_type in NODE_REGISTRY:
            raise ValueError(f"Node type '{node_type}' is already registered.")
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

    nodes_dir = Path(__file__).parent / 'nodes'
    for filename in os.listdir(nodes_dir):
        if filename.endswith('.py') and filename not in ('__init__.py', 'base_node.py'):
            module_name = filename[:-3]
            module_path = f'nodes.{module_name}'
            try:
                importlib.reload(importlib.import_module(module_path))
                print(f"Reloaded node module: {module_path}")
            except ModuleNotFoundError:
                # If the module isn't already loaded, import it
                importlib.import_module(module_path)
                print(f"Imported node module: {module_path}")
            except Exception as e:
                print(f"Failed to reload/import node module '{module_path}': {e}")

# Automatically import all node modules in the 'nodes' directory upon initial load
def initial_load_nodes():
    nodes_dir = Path(__file__).parent / 'nodes'
    for filename in os.listdir(nodes_dir):
        if filename.endswith('.py') and filename not in ('__init__.py', 'base_node.py'):
            module_name = filename[:-3]
            module_path = f'nodes.{module_name}'
            try:
                importlib.import_module(module_path)
                print(f"Initially loaded node module: {module_path}")
            except Exception as e:
                print(f"Failed to load node module '{module_path}': {e}")

# Perform the initial loading of nodes
initial_load_nodes()

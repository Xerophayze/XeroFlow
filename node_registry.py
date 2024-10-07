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

# Automatically import all node modules in the 'nodes' directory
nodes_dir = Path(__file__).parent / 'nodes'
for filename in os.listdir(nodes_dir):
    if filename.endswith('.py') and filename not in ('__init__.py', 'base_node.py'):
        module_name = filename[:-3]
        module_path = f'nodes.{module_name}'
        importlib.import_module(module_path)

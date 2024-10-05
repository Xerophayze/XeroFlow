# node_registry.py
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

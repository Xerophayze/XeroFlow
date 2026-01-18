# nodes/missing_node.py

from .base_node import BaseNode
from src.workflows.node_registry import register_node

@register_node("MissingNode")
class MissingNode(BaseNode):
    """A placeholder node for when the original node class cannot be found."""
    
    def __init__(self, node_id, config, original_type="Unknown"):
        super().__init__(node_id, config)
        self.original_type = original_type
        self.title = f"Missing Node: {original_type}"
        self.properties = {
            "description": {
                "type": "string",
                "default": f"This node type '{original_type}' is no longer available."
            }
        }
        self.inputs = {}
        self.outputs = {}
        self.width = 200
        self.height = 150
        self.is_missing = True  # Flag to identify missing nodes
        
    def define_inputs(self):
        return self.inputs  # No inputs for missing node
        
    def define_outputs(self):
        return self.outputs  # No outputs for missing node
        
    def define_properties(self):
        props = self.get_default_properties()
        props.update(self.properties)
        return props
        
    def process(self, inputs):
        return {"error": f"This node (originally of type {self.original_type}) is no longer available."}

    def get_title(self):
        return self.title

    def get_properties(self):
        return self.properties

    def get_inputs(self):
        return self.inputs

    def get_outputs(self):
        return self.outputs

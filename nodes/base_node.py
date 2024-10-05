# nodes/base_node.py
from abc import ABC, abstractmethod

class BaseNode(ABC):
    """
    Abstract Base Class for all nodes.
    """

    def __init__(self, node_id, config):
        self.id = node_id
        self.config = config
        self.properties = self.define_properties()
        self.inputs = self.define_inputs()      # Initialize inputs
        self.outputs = self.define_outputs()    # Initialize outputs

    @abstractmethod
    def define_inputs(self):
        """
        Define the input connectors for the node.
        Should return a list of input names.
        """
        pass

    @abstractmethod
    def define_outputs(self):
        """
        Define the output connectors for the node.
        Should return a list of output names.
        """
        pass

    @abstractmethod
    def define_properties(self):
        """
        Define the properties for the node.
        Should return a dictionary of properties.
        """
        pass

    @abstractmethod
    def process(self, inputs):
        """
        Process the node's logic.
        Should return a dictionary with outputs.
        """
        pass

    def set_properties(self, node_data):
        """
        Set the properties of the node from node_data.
        """
        for prop, value in node_data.get('properties', {}).items():
            if prop in self.properties:
                self.properties[prop]['default'] = value.get('default', self.properties[prop].get('default'))

    def get_default_properties(self):
        """
        Returns the default properties that every node should have.
        """
        return {
            'description': {'type': 'text', 'default': 'No description provided.'},
            'Prompt': {'type': 'textarea', 'default': ''},
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        }

    def requires_api_call(self):
        """
        Indicates whether this node requires an API call.
        Override in subclasses if needed.
        """
        return False

    def get_next_node_ids(self, node_output, connections):
        """
        Determines the next node IDs based on the current node's outputs and existing connections.

        Args:
            node_output (dict): The output data from the current node's process method.
            connections (list): A list of connection dictionaries.

        Returns:
            list: A list of IDs for the next nodes.
        """
        next_node_ids = []
        for output_key in node_output.keys():
            # Find connections where the current node is the source and the output matches
            for conn in connections:
                if conn['from_node'] == self.id and conn['from_output'] == output_key:
                    next_node_ids.append(conn['to_node'])
        return next_node_ids

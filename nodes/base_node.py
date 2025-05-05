# nodes/base_node.py
from abc import ABC, abstractmethod
from services.api_service import APIService, APIRequest, APIResponse

class BaseNode(ABC):
    """
    Abstract Base Class for all nodes.
    """

    def __init__(self, node_id, config):
        self.id = node_id
        self.config = config
        self._api_service = APIService(config)
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

    def get_api_service(self) -> APIService:
        """Get the API service instance"""
        return self._api_service

    def get_api_endpoints(self):
        """Get available API endpoints"""
        return self._api_service.get_available_endpoints()

    def send_api_request(self, content: str, api_name: str, **kwargs) -> APIResponse:
        """
        Send a request to the API service.
        
        Args:
            content: Content to send to the API
            api_name: Name of the API endpoint to use
            **kwargs: Additional API parameters
            
        Returns:
            APIResponse object containing the response
        """
        request = APIRequest(
            content=content,
            api_name=api_name,
            model=kwargs.get('model'),
            max_tokens=kwargs.get('max_tokens'),
            temperature=kwargs.get('temperature'),
            additional_params=kwargs.get('additional_params')
        )
        return self._api_service.send_request(request)

    @abstractmethod
    def process(self, inputs):
        """
        Process the inputs and return outputs.
        
        Args:
            inputs (dict): Dictionary of input values. Each input can be either a single value or a list of values
                         if multiple connections are made to the same input.
                        
        Returns:
            dict: Dictionary of output values
        """
        # Default implementation just passes through the input
        # Derived classes should override this method
        if not inputs:
            return {}
            
        # Handle the case where an input might be a list from multiple connections
        processed_inputs = {}
        for input_name, input_value in inputs.items():
            if isinstance(input_value, list):
                # If the input is a list, join the values with newlines
                if all(isinstance(x, str) for x in input_value):
                    processed_inputs[input_name] = "\n\n".join(input_value)
                else:
                    # For non-string values, keep as list
                    processed_inputs[input_name] = input_value
            else:
                processed_inputs[input_name] = input_value
        
        return processed_inputs

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

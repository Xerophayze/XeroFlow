# nodes/processing_node.py
from .base_node import BaseNode
from node_registry import register_node  # Import the decorator
from api_handler import process_api_request  # Correct import

@register_node('ProcessingNode')
class ProcessingNode(BaseNode):
    """
    Processing Node: Processes the input data and prepares the prompt for the API.
    """

    def define_inputs(self):
        return ['input']  # Consistent naming for the input - you could define multiple inputs here if needed

    def define_outputs(self):
        return ['prompt']  # Single output, 'prompt', you can define further outputs here for example 'output2', 'prompt2' etc

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'ProcessingNode'},  # New property for dynamic name
            'description': {'type': 'text', 'default': 'Processes the input prompt and prepares it for the API.'},
            'Prompt': {'type': 'textarea', 'default': 'Processing your request...'},
            'api_endpoint': {'type': 'dropdown', 'options': self.get_api_endpoints()},
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        print(f"[ProcessingNode] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        api_list = list(interfaces.keys())
        print(f"[ProcessingNode] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def process(self, inputs):
        """
        Process the input by:
        1. Combining the prompt with input.
        2. Making the API call.
        3. Processing the API response as needed.
        4. Outputting the result as 'prompt'.
        """
        print("[ProcessingNode] Starting process method.")

        # Get properties
        prompt = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')

        if not api_endpoint_name:
            print("[ProcessingNode] API endpoint not specified.")
            return {}  # Or handle as error

        # Combine prompt with input from the previous node
        previous_input = inputs.get('input', '').strip()
        combined_prompt = f"{prompt}\n{previous_input}" if previous_input else prompt

        # Log the combined prompt for debugging
        print(f"[ProcessingNode] Combined Prompt to be sent to API: {combined_prompt}")
        print(f"[ProcessingNode] Selected API Endpoint: {api_endpoint_name}")

        # Retrieve API details from configuration
        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            print(f"[ProcessingNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {}  # Or handle as error

        # Make the API call using process_api_request
        api_response_content = process_api_request(api_details, combined_prompt)

        if 'error' in api_response_content:
            print(f"[ProcessingNode] API Error: {api_response_content['error']}")
            return {}  # Or handle as error

        # Extract the actual response based on API type
        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            api_response = api_response_content.get('response', 'No response available')
        else:
            api_response = 'Unsupported API type.'

        print(f"[ProcessingNode] API Response: {api_response}")

        # Output the API response as 'prompt'
        return {'prompt': api_response}

    def requires_api_call(self):
        return False  # API call is handled within the node
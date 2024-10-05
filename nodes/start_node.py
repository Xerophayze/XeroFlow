# nodes/start_node.py
from .base_node import BaseNode
from node_registry import register_node  # Import the decorator
from api_handler import process_api_request  # Correct import

@register_node('StartNode')
class StartNode(BaseNode):
    """
    Start Node: Initiates the workflow by providing user input and selecting the API endpoint.
    """

    def define_inputs(self):
        # Start Node does not have any inputs as it receives input from the user directly
        return []

    def define_outputs(self):
        # Start Node outputs only 'prompt'
        return ['prompt']

    def define_properties(self):
        # Start with default properties
        props = self.get_default_properties()

        # Retrieve API endpoints
        api_endpoints = self.get_api_endpoints()

        # Set default API endpoint to the first one if available
        default_api = api_endpoints[0] if api_endpoints else ''

        # Update default properties specific to StartNode
        props.update({
            'node_name': {'type': 'text', 'default': 'StartNode'},  # New property for dynamic name
            'description': {'type': 'text', 'default': 'Start of the workflow'},
            'Prompt': {'type': 'textarea', 'default': 'Process the following request:'},
            'api_endpoint': {'type': 'dropdown', 'options': api_endpoints, 'default': default_api},
            'is_start_node': {'type': 'boolean', 'default': True},
            'is_end_node': {'type': 'boolean', 'default': False}
        })

        return props

    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        print(f"[StartNode] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        api_list = list(interfaces.keys())
        print(f"[StartNode] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def process(self, inputs):
        """
        Start the workflow by:
        1. Combining the prompt with user input.
        2. Making the API call.
        3. Outputting the API response as 'prompt'.
        """
        print("[StartNode] Starting process method.")

        # Get properties
        prompt = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')

        if not api_endpoint_name:
            print("[StartNode] API endpoint not specified.")
            return {}  # Or handle as error

        # Assume user input is provided externally; if not, handle accordingly
        user_input = inputs.get('input', '').strip()
        combined_prompt = f"{prompt}\n{user_input}" if user_input else prompt

        # Log the combined prompt for debugging
        print(f"[StartNode] Combined Prompt to be sent to API: {combined_prompt}")
        print(f"[StartNode] Selected API Endpoint: {api_endpoint_name}")

        # Retrieve API details from configuration
        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            print(f"[StartNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {}  # Or handle as error

        # Make the API call using process_api_request
        api_response_content = process_api_request(api_details, combined_prompt)

        if 'error' in api_response_content:
            print(f"[StartNode] API Error: {api_response_content['error']}")
            return {}  # Or handle as error

        # Extract the actual response based on API type
        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            api_response = api_response_content.get('response', 'No response available')
        else:
            api_response = 'Unsupported API type.'

        print(f"[StartNode] API Response: {api_response}")

        # Output the API response as 'prompt'
        return {'prompt': api_response}

    def requires_api_call(self):
        return False  # API call is handled within the node

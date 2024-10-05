# nodes/search_node.py
from .base_node import BaseNode
from node_registry import register_node  # Import the decorator
from api_handler import process_api_request  # Correct import

@register_node('SearchNode')
class SearchNode(BaseNode):
    """
    Search Node: Processes the input prompt, sends it to the API,
                receives the response, searches for a specified term,
                and routes the response accordingly.
    """

    def define_inputs(self):
        return ['input']  # Input from the previous node

    def define_outputs(self):
        return ['output_true', 'output_false']  # Outputs based on search result

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'SearchNode'},  # New property for dynamic name
            'description': {
                'type': 'text',
                'default': 'Processes the input prompt, sends it to the API, and searches for a specified term in the response.'
            },
            'Prompt': {
                'type': 'textarea',
                'default': 'Process the following request:'
            },
            'api_endpoint': {
                'type': 'dropdown',
                'options': self.get_api_endpoints()
            },
            'Search Term': {
                'type': 'text',
                'default': 'poem'  # Default search term; can be modified by the user
            },
            'is_start_node': {
                'type': 'boolean',
                'default': False
            },
            'is_end_node': {
                'type': 'boolean',
                'default': False
            }
        })
        return props

    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        print(f"[SearchNode] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        api_list = list(interfaces.keys())
        print(f"[SearchNode] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def process(self, inputs):
        """
        Process the input by:
        1. Combining the prompt with input.
        2. Making the API call.
        3. Searching for the term in the response.
        4. Routing the output based on the search result.
        """
        print("[SearchNode] Starting process method.")

        # Get properties
        prompt = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        search_term = self.properties.get('Search Term', {}).get('default', '').strip()

        if not api_endpoint_name:
            print("[SearchNode] API endpoint not specified.")
            return {}  # Or handle as error

        # Combine prompt with input from the previous node
        previous_input = inputs.get('input', '').strip()
        combined_prompt = f"{prompt}\n{previous_input}" if previous_input else prompt

        # Log the combined prompt for debugging
        print(f"[SearchNode] Combined Prompt to be sent to API: {combined_prompt}")
        print(f"[SearchNode] Selected API Endpoint: {api_endpoint_name}")
        print(f"[SearchNode] Search Term: '{search_term}'")

        # Retrieve API details from configuration
        api_details = self.config.get('interfaces').get(api_endpoint_name)
        if not api_details:
            print(f"[SearchNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {}  # Or handle as error

        # Make the API call using process_api_request
        api_response_content = process_api_request(api_details, combined_prompt)

        if 'error' in api_response_content:
            print(f"[SearchNode] API Error: {api_response_content['error']}")
            return {}  # Or handle as error

        # Extract the actual response based on API type
        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            api_response = api_response_content.get('response', 'No response available')
        else:
            api_response = 'Unsupported API type.'

        print(f"[SearchNode] API Response: {api_response}")

        # Perform the search (case-insensitive)
        if search_term.lower() in api_response.lower():
            # Search term found
            print(f"[SearchNode] Search term '{search_term}' found in API response.")
            return {'output_true': api_response}
        else:
            # Search term not found
            print(f"[SearchNode] Search term '{search_term}' not found in API response.")
            return {'output_false': api_response}

    def requires_api_call(self):
        return False  # API call is handled within the node
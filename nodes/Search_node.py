# nodes/search_node.py
import re
import string
import unicodedata
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
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'SearchNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input prompt, sends it to the API, and searches for a specified term in the response.'
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'Prompt',
                'default': 'Process the following request:'
            },
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            },
            'Search Term': {
                'type': 'text',
                'label': 'Search Term',
                'default': 'REVIEWPASS'  # Ensure default is set without quotes
            },
            'is_start_node': {
                'type': 'boolean',
                'label': 'Start Node',
                'default': False
            },
            'is_end_node': {
                'type': 'boolean',
                'label': 'End Node',
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
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[SearchNode] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def sanitize_text(self, text):
        """Remove non-printable characters from text."""
        printable = set(string.printable)
        return ''.join(filter(lambda x: x in printable, text))

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
        prompt_property = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        search_term = self.properties.get('Search Term', {}).get('default', '').strip()

        # Debugging Search Term
        print(f"[SearchNode] Debug - Search Term: '{search_term}'")

        if not api_endpoint_name:
            print("[SearchNode] API endpoint not specified.")
            return {"output_true": "API endpoint not specified.", "output_false": "API endpoint not specified."}

        # Combine prompt with input from the previous node
        previous_input = inputs.get('input', '').strip()
        combined_prompt = f"{prompt_property}\n{previous_input}" if previous_input else prompt_property

        # Log the combined prompt for debugging
        print(f"[SearchNode] Combined Prompt to be sent to API: {combined_prompt}")
        print(f"[SearchNode] Selected API Endpoint: {api_endpoint_name}")
        print(f"[SearchNode] Search Term: '{search_term}'")

        # Retrieve API details from configuration
        api_details = self.config.get('interfaces', {}).get(api_endpoint_name)
        if not api_details:
            print(f"[SearchNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {"output_true": f"API interface '{api_endpoint_name}' not found.", "output_false": f"API interface '{api_endpoint_name}' not found."}

        # Make the API call using process_api_request
        api_response_content = process_api_request(api_details, combined_prompt)

        if 'error' in api_response_content:
            print(f"[SearchNode] API Error: {api_response_content['error']}")
            return {"output_true": f"API Error: {api_response_content['error']}", "output_false": f"API Error: {api_response_content['error']}"}

        # Extract the actual response based on API type
        api_type = api_details.get('api_type')
        print(f"[SearchNode] API Type: {api_type}")
        if api_type == "OpenAI":
            api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            message = api_response_content.get('message', {})
            api_response = message.get('content', '') if isinstance(message, dict) else 'No response available'
        else:
            api_response = 'Unsupported API type.'

        print(f"[SearchNode] Raw API Response: {api_response}")

        # Sanitize and normalize texts
        sanitized_response = self.sanitize_text(api_response)
        normalized_response = unicodedata.normalize('NFKC', sanitized_response)
        normalized_search_term = unicodedata.normalize('NFKC', search_term)

        # Perform the search using regex for exact word match
        if re.search(r'\b' + re.escape(normalized_search_term) + r'\b', normalized_response, re.IGNORECASE):
            # Search term found
            print(f"[SearchNode] Search term '{search_term}' found in API response.")
            print(f"[SearchNode] Routing to 'output_true'.")
            return {'output_true': api_response, 'output_false': ''}
        else:
            # Search term not found
            print(f"[SearchNode] Search term '{search_term}' not found in API response.")
            print(f"[SearchNode] Routing to 'output_false'.")
            return {'output_true': '', 'output_false': api_response}

    def requires_api_call(self):
        return True  # API call is handled within the node

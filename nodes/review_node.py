# nodes/review_node.py

import re
import string
import unicodedata
from .base_node import BaseNode
from src.workflows.node_registry import register_node
from src.api.handler import process_api_request

@register_node('ReviewNode')
class ReviewNode(BaseNode):
    """
    Review Node: Processes the input, appends API response, and searches for a specified term in the combined text.
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
                'default': 'ReviewNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input, appends API response, and searches for a specified term in the combined text.'
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
        print(f"[ReviewNode] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[ReviewNode] Available API endpoints: {api_list}")  # Debug statement
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
        3. Appending API response to input to create combined text.
        4. Searching for the term in the combined text.
        5. Routing the output based on the search result.
        """
        print("[ReviewNode] Starting process method.")

        # Get properties
        prompt_property = self.get_property('Prompt')
        api_endpoint_name = self.get_property('api_endpoint')
        search_term = self.get_property('Search Term').strip()

        # Debugging Search Term
        print(f"[ReviewNode] Debug - Search Term: '{search_term}'")

        if not api_endpoint_name:
            print("[ReviewNode] API endpoint not specified.")
            return {"output_true": "API endpoint not specified.", "output_false": "API endpoint not specified."}

        # Combine prompt with input from the previous node
        previous_input = inputs.get('input', '').strip()
        combined_prompt = f"{prompt_property}\n{previous_input}" if previous_input else prompt_property

        # Log the combined prompt for debugging
        print(f"[ReviewNode] Combined Prompt to be sent to API: {combined_prompt}")
        print(f"[ReviewNode] Selected API Endpoint: {api_endpoint_name}")
        print(f"[ReviewNode] Search Term: '{search_term}'")

        # Retrieve API details from configuration
        api_details = self.config.get('interfaces', {}).get(api_endpoint_name)
        if not api_details:
            print(f"[ReviewNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {"output_true": f"API interface '{api_endpoint_name}' not found.", "output_false": f"API interface '{api_endpoint_name}' not found."}

        # Make the API call using process_api_request
        api_response_content = process_api_request(api_details, combined_prompt)

        if 'error' in api_response_content:
            print(f"[ReviewNode] API Error: {api_response_content['error']}")
            return {"output_true": f"API Error: {api_response_content['error']}", "output_false": f"API Error: {api_response_content['error']}"}

        # Extract the actual response based on API type
        api_type = api_details.get('api_type')
        print(f"[ReviewNode] API Type: {api_type}")
        if api_type == "OpenAI":
            api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            message = api_response_content.get('message', {})
            api_response = message.get('content', '') if isinstance(message, dict) else 'No response available'
        else:
            api_response = 'Unsupported API type.'

        print(f"[ReviewNode] Raw API Response: {api_response}")

        # Append API response to input to create combined text
        combined_text = previous_input + "\n\n" + api_response

        # Sanitize and normalize texts
        sanitized_text = self.sanitize_text(combined_text)
        normalized_text = unicodedata.normalize('NFKC', sanitized_text)
        normalized_search_term = unicodedata.normalize('NFKC', search_term)

        # Perform the search using regex for exact word match
        if re.search(r'\b' + re.escape(normalized_search_term) + r'\b', normalized_text, re.IGNORECASE):
            # Search term found
            print(f"[ReviewNode] Search term '{search_term}' found in combined text.")
            print(f"[ReviewNode] Routing to 'output_true'.")
            return {'output_true': previous_input, 'output_false': ''}
        else:
            # Search term not found
            print(f"[ReviewNode] Search term '{search_term}' not found in combined text.")
            print(f"[ReviewNode] Routing to 'output_false'.")
            return {'output_true': '', 'output_false': combined_text}

    def requires_api_call(self):
        return True  # API call is handled within the node

    def get_property(self, property_name):
        """Helper method to retrieve property values."""
        prop = self.properties.get(property_name, {})
        return prop.get('value', prop.get('default', ''))

    @property
    def is_start_node(self):
        """Property to get the current 'is_start_node' value."""
        prop = self.properties.get('is_start_node', {})
        return prop.get('value', prop.get('default', False))

    @property
    def is_end_node(self):
        """Property to get the current 'is_end_node' value."""
        prop = self.properties.get('is_end_node', {})
        return prop.get('value', prop.get('default', False))

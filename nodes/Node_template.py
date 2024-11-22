# nodes/chat_node.py
from .base_node import BaseNode
from node_registry import register_node
from api_handler import process_api_request

@register_node('TemplateNode')
class BasicNode(BaseNode):
    def define_inputs(self):
        return ['input']  # Single input named 'input'

    def define_outputs(self):
        return ['output']  # Single output named 'output'

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'TempateNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input prompt and prepares it for the API.'
            },
            # 'Prompt': { #this is the box where the user can enter a predesignated prompt that the input can be added to before processing
            #     'type': 'textarea',
            #     'label': 'Prompt',
            #     'default': 'Processing your request...'
            # },
            # 'api_endpoint': { # this dropdown allows the user to select a specific api endpoint to use on this node if it requires api interaction
            #     'type': 'dropdown',
            #     'label': 'API Endpoint',
            #     'options': self.get_api_endpoints(),
            #     'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            # },
            'is_start_node': {
                'type': 'boolean',
                'label': 'Start Node',
                'default': False
            },
            'is_end_node': {
                'type': 'boolean',
                'label': 'End Node',
                'default': False
            },
            'is_persistent': {
                'type': 'boolean',
                'label': 'Persistent Node',
                'default': True,
                'description': 'If true, the node will remain active and accept more inputs.'
            }
        })
        return props

    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        print(f"[BasicNode] Node name updated to: {new_name}")

    # def get_api_endpoints(self):
    #     # Retrieve API endpoint names from the configuration
    #     interfaces = self.config.get('interfaces', {})
    #     if interfaces is None:
    #         interfaces = {}
    #     api_list = list(interfaces.keys())
    #     print(f"[BasicNode] Available API endpoints: {api_list}")  # Debug statement
    #     return api_list

    def process(self, inputs):
        """
        The process section below is the code used to process the incoming input string.
        Process the input by appending it to the Prompt.
        if needed, send the combined input to the API, and return the API response as the output.
        """
        # Retrieve the incoming input
        incoming_input = inputs.get('input', '').strip()
        print(f"[BasicNode] Incoming input: '{incoming_input}'")  # Debug statement
        
        # Pass the input directly to output for a simple flow-through
        output = {'output': incoming_input}
        return output #use this to return the processed output if not using api endpoint.

    # def send_to_api(self, combined_input, api_details):
    #     """
    #     Sends the combined input to the specified API and returns the response.
    #     """
    #     if not combined_input:
    #         print("[BasicNode] No input provided to send to the API.")
    #         return "No input provided."

    #     if not api_details:
    #         print("[BasicNode] No API details provided.")
    #         return "API details are missing."

    #     # Construct the prompt using the combined input
    #     prompt = combined_input
    #     print(f"[BasicNode] Constructed prompt: '{prompt}'")  # Debug statement

    #     # Send the prompt to the API
    #     api_response_content = process_api_request(api_details, prompt)
    #     print(f"[BasicNode] Raw API response content: {api_response_content}")  # Debug statement

    #     if api_response_content is None:
    #         print("[BasicNode] API response is None.")
    #         return "API response is None."

    #     if not isinstance(api_response_content, dict):
    #         print("[BasicNode] API response is not a dictionary.")
    #         return "Invalid API response format."

    #     if 'error' in api_response_content:
    #         error_message = api_response_content.get('error', 'Unknown error occurred.')
    #         print(f"[BasicNode] API Error: {error_message}")  # Debug statement
    #         return f"API Error: {error_message}"

    #     # Extract the actual response based on API type
    #     api_type = api_details.get('api_type')
    #     if api_type == "OpenAI":
    #         response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
    #     elif api_type == "Ollama":
    #         if isinstance(api_response_content, dict):
    #             # Adjusted to match the actual response structure from Ollama
    #             message = api_response_content.get('message', {})
    #             response = message.get('content', 'No response available')
    #         elif isinstance(api_response_content, str):
    #             response = api_response_content
    #         else:
    #             response = 'No response available'
    #     else:
    #         response = 'Unsupported API type.'
    #         print(f"[BasicNode] Unsupported API type: {api_type}")  # Debug statement

    #     print(f"[BasicNode] Extracted response: '{response}'")  # Debug statement

    #     # Return the API response as a string
    #     return response #this is the output if using the api endpoint

    def requires_api_call(self):
        return False  # Set to True if this node makes an API call

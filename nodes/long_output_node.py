# nodes/long_output_node.py
"""
LongOutputNode: Processes an initial input by sending each item to the API endpoint.
The initial input is expected to be split by paragraph (empty lines between blocks of text).
It iteratively processes each item from this list, sending each to the API,
and accumulates the responses by appending each new response to the previous one along with the next item.
"""
from .base_node import BaseNode
from node_registry import register_node  # Import the decorator
from api_handler import process_api_request  # Correct import

@register_node('LongOutputNode')
class LongOutputNode(BaseNode):

    def define_inputs(self):
        return ['input']  # Input from the previous node

    def define_outputs(self):
        return ['prompt']  # Output the final combined response

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'LongOutputNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes a list of items through the API, combining responses.'
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'Prompt',
                'default': ''  # User-defined prompt
            },
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
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

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[LongOutputNode] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def process(self, inputs):
        print("[LongOutputNode] Starting process method.")

        # Get properties
        prompt_property = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')

        if not api_endpoint_name:
            print("[LongOutputNode] API endpoint not specified.")
            return {"output": "API endpoint not specified."}  # Or handle as error

        # Get input
        previous_input = inputs.get('input', '').strip()

        if not previous_input:
            print("[LongOutputNode] No input provided.")
            return {"output": "No input provided."}

        # Split the input into items (paragraphs separated by double newlines)
        items = [item.strip() for item in previous_input.split('\n\n') if item.strip()]
        if not items:
            print("[LongOutputNode] No valid items found in input.")
            return {"output": "No valid items found in input."}

        # Retrieve API details from configuration
        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            print(f"[LongOutputNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {"output": f"API interface '{api_endpoint_name}' not found."}  # Or handle as error

        api_type = api_details.get('api_type')
        if not api_type:
            print(f"[LongOutputNode] API type not specified for endpoint '{api_endpoint_name}'.")
            return {"output": f"API type not specified for endpoint '{api_endpoint_name}'."}

        # Initialize combined_response and last_response
        combined_response = ''
        last_response = ''

        # Iterate over the items
        for index, item in enumerate(items):
            if index == 0:
                # First item, use the base prompt
                prompt = f"{previous_input}\n\n the following should just be the title from the outline above, please just repeat the title and nothing else:\n{item}"
            elif index == len(items) - 1:
                # Last item, perform a final API call
                prompt = f"{previous_input}\n\n The section below should be the final section from the outline above, please finish writting the contend for this last outline item:\n{item}"
            else:
                # Intermediate items
                prompt = f"The outline is as follows:\n{previous_input}\n\nThe last section or chapter written is as follows:\n{last_response}\n\nAs a professional writter, Continue writing the detailed content for the next chapter/section shown below. do not include any of your own commentary, just write the content based on the next section listed below. Always include the chapter/section number and title in bold.  Be detailed, creative, giving depth and meaning:\n{item}"

            print(f"[LongOutputNode] Sending to API: {prompt}")

            # Make the API call using process_api_request
            api_response_content = process_api_request(api_details, prompt)

            if 'error' in api_response_content:
                print(f"[LongOutputNode] API Error: {api_response_content['error']}")
                return {"output": f"API Error: {api_response_content['error']}"}

            # Extract the actual response based on API type
            if api_type == "OpenAI":
                api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', '')
            elif api_type == "Ollama":
                message = api_response_content.get('message', {})
                api_response = message.get('content', '') if isinstance(message, dict) else ''
            else:
                api_response = 'Unsupported API type.'

            print(f"[LongOutputNode] API Response: {api_response}")

            # Update last_response to include the latest response
            last_response = api_response  # Replace last_response with current response

            # Append the response to the combined_response
            combined_response += '\n' + api_response + '\n'

        # Step 5: Return the final combined response
        final_output = combined_response.strip()
        print(f"[LongOutputNode] Final combined response: {final_output}")
        return {'prompt': final_output}

    def requires_api_call(self):
        return True  # API call is handled within the node

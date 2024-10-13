# nodes/long_output_node.py
"""
LongOutputNode: Processes an initial prompt and input by sending them to the API endpoint.
The API response is expected to be split by paragraph (empty lines between blocks of text).
It then iteratively processes each item from this list, sending each to the API,
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
            'node_name': {'type': 'text', 'default': 'LongOutputNode'},
            'description': {'type': 'text', 'default': 'Processes a list of items through the API, combining responses.'},
            'Prompt': {'type': 'textarea', 'default': ''},  # User-defined prompt
            'api_endpoint': {'type': 'dropdown', 'options': self.get_api_endpoints()},
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        api_list = list(interfaces.keys())
        print(f"[LongOutputNode] Available API endpoints: {api_list}")
        return api_list

    def process(self, inputs):
        print("[LongOutputNode] Starting process method.")

        # Get properties and reset combined prompt
        prompt_property = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')

        # Reset the combined prompt explicitly to an empty string
        combined_prompt = ""

        if not api_endpoint_name:
            print("[LongOutputNode] API endpoint not specified.")
            return {}  # Or handle as error

        # Get input
        previous_input = inputs.get('input', '').strip()

        # Append the input to the end of the Prompt property
        combined_prompt = f"{prompt_property}\n{previous_input}" if previous_input else prompt_property

        if not combined_prompt.strip():
            print("[LongOutputNode] No input provided.")
            return {}

        # Retrieve API details from configuration
        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            print(f"[LongOutputNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {}  # Or handle as error

        # Step 1: Send the combined prompt to the API endpoint
        print(f"[LongOutputNode] Sending initial prompt to API: {combined_prompt}")
        initial_api_response_content = process_api_request(api_details, combined_prompt)

        if 'error' in initial_api_response_content:
            print(f"[LongOutputNode] API Error: {initial_api_response_content['error']}")
            return {}  # Or handle as error

        # Extract the actual response based on API type
        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            initial_api_response = initial_api_response_content.get('choices', [{}])[0].get('message', {}).get('content', '')
        elif api_type == "Ollama":
            initial_api_response = initial_api_response_content.get('response', '')
        else:
            initial_api_response = 'Unsupported API type.'

        print(f"[LongOutputNode] Initial API Response: {initial_api_response}")

        # Step 2: Split the initial API response into items (array), assuming paragraphs (double newline-separated values)
        items = [item.strip() for item in initial_api_response.split('\n\n') if item.strip()]
        if not items:
            print("[LongOutputNode] No valid items found in initial API response.")
            return {}

        # Step 3: Initialize combined_response and last_response
        combined_response = ''
        last_response = ''

        # Step 4: Iterate over the items
        for index, item in enumerate(items):
            if index == 0:
                # First item, send it to API
                prompt = f'\nyou will be writing a story based on the following context: {initial_api_response} \nThe content below may be the Title or prologue. If it is the Title, you will just repeat the title.  the title or beginning is as follows:\n{item}'
            elif index == len(items) - 1:
                # Last item, perform a final API call
                prompt = last_response + f'\nThis is the final section to be processed, based on: {initial_api_response}. Continue writing as follows:\n{item}'
            else:
                # Intermediate items
                prompt = last_response + f'\nUsing the following outline: {initial_api_response} continue writing the content for the following section and only this seciont without any other commentary. make sure Chapter headings are bold:\n{item}'

            print(f"[LongOutputNode] Sending to API: {prompt}")

            # Make the API call using process_api_request
            api_response_content = process_api_request(api_details, prompt)

            if 'error' in api_response_content:
                print(f"[LongOutputNode] API Error: {api_response_content['error']}")
                return {}  # Or handle as error

            # Extract the actual response based on API type
            if api_type == "OpenAI":
                api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', '')
            elif api_type == "Ollama":
                api_response = api_response_content.get('response', '')
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
        return False  # API call is handled within the node
# nodes/basic_node.py
from .base_node import BaseNode
from node_registry import register_node

@register_node('BasicNode')
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
                'default': 'BasicNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input prompt and prepares it for the API.'
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'Prompt',
                'default': 'Processing your request...'
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

    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        print(f"[BasicNode] Node name updated to: {new_name}")

    def process(self, inputs):
        """
        Process the input by appending it to the Prompt,
        send the combined input to the API, and return the API response as the output.
        """
        # Retrieve the incoming input
        incoming_input = inputs.get('input', '').strip()
        print(f"[BasicNode] Incoming input: '{incoming_input}'")

        # Retrieve the Prompt from properties
        prompt = self.properties.get('Prompt', {}).get('default', '').strip()
        print(f"[BasicNode] Original Prompt: '{prompt}'")

        # Combine the Prompt with the incoming input
        combined_input = f"{prompt} {incoming_input}".strip()
        print(f"[BasicNode] Combined input: '{combined_input}'")

        # Get the selected API endpoint
        selected_api = self.properties.get('api_endpoint', {}).get('default', '')
        if not selected_api:
            print("[BasicNode] No API endpoint selected.")
            return {'output': "No API endpoint selected."}

        # Get API details and send request
        api_config = self.config.get('interfaces', {}).get(selected_api, {})
        if not api_config:
            print("[BasicNode] API details not found for the selected endpoint.")
            return {'output': "API details not found for the selected endpoint."}

        # Send request through the API service
        response = self.send_api_request(
            content=combined_input,
            api_name=selected_api,
            model=api_config.get('selected_model'),
            max_tokens=api_config.get('max_tokens'),
            temperature=api_config.get('temperature', 0.7)
        )

        if not response.success:
            print(f"[BasicNode] API Error: {response.error}")
            return {'output': f"API Error: {response.error}"}

        return {'output': response.content}

    def requires_api_call(self):
        """Indicates whether this node requires an API call."""
        return True

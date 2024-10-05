# nodes/finish_node.py
from .base_node import BaseNode
from node_registry import register_node  # Import the decorator
from api_handler import process_api_request  # Correct import

@register_node('FinishNode')
class FinishNode(BaseNode):
    """
    Finish Node: Terminates the workflow and outputs the final result.
    """

    def define_inputs(self):
        # Finish Node has one input, which can come from multiple outputs of other nodes
        return ['input']  # Standardized to 'input'

    def define_outputs(self):
        # Finish Node has no outputs
        return []

    def define_properties(self):
        # Define basic properties without unnecessary fields
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'FinishNode'},  # New property for dynamic name
            'description': {'type': 'text', 'default': 'End of the workflow'},
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': True}  # Mark as end node
        })
        return props

    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        print(f"[FinishNode] Node name updated to: {new_name}")

    def process(self, inputs):
        # Handle the input received from the previous node
        input_data = inputs.get('input', '').strip()

        # If there's no input data, return a message indicating no data was received
        if not input_data:
            final_output = "No input received for final processing."
        else:
            final_output = input_data

        # Log the final output for debugging
        print(f"[FinishNode] Final Output: {final_output}")

        # Return the final output to be shown in the chat window
        return {'final_output': final_output}

    def requires_api_call(self):
        """
        Indicates that FinishNode does not require an API call.
        """
        return False
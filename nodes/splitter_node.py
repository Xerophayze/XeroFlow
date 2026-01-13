# nodes/splitter_node.py
"""
SplitterNode: Takes a single input and duplicates it to two outputs.
Useful for creating parallel processing branches in workflows.
"""
from .base_node import BaseNode
from node_registry import register_node


@register_node('SplitterNode')
class SplitterNode(BaseNode):
    """
    A simple logic node that takes one input and sends it to two outputs.
    Both outputs receive the exact same content.
    """

    def define_inputs(self):
        return ['input']

    def define_outputs(self):
        return ['output1', 'output2']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'SplitterNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Duplicates input to two outputs for parallel processing.'
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

    def process(self, inputs):
        """
        Duplicate the input to both outputs.
        """
        incoming_input = inputs.get('input', '')
        if isinstance(incoming_input, list):
            incoming_input = "\n\n".join(str(item) for item in incoming_input)

        print(f"[SplitterNode] Received input, duplicating to output1 and output2")
        return {
            'output1': incoming_input,
            'output2': incoming_input
        }

    def requires_api_call(self):
        return False

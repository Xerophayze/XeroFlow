# nodes/merger_node.py
"""
MergerNode: Takes two inputs and combines them into a single output.
Useful for rejoining parallel processing branches in workflows.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node


@register_node('MergerNode')
class MergerNode(BaseNode):
    """
    A simple logic node that takes two inputs and merges them into one output.
    The inputs are joined with a configurable separator.
    """

    def define_inputs(self):
        return ['input1', 'input2']

    def define_outputs(self):
        return ['output']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'MergerNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Combines two inputs into a single output.'
            },
            'separator': {
                'type': 'text',
                'label': 'Separator',
                'default': '\n\n',
                'description': 'Text to insert between the two inputs when merging.'
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
        Merge the two inputs into a single output using the configured separator.
        """
        input1 = inputs.get('input1', '')
        input2 = inputs.get('input2', '')

        # Handle list inputs
        if isinstance(input1, list):
            input1 = "\n\n".join(str(item) for item in input1)
        if isinstance(input2, list):
            input2 = "\n\n".join(str(item) for item in input2)

        separator = self.properties.get('separator', {}).get('default', '\n\n')

        # Build merged output
        parts = []
        if input1:
            parts.append(str(input1))
        if input2:
            parts.append(str(input2))

        merged = separator.join(parts)
        print(f"[MergerNode] Merged {len(parts)} input(s) into single output ({len(merged)} chars)")

        return {'output': merged}

    def requires_api_call(self):
        return False

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
        # Support up to 4 outputs; output_count property controls which are used
        return ['output1', 'output2', 'output3', 'output4']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'output_count': {
                'type': 'text',
                'label': 'Number of Outputs (1-4)',
                'default': '2',
                'description': 'How many outputs to populate (up to 4).'
            },
            'output1_as_text': {
                'type': 'boolean',
                'label': 'Convert Output 1 Array to Text',
                'default': False,
                'description': 'If enabled, arrays are joined into a single string for output1.'
            },
            'output2_as_text': {
                'type': 'boolean',
                'label': 'Convert Output 2 Array to Text',
                'default': False,
                'description': 'If enabled, arrays are joined into a single string for output2.'
            },
            'output3_as_text': {
                'type': 'boolean',
                'label': 'Convert Output 3 Array to Text',
                'default': False,
                'description': 'If enabled, arrays are joined into a single string for output3.'
            },
            'output4_as_text': {
                'type': 'boolean',
                'label': 'Convert Output 4 Array to Text',
                'default': False,
                'description': 'If enabled, arrays are joined into a single string for output4.'
            },
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
        # Preserve arrays for downstream nodes that expect lists
        if isinstance(incoming_input, tuple):
            incoming_input = list(incoming_input)

        output_count_raw = self.properties.get('output_count', {}).get('default', '2')
        try:
            output_count = max(1, min(4, int(output_count_raw)))
        except (TypeError, ValueError):
            output_count = 2

        def format_output(value, as_text):
            if as_text and isinstance(value, (list, tuple)):
                return "\n\n".join(str(item) for item in value)
            if isinstance(value, tuple):
                return list(value)
            return value

        outputs = {}
        for idx in range(1, 5):
            key = f"output{idx}"
            as_text = self.properties.get(f"output{idx}_as_text", {}).get('default', False)
            if idx <= output_count:
                outputs[key] = format_output(incoming_input, as_text)
            else:
                outputs[key] = ''

        print(f"[SplitterNode] Received input, duplicating to {output_count} outputs")
        return outputs

    def requires_api_call(self):
        return False

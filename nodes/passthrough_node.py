# nodes/passthrough_node.py
"""
PassThroughNode: A simple node that passes input directly to output without modification.
Useful for debugging, breakpoints, or as a placeholder in workflows.
"""
from .base_node import BaseNode
from node_registry import register_node


@register_node('PassThroughNode')
class PassThroughNode(BaseNode):
    """
    A simple pass-through node that forwards input to output unchanged.
    Can optionally log the content for debugging purposes.
    """

    def define_inputs(self):
        return ['input']

    def define_outputs(self):
        return ['output']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'PassThroughNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Passes input directly to output. Useful for debugging or as a placeholder.'
            },
            'log_content': {
                'type': 'boolean',
                'label': 'Log Content',
                'default': False,
                'description': 'If checked, logs the content passing through for debugging.'
            },
            'log_prefix': {
                'type': 'text',
                'label': 'Log Prefix',
                'default': '[PassThrough]',
                'description': 'Prefix to use when logging content.'
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
        Pass input directly to output, optionally logging the content.
        """
        incoming_input = inputs.get('input', '')
        if isinstance(incoming_input, list):
            incoming_input = "\n\n".join(str(item) for item in incoming_input)

        log_content = self.properties.get('log_content', {}).get('default', False)
        log_prefix = self.properties.get('log_prefix', {}).get('default', '[PassThrough]')

        if log_content:
            content_preview = incoming_input[:200] + '...' if len(incoming_input) > 200 else incoming_input
            print(f"{log_prefix} Content ({len(incoming_input)} chars): {content_preview}")
        else:
            print(f"[PassThroughNode] Passing through {len(incoming_input)} chars")

        return {'output': incoming_input}

    def requires_api_call(self):
        return False

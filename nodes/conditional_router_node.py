# nodes/conditional_router_node.py
"""
ConditionalRouterNode: Routes input to one of two outputs based on a search condition.
If the search string is found in the input, it goes to output1; otherwise to output2.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node


@register_node('ConditionalRouterNode')
class ConditionalRouterNode(BaseNode):
    """
    A conditional logic node that routes input to one of two outputs
    based on whether a search string is found in the input.
    """

    def define_inputs(self):
        return ['input']

    def define_outputs(self):
        return ['match', 'no_match']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'ConditionalRouterNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Routes input based on whether a search string is found.'
            },
            'search_string': {
                'type': 'text',
                'label': 'Search String',
                'default': '',
                'description': 'String to search for in the input. If found, routes to "match" output.'
            },
            'case_sensitive': {
                'type': 'boolean',
                'label': 'Case Sensitive',
                'default': False,
                'description': 'If checked, the search will be case-sensitive.'
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
        Route input to match or no_match output based on search string presence.
        """
        incoming_input = inputs.get('input', '')
        if isinstance(incoming_input, list):
            incoming_input = "\n\n".join(str(item) for item in incoming_input)

        search_string = self.properties.get('search_string', {}).get('default', '')
        case_sensitive = self.properties.get('case_sensitive', {}).get('default', False)

        if not search_string:
            print("[ConditionalRouterNode] No search string configured, routing to no_match")
            return {'match': '', 'no_match': incoming_input}

        # Perform the search
        if case_sensitive:
            found = search_string in incoming_input
        else:
            found = search_string.lower() in incoming_input.lower()

        if found:
            print(f"[ConditionalRouterNode] Search string '{search_string}' FOUND, routing to match")
            return {'match': incoming_input, 'no_match': ''}
        else:
            print(f"[ConditionalRouterNode] Search string '{search_string}' NOT found, routing to no_match")
            return {'match': '', 'no_match': incoming_input}

    def requires_api_call(self):
        return False

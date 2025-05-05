from .base_node import BaseNode
from node_registry import register_node

@register_node('AccumulatorNode')
class AccumulatorNode(BaseNode):
    def __init__(self, node_id, config):
        super().__init__(node_id=node_id, config=config)
        # Initialize state properties
        self._ensure_state_properties()

    def _ensure_state_properties(self):
        """Ensure all required state properties exist with default values"""
        state_props = {
            'initial_input': {'type': 'hidden', 'default': ''},
            'accumulated_data': {'type': 'hidden', 'default': ''},
            'iteration_count': {'type': 'hidden', 'default': 0},
            'append_accumulated_data': {'type': 'boolean', 'default': False}
        }
        for key, value in state_props.items():
            if key not in self.properties:
                self.properties[key] = value

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
                'default': 'AccumulatorNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Accumulates inputs over a specified number of iterations.'
            },
            'iterations': {
                'type': 'number',
                'label': 'Number of Iterations',
                'default': 3,
                'min': 1,
                'description': 'Specify how many times to iterate.'
            },
            'append_accumulated_data': {
                'type': 'boolean',
                'label': 'Append Accumulated Data',
                'default': False,
                'description': 'If checked, appends accumulated data to the initial input during iterations.'
            }
        })
        return props

    def process(self, inputs):
        output = {}

        # Get input text
        input_text = inputs.get('input', '').strip()
        if not input_text:
            print("[AccumulatorNode] No input received.")
            return output

        # Get current state
        initial_input = self.properties['initial_input']['default']
        accumulated_data = self.properties['accumulated_data']['default']
        iteration_count = int(self.properties['iteration_count']['default'])
        iterations = int(self.properties['iterations']['default'])
        append_accumulated_data = self.properties['append_accumulated_data']['default']

        # Check if we're already at max iterations
        if iteration_count >= iterations and initial_input:
            print("[AccumulatorNode] Already at max iterations. No further processing.")
            # Ensure end node is set
            self.properties['is_end_node'] = {'type': 'boolean', 'default': True}
            return output

        # First input handling - store it but don't count as iteration
        if not initial_input:
            self.properties['initial_input']['default'] = input_text
            output['output'] = input_text
            print(f"[AccumulatorNode] Stored initial input: '{input_text}'")
            return output

        # We have the initial input stored, now handle the response
        # Increment iteration count as we received a response
        iteration_count += 1
        self.properties['iteration_count']['default'] = iteration_count
        print(f"[AccumulatorNode] Processing iteration {iteration_count}/{iterations}")

        # Store the response in accumulated data
        if accumulated_data:
            accumulated_data += '\n\n' + input_text
        else:
            accumulated_data = input_text
        self.properties['accumulated_data']['default'] = accumulated_data

        # Check if this was the final iteration
        if iteration_count >= iterations:
            print(f"[AccumulatorNode] Final iteration {iteration_count}/{iterations}. Marking as end node.")
            self.properties['is_end_node'] = {'type': 'boolean', 'default': True}
            # On final iteration, output the accumulated data
            output['output'] = accumulated_data
            return output

        # Not the final iteration - continue with initial input
        if append_accumulated_data:
            output['output'] = initial_input + "\n\nBut completely different from the following prompts:\n" + accumulated_data
        else:
            output['output'] = initial_input

        print(f"[AccumulatorNode] Iteration {iteration_count}/{iterations} in progress, sending initial input.")
        return output

    def reset_state(self):
        """Reset all state properties to their default values"""
        self.properties['initial_input']['default'] = ''
        self.properties['accumulated_data']['default'] = ''
        self.properties['iteration_count']['default'] = 0
        self.properties['is_end_node'] = {'type': 'boolean', 'default': False}
        print("[AccumulatorNode] State has been reset.")

    def requires_api_call(self):
        return False

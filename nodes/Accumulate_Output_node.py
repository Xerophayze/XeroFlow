# nodes/Accumulate_Output_node.py
from .base_node import BaseNode
from node_registry import register_node
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

@register_node('AccumulateOutputNode')
class AccumulateOutputNode(BaseNode):
    def __init__(self, node_id, config):
        super().__init__(node_id=node_id, config=config)
        self.review_approved = False
        self._ensure_state_properties()

    def _ensure_state_properties(self):
        """Ensure all required state properties exist with default values"""
        state_props = {
            'initial_input': {'type': 'hidden', 'default': ''},
            'accumulated_data': {'type': 'hidden', 'default': ''},
            'iteration_count': {'type': 'hidden', 'default': 0},
            'append_accumulated_data': {'type': 'boolean', 'default': True}  # Changed to match the property name in state
        }
        for key, value in state_props.items():
            if key not in self.properties:
                self.properties[key] = value

    def define_inputs(self):
        return ['input']  # Single input named 'input'

    def define_outputs(self):
        return ['output', 'output2']  # Two outputs: regular output and final accumulated output

    def set_properties(self, node_data):
        """
        Ensures that self.properties is properly initialized with default values
        and linked to node_data['properties'] to maintain state across invocations.
        """
        # Initialize properties with defaults
        default_properties = self.define_properties()
        existing_properties = node_data.get('properties', {})
        
        # Debug incoming properties
        print("\n[AccumulateOutputNode] Incoming node_data properties:")
        print(existing_properties)
        
        # Merge existing properties with defaults
        for key, value in default_properties.items():
            if key not in existing_properties:
                existing_properties[key] = value
            else:
                # For boolean properties, check if the value itself is a boolean
                if value.get('type') == 'boolean' and isinstance(existing_properties[key], bool):
                    value['value'] = existing_properties[key]
                # Otherwise handle as before
                elif isinstance(existing_properties[key], dict):
                    if 'value' in existing_properties[key]:
                        value['value'] = existing_properties[key]['value']
                    if 'default' in existing_properties[key]:
                        value['default'] = existing_properties[key]['default']
                existing_properties[key] = value
                
        self.properties = existing_properties
        node_data['properties'] = self.properties
        
        # Debug final properties
        print("\n[AccumulateOutputNode] Final properties after initialization:")
        for key, value in self.properties.items():
            print(f"  {key}: {value}")

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'AccumulateOutputNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Accumulates inputs over iterations with dual outputs.'
            },
            'iterations': {
                'type': 'number',
                'label': 'Number of Iterations',
                'default': 3,
                'min': 1,
                'description': 'Specify how many times to iterate.'
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
            },
        })
        return props

    def show_review_window(self, accumulated_data):
        def on_approve():
            self.review_approved = True
            root.destroy()
            
        def on_cancel():
            self.review_approved = False
            root.destroy()

        root = tk.Tk()
        root.title("Review Accumulated Data")
        root.geometry("600x400")

        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Add label
        ttk.Label(main_frame, text="Review the accumulated data before sending to output2:").grid(row=0, column=0, columnspan=2, pady=(0, 10))

        # Add text area with scrollbar
        text_area = tk.Text(main_frame, wrap=tk.WORD, width=60, height=15)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=text_area.yview)
        text_area.configure(yscrollcommand=scrollbar.set)
        
        text_area.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))

        # Insert the accumulated data
        text_area.insert('1.0', accumulated_data)
        text_area.configure(state='disabled')  # Make it read-only

        # Add buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Approve", command=on_approve).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)

        root.mainloop()

    def process(self, inputs):
        output = {}

        # Debug the full properties structure at the start of processing
        print("\n[AccumulateOutputNode] Full properties structure:")
        for key, value in self.properties.items():
            print(f"  {key}: {value}")

        # Retrieve the iterations property
        iterations = self.properties.get('iterations', {}).get('default', 3)
        try:
            iterations = int(iterations)
        except ValueError:
            iterations = 3  # Fallback to default if conversion fails

        # Get input text
        input_text = inputs.get('input', '').strip()
        if not input_text:
            # No input to process
            print("[AccumulateOutputNode] No input received.")
            return output

        # Retrieve internal state from properties
        initial_input = self.properties['initial_input']['default']
        accumulated_data = self.properties['accumulated_data']['default']
        iteration_count = self.properties['iteration_count']['default']
        try:
            iteration_count = int(iteration_count)
        except ValueError:
            iteration_count = 0  # Reset if conversion fails

        # Increment iteration count first
        if iteration_count > 0:  # Only increment if we're past the first input
            iteration_count += 1
        self.properties['iteration_count']['default'] = iteration_count
        
        if iteration_count == 0:
            # First input - store initial input but don't accumulate it
            self.properties['initial_input']['default'] = input_text  # Store for output1
            self.properties['accumulated_data']['default'] = ""  # Start with empty accumulation
            # Only send to output for the first input
            output['output'] = input_text
            self.properties['iteration_count']['default'] = 1  # Set to 1 after processing first input
            print(f"[AccumulateOutputNode] First input: stored '{input_text}' as initial input")
        else:
            # For subsequent iterations:
            initial_input = self.properties['initial_input']['default']
            
            # Get current accumulated data
            accumulated_data = self.properties['accumulated_data']['default']
            
            # For subsequent inputs, if this is the first accumulated input, don't add the newlines
            if not accumulated_data:
                accumulated_data = input_text
            else:
                accumulated_data += '\n\n' + input_text
                
            self.properties['accumulated_data']['default'] = accumulated_data
            
            # Get the append_accumulated_data setting - access it directly
            append_accumulated = self.properties['append_accumulated_data']['default']
            
            print(f"\n[AccumulateOutputNode] Property check:")
            print(f"  Append accumulated data: {append_accumulated}")
            
            # If append_accumulated_data is enabled, append the accumulated data to the output
            if append_accumulated:
                separator = "\n\nThe new post should be a completely different subject and content from any of the following posts. do not create a duplicate post containing the same subject matter:\n\n" if accumulated_data else ""
                output_text = initial_input + separator + accumulated_data
                output['output'] = output_text
                print(f"[AccumulateOutputNode] Sending combined output with accumulated data")
            else:
                output['output'] = initial_input
                print("[AccumulateOutputNode] Sending only initial input")
            
            print(f"[AccumulateOutputNode] Iteration {iteration_count}: appended '{input_text}' to accumulation")

            # Check if we've reached the final iteration
            # We want iterations + 1 because iteration_count starts at 1 after the initial input
            if iteration_count >= iterations + 1:
                print(f"[AccumulateOutputNode] Final iteration reached. Showing review window.")
                self.properties['is_end_node']['default'] = True
                
                # Show review window with accumulated data
                final_accumulated_data = self.properties['accumulated_data']['default']
                print(f"[AccumulateOutputNode] Accumulated data before review: {final_accumulated_data}")
                
                self.show_review_window(final_accumulated_data)
                
                if self.review_approved:
                    # Only send the accumulated data to output2 after review is approved
                    output['output2'] = final_accumulated_data
                    # Clear the iteration count and accumulated data for next run
                    self.properties['iteration_count']['default'] = 0
                    self.properties['accumulated_data']['default'] = ''
                    self.properties['initial_input']['default'] = ''
                    print("[AccumulateOutputNode] Review approved. Data sent to output2.")
                    # Don't send to output1 on final iteration after review
                    output.pop('output', None)
                else:
                    print("[AccumulateOutputNode] Review cancelled. Data not sent to output2.")
            else:
                # Not the final iteration, continue the process by sending to output
                print(f"[AccumulateOutputNode] Continuing iteration, sending initial input to output")

        return output

    def reset_state(self):
        # Reset internal state in properties
        self.properties['initial_input']['default'] = ''
        self.properties['accumulated_data']['default'] = ''
        self.properties['iteration_count']['default'] = 0
        self.properties['is_end_node']['default'] = False
        print(f"[AccumulateOutputNode] State has been reset.")

    def requires_api_call(self):
        return False  # This node does not make any API calls

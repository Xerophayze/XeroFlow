# nodes/accumulate_outputv2_node.py
from .base_node import BaseNode
from node_registry import register_node
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

@register_node('AccumulateOutputV2Node')
class AccumulateOutputV2Node(BaseNode):
    def __init__(self, node_id, config):
        super().__init__(node_id=node_id, config=config)
        self._ensure_state_properties()

    def _ensure_state_properties(self):
        """Ensure all required state properties exist with default values"""
        state_props = {
            'initial_input': {'type': 'text', 'default': ''},
            'accumulated_data': {'type': 'text', 'default': ''},
            'iteration_count': {'type': 'number', 'default': 0},
            'append_accumulated_data': {'type': 'boolean', 'default': True}
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
        print("\n[AccumulateOutputV2Node] Incoming node_data properties:")
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
        print("\n[AccumulateOutputV2Node] Final properties after initialization:")
        for key, value in self.properties.items():
            print(f"  {key}: {value}")

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'AccumulateOutputV2Node'
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
                'default': True
            },
        })
        return props

    def show_iterations_dialog(self):
        """Show a dialog to get the number of iterations from the user"""
        iterations = None
        
        def on_submit():
            nonlocal iterations
            try:
                value = int(entry.get())
                if value > 0:
                    iterations = value
                    root.destroy()
                else:
                    messagebox.showerror("Error", "Please enter a positive number")
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number")
        
        root = tk.Tk()
        root.title("Set Number of Iterations")
        root.geometry("300x150")
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Add label
        ttk.Label(main_frame, text="Enter the number of iterations:").grid(row=0, column=0, columnspan=2, pady=(0, 10))
        
        # Add entry field
        entry = ttk.Entry(main_frame)
        entry.grid(row=1, column=0, columnspan=2, pady=(0, 20))
        entry.insert(0, str(self.properties['iterations']['default']))
        
        # Add submit button
        ttk.Button(main_frame, text="Submit", command=on_submit).grid(row=2, column=0, columnspan=2)
        
        # Center the window
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        root.mainloop()
        return iterations

    def process(self, inputs):
        output = {}

        # Debug the full properties structure at the start of processing
        print("\n[AccumulateOutputV2Node] Full properties structure:")
        for key, value in self.properties.items():
            print(f"  {key}: {value}")

        # Get the current iteration count
        current_iteration = self.properties.get('iteration_count', {}).get('default', 0)
        try:
            current_iteration = int(current_iteration)
        except (ValueError, TypeError):
            current_iteration = 0

        # Check if this is the first run (iteration_count is 0) and get iterations from user
        if current_iteration == 0:
            user_iterations = self.show_iterations_dialog()
            if user_iterations is not None:
                self.properties['iterations'] = {'type': 'number', 'default': user_iterations}
                print(f"[AccumulateOutputV2Node] User set iterations to: {user_iterations}")
            else:
                # If user cancelled the dialog, reset and return
                return {'output': 'Cancelled by user', 'output2': ''}

        # Retrieve the iterations property
        iterations = self.properties.get('iterations', {}).get('default', 3)
        try:
            iterations = int(iterations)
        except ValueError:
            iterations = 3  # Fallback to default if conversion fails

        print(f"[AccumulateOutputV2Node] Current iteration: {current_iteration} of {iterations}")

        # Get input text
        input_text = inputs.get('input', '').strip()
        if not input_text:
            # No input to process
            print("[AccumulateOutputV2Node] No input received.")
            return {'output': 'Error: No input received', 'output2': ''}

        # Retrieve internal state from properties
        initial_input = self.properties.get('initial_input', {}).get('default', '')
        accumulated_data = self.properties.get('accumulated_data', {}).get('default', '')
        
        # If this is the first input
        if not initial_input:
            # First input - store initial input but don't accumulate it
            self.properties['initial_input'] = {'type': 'text', 'default': input_text}  # Store for output1
            self.properties['accumulated_data'] = {'type': 'text', 'default': ""}  # Start with empty accumulation
            # Only send to output for the first input
            output['output'] = input_text
            self.properties['iteration_count'] = {'type': 'number', 'default': 1}  # Set to 1 after processing first input
            print(f"[AccumulateOutputV2Node] First input: stored '{input_text}' as initial input")
        else:
            # For subsequent iterations:
            # Increment the iteration count first
            current_iteration += 1
            self.properties['iteration_count'] = {'type': 'number', 'default': current_iteration}
            print(f"[AccumulateOutputV2Node] Processing iteration {current_iteration} of {iterations}")

            # Get current accumulated data and append new input
            if not accumulated_data:
                accumulated_data = input_text
            else:
                accumulated_data += '\n\n' + input_text
                
            self.properties['accumulated_data'] = {'type': 'text', 'default': accumulated_data}
            print(f"[AccumulateOutputV2Node] Added input to accumulated data")
            
            # Get the append_accumulated_data setting
            append_accumulated = self.properties.get('append_accumulated_data', {}).get('default', True)
            
            print(f"\n[AccumulateOutputV2Node] Property check:")
            print(f"  Append accumulated data: {append_accumulated}")
            
            # If append_accumulated_data is enabled, append the accumulated data to the output
            if append_accumulated:
                separator = "\n\nThe new post should be a completely different subject and content from any of the following posts. do not create a duplicate post containing the same subject matter:\n\n"
                output_text = initial_input + separator + accumulated_data
                output['output'] = output_text
            else:
                output['output'] = initial_input
            
            print(f"[AccumulateOutputV2Node] Iteration {current_iteration} of {iterations} completed")
            
            # Check if we've completed all iterations
            if current_iteration > iterations:
                print(f"[AccumulateOutputV2Node] All {iterations} iterations completed. Sending final output.")
                
                # Send the accumulated data to output2
                final_accumulated_data = self.properties.get('accumulated_data', {}).get('default', '')
                output['output2'] = final_accumulated_data
                print("[AccumulateOutputV2Node] Final data sent to output2.")
                
                # Don't send to output1 on final iteration
                output.pop('output', None)
                
                # Reset state for next run but keep end_node status
                self.reset_state()
                # Ensure we stay marked as an end node
                self.properties['is_end_node'] = {'type': 'boolean', 'default': True}
            else:
                print(f"[AccumulateOutputV2Node] Continuing to next iteration")

        return output

    def reset_state(self):
        # Reset internal state in properties
        self.properties['initial_input'] = {'type': 'text', 'default': ''}
        self.properties['accumulated_data'] = {'type': 'text', 'default': ''}
        self.properties['iteration_count'] = {'type': 'number', 'default': 0}
        print(f"[AccumulateOutputV2Node] State has been reset.")

    def requires_api_call(self):
        return False  # This node does not make any API calls

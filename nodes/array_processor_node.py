# nodes/array_processor_node.py
"""
ArrayProcessorNode: Processes an array input through a two-stage API processing system.
Each array element is processed through a loop of API calls until a specified condition is met.
The process involves two different prompts and a search condition.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node
from src.api.handler import process_api_request
from utils.progress_window import ProgressWindow

@register_node('ArrayProcessorNode')
class ArrayProcessorNode(BaseNode):
    def define_inputs(self):
        return ['input']  # Input will be an array from LongOutputV2Node

    def define_outputs(self):
        return ['output']  # Output will be the final combined string

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'ArrayProcessorNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes array elements through multiple API calls until condition is met.'
            },
            'validation_prompt': {
                'type': 'textarea',
                'label': 'Validation Prompt',
                'default': 'Process this content: {content}'  # First prompt for validation
            },
            'refinement_prompt': {
                'type': 'textarea',
                'label': 'Refinement Prompt',
                'default': 'Refine this result: {content}'  # Second prompt for refinement
            },
            'search_string': {
                'type': 'text',
                'label': 'Search String',
                'default': '',
                'description': 'String to search for in validation results'
            },
            'max_iterations': {
                'type': 'text',
                'label': 'Max Iterations',
                'default': '10',
                'description': 'Maximum number of iterations per array element'
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

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[ArrayProcessorNode] Available API endpoints: {api_list}")
        return api_list

    def make_api_call(self, prompt, api_details):
        """Make an API call and extract the response."""
        api_response_content = process_api_request(api_details, prompt)
        
        if 'error' in api_response_content:
            print(f"[ArrayProcessorNode] API Error: {api_response_content['error']}")
            return None

        # Extract the response based on API type
        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            return api_response_content.get('choices', [{}])[0].get('message', {}).get('content', '')
        elif api_type == "Ollama":
            message = api_response_content.get('message', {})
            return message.get('content', '') if isinstance(message, dict) else ''
        else:
            return 'Unsupported API type.'

    def process_single_element(self, element, api_details, validation_prompt_template, refinement_prompt_template, search_string, max_iterations, progress_window=None):
        """Process a single array element through the validation-refinement loop."""
        iteration_count = 0
        current_validation_input = str(element)
        accumulated_result = ""

        print(f"\n[ArrayProcessorNode] Starting to process element: {element}")
        
        while iteration_count < max_iterations:
            # Check for cancellation at the start of each iteration
            if progress_window and progress_window.is_cancelled():
                print("[ArrayProcessorNode] Processing cancelled by user during iteration")
                return "CANCELLED"
            
            # Prepare validation prompt by appending the current input to the template
            full_validation_prompt = f"{validation_prompt_template}\n\nContent to Review:\n{current_validation_input}"
            print(f"\n[ArrayProcessorNode] Iteration {iteration_count + 1}: Sending validation prompt to API:")
            print(f"[ArrayProcessorNode] Validation Prompt: {full_validation_prompt}")
            
            validation_result = self.make_api_call(full_validation_prompt, api_details)
            if validation_result is None:
                print("[ArrayProcessorNode] Error: API call failed during validation")
                return None
                
            print(f"[ArrayProcessorNode] Received validation result: {validation_result}")
            print(f"[ArrayProcessorNode] Checking for search string: '{search_string}'")

            # Check if validation result contains search string
            if search_string in validation_result:
                print(f"[ArrayProcessorNode] Search string found!")
                # If this is the first iteration, use the original element
                # Otherwise, use the current validation input (refined version)
                if iteration_count == 0:
                    print(f"[ArrayProcessorNode] Using original element as result")
                    if accumulated_result:
                        accumulated_result += "\n\n"
                    accumulated_result += str(element)
                else:
                    print(f"[ArrayProcessorNode] Using refined content as result")
                    if accumulated_result:
                        accumulated_result += "\n\n"
                    accumulated_result += current_validation_input
                
                print(f"[ArrayProcessorNode] Element successfully processed")
                print(f"[ArrayProcessorNode] Final accumulated result: {accumulated_result}")
                return accumulated_result

            print("[ArrayProcessorNode] Search string not found, proceeding to refinement")
            
            # Prepare refinement prompt by including both the content and the validation result
            full_refinement_prompt = f"{refinement_prompt_template}\n\nOriginal Content:\n{current_validation_input}\n\nReview and Suggestions:\n{validation_result}"
            print(f"[ArrayProcessorNode] Sending refinement prompt to API:")
            print(f"[ArrayProcessorNode] Refinement Prompt: {full_refinement_prompt}")
            
            refined_result = self.make_api_call(full_refinement_prompt, api_details)
            if refined_result is None:
                print("[ArrayProcessorNode] Error: API call failed during refinement")
                return None

            print(f"[ArrayProcessorNode] Received refinement result: {refined_result}")
            
            # Use refined result as input for next validation
            current_validation_input = refined_result
            iteration_count += 1

            if iteration_count >= max_iterations:
                print(f"[ArrayProcessorNode] Max iterations ({max_iterations}) reached without finding search string")
                return None

        print(f"[ArrayProcessorNode] Finished processing element. Accumulated result: {accumulated_result}")
        return accumulated_result

    def process(self, inputs):
        """Process the input array through the validation-refinement loop."""
        input_array = inputs.get('input', [])
        if not isinstance(input_array, list):
            print("[ArrayProcessorNode] Input is not an array.")
            return {"output": "Input must be an array."}

        # Get properties
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        validation_prompt = self.properties.get('validation_prompt', {}).get('default', '')
        refinement_prompt = self.properties.get('refinement_prompt', {}).get('default', '')
        search_string = self.properties.get('search_string', {}).get('default', '')
        max_iterations = int(self.properties.get('max_iterations', {}).get('default', '10'))

        # Create progress window
        progress_window = ProgressWindow("Processing Array", len(input_array))
        
        # Process each element
        results = []
        for i, element in enumerate(input_array):
            # Update progress window with current index + 1 to show actual progress
            progress_window.update_progress(i + 1, f"Processing item {i+1}/{len(input_array)}: {str(element)[:50]}...")
            
            # Check if processing was cancelled
            if progress_window.is_cancelled():
                print("[ArrayProcessorNode] Processing cancelled by user")
                return {"output": "Processing cancelled by user"}
            
            # Get API details from configuration
            api_details = self.config['interfaces'].get(api_endpoint_name)
            if not api_details:
                print(f"[ArrayProcessorNode] API interface '{api_endpoint_name}' not found in configuration.")
                progress_window.close()
                return {"output": f"API interface '{api_endpoint_name}' not found in configuration."}

            # Process the element
            result = self.process_single_element(
                element,
                api_details,
                validation_prompt,
                refinement_prompt,
                search_string,
                max_iterations,
                progress_window
            )
            
            # Check if processing was cancelled
            if result == "CANCELLED":
                print("[ArrayProcessorNode] Processing cancelled, returning partial results")
                progress_window.close()
                if results:
                    final_output = "\n\n".join(str(r) for r in results if r)
                    return {"output": f"Processing cancelled by user.\n\nPartial results:\n{final_output}"}
                return {"output": "Processing cancelled by user"}
            
            results.append(result)

        # Update final progress and close window
        progress_window.update_progress(len(input_array), "Processing complete!")
        progress_window.close()

        # Convert results to string format
        final_output = "\n\n".join(str(result) for result in results) if results else ""
        return {"output": final_output}

    def requires_api_call(self):
        return True  # API call is handled within the node

# nodes/Array_process_Test_process_node.py
"""
ArrayProcessTestProcessNode: Processes an array input through a two-stage API processing system.
Each array element is processed through a loop of API calls until a specified condition is met.
The process involves two different prompts and a search condition.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node
from utils.progress_window import ProgressWindow
from utils.refinement_review_window import RefinementReviewWindow
import threading
import time
from tkinter import messagebox

@register_node('ArrayProcessTestProcessNode')
class ArrayProcessTestProcessNode(BaseNode):
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
                'default': 'ArrayProcessTestProcessNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes array elements through multiple API calls until condition is met.'
            },
            'use_single_string': {
                'type': 'boolean',
                'label': 'Use Single String Input',
                'default': False,
                'description': 'If enabled, treats input as a single string instead of an array'
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
            'minimum_rating': {
                'type': 'text',
                'label': 'Minimum Rating',
                'default': '7.0',
                'description': 'Minimum overall rating required (e.g., 7.5)'
            },
            'max_iterations': {
                'type': 'text',
                'label': 'Max Iterations',
                'default': '10',
                'description': 'Maximum number of iterations per array element'
            },
            'skip_first_item': {
                'type': 'boolean',
                'label': 'Skip First Array Item During Processing',
                'default': False,
                'description': 'If enabled, the first array element bypasses processing but is still included in the final output'
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

    def get_property_value(self, key, default=None):
        prop = self.properties.get(key, {})
        if isinstance(prop, dict):
            return prop.get('value', prop.get('default', default))
        return prop if prop is not None else default

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[ArrayProcessTestProcessNode] Available API endpoints: {api_list}")
        return api_list

    def make_api_call(self, prompt, api_details):
        """Make an API call and return the response text."""
        try:
            max_tokens = api_details.get('max_tokens')
            # Use the API service from BaseNode
            api_response = self.send_api_request(
                content=prompt,
                api_name=api_details['endpoint_name'],
                model=self.config['interfaces'][api_details['endpoint_name']].get('selected_model'),
                max_tokens=max_tokens
            )
            
            if not api_response.success:
                print(f"[ArrayProcessTestProcessNode] API call failed: {api_response.error}")
                return None
                
            # Return the content directly
            return api_response.content
                
        except Exception as e:
            print(f"[ArrayProcessTestProcessNode] Error in make_api_call: {str(e)}")
            return None

    def extract_rating(self, validation_result):
        """Extract the overall rating from the validation result."""
        try:
            if not validation_result:
                return None
                
            # Look for OVERALL RATING pattern
            import re
            rating_pattern = r"OVERALL RATING:\s*(\d+\.?\d*)"
            match = re.search(rating_pattern, validation_result)
            
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    print("[ArrayProcessTestProcessNode] Error converting rating to float")
                    return None
                    
            # If no direct OVERALL RATING, look for Rating: pattern
            rating_pattern = r"Rating:\s*(\d+\.?\d*)"
            match = re.search(rating_pattern, validation_result)
            
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    print("[ArrayProcessTestProcessNode] Error converting rating to float")
                    return None
                    
            print("[ArrayProcessTestProcessNode] No rating found in validation result")
            return None
            
        except Exception as e:
            print(f"[ArrayProcessTestProcessNode] Error extracting rating: {str(e)}")
            return None

    def meets_rating_requirement(self, response):
        """Check if the response meets the minimum rating requirement."""
        rating = self.extract_rating(response)
        if rating is None:
            return False
            
        try:
            min_rating_prop = self.properties.get('minimum_rating', '7.0')
            if isinstance(min_rating_prop, dict):
                min_rating_value = min_rating_prop.get('value', min_rating_prop.get('default', '7.0'))
            else:
                min_rating_value = min_rating_prop
            min_rating = float(min_rating_value)
            print(f"[ArrayProcessTestProcessNode] Comparing rating {rating} against minimum {min_rating}")
            return rating >= min_rating
        except (ValueError, AttributeError) as e:
            print(f"[ArrayProcessTestProcessNode] Error comparing ratings: {e}")
            return False

    def process_single_element(self, element, api_details, validation_prompt_template, refinement_prompt_template, search_string, max_iterations, progress_window, index, min_rating):
        """Process a single array element through the validation-refinement loop."""
        try:
            iteration_count = 0
            current_content = str(element)
            original_content = current_content  # Store the original content
            last_validation_result = None
            
            # Initialize variables to track highest-rated content
            highest_rating = float('-inf')
            best_content = current_content
            best_validation_result = None
            
            print(f"\n[ArrayProcessTestProcessNode] Starting to process element: {element}")
            
            while iteration_count < max_iterations:
                # Check for cancellation at the start of each iteration
                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNode] Processing cancelled by user during iteration")
                    return "CANCELLED", "Processing cancelled by user"

                if progress_window.is_skip_requested():
                    progress_window.clear_skip()
                    print("[ArrayProcessTestProcessNode] Skip requested - using best content so far")
                    if best_validation_result:
                        return best_content, best_validation_result
                    return current_content, last_validation_result or "[INFO] Skipped by user"
                
                # Step 2: Append current item to the END of validation prompt
                full_validation_prompt = f"{validation_prompt_template}\n\n{current_content}"
                    
                print(f"\n[ArrayProcessTestProcessNode] Iteration {iteration_count + 1}: Sending validation prompt to API")
                
                # Step 3: Send to API endpoint and wait for response
                validation_result = self.make_api_call(full_validation_prompt, api_details)
                if validation_result is None:
                    print("[ArrayProcessTestProcessNode] Error: API call failed during validation")
                    if best_validation_result:
                        return best_content, best_validation_result
                    return None, None
                    
                print(f"[ArrayProcessTestProcessNode] Received validation result")
                last_validation_result = validation_result
                
                # Extract current rating
                current_rating = self.extract_rating(validation_result)
                if current_rating is not None:
                    print(f"[ArrayProcessTestProcessNode] Current rating: {current_rating}, Highest rating so far: {highest_rating}")
                    
                    # Update highest rating and best content if current rating is higher
                    if current_rating > highest_rating:
                        highest_rating = current_rating
                        best_content = current_content
                        best_validation_result = validation_result
                        print(f"[ArrayProcessTestProcessNode] New highest rating achieved: {highest_rating}")
                
                # Step 4: Test for Overall Rating and search term
                meets_rating = self.meets_rating_requirement(validation_result)
                contains_search = search_string.lower() in validation_result.lower() if search_string else True
                
                print(f"[ArrayProcessTestProcessNode] Rating check: {meets_rating}")
                print(f"[ArrayProcessTestProcessNode] Search string check: {contains_search}")
                
                # If either condition is met, return the current content and validation result
                if meets_rating or contains_search:
                    print("[ArrayProcessTestProcessNode] Validation successful - met rating or contains search term")
                    return current_content, validation_result
                
                # Step 5: If validation failed, try refinement
                print("[ArrayProcessTestProcessNode] Validation failed, attempting refinement")
                
                # Prepare refinement content using both current and best validation results
                if best_validation_result and best_validation_result != validation_result:
                    combined_validation = f"Previous Best Validation (Rating {highest_rating}):\n{best_validation_result}\n\nCurrent Validation (Rating {current_rating}):\n{validation_result}"
                    refinement_content = f"{best_content}\n\nCombined Validation Results:\n{combined_validation}"
                else:
                    refinement_content = f"{best_content}\n\nValidation Results:\n{validation_result}"
                
                # Create refinement prompt with combined content
                full_refinement_prompt = f"{refinement_prompt_template}\n\n{refinement_content}"
                
                print(f"[ArrayProcessTestProcessNode] Sending refinement prompt to API")
                
                # Check for cancellation before refinement API call
                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNode] Processing cancelled by user before refinement")
                    return "CANCELLED", "Processing cancelled by user"
                
                # Send to refinement API and explicitly wait for response
                refined_result = self.make_api_call(full_refinement_prompt, api_details)
                if refined_result is None:
                    print("[ArrayProcessTestProcessNode] Error: API call failed during refinement")
                    if best_validation_result:
                        return best_content, best_validation_result
                    return None, None

                # Check for cancellation after refinement API call
                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNode] Processing cancelled by user after refinement")
                    return "CANCELLED", "Processing cancelled by user"

                print(f"[ArrayProcessTestProcessNode] Received refinement result")

                # For the next iteration, use the refined result as the current content
                current_content = refined_result
                
                print(f"[ArrayProcessTestProcessNode] Updated current content for next validation iteration")
                iteration_count += 1
                
                # Update progress window
                rating_text = f"Current rating: {current_rating if current_rating is not None else 'N/A'} | Best: {highest_rating if highest_rating != float('-inf') else 'N/A'} | Min: {min_rating}"
                snippet = ""
                if validation_result:
                    snippet_lines = [line.strip() for line in validation_result.splitlines() if line.strip()]
                    snippet = "\n".join(snippet_lines[:4])
                detail_text = rating_text
                if snippet:
                    detail_text += f"\n\nValidation (snippet):\n{snippet}"
                progress_window.update_progress(index, f"Processing item {index+1} - Iteration {iteration_count}", detail_text)

            print(f"[ArrayProcessTestProcessNode] Max iterations ({max_iterations}) reached without successful validation")
            # If we didn't meet the conditions but have some content, return the best we found
            if best_validation_result is not None:
                print(f"[ArrayProcessTestProcessNode] Returning best content found with rating: {highest_rating}")
                return best_content, best_validation_result
            return None, None
            
        except Exception as e:
            print(f"[ArrayProcessTestProcessNode] Error in process_single_element: {str(e)}")
            if best_validation_result:
                return best_content, best_validation_result
            return None, None

    def process(self, inputs):
        """Process the input array through the validation-refinement loop."""
        input_data = inputs.get('input', [])
        use_single_string = self.get_property_value('use_single_string', False)
        skip_first_item = self.get_property_value('skip_first_item', False)
        
        # Convert input to array based on the toggle setting
        if use_single_string:
            if not isinstance(input_data, str):
                input_data = str(input_data)
            input_array = [input_data]  # Create a single-element array
            print("[ArrayProcessTestProcessNode] Using single string input mode.")
        else:
            # Original array handling
            if not isinstance(input_data, list):
                print("[ArrayProcessTestProcessNode] Input is not an array.")
                return {"output": "Input must be an array when not in single string mode."}
            input_array = input_data

        # Get properties
        api_endpoint = self.get_property_value('api_endpoint', '')
        validation_prompt = self.get_property_value('validation_prompt', '')
        refinement_prompt = self.get_property_value('refinement_prompt', '')
        search_string = self.get_property_value('search_string', '')
        max_iterations = int(self.get_property_value('max_iterations', '10'))

        # Validate API configuration
        api_config = self.config.get('interfaces', {}).get(api_endpoint)
        if not api_config:
            error_msg = f"API endpoint '{api_endpoint}' not found in configuration"
            print(f"[ArrayProcessTestProcessNode] Error: {error_msg}")
            return {"output": error_msg}

        # Format API details
        # Parse max tokens from interface configuration
        interface_max_tokens = api_config.get('max_tokens')
        try:
            max_tokens = int(interface_max_tokens) if interface_max_tokens else None
        except (TypeError, ValueError):
            max_tokens = None

        api_details = {
            'endpoint_name': api_endpoint,
            'config': api_config,
            'api_type': api_config.get('api_type', 'OpenAI'),
            'max_tokens': max_tokens
        }
        print(f"[ArrayProcessTestProcessNode] Using API endpoint: {api_endpoint}")
        print(f"[ArrayProcessTestProcessNode] API Type: {api_details['api_type']}")

        # Create progress window
        progress_window = ProgressWindow(max_value=len(input_array), title="Processing Array")
        
        # Process each element
        refinement_results = []
        validation_results = []
        
        try:
            for i, element in enumerate(input_array):
                # Update initial progress
                progress_window.clear_skip()
                progress_window.update_progress(i, f"Starting item {i+1}/{len(input_array)}")
                
                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNode] Processing cancelled by user")
                    progress_window.close()
                    return {"output": "Processing cancelled by user"}

                if skip_first_item and i == 0:
                    print("[ArrayProcessTestProcessNode] Skipping first array item per configuration")
                    refinement_results.append(str(element))
                    validation_results.append("[INFO] First item skipped per configuration")
                    continue

                # Process the element and wait for result
                refinement_result, validation_result = self.process_single_element(
                    element,
                    api_details,
                    validation_prompt,
                    refinement_prompt,
                    search_string,
                    max_iterations,
                    progress_window,
                    i,
                    float(self.get_property_value('minimum_rating', '7.0'))
                )
                
                # Check if processing was cancelled
                if refinement_result == "CANCELLED":
                    print("[ArrayProcessTestProcessNode] Processing cancelled, returning partial results")
                    progress_window.close()
                    if refinement_results:
                        # Return what we have so far
                        output_text = "\n\n".join(str(item) for item in refinement_results)
                        return {'output': f"Processing cancelled by user.\n\nPartial results:\n{output_text}"}
                    return {'output': 'Processing cancelled by user'}
                
                if refinement_result is not None and validation_result is not None:
                    refinement_results.append(refinement_result)
                    validation_results.append(validation_result)
                else:
                    print(f"[ArrayProcessTestProcessNode] Warning: Item {i+1} processing failed")
                    refinement_results.append(f"[ERROR] Processing failed for item {i+1}")
                    validation_results.append(f"[ERROR] Validation failed for item {i+1}")

            # Update final progress and close window
            progress_window.update_progress(len(input_array), "Processing complete!")
            progress_window.close()
            
            # Format final output - only include the refined content without headers or validation results
            output_text = ""
            
            if refinement_results:
                for i, item in enumerate(refinement_results):
                    if i > 0:
                        output_text += "\n\n"
                    output_text += str(item)
                    
            return {'output': output_text}
            
        except Exception as e:
            error_msg = f"Error processing array: {str(e)}"
            print(f"[ArrayProcessTestProcessNode] {error_msg}")
            progress_window.close()
            return {'output': error_msg}

    def requires_api_call(self):
        return True  # API call is handled within the node

    def get_refinement(self, refinement, validation, previous_validation=None):
        """Get refinement using both current and previous validation results"""
        # Combine validation results if we have previous validation
        combined_validation = validation
        if previous_validation:
            combined_validation = f"{previous_validation}\n\nNew Validation Results:\n{validation}"
        
        # Create refinement prompt with combined content
        full_refinement_prompt = f"{self.properties.get('refinement_prompt', {}).get('default', '')}\n\n{refinement}\n\nValidation Results:\n{combined_validation}"
        
        print(f"[ArrayProcessTestProcessNode] Sending refinement prompt to API:")
        print(f"[ArrayProcessTestProcessNode] Refinement Prompt: {full_refinement_prompt}")
        
        # Send to refinement API and explicitly wait for response
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        api_details = self.config['interfaces'].get(api_endpoint_name)
        refined_result = self.make_api_call(full_refinement_prompt, api_details)
        if refined_result is None:
            print("[ArrayProcessTestProcessNode] Error: API call failed during refinement")
            return None

        print(f"[ArrayProcessTestProcessNode] Received refinement result: {refined_result}")
        return refined_result

    def validate_refinement(self, refinement):
        # Create validation prompt with combined content
        full_validation_prompt = f"{self.properties.get('validation_prompt', {}).get('default', '')}\n\n{refinement}"
        
        print(f"[ArrayProcessTestProcessNode] Sending validation prompt to API:")
        print(f"[ArrayProcessTestProcessNode] Validation Prompt: {full_validation_prompt}")
        
        # Send to validation API and explicitly wait for response
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        api_details = self.config['interfaces'].get(api_endpoint_name)
        validation_result = self.make_api_call(full_validation_prompt, api_details)
        if validation_result is None:
            print("[ArrayProcessTestProcessNode] Error: API call failed during validation")
            return None

        print(f"[ArrayProcessTestProcessNode] Received validation result: {validation_result}")
        return validation_result

    def continue_refinement(self, current_refinement, current_validation, min_rating, callback):
        """Continue refining a specific result with a new minimum rating"""
        def process_refinement():
            try:
                current_rating = self.extract_rating(current_validation)
                iterations = 0
                best_refinement = current_refinement
                best_validation = current_validation
                best_rating = current_rating
                previous_validation = current_validation  # Store initial validation
                
                max_iter = int(self.properties.get('max_iterations', {}).get('default', '10'))
                print(f"[ArrayProcessTestProcessNode] Starting refinement loop. Current rating: {current_rating}, Target: {min_rating}")
                
                # Check if we already meet the minimum rating
                if best_rating >= min_rating:
                    print(f"[ArrayProcessTestProcessNode] Current rating {best_rating} already meets minimum {min_rating}")
                    return
                
                while iterations < max_iter:
                    print(f"[ArrayProcessTestProcessNode] Iteration {iterations + 1}/{max_iter}")
                    
                    # Get new refinement using both current and previous validation
                    new_refinement = self.get_refinement(best_refinement, best_validation, previous_validation)
                    if new_refinement is None:
                        print("[ArrayProcessTestProcessNode] Failed to get refinement, stopping")
                        break
                        
                    # Get validation for new refinement
                    new_validation = self.validate_refinement(new_refinement)
                    if new_validation is None:
                        print("[ArrayProcessTestProcessNode] Failed to get validation, stopping")
                        break
                        
                    # Extract rating from new validation
                    try:
                        new_rating = self.extract_rating(new_validation)
                        print(f"[ArrayProcessTestProcessNode] New rating: {new_rating} (current best: {best_rating}, target: {min_rating})")
                    except Exception as e:
                        print(f"[ArrayProcessTestProcessNode] Failed to extract rating: {str(e)}")
                        continue
                    
                    # Update if rating improved
                    if new_rating > best_rating:
                        print(f"[ArrayProcessTestProcessNode] Rating improved: {best_rating} -> {new_rating}")
                        best_refinement = new_refinement
                        best_validation = new_validation
                        best_rating = new_rating
                        
                        # Call the callback directly - it will handle the UI update
                        callback(best_refinement, best_validation)
                    else:
                        # If rating didn't improve, keep the validation result for next iteration
                        previous_validation = best_validation
                        if new_rating > 0:  # Only append if we got a valid rating
                            previous_validation += f"\n\nPrevious Validation Results:\n{new_validation}"
                    
                    # Check if we've met the minimum rating
                    if best_rating >= min_rating:
                        print(f"[ArrayProcessTestProcessNode] Reached target rating: {best_rating} >= {min_rating}")
                        break
                    
                    iterations += 1
                    
                print(f"[ArrayProcessTestProcessNode] Refinement complete. Final rating: {best_rating}, Target was: {min_rating}")
                
            except Exception as e:
                print(f"[ArrayProcessTestProcessNode] Error in refinement process: {str(e)}")
                messagebox.showerror("Refinement Error", str(e))
        
        # Start refinement in a separate thread
        thread = threading.Thread(target=process_refinement)
        thread.daemon = True
        thread.start()

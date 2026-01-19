# nodes/Array_process_Test_process_node_v2.py
"""
ArrayProcessTestProcessNodeV2: Processes an array input through a two-stage API processing system.
Each array element is processed through a loop of API calls until a specified condition is met.
Adds previous/next chapter context to validation/refinement prompts.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node
from utils.progress_window import ProgressWindow
from utils.refinement_review_window import RefinementReviewWindow
import threading
import time
from tkinter import messagebox


@register_node('ArrayProcessTestProcessV2Node')
class ArrayProcessTestProcessV2Node(BaseNode):
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
                'default': 'ArrayProcessTestProcessV2Node'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes array elements through multiple API calls until condition is met. Includes previous/next context.'
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
                'default': 'Process this content: {content}'
            },
            'refinement_prompt': {
                'type': 'textarea',
                'label': 'Refinement Prompt',
                'default': 'Refine this result: {content}'
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
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[ArrayProcessTestProcessNodeV2] Available API endpoints: {api_list}")
        return api_list

    def make_api_call(self, prompt, api_details):
        """Make an API call and return the response text."""
        try:
            max_tokens = api_details.get('max_tokens')
            api_response = self.send_api_request(
                content=prompt,
                api_name=api_details['endpoint_name'],
                model=self.config['interfaces'][api_details['endpoint_name']].get('selected_model'),
                max_tokens=max_tokens
            )

            if not api_response.success:
                print(f"[ArrayProcessTestProcessNodeV2] API call failed: {api_response.error}")
                return None

            return api_response.content

        except Exception as e:
            print(f"[ArrayProcessTestProcessNodeV2] Error in make_api_call: {str(e)}")
            return None

    def build_context_prompt(self, prompt_template, prev_item, current_item, next_item):
        parts = []
        if prev_item:
            parts.append(str(prev_item))
        if prompt_template:
            parts.append(str(prompt_template))
        if current_item:
            parts.append(str(current_item))
        if next_item:
            parts.append("the following chapter bellow is only for reference to keep the chapter above consistent with the rest of the story:")
            parts.append(str(next_item))
        return "\n\n".join(part for part in parts if part)

    def extract_rating(self, validation_result):
        """Extract the overall rating from the validation result."""
        try:
            if not validation_result:
                return None

            import re
            rating_pattern = r"OVERALL RATING:\s*(\d+\.?\d*)"
            match = re.search(rating_pattern, validation_result)

            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    print("[ArrayProcessTestProcessNodeV2] Error converting rating to float")
                    return None

            rating_pattern = r"Rating:\s*(\d+\.?\d*)"
            match = re.search(rating_pattern, validation_result)

            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    print("[ArrayProcessTestProcessNodeV2] Error converting rating to float")
                    return None

            print("[ArrayProcessTestProcessNodeV2] No rating found in validation result")
            return None

        except Exception as e:
            print(f"[ArrayProcessTestProcessNodeV2] Error extracting rating: {str(e)}")
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
            print(f"[ArrayProcessTestProcessNodeV2] Comparing rating {rating} against minimum {min_rating}")
            return rating >= min_rating
        except (ValueError, AttributeError) as e:
            print(f"[ArrayProcessTestProcessNodeV2] Error comparing ratings: {e}")
            return False

    def process_single_element(self, element, api_details, validation_prompt_template, refinement_prompt_template, search_string,
                               max_iterations, progress_window, index, prev_item, next_item, min_rating):
        """Process a single array element through the validation-refinement loop."""
        try:
            iteration_count = 0
            current_content = str(element)
            last_validation_result = None

            highest_rating = float('-inf')
            best_content = current_content
            best_validation_result = None

            print(f"\n[ArrayProcessTestProcessNodeV2] Starting to process element: {element}")

            while iteration_count < max_iterations:
                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNodeV2] Processing cancelled by user during iteration")
                    return "CANCELLED", "Processing cancelled by user"

                if progress_window.is_skip_requested():
                    progress_window.clear_skip()
                    print("[ArrayProcessTestProcessNodeV2] Skip requested - using best content so far")
                    if best_validation_result:
                        return best_content, best_validation_result
                    return current_content, last_validation_result or "[INFO] Skipped by user"

                full_validation_prompt = self.build_context_prompt(
                    validation_prompt_template,
                    prev_item,
                    current_content,
                    next_item
                )

                print(f"\n[ArrayProcessTestProcessNodeV2] Iteration {iteration_count + 1}: Sending validation prompt to API")

                validation_result = self.make_api_call(full_validation_prompt, api_details)
                if validation_result is None:
                    print("[ArrayProcessTestProcessNodeV2] Error: API call failed during validation")
                    if best_validation_result:
                        return best_content, best_validation_result
                    return None, None

                print(f"[ArrayProcessTestProcessNodeV2] Received validation result")
                last_validation_result = validation_result

                current_rating = self.extract_rating(validation_result)
                if current_rating is not None:
                    print(f"[ArrayProcessTestProcessNodeV2] Current rating: {current_rating}, Highest rating so far: {highest_rating}")

                    if current_rating > highest_rating:
                        highest_rating = current_rating
                        best_content = current_content
                        best_validation_result = validation_result
                        print(f"[ArrayProcessTestProcessNodeV2] New highest rating achieved: {highest_rating}")

                meets_rating = self.meets_rating_requirement(validation_result)
                contains_search = search_string.lower() in validation_result.lower() if search_string else True

                print(f"[ArrayProcessTestProcessNodeV2] Rating check: {meets_rating}")
                print(f"[ArrayProcessTestProcessNodeV2] Search string check: {contains_search}")

                if meets_rating or contains_search:
                    print("[ArrayProcessTestProcessNodeV2] Validation successful - met rating or contains search term")
                    return current_content, validation_result

                print("[ArrayProcessTestProcessNodeV2] Validation failed, attempting refinement")

                if best_validation_result and best_validation_result != validation_result:
                    combined_validation = (
                        f"Previous Best Validation (Rating {highest_rating}):\n{best_validation_result}\n\n"
                        f"Current Validation (Rating {current_rating}):\n{validation_result}"
                    )
                    refinement_content = f"{best_content}\n\nCombined Validation Results:\n{combined_validation}"
                else:
                    refinement_content = f"{best_content}\n\nValidation Results:\n{validation_result}"

                full_refinement_prompt = self.build_context_prompt(
                    refinement_prompt_template,
                    prev_item,
                    refinement_content,
                    next_item
                )

                print("[ArrayProcessTestProcessNodeV2] Sending refinement prompt to API")

                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNodeV2] Processing cancelled by user before refinement")
                    return "CANCELLED", "Processing cancelled by user"

                refined_result = self.make_api_call(full_refinement_prompt, api_details)
                if refined_result is None:
                    print("[ArrayProcessTestProcessNodeV2] Error: API call failed during refinement")
                    if best_validation_result:
                        return best_content, best_validation_result
                    return None, None

                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNodeV2] Processing cancelled by user after refinement")
                    return "CANCELLED", "Processing cancelled by user"

                print(f"[ArrayProcessTestProcessNodeV2] Received refinement result")

                current_content = refined_result

                print("[ArrayProcessTestProcessNodeV2] Updated current content for next validation iteration")
                iteration_count += 1

                rating_text = f"Current rating: {current_rating if current_rating is not None else 'N/A'} | Best: {highest_rating if highest_rating != float('-inf') else 'N/A'} | Min: {min_rating}"
                snippet = ""
                if validation_result:
                    snippet_lines = [line.strip() for line in validation_result.splitlines() if line.strip()]
                    snippet = "\n".join(snippet_lines[:4])
                detail_text = rating_text
                if snippet:
                    detail_text += f"\n\nValidation (snippet):\n{snippet}"
                progress_window.update_progress(index, f"Processing item {index+1} - Iteration {iteration_count}", detail_text)

            print(f"[ArrayProcessTestProcessNodeV2] Max iterations ({max_iterations}) reached without successful validation")
            if best_validation_result is not None:
                print(f"[ArrayProcessTestProcessNodeV2] Returning best content found with rating: {highest_rating}")
                return best_content, best_validation_result
            return None, None

        except Exception as e:
            print(f"[ArrayProcessTestProcessNodeV2] Error in process_single_element: {str(e)}")
            if best_validation_result:
                return best_content, best_validation_result
            return None, None

    def process(self, inputs):
        """Process the input array through the validation-refinement loop."""
        input_data = inputs.get('input', [])
        use_single_string = self.get_property_value('use_single_string', False)
        skip_first_item = self.get_property_value('skip_first_item', False)

        if use_single_string:
            if not isinstance(input_data, str):
                input_data = str(input_data)
            input_array = [input_data]
            print("[ArrayProcessTestProcessNodeV2] Using single string input mode.")
        else:
            if not isinstance(input_data, list):
                print("[ArrayProcessTestProcessNodeV2] Input is not an array.")
                return {"output": "Input must be an array when not in single string mode."}
            input_array = input_data

        api_endpoint = self.get_property_value('api_endpoint', '')
        validation_prompt = self.get_property_value('validation_prompt', '')
        refinement_prompt = self.get_property_value('refinement_prompt', '')
        search_string = self.get_property_value('search_string', '')
        max_iterations = int(self.get_property_value('max_iterations', '10'))

        api_config = self.config.get('interfaces', {}).get(api_endpoint)
        if not api_config:
            error_msg = f"API endpoint '{api_endpoint}' not found in configuration"
            print(f"[ArrayProcessTestProcessNodeV2] Error: {error_msg}")
            return {"output": error_msg}

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
        print(f"[ArrayProcessTestProcessNodeV2] Using API endpoint: {api_endpoint}")
        print(f"[ArrayProcessTestProcessNodeV2] API Type: {api_details['api_type']}")

        progress_window = ProgressWindow(max_value=len(input_array), title="Processing Array")

        refinement_results = []
        validation_results = []

        try:
            for i, element in enumerate(input_array):
                progress_window.clear_skip()
                progress_window.update_progress(i, f"Starting item {i+1}/{len(input_array)}")

                if progress_window.is_cancelled():
                    print("[ArrayProcessTestProcessNodeV2] Processing cancelled by user")
                    progress_window.close()
                    return {"output": "Processing cancelled by user"}

                if skip_first_item and i == 0:
                    print("[ArrayProcessTestProcessNodeV2] Skipping first array item per configuration")
                    refinement_results.append(str(element))
                    validation_results.append("[INFO] First item skipped per configuration")
                    detail_text = (
                        f"Item {i + 1} (skipped)\n\n"
                        f"Input:\n{element}\n\n"
                        "Result:\n[INFO] First item skipped per configuration"
                    )
                    progress_window.update_item_entry(
                        i,
                        label=f"Item {i + 1}: {str(element)[:60]}",
                        detail_text=detail_text,
                        set_current=True
                    )
                    continue

                prev_item = input_array[i - 1] if i > 0 else None
                next_item = input_array[i + 1] if i < len(input_array) - 1 else None

                refinement_result, validation_result = self.process_single_element(
                    element,
                    api_details,
                    validation_prompt,
                    refinement_prompt,
                    search_string,
                    max_iterations,
                    progress_window,
                    i,
                    prev_item,
                    next_item,
                    float(self.get_property_value('minimum_rating', '7.0'))
                )

                if refinement_result == "CANCELLED":
                    print("[ArrayProcessTestProcessNodeV2] Processing cancelled, returning partial results")
                    progress_window.close()
                    if refinement_results:
                        output_text = "\n\n".join(str(item) for item in refinement_results)
                        return {'output': f"Processing cancelled by user.\n\nPartial results:\n{output_text}"}
                    return {'output': 'Processing cancelled by user'}

                if refinement_result is not None and validation_result is not None:
                    refinement_results.append(refinement_result)
                    validation_results.append(validation_result)
                    detail_text = (
                        f"Item {i + 1}\n\n"
                        f"Input:\n{element}\n\n"
                        f"Result:\n{refinement_result}\n\n"
                        f"Validation:\n{validation_result}"
                    )
                else:
                    print(f"[ArrayProcessTestProcessNodeV2] Warning: Item {i+1} processing failed")
                    refinement_results.append(f"[ERROR] Processing failed for item {i+1}")
                    validation_results.append(f"[ERROR] Validation failed for item {i+1}")
                    detail_text = (
                        f"Item {i + 1} (failed)\n\n"
                        f"Input:\n{element}\n\n"
                        f"Result:\n[ERROR] Processing failed for item {i + 1}"
                    )

                progress_window.update_item_entry(
                    i,
                    label=f"Item {i + 1}: {str(element)[:60]}",
                    detail_text=detail_text,
                    set_current=True
                )

            progress_window.update_progress(len(input_array), "Processing complete!")
            progress_window.close()

            output_text = ""
            if refinement_results:
                for i, item in enumerate(refinement_results):
                    if i > 0:
                        output_text += "\n\n"
                    output_text += str(item)

            return {'output': output_text}

        except Exception as e:
            error_msg = f"Error processing array: {str(e)}"
            print(f"[ArrayProcessTestProcessNodeV2] {error_msg}")
            progress_window.close()
            return {'output': error_msg}

    def requires_api_call(self):
        return True

    def get_refinement(self, refinement, validation, previous_validation=None):
        combined_validation = validation
        if previous_validation:
            combined_validation = f"{previous_validation}\n\nNew Validation Results:\n{validation}"

        full_refinement_prompt = f"{self.properties.get('refinement_prompt', {}).get('default', '')}\n\n{refinement}\n\nValidation Results:\n{combined_validation}"

        print("[ArrayProcessTestProcessNodeV2] Sending refinement prompt to API:")
        print(f"[ArrayProcessTestProcessNodeV2] Refinement Prompt: {full_refinement_prompt}")

        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        api_details = self.config['interfaces'].get(api_endpoint_name)
        refined_result = self.make_api_call(full_refinement_prompt, api_details)
        if refined_result is None:
            print("[ArrayProcessTestProcessNodeV2] Error: API call failed during refinement")
            return None

        print(f"[ArrayProcessTestProcessNodeV2] Received refinement result: {refined_result}")
        return refined_result

    def validate_refinement(self, refinement):
        full_validation_prompt = f"{self.properties.get('validation_prompt', {}).get('default', '')}\n\n{refinement}"

        print("[ArrayProcessTestProcessNodeV2] Sending validation prompt to API:")
        print(f"[ArrayProcessTestProcessNodeV2] Validation Prompt: {full_validation_prompt}")

        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        api_details = self.config['interfaces'].get(api_endpoint_name)
        validation_result = self.make_api_call(full_validation_prompt, api_details)
        if validation_result is None:
            print("[ArrayProcessTestProcessNodeV2] Error: API call failed during validation")
            return None

        print(f"[ArrayProcessTestProcessNodeV2] Received validation result: {validation_result}")
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
                previous_validation = current_validation

                max_iter = int(self.properties.get('max_iterations', {}).get('default', '10'))
                print(f"[ArrayProcessTestProcessNodeV2] Starting refinement loop. Current rating: {current_rating}, Target: {min_rating}")

                if best_rating >= min_rating:
                    print(f"[ArrayProcessTestProcessNodeV2] Current rating {best_rating} already meets minimum {min_rating}")
                    return

                while iterations < max_iter:
                    print(f"[ArrayProcessTestProcessNodeV2] Iteration {iterations + 1}/{max_iter}")

                    new_refinement = self.get_refinement(best_refinement, best_validation, previous_validation)
                    if new_refinement is None:
                        print("[ArrayProcessTestProcessNodeV2] Failed to get refinement, stopping")
                        break

                    new_validation = self.validate_refinement(new_refinement)
                    if new_validation is None:
                        print("[ArrayProcessTestProcessNodeV2] Failed to get validation, stopping")
                        break

                    try:
                        new_rating = self.extract_rating(new_validation)
                        print(f"[ArrayProcessTestProcessNodeV2] New rating: {new_rating} (current best: {best_rating}, target: {min_rating})")
                    except Exception as e:
                        print(f"[ArrayProcessTestProcessNodeV2] Failed to extract rating: {str(e)}")
                        continue

                    if new_rating > best_rating:
                        print(f"[ArrayProcessTestProcessNodeV2] Rating improved: {best_rating} -> {new_rating}")
                        best_refinement = new_refinement
                        best_validation = new_validation
                        best_rating = new_rating
                        callback(best_refinement, best_validation)
                    else:
                        previous_validation = best_validation
                        if new_rating > 0:
                            previous_validation += f"\n\nPrevious Validation Results:\n{new_validation}"

                    if best_rating >= min_rating:
                        print(f"[ArrayProcessTestProcessNodeV2] Reached target rating: {best_rating} >= {min_rating}")
                        break

                    iterations += 1

                print(f"[ArrayProcessTestProcessNodeV2] Refinement complete. Final rating: {best_rating}, Target was: {min_rating}")

            except Exception as e:
                print(f"[ArrayProcessTestProcessNodeV2] Error in refinement process: {str(e)}")
                messagebox.showerror("Refinement Error", str(e))

        thread = threading.Thread(target=process_refinement)
        thread.daemon = True
        thread.start()

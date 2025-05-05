# nodes/long_outputV2_node.py
"""
LongOutputNode: Processes an initial input by sending each item to the API endpoint.
The initial input is expected to be split by paragraph (empty lines between blocks of text).
It iteratively processes each item from this list, sending each to the API,
and accumulates the responses either as a combined string or as an array of responses.
"""
from .base_node import BaseNode
from node_registry import register_node  # Import the decorator
from api_handler import process_api_request  # Correct import
from utils.progress_window import ProgressWindow
from utils.array_review_window import ArrayReviewWindow

@register_node('LongOutputV2Node')
class LongOutputV2Node(BaseNode):

    def define_inputs(self):
        return ['input']  # Input from the previous node

    def define_outputs(self):
        return ['prompt']  # Output the final combined response or array

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'LongOutputV2Node'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes a list of items through the API, combining responses.'
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'Prompt',
                'default': ''  # User-defined prompt
            },
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            },
            'use_array': {
                'type': 'boolean',
                'label': 'Use Array',
                'default': False,
                'description': 'Store results in an array instead of combining into a single string'
            },
            'review_array': {
                'type': 'boolean',
                'label': 'Review Array',
                'default': True,
                'description': 'Show review window for array items before output'
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
        print(f"[LongOutputNodeV2] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def process(self, inputs):
        print("[LongOutputNodeV2] Starting process method.")

        # Get properties
        prompt_property = self.properties.get('Prompt', {}).get('default', '')
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('default', '')
        use_array = self.properties.get('use_array', {}).get('default', False)
        review_array = self.properties.get('review_array', {}).get('default', True)

        if not api_endpoint_name:
            print("[LongOutputNodeV2] API endpoint not specified.")
            return {"output": "API endpoint not specified."}

        # Get input
        previous_input = inputs.get('input', '').strip()

        if not previous_input:
            print("[LongOutputNodeV2] No input provided.")
            return {"output": "No input provided."}

        # Split the input into items (paragraphs separated by double newlines)
        items = [item.strip() for item in previous_input.split('\n\n') if item.strip()]
        if not items:
            print("[LongOutputNodeV2] No valid items found in input.")
            return {"output": "No valid items found in input."}

        # Create progress window
        progress_window = ProgressWindow("Processing Text", len(items))

        # Retrieve API details from configuration
        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            print(f"[LongOutputNodeV2] API interface '{api_endpoint_name}' not found in configuration.")
            progress_window.close()
            return {"output": f"API interface '{api_endpoint_name}' not found in configuration."}

        api_type = api_details.get('api_type')
        if not api_type:
            print(f"[LongOutputNodeV2] API type not specified for endpoint '{api_endpoint_name}'.")
            progress_window.close()
            return {"output": f"API type not specified for endpoint '{api_endpoint_name}'."}

        # Initialize responses based on output type
        responses = [] if use_array else ''

        # Process each item
        for i, item in enumerate(items):
            # Update progress window with current index + 1 to show actual progress
            progress_window.update_progress(i + 1, f"Processing item {i+1}/{len(items)}: {item[:50]}...")
            
            # Check if processing was cancelled
            if progress_window.is_cancelled():
                print("[LongOutputNodeV2] Processing cancelled by user")
                return {"output": "Processing cancelled by user"}
            
            # Format the prompt with the current item
            if i == 0:
                # First item, use the base prompt
                prompt = f"{previous_input}\n\n the following should just be the title from the outline above, please just repeat the title and nothing else:\n{item}"
                prompt_type = "first"
            elif i == len(items) - 1:
                # Last item, perform a final API call
                prompt = f"{previous_input}\n\n The section above is the last section of content written. Using it as context, continue writing the final section of content using the outline provided below. As you write, ensure the ideas are clearly understood by rephrasing complex concepts into simpler terms without altering their meaning. Vary sentence lengths and structures to create a dynamic rhythm—combine short, impactful sentences with longer, more intricate ones. Experiment with diverse grammatical constructions and replace predictable word choices with more unexpected yet contextually appropriate alternatives. Avoid repetitive phrasing by using synonyms, rearranging sentences for better flow, and paraphrasing ideas to keep the writing engaging and original. Introduce bursts of focus by repeating key terms briefly where emphasis is needed, then reduce their frequency as the text progresses. Ensure logical flow with smooth transitions, adding occasional subtle shifts in tone or perspective to maintain reader interest. Use a natural storytelling format, clearly separating dialogue, descriptions, and internal thoughts into distinct paragraphs. Begin a new paragraph for each new speaker in dialogue, keeping dialogue distinct from narrative descriptions or reflections. Follow the same chapter or section heading if one exists, ensuring clarity, engagement, and adherence to the storytelling outline.\n{item}"
                prompt_type = "last"
            else:
                # Get the next item safely
                next_item = items[i + 1] if i + 1 < len(items) else None
                # Intermediate items
                prompt = f"""The outline is as follows:
{previous_input}

The previous section or chapter written for context is as follows:
{responses}

The next section in the outline for context is as follows:
{next_item}

As a professional writer, please craft detailed content for the chapter/section shown below. Focus on delivering rich, creative, and meaningful text, ensuring depth and engagement. Fully understand the subject matter, then restate ideas in your own words, preserving meaning while simplifying complex concepts for clarity. Consciously vary sentence lengths and structures to create a dynamic rhythm—alternate between short, impactful sentences and longer, complex ones. Use diverse grammatical constructions to avoid monotonous patterns, incorporating unique word choices and phrasing to enhance unpredictability. Weave in key terms or themes naturally, integrating them seamlessly into the narrative while avoiding repetitive language. Write in a natural storytelling format by separating dialogue, descriptions, and internal thoughts into distinct paragraphs, starting a new paragraph for each speaker in dialogue, and keeping dialogue separate from narrative descriptions. Rearrange ideas where necessary to ensure logical flow, using smooth transitions and subtle shifts or surprises to sustain reader interest. Align the tone and style with traditional storytelling while balancing clarity, nuance, and originality, and always retain the chapter or section heading as listed below. The content to write about is as follows:
{item}"""
                prompt_type = "intermediate"

            print(f"[LongOutputNodeV2] Processing with {prompt_type} prompt")
            print(f"[LongOutputNodeV2] Prompt: {prompt}")

            # Make the API call using process_api_request
            api_response_content = process_api_request(api_details, prompt)

            if 'error' in api_response_content:
                print(f"[LongOutputNodeV2] API Error: {api_response_content['error']}")
                progress_window.close()
                return {"output": f"API Error: {api_response_content['error']}"}

            # Extract the actual response based on API type
            if api_type == "OpenAI":
                api_response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', '')
            elif api_type == "Ollama":
                message = api_response_content.get('message', {})
                api_response = message.get('content', '') if isinstance(message, dict) else ''
            else:
                api_response = 'Unsupported API type.'

            print(f"[LongOutputNodeV2] API Response for item {i+1}: {api_response}")

            # Store the response based on the output type
            if use_array:
                responses.append(api_response)
            else:
                if responses:
                    responses += '\n\n'
                responses += api_response

        # Update final progress and close window
        progress_window.update_progress(len(items), "Processing complete!")
        progress_window.close()

        # If using array output and review is enabled, show review window
        if use_array and review_array and responses:
            review_window = ArrayReviewWindow(responses)
            reviewed_responses = review_window.show()
            
            # If user cancelled, return empty result
            if reviewed_responses is None:
                return {'prompt': []}
            
            responses = reviewed_responses
        
        # Return the final output based on the chosen format
        final_output = responses if use_array else responses.strip()
        print(f"[LongOutputNodeV2] Final output type: {'array' if use_array else 'string'}")
        if use_array:
            print(f"[LongOutputNodeV2] Final array length: {len(responses)}")
            print(f"[LongOutputNodeV2] Final array contents: {responses}")
        else:
            print(f"[LongOutputNodeV2] Final string length: {len(responses)}")
        return {'prompt': final_output}

    def requires_api_call(self):
        return True  # API call is handled within the node

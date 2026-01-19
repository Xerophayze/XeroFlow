# nodes/long_outputV3_node.py
"""
LongOutputNode: Processes an initial input by sending each item to the API endpoint.
The initial input is expected to be split by paragraph (empty lines between blocks of text).
It iteratively processes each item from this list, sending each to the API,
and accumulates the responses either as a combined string or as an array of responses.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node  # Import the decorator
from src.api.handler import process_api_request  # Correct import
from utils.progress_window import ProgressWindow
from utils.array_review_window import ArrayReviewWindow
import time

@register_node('LongOutputV3Node')
class LongOutputV3Node(BaseNode):

    def __init__(self, node_id=None, config=None):
        """Initialize the node with configuration"""
        # Call parent's init first to set up properties
        super().__init__(node_id=node_id, config=config)
        
        # Update rate limits based on actual API limits
        self.rpm_limit = 100  # Increased from 8
        self.rph_limit = 5000  # Increased from 200
        self.tpm_limit = 1000000  # Increased from 300,000
        
        # Tracking variables
        self.request_times = []
        self.hourly_requests = []
        self.token_counts = []
        
        # Timing configuration
        self.default_timeout = 30  # Reduced from 120s since we're hitting API more frequently
        self.default_cooldown = 60  # Reduced from 120s
        self.min_request_delay = 1  # Reduced from 5s to 1s

        # Initialize properties with defaults
        self.properties = {
            **self.get_default_properties(),  # Get base properties
            **self.define_properties()  # Get our custom properties
        }
        
    def define_inputs(self):
        return ['input']  # Input from the previous node

    def define_outputs(self):
        return ['prompt']  # Output the final combined response or array

    def define_properties(self):
        """Define the properties for this node"""
        return {
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            },
            'use_array': {
                'type': 'boolean',
                'default': True,
                'description': 'Output as array instead of string'
            },
            'review_array': {
                'type': 'boolean',
                'default': True,
                'description': 'Show review window for array output'
            },
            'chunk_size': {
                'type': 'integer',
                'default': 10,
                'description': 'Number of items to process in each chunk'
            },
            'Instructions for how to processthe first element in the array:': {
                'type': 'text',
                'default': 'please just repeat the title content bellow exactly and nothing else:\n\n',
                'description': 'Prompt template for the first item'
            },
            'Instructions for how to process the Original user request and original content:': {
                'type': 'text',
                'default': 'The outline and user request is as follows and only for reference, do not use the same formatting as the outline:\n',
                'description': 'Template for the context section'
            },
            'Main instructions for array element to focus on:': {
                'type': 'text',
                'default': """As a professional writter, please write the detailed content for the section shown below. do not include any of your own commentary, just write the content based on the section listed below. Be detailed, creative, giving depth and meaning and remember To incorporate burstiness into your writing, consciously vary sentence lengths and structures as you generate text - mix short, impactful sentences with longer, more complex ones to create a dynamic rhythm; use different grammatical constructions, monitor your output for monotonous patterns in real time, and adjust accordingly to enhance engagement and mirror natural speech patterns. Write in a natural storytelling format by separating dialogue, descriptions, and internal thoughts into distinct paragraphs. Begin a new paragraph for each new speaker in dialogue, and keep spoken dialogue separate from narrative descriptions or internal reflections. This structure ensures clarity, readability, and a traditional storytelling flow.""",
                'description': 'Main instruction template for content generation'
            },
            'Instructions for how the AI should use the next array element for context:': {
                'type': 'text',
                'default': '\nthe next section to write about is as follows:\n',
                'description': 'Template for introducing the current section'
            },
            'Instructions for custom formatting:': {
                'type': 'text',
                'default': """if the section above starts with "Chapter #" then include that chapter number as a heading when writing the content.
if the section above starts with "(Continued)" then only include "(Continued) - " at the beginning of your output like this:  (Continued) - content......""",
                'description': 'Template for formatting instructions'
            }
        }

    def get_property(self, name, default=None):
        """Helper to safely get property values"""
        if not hasattr(self, 'properties'):
            self.properties = {
                **self.get_default_properties(),
                **self.define_properties()
            }
        
        if name in self.properties:
            return self.properties[name].get('default', default)
        return default

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[LongOutputNodeV3] Available API endpoints: {api_list}")  # Debug statement
        return api_list

    def check_rate_limits(self, prompt_tokens=0):
        """Check and wait for rate limits if necessary"""
        current_time = time.time()
        minute_ago = current_time - 60
        hour_ago = current_time - 3600
        
        # Clean up old entries
        self.request_times = [t for t in self.request_times if t > minute_ago]
        self.token_counts = self.token_counts[-len(self.request_times):]
        self.hourly_requests = [t for t in self.hourly_requests if t > hour_ago]
        
        # Only wait if we're very close to limits
        if len(self.hourly_requests) >= self.rph_limit * 0.95:  # 95% of limit
            wait_time = self.hourly_requests[0] - hour_ago
            if wait_time > 0:
                print(f"[LongOutputNodeV3] Close to hourly limit ({len(self.hourly_requests)}/{self.rph_limit}). Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
        
        if len(self.request_times) >= self.rpm_limit * 0.95:  # 95% of limit
            wait_time = self.request_times[0] - minute_ago
            if wait_time > 0:
                print(f"[LongOutputNodeV3] Close to minute limit ({len(self.request_times)}/{self.rpm_limit}). Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
        
        # Check TPM (tokens per minute) - only wait if very close to limit
        current_tpm = sum(self.token_counts)
        if current_tpm + prompt_tokens > self.tpm_limit * 0.95:  # 95% of limit
            wait_time = 60 * ((current_tpm + prompt_tokens - self.tpm_limit) / self.tpm_limit)
            print(f"[LongOutputNodeV3] Close to token limit ({current_tpm}/{self.tpm_limit}). Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        # Update tracking
        current_time = time.time()
        self.request_times.append(current_time)
        self.hourly_requests.append(current_time)
        self.token_counts.append(prompt_tokens)

    def adjust_rate_limits_from_response(self, response):
        """Adjust rate limits based on API response headers"""
        if 'rate_limits' in response:
            limits = response['rate_limits']
            
            # Log current limits
            print("\n[LongOutputNodeV3] Current API Rate Limits:")
            for key, value in limits.items():
                if value is not None:
                    print(f"[LongOutputNodeV3] {key}: {value}")
            
            # Update our limits if we get new information
            remaining_requests = limits.get('x-ratelimit-remaining-requests')
            reset_requests = limits.get('x-ratelimit-reset-requests')
            remaining_tokens = limits.get('x-ratelimit-remaining-tokens')
            reset_tokens = limits.get('x-ratelimit-reset-tokens')
            
            if remaining_requests is not None and remaining_requests.isdigit():
                remaining = int(remaining_requests)
                if remaining < 10:  # If we're running low on requests
                    print(f"[LongOutputNodeV3] Warning: Only {remaining} requests remaining!")
                    if reset_requests and reset_requests.isdigit():
                        wait_time = int(reset_requests)
                        print(f"[LongOutputNodeV3] Rate limit will reset in {wait_time} seconds")
                        return wait_time
            
            if remaining_tokens is not None and remaining_tokens.isdigit():
                remaining = int(remaining_tokens)
                if remaining < 1000:  # If we're running low on tokens
                    print(f"[LongOutputNodeV3] Warning: Only {remaining} tokens remaining!")
                    if reset_tokens and reset_tokens.isdigit():
                        wait_time = int(reset_tokens)
                        print(f"[LongOutputNodeV3] Token limit will reset in {wait_time} seconds")
                        return wait_time
        
        return 0

    def estimate_tokens(self, text):
        """Rough estimate of tokens in text"""
        return len(text.split()) * 1.3  # Rough estimate: 1.3 tokens per word

    def process_with_retry(self, api_details, prompt, max_retries=3, timeout=None, cooldown=None, request_delay=None):
        """Process API request with retry logic and rate limit handling"""
        import time
        for attempt in range(max_retries):
            try:
                # Make the API call
                response = self._make_api_call(api_details, prompt)
                return response
            except Exception as e:
                print(f"[LongOutputNodeV3] Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    # Wait based on the attempt number
                    wait_time = [30, 60, 120][attempt]
                    print(f"[LongOutputNodeV3] Waiting for {wait_time} seconds before retrying...")
                    time.sleep(wait_time)
                else:
                    raise e

    def _make_api_call(self, api_details, prompt):
        """Internal method to make the actual API call"""
        try:
            # Check rate limits before making request
            estimated_tokens = self.estimate_tokens(prompt)
            self.check_rate_limits(estimated_tokens)
            
            print("[LongOutputNodeV3] Making API call...")
            response = process_api_request(api_details, prompt)
            print("[LongOutputNodeV3] API call completed")
            
            return response
            
        except Exception as e:
            print(f"[LongOutputNodeV3] Exception in api_call: {str(e)}")
            return {'error': str(e)}

    def process(self, inputs):
        print("[LongOutputNodeV3] Starting process method.")
        
        # Get input text and configuration from properties
        input_text = inputs.get('input', '')
        if not input_text:
            return {'prompt': '' if not self.get_property('use_array', False) else []}
        
        # Get configuration from properties with defaults
        use_array = self.get_property('use_array', False)
        chunk_size = int(self.get_property('chunk_size', 10))
        review_array = self.get_property('review_array', True)
        api_endpoint = self.get_property('api_endpoint', 'OpenAI GPT gpt-4o-mini')
        
        # Get prompt templates from properties
        first_prompt_template = self.get_property('Instructions for how to processthe first element in the array:', '')
        context_template = self.get_property('Instructions for how to process the Original user request and original content:', '')
        instruction_template = self.get_property('Main instructions for array element to focus on:', '')
        section_template = self.get_property('Instructions for how the AI should use the next array element for context:', '')
        formatting_template = self.get_property('Instructions for custom formatting:', '')
        
        temp_file = None
        
        try:
            # If we're processing a large amount of text, use temporary file storage
            if use_array:
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8')
                print(f"[LongOutputNodeV3] Using temporary storage: {temp_file.name}")
                responses = []  # Just keep track of count for progress
            else:
                responses = ""
            
            # Split input into items (paragraphs)
            items = input_text.split('\n\n') if isinstance(input_text, str) else input_text
            if not items:
                return {'prompt': [] if use_array else ''}
            
            # Get API configuration
            api_details = self.config['interfaces'].get(api_endpoint)
            if not api_details:
                error_msg = f"API interface '{api_endpoint}' not found in configuration"
                print(f"[LongOutputNodeV3] Error: {error_msg}")
                return {'prompt': error_msg}
            
            # Create progress window
            progress_window = ProgressWindow(len(items))
            
            previous_response = ""
            # Process items in chunks
            for chunk_start in range(0, len(items), chunk_size):
                chunk = items[chunk_start:chunk_start + chunk_size]
                
                # Process each item in the chunk
                for i, item in enumerate(chunk, chunk_start):
                    # Show progress with current item number and first line of content
                    first_line = str(item).split('\n')[0] if item else ''
                    progress_text = f"Processing item {i+1}/{len(items)}: {first_line}"
                    progress_window.update_progress(i, progress_text)
                    
                    # Skip empty items
                    if not item or not str(item).strip():
                        continue
                    
                    # Format the prompt with the current item
                    if i == 0:
                        prompt = first_prompt_template + str(item)
                        prompt_type = "first"
                    elif i == len(items) - 1:
                        # Build context section
                        context = context_template
                        context += str(input_text) + "\n\n"
                        
                        # Static instruction section
                        instructions = instruction_template
                        
                        # Section with current item
                        section = section_template + str(item) + "\n\n"
                        
                        # Formatting instructions
                        formatting = formatting_template
                        
                        # Combine all parts
                        prompt = context + previous_response + instructions + section + formatting
                        prompt_type = "last"
                    else:
                        # Build context section
                        context = context_template
                        context += str(input_text) + "\n\n"
                        
                        # Static instruction section
                        instructions = instruction_template
                        
                        # Section with current item
                        section = section_template + str(item) + "\n\n"
                        
                        # Formatting instructions
                        formatting = formatting_template
                        
                        # Combine all parts
                        prompt = context + previous_response + instructions + section + formatting
                        prompt_type = "middle"
                    
                    # Make the API call with retry logic
                    api_response = self.process_with_retry(api_details, prompt, max_retries=3, timeout=30, cooldown=60, request_delay=1)
                    if 'error' in api_response:
                        error_msg = api_response['error']
                        print(f"[LongOutputNodeV3] API Error: {error_msg}")
                        if use_array:
                            return {'prompt': [f'[ERROR]: {error_msg}']}
                        return {'prompt': f'[ERROR]: {error_msg}'}
                    
                    # Extract the response based on API type
                    api_type = api_details.get('api_type', 'OpenAI')
                    if api_type == "OpenAI":
                        response_text = api_response.get('choices', [{}])[0].get('message', {}).get('content', '')
                    elif api_type == "Ollama":
                        message = api_response.get('message', {})
                        response_text = message.get('content', '') if isinstance(message, dict) else ''
                    else:
                        response_text = 'Unsupported API type.'
                    
                    print(f"[LongOutputNodeV3] API Response for item {i+1}: {response_text[:100]}...")
                    
                    # Store the response
                    if use_array:
                        # Write to temp file immediately
                        temp_file.write(response_text + '\n---CHAPTER_BREAK---\n')
                        temp_file.flush()
                        responses.append(None)  # Just for progress tracking
                    else:
                        if responses:
                            responses += '\n\n'
                        responses += response_text
                    
                    # Update previous response
                    previous_response = response_text
                    
                    # Free memory explicitly
                    del response_text
                    del api_response
                
                # Yield control briefly
                from time import sleep
                try:
                    sleep(0.1)
                except Exception as e:
                    print(f"[LongOutputNodeV3] Warning: Could not yield control: {str(e)}")
            
            # Update final progress and close window
            progress_window.update_progress(len(items), "Processing complete!")
            progress_window.close()
            
            # If using array output and review is enabled, show review window
            if use_array and review_array:
                # Read chapters from temp file
                temp_file.seek(0)
                chapters = temp_file.read().split('---CHAPTER_BREAK---')
                chapters = [ch.strip() for ch in chapters if ch.strip()]
                
                review_window = ArrayReviewWindow(chapters)
                reviewed_responses = review_window.show()
                
                # If user cancelled in review window
                if reviewed_responses is None:
                    print("[LongOutputNodeV3] User cancelled during review")
                    return {'prompt': ['[CANCELLED]']}
                
                return {'prompt': reviewed_responses}
            
            # Return the final output
            if use_array:
                # Read chapters from temp file
                temp_file.seek(0)
                chapters = temp_file.read().split('---CHAPTER_BREAK---')
                return {'prompt': [ch.strip() for ch in chapters if ch.strip()]}
            else:
                return {'prompt': responses.strip()}
                
        except Exception as e:
            print(f"[LongOutputNodeV3] Error in process: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'prompt': f'[ERROR]: {str(e)}'}
            
        finally:
            # Clean up temporary file
            if temp_file:
                try:
                    import os
                    temp_file.close()
                    os.unlink(temp_file.name)
                    print("[LongOutputNodeV3] Cleaned up temporary storage")
                except Exception as e:
                    print(f"[LongOutputNodeV3] Warning: Could not clean up temp file: {str(e)}")

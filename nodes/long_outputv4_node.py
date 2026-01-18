# nodes/long_outputv4_node.py
"""
LongOutputV4Node: Enhanced version of LongOutputV3Node with additional features:
- Automatic processing of input array from previous node
- Rate limiting and retry logic for API calls
- Progress tracking during processing
- Final array review window after processing completes
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node
from utils.progress_window import ProgressWindow
from utils.array_review_window import ArrayReviewWindow
import tkinter as tk
from tkinter import ttk
import requests
from bs4 import BeautifulSoup
import time
from src.api.handler import process_api_request
import sys
import os

# Import the SearchScrapeSummarizeNode for web search functionality
from .SearchScrapeSummarize import SearchScrapeSummarizeNode

class ContentReviewWindow:
    def __init__(self, api_details=None, searxng_api_url=None, num_search_results=5, num_results_to_skip=0, enable_url_selection=False, parent=None):
        self.api_details = api_details
        self.searxng_api_url = searxng_api_url or 'http://localhost:8888/search'
        self.num_search_results = num_search_results
        self.num_results_to_skip = num_results_to_skip
        self.enable_url_selection = enable_url_selection
        self.result = None
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("Initial Content Review")
        
        # Configure window for resizing
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        
        # Set initial size and center the window - increased minimum size
        window_width = 1200
        window_height = 800
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.window.minsize(1000, 700)  # Set minimum size
        
        # Create main frame
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure main frame for resizing
        main_frame.columnconfigure(0, weight=1)  # Left panel
        main_frame.columnconfigure(1, weight=3)  # Right panel (larger)
        main_frame.rowconfigure(0, weight=1)
        
        # Left panel for array elements list
        left_frame = ttk.LabelFrame(main_frame, text="Array Elements", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # Configure left frame for resizing
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        
        # Listbox with scrollbar
        self.listbox = tk.Listbox(left_frame, font=("TkDefaultFont", 10), width=30)  # Set minimum width
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.listbox.configure(yscrollcommand=scrollbar.set)
        
        self.listbox.bind('<<ListboxSelect>>', self.on_select)
        
        # Right panel for content and controls
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure right frame for resizing
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=0)  # Label
        right_frame.rowconfigure(1, weight=3)  # Content text (larger)
        right_frame.rowconfigure(2, weight=0)  # Label
        right_frame.rowconfigure(3, weight=1)  # Input text
        right_frame.rowconfigure(4, weight=0)  # Status label
        right_frame.rowconfigure(5, weight=0)  # Button frame
        
        # Content display
        content_label = ttk.Label(right_frame, text="Content:", font=("TkDefaultFont", 11, "bold"))
        content_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        # Content text with scrollbar
        content_frame = ttk.Frame(right_frame)
        content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        self.content_text = tk.Text(content_frame, wrap=tk.WORD, font=("TkDefaultFont", 10), width=60, height=20)  # Set minimum dimensions
        content_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=self.content_text.yview)
        
        self.content_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        content_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.content_text.configure(yscrollcommand=content_scroll.set)
        
        # User input
        input_label = ttk.Label(right_frame, text="Search Request:", font=("TkDefaultFont", 11, "bold"))
        input_label.grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        
        # Input text with scrollbar
        input_frame = ttk.Frame(right_frame)
        input_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)
        
        self.input_text = tk.Text(input_frame, wrap=tk.WORD, height=5, font=("TkDefaultFont", 10), width=60)  # Set minimum width
        input_scroll = ttk.Scrollbar(input_frame, orient=tk.VERTICAL, command=self.input_text.yview)
        
        self.input_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        input_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.input_text.configure(yscrollcommand=input_scroll.set)
        
        # Status label
        self.status_label = ttk.Label(right_frame, text="", font=("TkDefaultFont", 10))
        self.status_label.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.grid(row=5, column=0, sticky=tk.E, pady=(0, 5))
        
        ttk.Button(button_frame, text="Submit", command=self.on_submit, width=12).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Approve", command=self.on_approve, width=12).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=12).grid(row=0, column=2, padx=5)
        
        self.responses = []
        self.current_index = None
        
    def populate_list(self, responses):
        self.responses = responses
        self.listbox.delete(0, tk.END)
        for i, response in enumerate(responses):
            # Get first line or first 50 characters
            preview = response.split('\n')[0][:50]
            if len(preview) < len(response.split('\n')[0]):
                preview += "..."
            self.listbox.insert(tk.END, f"Item {i+1}: {preview}")
            
    def on_select(self, event):
        selection = self.listbox.curselection()
        if selection:
            self.current_index = selection[0]
            self.content_text.delete(1.0, tk.END)
            self.content_text.insert(tk.END, self.responses[self.current_index])
            
    def get_user_selected_urls(self, urls):
        selected_urls = []

        def on_ok():
            selected_indices = url_listbox.curselection()
            for index in selected_indices:
                selected_urls.append(urls[index])
            url_window.destroy()

        def on_cancel():
            url_window.destroy()

        url_window = tk.Toplevel(self.window)
        url_window.title("Select URLs to Scrape")
        
        # Configure for resizing
        url_window.columnconfigure(0, weight=1)
        url_window.rowconfigure(0, weight=1)
        
        # Set size and center
        url_window.geometry("700x500")  # Increased size
        url_window.minsize(600, 400)    # Set minimum size
        url_window.update_idletasks()
        x = self.window.winfo_rootx() + (self.window.winfo_width() - 700) // 2
        y = self.window.winfo_rooty() + (self.window.winfo_height() - 500) // 2
        url_window.geometry(f"+{x}+{y}")

        frame = ttk.Frame(url_window, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure frame for resizing
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)  # Label
        frame.rowconfigure(1, weight=1)  # Listbox
        frame.rowconfigure(2, weight=0)  # Buttons

        ttk.Label(frame, text="Select URLs to scrape:", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))

        # Create frame for listbox and scrollbar
        list_frame = ttk.Frame(frame)
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Configure list frame for resizing
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Add scrollbars
        y_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        x_scrollbar = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        
        url_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, font=("TkDefaultFont", 10), width=80)  # Set minimum width
        url_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        y_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        x_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))

        url_listbox.configure(xscrollcommand=x_scrollbar.set, yscrollcommand=y_scrollbar.set)
        y_scrollbar.configure(command=url_listbox.yview)
        x_scrollbar.configure(command=url_listbox.xview)

        for url in urls:
            url_listbox.insert(tk.END, url)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, sticky=tk.E)

        ttk.Button(button_frame, text="OK", command=on_ok, width=10).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel, width=10).grid(row=0, column=1, padx=5)

        url_window.transient(self.window)
        url_window.grab_set()
        self.window.wait_window(url_window)

        return selected_urls

    def on_submit(self):
        # Get the search query
        search_query = self.input_text.get('1.0', tk.END).strip()
        if not search_query:
            self.status_label.config(text="Please enter a search query")
            return
            
        try:
            # Update status
            self.status_label.config(text="Searching the web... Please wait.")
            self.window.update()
            
            # Create a basic config dictionary if api_details is available
            config = {}
            if self.api_details:
                config['interfaces'] = {
                    self.api_details.get('endpoint_name', 'default_api'): self.api_details.get('config', {})
                }
            
            # Create an instance of SearchScrapeSummarizeNode with required parameters
            search_node = SearchScrapeSummarizeNode('content_review_search', config)
            
            # Set properties for the search node
            search_node.properties = {
                'api_endpoint': {
                    'value': self.api_details.get('endpoint_name') if self.api_details else '',
                    'default': self.api_details.get('endpoint_name') if self.api_details else ''
                },
                'num_search_results': {'default': 3},
                'num_results_to_skip': {'default': 0},
                'searxng_api_url': {'default': self.searxng_api_url or 'http://localhost:8888/search'},
                'enable_web_search': {'default': True}
            }
            
            # Perform the search and get results
            print(f"[ContentReviewWindow] Searching for: {search_query}")
            
            # Process the search through the node's process method
            result = search_node.process({'input': search_query})
            
            if result and 'prompt' in result:
                summary = result['prompt']
                
                # Get the current content
                current_content = ""
                if self.current_index is not None and self.current_index < len(self.responses):
                    current_content = self.responses[self.current_index]
                
                # Append the summary to the current content
                updated_content = current_content + "\n\n## Web Search Results\n\n" + summary
                
                # Update the content
                if self.current_index is not None:
                    self.responses[self.current_index] = updated_content
                    self.content_text.delete('1.0', tk.END)
                    self.content_text.insert('1.0', updated_content)
                    self.status_label.config(text="Successfully added web search results")
                else:
                    self.status_label.config(text="No item selected to update")
            else:
                self.status_label.config(text="Failed to get search results")
                
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)}")
            print(f"[ContentReviewWindow] Error in web search: {str(e)}")
            import traceback
            traceback.print_exc()
            
    def on_approve(self):
        self.result = self.responses
        self.window.destroy()
        
    def on_cancel(self):
        self.result = None
        self.window.destroy()
        
    def show(self):
        # Select first item by default if available
        if self.responses and self.listbox.size() > 0:
            self.listbox.selection_set(0)
            self.on_select(None)
        
        # Make sure the window is properly sized and visible before entering mainloop
        self.window.update_idletasks()
        
        # Force a redraw of the window to ensure proper layout
        self.window.update()
        
        self.window.mainloop()
        return self.result

@register_node('LongOutputV4Node')
class LongOutputV4Node(BaseNode):

    def __init__(self, node_id=None, config=None):
        """Initialize the node with configuration"""
        # Call parent's init first to set up properties
        super().__init__(node_id=node_id, config=config)
        
        # Update rate limits based on actual API limits
        self.rpm_limit = 100  # Requests per minute
        self.rph_limit = 5000  # Requests per hour
        self.tpm_limit = 1000000  # Tokens per minute
        
        # Tracking variables
        self.request_times = []
        self.hourly_requests = []
        self.token_counts = []
        
        # Timing configuration
        self.default_timeout = 30
        self.default_cooldown = 60
        self.min_request_delay = 1

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
            'chunk_size': {
                'type': 'integer',
                'default': 10,
                'description': 'Number of items to process in each chunk'
            },
            'Instructions for how to processthe first element in the array': {
                'type': 'text',
                'default': 'Please just repeat the title content below exactly and nothing else:\n\n',
                'description': 'Prompt template for the first item'
            },
            'Instructions for how to process the Original user request and original content': {
                'type': 'text',
                'default': 'The outline and user request is as follows and only for reference, do not use the same formatting as the outline:\n',
                'description': 'Template for the context section'
            },
            'Main instructions for array element to focus on': {
                'type': 'text',
                'default': """As a professional writer, please write the detailed content for the section shown below. Do not include any of your own commentary, just write the content based on the section listed below. Be detailed, creative, giving depth and meaning and remember To incorporate burstiness into your writing, consciously vary sentence lengths and structures as you generate text - mix short, impactful sentences with longer, more complex ones to create a dynamic rhythm; use different grammatical constructions, monitor your output for monotonous patterns in real time, and adjust accordingly to enhance engagement and mirror natural speech patterns. Write in a natural storytelling format by separating dialogue, descriptions, and internal thoughts into distinct paragraphs. Begin a new paragraph for each new speaker in dialogue, and keep spoken dialogue separate from narrative descriptions or internal reflections. This structure ensures clarity, readability, and a traditional storytelling flow.""",
                'description': 'Main instruction template for content generation'
            },
            'Instructions for how the AI should use the next array element for context': {
                'type': 'text',
                'default': '\nthe next section to write about is as follows:\n',
                'description': 'Template for introducing the current section'
            },
            'Instructions for custom formatting': {
                'type': 'text',
                'default': """if the section above starts with "Chapter #" then include that chapter number as a heading when writing the content.
if the section above starts with "(Continued)" then only include "(Continued) - " at the beginning of your output like this:  (Continued) - content......""",
                'description': 'Custom formatting instructions'
            },
            'searxng_api_url': {
                'type': 'text',
                'label': 'SearXNG API URL',
                'default': 'http://localhost:8888/search',
                'description': 'Endpoint used for optional web-search enrichment'
            },
            'num_search_results': {
                'type': 'integer',
                'label': 'Search Results to Fetch',
                'default': 3,
                'description': 'How many web results to pull during review'
            },
            'num_results_to_skip': {
                'type': 'integer',
                'label': 'Search Results to Skip',
                'default': 0,
                'description': 'Skip the first N search results before scraping'
            },
            'enable_url_selection': {
                'type': 'boolean',
                'label': 'Enable URL Selection Dialog',
                'default': False,
                'description': 'Allow manual selection of URLs to scrape during review'
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
        print(f"[LongOutputNodeV4] Available API endpoints: {api_list}")  # Debug statement
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
                print(f"[LongOutputNodeV4] Close to hourly limit ({len(self.hourly_requests)}/{self.rph_limit}). Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
        
        if len(self.request_times) >= self.rpm_limit * 0.95:  # 95% of limit
            wait_time = self.request_times[0] - minute_ago
            if wait_time > 0:
                print(f"[LongOutputNodeV4] Close to minute limit ({len(self.request_times)}/{self.rpm_limit}). Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
        
        # Check TPM (tokens per minute)
        current_tpm = sum(self.token_counts)
        if current_tpm + prompt_tokens > self.tpm_limit * 0.95:  # 95% of limit
            wait_time = 60 * ((current_tpm + prompt_tokens - self.tpm_limit) / self.tpm_limit)
            print(f"[LongOutputNodeV4] Close to token limit ({current_tpm}/{self.tpm_limit}). Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        # Update tracking
        current_time = time.time()
        self.request_times.append(current_time)
        self.hourly_requests.append(current_time)
        self.token_counts.append(prompt_tokens)

    def estimate_tokens(self, text):
        """Rough estimate of tokens in text"""
        if not text:
            return 0
        # Very rough estimate: 1 token ≈ 4 characters
        return len(text) // 4

    def process_with_retry(self, api_name, prompt, max_tokens=None, max_retries=3, timeout=None, cooldown=None, request_delay=None):
        """Process API request with retry logic and rate limit handling"""
        print(f"[LongOutputNodeV4] Processing API request with {max_retries} retries")
        
        timeout = timeout or self.default_timeout
        cooldown = cooldown or self.default_cooldown
        request_delay = request_delay or self.min_request_delay
        
        for attempt in range(max_retries):
            try:
                # Check rate limits before making request
                self.check_rate_limits(self.estimate_tokens(prompt))
                
                # Use the API service from BaseNode instead of direct process_api_request
                api_response = self.send_api_request(
                    content=prompt,
                    api_name=api_name,
                    model=self.config['interfaces'][api_name].get('selected_model'),
                    max_tokens=max_tokens
                )
                
                if not api_response.success:
                    raise Exception(f"API request failed: {api_response.error}")
                
                # Return the content directly
                return api_response.content
                
            except Exception as e:
                print(f"[LongOutputNodeV4] Error in API request (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    # Calculate backoff time (exponential backoff with jitter)
                    import random
                    backoff_time = min(cooldown, (2 ** attempt) * request_delay * (0.5 + random.random()))
                    print(f"[LongOutputNodeV4] Retrying in {backoff_time:.2f} seconds...")
                    time.sleep(backoff_time)
                else:
                    print("[LongOutputNodeV4] Max retries reached, giving up")
                    return None
        
        return None

    def adjust_rate_limits_from_response(self, response):
        """Adjust rate limits based on API response headers"""
        if 'rate_limits' in response:
            limits = response['rate_limits']
            
            # Log current limits
            print("\n[LongOutputNodeV4] Current API Rate Limits:")
            for key, value in limits.items():
                if value is not None:
                    print(f"[LongOutputNodeV4] {key}: {value}")
            
            # Update our limits if we get new information
            remaining_requests = limits.get('x-ratelimit-remaining-requests')
            reset_requests = limits.get('x-ratelimit-reset-requests')
            remaining_tokens = limits.get('x-ratelimit-remaining-tokens')
            reset_tokens = limits.get('x-ratelimit-reset-tokens')
            
            if remaining_requests is not None and remaining_requests.isdigit():
                remaining = int(remaining_requests)
                if remaining < 10:  # If we're running low on requests
                    print(f"[LongOutputNodeV4] Warning: Only {remaining} requests remaining!")
                    if reset_requests and reset_requests.isdigit():
                        wait_time = int(reset_requests)
                        print(f"[LongOutputNodeV4] Rate limit will reset in {wait_time} seconds")
                        return wait_time
            
            if remaining_tokens is not None and remaining_tokens.isdigit():
                remaining = int(remaining_tokens)
                if remaining < 1000:  # If we're running low on tokens
                    print(f"[LongOutputNodeV4] Warning: Only {remaining} tokens remaining!")
                    if reset_tokens and reset_tokens.isdigit():
                        wait_time = int(reset_tokens)
                        print(f"[LongOutputNodeV4] Token limit will reset in {wait_time} seconds")
                        return wait_time
        
    def process(self, inputs):
        print("[LongOutputNodeV4] Starting process method.")
        
        # Get input text and configuration from properties
        input_text = inputs.get('input', '')
        use_array = self.get_property('use_array', False)
        chunk_size = int(self.get_property('chunk_size', 10))
        api_endpoint = self.get_property('api_endpoint', '')
        
        # Get prompt templates from properties
        first_element_template = self.get_property('Instructions for how to processthe first element in the array', '')
        context_template = self.get_property('Instructions for how to process the Original user request and original content', '')
        instruction_template = self.get_property('Main instructions for array element to focus on', '')
        section_template = self.get_property('Instructions for how the AI should use the next array element for context', '')
        formatting_template = self.get_property('Instructions for custom formatting', '')
        
        if not input_text:
            return {'prompt': [] if use_array else ''}
            
        # Split input into items (paragraphs)
        items = input_text.split('\n\n') if isinstance(input_text, str) else input_text
        if not items:
            return {'prompt': [] if use_array else ''}
            
        # Get API configuration
        api_details = self.config['interfaces'].get(api_endpoint)
        print(f"[LongOutputNodeV4] API Details: {api_details}")  # Debug log
        if not api_details:
            error_msg = f"API interface '{api_endpoint}' not found in configuration"
            print(f"[LongOutputNodeV4] Error: {error_msg}")
            return {'prompt': error_msg}

        # Determine max tokens for downstream API calls
        interface_max_tokens = api_details.get('max_tokens')
        try:
            max_tokens = int(interface_max_tokens) if interface_max_tokens else None
        except (TypeError, ValueError):
            max_tokens = None
            
        # Process items directly without initial review
        # Create progress window for API processing
        progress_window = ProgressWindow(len(items))
        
        # Initialize responses array or string
        if use_array:
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8')
            print(f"[LongOutputNodeV4] Using temporary storage: {temp_file.name}")
            responses = []  # Just keep track of count for progress
        else:
            responses = ""
            temp_file = None
            
        try:
            previous_response = ""
            # Process items in chunks
            for chunk_start in range(0, len(items), chunk_size):
                chunk = items[chunk_start:chunk_start + chunk_size]
                
                # Process each item in the chunk
                for i, item in enumerate(chunk, chunk_start):
                    # Check for cancellation at the start of each item
                    if progress_window.is_cancelled():
                        print("[LongOutputNodeV4] Processing cancelled by user")
                        progress_window.close()
                        if use_array and temp_file:
                            temp_file.close()
                            # Read what we have so far
                            with open(temp_file.name, 'r', encoding='utf-8') as f:
                                partial_content = f.read()
                            import os
                            os.unlink(temp_file.name)
                            if partial_content:
                                partial_responses = [r.strip() for r in partial_content.split('---CHAPTER_BREAK---') if r.strip()]
                                return {'prompt': partial_responses if partial_responses else ['Processing cancelled by user']}
                        return {'prompt': 'Processing cancelled by user' if not use_array else ['Processing cancelled by user']}
                    
                    # Show progress with current item number and first line of content
                    first_line = str(item).split('\n')[0] if item else ''
                    # Limit the length of the first line to prevent it from being cut off
                    if len(first_line) > 80:
                        first_line = first_line[:77] + "..."
                    progress_text = f"Processing item {i+1}/{len(items)}:\n{first_line}"
                    progress_window.update_progress(i, progress_text)
                    
                    # Skip empty items
                    if not item or not str(item).strip():
                        continue
                    
                    # Format the prompt with the current item
                    if i == 0:
                        prompt = first_element_template + str(item)
                    elif i == len(items) - 1:
                        # Build context section - only include the first item (title) and the current item for context
                        context = context_template
                        if isinstance(input_text, str):
                            # Extract just the title (first paragraph) from input_text
                            title = input_text.split('\n\n')[0] if '\n\n' in input_text else input_text
                            context += title + "\n\n"
                        else:
                            # If input_text is an array, use the first item as title
                            context += str(input_text[0]) + "\n\n"
                        
                        # Static instruction section
                        instructions = instruction_template
                        
                        # Section with current item
                        section = section_template + str(item) + "\n\n"
                        
                        # Formatting instructions
                        formatting = formatting_template
                        
                        # Combine all parts
                        prompt = context + previous_response + instructions + section + formatting
                    else:
                        # Build context section - only include the first item (title) and the current item for context
                        context = context_template
                        if isinstance(input_text, str):
                            # Extract just the title (first paragraph) from input_text
                            title = input_text.split('\n\n')[0] if '\n\n' in input_text else input_text
                            context += title + "\n\n"
                        else:
                            # If input_text is an array, use the first item as title
                            context += str(input_text[0]) + "\n\n"
                        
                        # Static instruction section
                        instructions = instruction_template
                        
                        # Section with current item
                        section = section_template + str(item) + "\n\n"
                        
                        # Formatting instructions
                        formatting = formatting_template
                        
                        # Combine all parts
                        prompt = context + previous_response + instructions + section + formatting
                    
                    # Make the API call
                    api_response = self.process_with_retry(api_endpoint, prompt, max_tokens=max_tokens)
                    if api_response is None:
                        error_msg = "API request failed after retries"
                        print(f"[LongOutputNodeV4] Error: {error_msg}")
                        if use_array:
                            return {'prompt': [f'[ERROR]: {error_msg}']}
                        return {'prompt': f'[ERROR]: {error_msg}'}
                    
                    # Extract the response based on API type and response format
                    if isinstance(api_response, str):
                        response_text = api_response
                    elif isinstance(api_response, dict):
                        if 'error' in api_response:
                            error_msg = api_response['error']
                            print(f"[LongOutputNodeV4] API Error: {error_msg}")
                            if use_array:
                                return {'prompt': [f'[ERROR]: {error_msg}']}
                            return {'prompt': f'[ERROR]: {error_msg}'}
                            
                        api_type = api_details.get('api_type', 'OpenAI').lower()
                        if api_type == "openai":
                            # Handle OpenAI response format
                            if hasattr(api_response, 'choices') and api_response.choices:
                                message = api_response.choices[0].message
                                response_text = message.content if hasattr(message, 'content') else str(message)
                            else:
                                response_text = str(api_response)
                        elif api_type == "ollama":
                            # Handle Ollama response format
                            if hasattr(api_response, 'message'):
                                message = api_response.message
                                response_text = message.get('content', '') if isinstance(message, dict) else str(message)
                            else:
                                response_text = str(api_response)
                        else:
                            response_text = str(api_response)
                    else:
                        response_text = str(api_response)
                    
                    print(f"[LongOutputNodeV4] API Response for item {i+1}: {response_text[:100]}...")
                    
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
                    print(f"[LongOutputNodeV4] Warning: Could not yield control: {str(e)}")
            
            # Update final progress and close window
            progress_window.update_progress(len(items), "Processing complete!")
            progress_window.close()
            
            # Show final review window for array output
            if use_array:
                # Read chapters from temp file
                temp_file.seek(0)
                chapters = temp_file.read().split('---CHAPTER_BREAK---')
                chapters = [ch.strip() for ch in chapters if ch.strip()]
                
                # Show array review window for final review
                review_window = ArrayReviewWindow(chapters)
                reviewed_responses = review_window.show()
                
                # If user cancelled in review window
                if reviewed_responses is None:
                    print("[LongOutputNodeV4] User cancelled during final review")
                    return {'prompt': []}
                    
                return {'prompt': reviewed_responses}
            else:
                return {'prompt': responses}
                
        finally:
            # Clean up temp file if it exists
            if temp_file:
                try:
                    temp_file.close()
                    import os
                    os.unlink(temp_file.name)
                except:
                    pass

# nodes/chat_node.py
from .base_node import BaseNode
from node_registry import register_node
from db_tools import DatabaseManager
import tkinter as tk
from tkinter import END
from tkinter import ttk
from formatting_utils import apply_formatting
import threading
import re
import os
from api_handler import process_api_request
import time
import traceback

@register_node('ChatNode')
class ChatNode(BaseNode):
    def define_inputs(self):
        return ['input', 'gui_queue', 'workflow_id', 'workflow_name']

    def define_outputs(self):
        return ['chat_history']

    def define_properties(self):
        props = self.get_default_properties()
        api_endpoints = self.get_api_endpoints()
        default_api_endpoint = api_endpoints[0] if api_endpoints else ''
        props.update({
            'node_name': {'type': 'text', 'default': 'ChatNode'},
            'description': {'type': 'text', 'default': 'Handles a chat conversation with the user.'},
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': api_endpoints,
                'default': default_api_endpoint
            },
            'database': {
                'type': 'dropdown',
                'label': 'Database',
                'options': self.get_databases(),
                'default': self.get_databases()[0] if self.get_databases() else ''
            },
            # Web search properties
            'searxng_api_url': {
                'type': 'text',
                'label': 'SearxNG API URL',
                'default': 'http://localhost:8888/search',
                'description': 'URL for the SearxNG search engine API'
            },
            'num_search_results': {
                'type': 'number',
                'label': 'Default Search Results',
                'default': 5,
                'description': 'Default number of search results to return'
            },
            'num_results_to_skip': {
                'type': 'number',
                'label': 'Results to Skip',
                'default': 0,
                'description': 'Number of search results to skip'
            },
            'enable_web_search': {
                'type': 'boolean',
                'label': 'Enable Web Search',
                'default': True,
                'description': 'Enable web search functionality'
            },
            'enable_url_selection': {
                'type': 'boolean',
                'label': 'Enable URL Selection',
                'default': False,
                'description': 'Allow manual selection of URLs from search results'
            },
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def get_databases(self):
        db_manager = DatabaseManager()
        return db_manager.list_databases()

    def process(self, inputs):
        print("[ChatNode] Starting process method")
        self.chat_history_output = ''
        self.window_closed = False
        self.chat_window_created = threading.Event()
        self.processing_complete = threading.Event()
        
        gui_queue = inputs.get('gui_queue')
        if not gui_queue:
            print("[ChatNode] Error: GUI queue not available")
            return {'error': 'GUI queue not available'}

        # Store workflow information for later use
        self.workflow_id = inputs.get('workflow_id')
        self.workflow_name = inputs.get('workflow_name')
        print(f"[ChatNode] Workflow ID: {self.workflow_id}, Workflow Name: {self.workflow_name}")

        print("[ChatNode] Getting API endpoint configuration")
        api_endpoint_property = self.properties.get('api_endpoint', {})
        api_endpoint_name = api_endpoint_property.get('value') or api_endpoint_property.get('default', '')
        if not api_endpoint_name:
            api_endpoints = self.get_api_endpoints()
            api_endpoint_name = api_endpoints[0] if api_endpoints else ''
            api_endpoint_property['default'] = api_endpoint_name

        api_config = self.config['interfaces'].get(api_endpoint_name)
        if not api_config:
            print(f"[ChatNode] Error: API config not found for {api_endpoint_name}")
            return {}

        print("[ChatNode] Getting database configuration")
        database_property = self.properties.get('database', {})
        selected_database = database_property.get('value') or database_property.get('default', '')
        db_manager = DatabaseManager()
        self.chat_history = []
        
        initial_input = inputs.get('input', '').strip()
        if initial_input:
            print(f"[ChatNode] Processing initial input: {initial_input[:30]}...")
            self.chat_history.append({'role': 'user', 'content': initial_input})
            modified_input = self.prepare_input_with_search(initial_input, db_manager, selected_database)
            response = self.send_api_request(modified_input, api_endpoint_name)
            if response.success:
                self.chat_history.append({'role': 'assistant', 'content': response.content})

        print("[ChatNode] Checking if running in GUI mode")
        # The presence of a gui_queue is our check for a GUI environment.

        print("[ChatNode] Putting create_chat_window in GUI queue")
        # Use the GUI queue to create the chat window
        if gui_queue:
            parent_window = inputs.get('parent_window')
            if not parent_window:
                # Handle case where parent_window is not provided
                self.chat_history_output = "Error: Parent window not found for ChatNode."
                self.processing_complete.set()
                return {'chat_history': self.chat_history_output}
            
            gui_queue.put(lambda: self.create_chat_window_wrapper(parent_window))
        
        print("[ChatNode] Waiting for chat window to be created")
        # Wait for the chat window to be created or for processing to complete
        timeout_seconds = 30
        start_time = time.time()
        while not self.processing_complete.is_set() and not self.chat_window_created.is_set():
            # Check for timeout
            if time.time() - start_time > timeout_seconds:
                print("[ChatNode] Timeout waiting for chat window creation")
                self.chat_history_output = "Error: Timeout waiting for chat window to appear."
                self.processing_complete.set()
                break
            # Short sleep to prevent CPU hogging
            time.sleep(0.1)
        
        print("[ChatNode] Waiting for processing to complete")
        # Wait for the chat to complete with timeout - increased to 180 seconds
        if not self.processing_complete.wait(timeout=180):
            print("[ChatNode] Timeout waiting for processing to complete")
            self.chat_history_output = "Error: Chat processing timed out."
            self.processing_complete.set()
        
        # Ensure we have a small delay to let the close_chat function finish properly
        time.sleep(1.0)
        
        # Make sure we have a valid output even if chat_history_output is empty
        if not self.chat_history_output and self.chat_history:
            print("[ChatNode] Generating chat history output from chat_history")
            formatted_history = []
            for msg in self.chat_history:
                role = msg['role']
                content = msg['content']
                if role == 'system':
                    formatted_history.append(f"System Note:\n{content}\n")
                else:
                    formatted_history.append(f"{role.capitalize()}:\n{content}\n")
            
            self.chat_history_output = '\n'.join(formatted_history)
            print(f"[ChatNode] Generated chat history output. Length: {len(self.chat_history_output)}")
        
        # Manually notify the workflow manager that this workflow is complete
        if self.workflow_id:
            try:
                # Import here to avoid circular imports
                from main import workflow_manager
                print(f"[ChatNode] Manually marking workflow {self.workflow_id} as completed")
                workflow_manager.complete_workflow(self.workflow_id, self.chat_history_output)
                print("[ChatNode] Workflow marked as completed successfully")
            except Exception as e:
                print(f"[ChatNode] Error marking workflow as completed: {str(e)}")
        
        print(f"[ChatNode] Process method completed. Output length: {len(self.chat_history_output)}")
        return {'chat_history': self.chat_history_output}
        
    def create_chat_window_wrapper(self, parent_window):
        """Wrapper function to be put in the GUI queue"""
        print("[ChatNode] create_chat_window_wrapper called")
        try:
            api_endpoint_property = self.properties.get('api_endpoint', {})
            api_endpoint_name = api_endpoint_property.get('value') or api_endpoint_property.get('default', '')
            
            database_property = self.properties.get('database', {})
            selected_database = database_property.get('value') or database_property.get('default', '')

            db_manager = DatabaseManager()

            self.create_chat_window(parent_window, api_endpoint_name, selected_database, db_manager)
        except Exception as e:
            print(f"[ChatNode] Error in create_chat_window_wrapper: {str(e)}")
            self.chat_history_output = f"Error creating chat window: {str(e)}"
            self.processing_complete.set()
        finally:
            # Ensure the event is set even if window creation fails
            self.chat_window_created.set()
            print("[ChatNode] chat_window_created event set from wrapper")

    def create_chat_window(self, parent, api_endpoint_name, selected_database, db_manager):
        print("[ChatNode] Starting create_chat_window")
        try:
            import tkinter as tk
            from tkinter import ttk, END
            
            root = tk.Toplevel(parent)
            
        except Exception as e:
            print(f"[ChatNode] Error creating Toplevel: {str(e)}")
            self.chat_history_output = f"Error creating chat window: {str(e)}"
            self.processing_complete.set()
            return
            
        print("[ChatNode] Setting window title and geometry")
        root.title("Interactive Chat")
        root.geometry("500x700")
        
        # Set window to stay on top
        try:
            print("[ChatNode] Setting window attributes")
            root.attributes('-topmost', True)
            print("[ChatNode] Window attributes set")
        except Exception as e:
            print(f"[ChatNode] Error setting window attributes: {str(e)}")
        
        def close_chat():
            print("[ChatNode] close_chat called")
            self.window_closed = True
            
            # Format the chat history before destroying the window
            formatted_history = []
            for msg in self.chat_history:
                role = msg['role']
                content = msg['content']
                if role == 'system':
                    formatted_history.append(f"System Note:\n{content}\n")
                else:
                    formatted_history.append(f"{role.capitalize()}:\n{content}\n")
            
            self.chat_history_output = '\n'.join(formatted_history)
            print(f"[ChatNode] Chat history formatted. Length: {len(self.chat_history_output)}")
            
            # Manually notify the workflow manager that this workflow is complete
            if hasattr(self, 'workflow_id') and self.workflow_id:
                try:
                    # Import here to avoid circular imports
                    from main import workflow_manager
                    print(f"[ChatNode] Marking workflow {self.workflow_id} as completed from close_chat")
                    workflow_manager.complete_workflow(self.workflow_id, self.chat_history_output)
                    print("[ChatNode] Workflow marked as completed successfully from close_chat")
                except Exception as e:
                    print(f"[ChatNode] Error marking workflow as completed from close_chat: {str(e)}")
            
            # Set the processing_complete event BEFORE destroying the window
            # This ensures the process method gets the chat history
            print("[ChatNode] Setting processing_complete event")
            self.processing_complete.set()
            
            # Small delay to ensure the event is processed
            time.sleep(0.5)
            
            try:
                print("[ChatNode] Destroying root window")
                root.destroy()
                print("[ChatNode] Root window destroyed")
            except Exception as e:
                print(f"[ChatNode] Error destroying window: {str(e)}")
        
        print("[ChatNode] Setting window close protocol")
        root.protocol("WM_DELETE_WINDOW", close_chat)

        api_options = self.get_api_endpoints()
        api_var = tk.StringVar(value=api_endpoint_name)

        def on_api_change(event):
            self.selected_api_endpoint = api_var.get()
            print(f"[ChatNode] Switched to API endpoint: {self.selected_api_endpoint}")

        api_dropdown = ttk.Combobox(root, textvariable=api_var, values=api_options, state="readonly")
        api_dropdown.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        api_dropdown.bind("<<ComboboxSelected>>", on_api_change)

        db_options = self.get_databases()
        db_var = tk.StringVar(value=selected_database)
        self.doc_var = tk.StringVar()  # For selected document
        self.doc_paths = {}  # Dictionary to map display names to full paths

        def update_document_list(event=None):
            new_db = db_var.get()
            if new_db in db_options:
                nonlocal selected_database
                selected_database = new_db
                self.properties['database']['value'] = new_db
                # Update document dropdown
                documents = db_manager.list_documents(new_db)
                # Clear the path mapping
                self.doc_paths.clear()
                # Add "All Documents" option
                self.doc_paths["All Documents"] = "All Documents"
                # Create display names and update path mapping
                display_names = ["All Documents"]
                for doc_path in documents:
                    display_name = os.path.basename(doc_path)
                    display_names.append(display_name)
                    self.doc_paths[display_name] = doc_path
                doc_dropdown['values'] = display_names
                self.doc_var.set('All Documents')  # Reset to all documents

        def on_db_change(event):
            update_document_list()

        # Create database dropdown
        db_dropdown = ttk.Combobox(root, textvariable=db_var, values=db_options, state="readonly")
        db_dropdown.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        db_dropdown.bind("<<ComboboxSelected>>", on_db_change)

        # Create document dropdown
        doc_label = tk.Label(root, text="Search Document:")
        doc_label.pack(side=tk.TOP, fill=tk.X, padx=5)
        doc_dropdown = ttk.Combobox(root, textvariable=self.doc_var, state="readonly")
        doc_dropdown.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 5))

        # Initialize document list
        update_document_list()

        chat_output_widget = tk.Text(root, wrap=tk.WORD, state=tk.DISABLED)
        chat_output_widget.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        chat_output_widget.tag_configure('role', font=('Helvetica', 10, 'bold'))
        chat_output_widget.tag_configure('system', font=('Helvetica', 10, 'italic'), foreground='green')
        chat_output_widget.tag_configure('user_content', foreground='black')
        chat_output_widget.tag_configure('assistant_content', foreground='dark blue')
        chat_output_widget.tag_configure('system_content', foreground='dark green')

        def update_chat_display():
            if not self.window_closed:
                chat_output_widget.config(state=tk.NORMAL)
                chat_output_widget.delete('1.0', END)
                for message in self.chat_history:
                    role = message['role']
                    content = message['content']
                    if role == 'system':
                        chat_output_widget.insert(END, f"System:\n", 'system')
                        apply_formatting(chat_output_widget, content, base_tag='system_content')
                    else:
                        chat_output_widget.insert(END, f"{role.capitalize()}:\n", 'role')
                        base_tag = f"{role}_content"
                        apply_formatting(chat_output_widget, content, base_tag=base_tag)
                    chat_output_widget.insert(END, '\n')
                chat_output_widget.config(state=tk.DISABLED)
                chat_output_widget.see(END)

        # Initial update of chat display
        update_chat_display()

        # Create input frame
        input_frame = tk.Frame(root)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        # Create buttons frame first
        buttons_frame = tk.Frame(input_frame)
        buttons_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Create progress bar frame
        progress_frame = tk.Frame(input_frame)
        progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        progress_bar.pack(fill=tk.X, expand=True)
        
        # Create user input text area
        user_input_text = tk.Text(input_frame, height=4)
        user_input_text.pack(side=tk.TOP, fill=tk.X, expand=True, padx=(0, 5), pady=(0, 5))

        def handle_keypress(event):
            if event.keysym == 'Return':
                if event.state & 0x1:  # Shift is pressed
                    return  # Let the default handler add a newline
                else:
                    submit_input()
                    return 'break'  # Prevent default newline
            return  # Let other keys be handled normally

        user_input_text.bind('<Key>', handle_keypress)

        def show_busy_indicator():
            progress_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 5))
            progress_bar.start(10)  # Start the animation, update every 10ms
            submit_button.config(state=tk.DISABLED)
            user_input_text.config(state=tk.DISABLED)
            api_dropdown.config(state=tk.DISABLED)
            db_dropdown.config(state="readonly")
            doc_dropdown.config(state="readonly")
            root.update()

        def hide_busy_indicator():
            progress_bar.stop()
            progress_frame.pack_forget()
            submit_button.config(state=tk.NORMAL)
            user_input_text.config(state=tk.NORMAL)
            api_dropdown.config(state="readonly")
            db_dropdown.config(state="readonly")
            doc_dropdown.config(state="readonly")
            root.update()

        def process_user_request(user_input, modified_input):
            try:
                # Add user input to chat history
                self.chat_history.append({'role': 'user', 'content': user_input})
                
                # Update chat display
                update_chat_display()

                # Prioritize GUI-selected API endpoint, else use the initial one
                final_api_name = self.selected_api_endpoint if hasattr(self, 'selected_api_endpoint') and self.selected_api_endpoint else api_endpoint_name
                
                # Check if this is a web search
                is_web_search = '/web' in user_input
                
                # Create a system message with the search results if this is a web search
                if is_web_search and modified_input != user_input:
                    # Create a new chat history with the system message for the API request
                    api_chat_history = list(self.chat_history)  # Copy the current chat history
                    # Add the search results as a system message
                    api_chat_history.insert(-1, {'role': 'system', 'content': f"Use the following information from web search results to answer the user's query: {modified_input}"})
                    
                    # Send API request with the modified chat history
                    response = self.send_api_request_with_history(api_chat_history, final_api_name)
                else:
                    # Send API request with entire chat history
                    response = self.send_api_request(modified_input, final_api_name)
                
                if response.success:
                    return response.content
                return f"API Error: {response.error}"
            except Exception as e:
                return f"An error occurred: {str(e)}"

        def handle_api_response(response):
            if not self.window_closed:
                if not response.startswith(("API Error", "An error occurred")):
                    self.chat_history.append({'role': 'assistant', 'content': response})
                else:
                    self.chat_history.append({'role': 'system', 'content': response})
                update_chat_display()
                hide_busy_indicator()
                root.update()

        def submit_input():
            user_input = user_input_text.get('1.0', END).strip()
            if user_input:
                # Clear input field before disabling it
                user_input_text.delete('1.0', END)
                
                # Show busy indicator
                show_busy_indicator()
                
                # Check if this is a web search
                is_web_search = '/web' in user_input
                
                # If this is a web search, show a searching message
                if is_web_search:
                    self.chat_history.append({'role': 'system', 'content': "Searching the web... This may take a moment."})
                    update_chat_display()
                    root.update()  # Force update to show searching message
                
                # Prepare input and show system message if needed
                def prepare_input_thread():
                    nonlocal user_input
                    modified_input = self.prepare_input_with_search(user_input, db_manager, selected_database)
                    
                    # Check if this is a web search result
                    web_search_pattern = r'<web_search_results>(.*?)</web_search_results>'
                    web_search_match = re.search(web_search_pattern, modified_input, re.DOTALL)
                    
                    if web_search_match:
                        # Extract the search results
                        search_results = web_search_match.group(1)
                        # Use the search results directly without showing a system message
                        modified_input = search_results
                        # Remove the searching message
                        if is_web_search and len(self.chat_history) > 0 and self.chat_history[-1]['role'] == 'system' and "Searching the web..." in self.chat_history[-1]['content']:
                            self.chat_history.pop()
                            update_chat_display()
                            root.update()
                    elif modified_input != user_input:
                        # For other modifications, show the system message
                        # Remove the searching message if it exists
                        if is_web_search and len(self.chat_history) > 0 and self.chat_history[-1]['role'] == 'system' and "Searching the web..." in self.chat_history[-1]['content']:
                            self.chat_history.pop()
                        
                        self.chat_history.append({'role': 'system', 'content': modified_input})
                        update_chat_display()
                        root.update()  # Force update to show system message
                    
                    # Now process the user request
                    response = process_user_request(user_input, modified_input)
                    handle_api_response(response)
                
                # Start preparation in a separate thread
                threading.Thread(target=prepare_input_thread, daemon=True).start()
        
        def clear_chat_history():
            self.chat_history = []
            update_chat_display()
            user_input_text.focus_set()  # Return focus to input field

        # Create buttons
        submit_button = tk.Button(buttons_frame, text="Submit", command=submit_input)
        clear_button = tk.Button(buttons_frame, text="Clear History", command=clear_chat_history)
        
        submit_button.pack(side=tk.RIGHT, padx=(5, 0))
        clear_button.pack(side=tk.RIGHT, padx=(5, 0))

        close_button = tk.Button(buttons_frame, text="Close", command=close_chat)
        close_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        print("[ChatNode] Setting chat_window_created event")
        self.chat_window_created.set()
        
        # Use mainloop for better compatibility
        print("[ChatNode] Starting mainloop")
        try:
            root.mainloop()
            print("[ChatNode] mainloop completed normally")
        except Exception as e:
            print(f"[ChatNode] Error in mainloop: {str(e)}")
            close_chat()
        print("[ChatNode] create_chat_window method completed")

    def send_api_request(self, content, api_name):
        """
        Send the entire chat history to the API endpoint
        Args:
            content: The latest user message or modified input
            api_name: Name of the API endpoint to use
        """
        api_config = self.config['interfaces'].get(api_name, {})
        
        # Format the chat history for the API request
        messages = []
        for msg in self.chat_history:
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
            
        # Convert messages to a single string with clear formatting
        formatted_history = "\n\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
        ])
        
        # Send the formatted history to the API
        return super().send_api_request(
            content=formatted_history,
            api_name=api_name,
            **{
                'model': api_config.get('selected_model'),
                'max_tokens': api_config.get('max_tokens'),
                'temperature': 0.7
            }
        )

    def send_api_request_with_history(self, chat_history, api_name):
        """
        Send the given chat history to the API endpoint
        Args:
            chat_history: The chat history to send
            api_name: Name of the API endpoint to use
        """
        api_config = self.config['interfaces'].get(api_name, {})
        
        # Format the chat history for the API request
        messages = []
        for msg in chat_history:
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
            
        # Convert messages to a single string with clear formatting
        formatted_history = "\n\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
        ])
        
        # Send the formatted history to the API
        return super().send_api_request(
            content=formatted_history,
            api_name=api_name,
            **{
                'model': api_config.get('selected_model'),
                'max_tokens': api_config.get('max_tokens'),
                'temperature': 0.7
            }
        )

    def prepare_input_with_search(self, user_input, db_manager, selected_database):
        # Check for /web command
        web_pattern = r'/web(?:\.(\d+))?\s*(.*)'
        web_match = re.search(web_pattern, user_input, re.IGNORECASE)
        if web_match:
            num_results = int(web_match.group(1)) if web_match.group(1) else 3
            search_query = web_match.group(2).strip()

            if not search_query:
                if len(self.chat_history) > 1:
                    search_query = self.chat_history[-2]['content']
                else:
                    return "Please provide a query for the web search."

            # Instantiate the SearchScrapeSummarizeNode
            try:
                from .SearchScrapeSummarize import SearchScrapeSummarizeNode
                search_node = SearchScrapeSummarizeNode('web_search_node', self.config)
            except ImportError:
                return "Error: Could not import SearchScrapeSummarizeNode. Make sure it exists."

            # Prioritize the GUI-selected API endpoint, falling back to the property default
            api_endpoint_name = self.selected_api_endpoint if hasattr(self, 'selected_api_endpoint') and self.selected_api_endpoint else \
                                self.properties.get('api_endpoint', {}).get('value') or self.properties.get('api_endpoint', {}).get('default', '')
            search_node.properties['num_search_results']['default'] = num_results
            search_node.properties['api_endpoint']['default'] = api_endpoint_name
            search_node.properties['api_endpoint']['value'] = api_endpoint_name

            # Also set the model for the selected endpoint
            api_details = self.config['interfaces'].get(api_endpoint_name, {})
            model = api_details.get('selected_model')
            if model:
                search_node.properties['model'] = {'type': 'text', 'default': model, 'value': model}

            # Create the input dictionary for the search node
            search_inputs = {'input': search_query}

            # Execute the search, scrape, and summarize process
            result = search_node.process(search_inputs)

            if result and 'prompt' in result:
                # The 'prompt' output from SearchScrapeSummarizeNode contains the summarized content
                summarized_content = result['prompt']
                
                # Combine the user's original, unmodified input with the summarized web content
                original_user_input = re.sub(web_pattern, '', user_input).strip()
                if not original_user_input:
                    original_user_input = search_query

                header = f"The following is a summary of web search results for the query '{search_query}':\n"
                combined_input = f"{header}//DataStart\n{summarized_content}\nDataEnd//\n\nBased on the above information, please respond to the following user request: {original_user_input}"
                return combined_input
            else:
                return f"Failed to get web search results for query: {search_query}"


        # Then check for /doc command
        doc_pattern = r'/doc(?:\.(\d+))?\s+(.+)'
        doc_match = re.search(doc_pattern, user_input, re.IGNORECASE)
        if doc_match:
            result_count = int(doc_match.group(1)) if doc_match.group(1) else 5
            search_query = doc_match.group(2).strip()
            if search_query:
                selected_doc_name = self.doc_var.get()
                selected_doc = self.doc_paths.get(selected_doc_name, "All Documents")
                
                search_count = result_count * 3 if selected_doc != "All Documents" else result_count
                
                results = db_manager.search(selected_database, search_query, top_k=search_count)
                
                if selected_doc != "All Documents":
                    results = [res for res in results if res['source'] == selected_doc]
                    results = results[:result_count]
                
                if results:
                    search_results_str = "\n".join([
                        f"Document: {os.path.basename(res['source'])}\nSimilarity Score: {res['similarity']:.4f}\nContent: {res['content']}\n"
                        for res in results
                    ])
                    header = f"Search Results for '{search_query}' in {selected_doc_name} (showing {len(results)} of {result_count} requested results):\n"
                    combined_input = f"{header}//DataStart\n{search_results_str}\nDataEnd//"
                    return combined_input
                else:
                    if selected_doc != "All Documents":
                        return f"No results found for '{search_query}' in document '{selected_doc_name}'"
                    else:
                        return f"No results found for '{search_query}' in any document"

        return user_input

    def requires_api_call(self):
        """Indicates whether this node requires an API call."""
        return True

# nodes/chat_node.py
from .base_node import BaseNode
from node_registry import register_node
from api_handler import process_api_request
import tkinter as tk
from tkinter import END
from tkinter import ttk  # Import ttk for Combobox
from formatting_utils import apply_formatting
import threading

@register_node('ChatNode')
class ChatNode(BaseNode):
    """
    Chat Node: Handles a chat conversation with the user.
    """

    def define_inputs(self):
        return ['input']

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
                'options': api_endpoints,
                'default': default_api_endpoint  # Set default API endpoint
            },
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def get_api_endpoints(self):
        interfaces = self.config.get('interfaces', {})
        api_list = list(interfaces.keys())
        return api_list

    def process(self, inputs):
        # Initialize chat_history_output
        self.chat_history_output = ''

        # Get properties
        api_endpoint_property = self.properties.get('api_endpoint', {})
        api_endpoint_name = api_endpoint_property.get('value') or api_endpoint_property.get('default', '')
        if not api_endpoint_name:
            # Fall back to first available API endpoint
            api_endpoints = self.get_api_endpoints()
            api_endpoint_name = api_endpoints[0] if api_endpoints else ''
            api_endpoint_property['default'] = api_endpoint_name
            print(f"[ChatNode] No api_endpoint specified, defaulting to {api_endpoint_name}")

        # Retrieve API details from configuration
        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            print(f"[ChatNode] API interface '{api_endpoint_name}' not found in configuration.")
            return {}

        # Initialize chat history
        chat_history = []

        # Get initial input
        initial_input = inputs.get('input', '').strip()
        if initial_input:
            chat_history.append({'role': 'user', 'content': initial_input})

            # Send initial input to API
            response = self.send_to_api(chat_history, api_details)
            if response:
                chat_history.append({'role': 'assistant', 'content': response})
            else:
                print("[ChatNode] No response from API.")

        # Function to update chat window
        def update_chat_window():
            chat_output_widget.config(state=tk.NORMAL)
            chat_output_widget.delete('1.0', END)
            for message in chat_history:
                role = message['role']
                content = message['content']

                # Insert the role
                chat_output_widget.insert(END, f"{role.capitalize()}:\n", 'role')

                # Apply formatting to the content
                base_tag = f"{role}_content"
                chat_output_widget.mark_set("insert", END)
                apply_formatting(chat_output_widget, content, base_tag=base_tag)

                # Insert a blank line
                chat_output_widget.insert(END, '\n')

            chat_output_widget.config(state=tk.DISABLED)
            chat_output_widget.see(END)  # Scroll to the end

        # Function to handle submit button click
        def submit_input(event=None):
            user_input = user_input_entry.get().strip()
            if user_input:
                chat_history.append({'role': 'user', 'content': user_input})
                user_input_entry.delete(0, END)
                update_chat_window()
                submit_button.config(state=tk.DISABLED)

                # Start a new thread to handle the API request
                threading.Thread(target=handle_api_request).start()

        # Function to handle API request in a separate thread
        def handle_api_request():
            response = self.send_to_api(chat_history, api_details)
            if response:
                chat_history.append({'role': 'assistant', 'content': response})
                chat_output_widget.after(0, update_chat_window)
            else:
                print("[ChatNode] No response from API.")
            submit_button.after(0, lambda: submit_button.config(state=tk.NORMAL))

        # Function to handle closing the chat
        def close_chat():
            self.chat_history_output = '\n'.join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
            root.destroy()

        # Set up the GUI
        root = tk.Tk()
        root.title("Chat")
        root.geometry("500x500")  # Increased initial window height

        # Bind the window close event to close_chat
        root.protocol("WM_DELETE_WINDOW", close_chat)

        # Add a Combobox to select the API endpoint
        api_options = self.get_api_endpoints()
        api_var = tk.StringVar(value=api_endpoint_name)

        def on_api_change(event):
            nonlocal api_details, api_endpoint_name
            new_api_name = api_var.get()
            if new_api_name not in api_options:
                return  # Ignore invalid selections
            api_endpoint_name = new_api_name
            api_details = self.config['interfaces'].get(new_api_name)
            if not api_details:
                print(f"[ChatNode] API interface '{new_api_name}' not found in configuration.")
            else:
                print(f"[ChatNode] Switched to API endpoint: {new_api_name}")
            # Update the node properties with the new selection
            self.properties['api_endpoint']['value'] = new_api_name

        api_dropdown = ttk.Combobox(root, textvariable=api_var, values=api_options, state="readonly")
        api_dropdown.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        api_dropdown.bind("<<ComboboxSelected>>", on_api_change)
        api_dropdown.set(api_endpoint_name)  # Ensure the Combobox displays the current selection

        # Chat output text widget
        chat_output_widget = tk.Text(root, wrap=tk.WORD, state=tk.DISABLED)
        chat_output_widget.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

        # Define tags
        chat_output_widget.tag_configure('role', font=('Helvetica', 10, 'bold'))
        chat_output_widget.tag_configure('user_content', foreground='black')
        chat_output_widget.tag_configure('assistant_content', foreground='dark blue')

        # Frame for input and buttons
        input_frame = tk.Frame(root)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        user_input_entry = tk.Entry(input_frame)
        user_input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        user_input_entry.bind("<Return>", submit_input)  # Bind Enter key to submit_input

        submit_button = tk.Button(input_frame, text="Submit", command=submit_input)
        submit_button.pack(side=tk.LEFT, padx=(0, 5))

        close_button = tk.Button(input_frame, text="Close", command=close_chat)
        close_button.pack(side=tk.LEFT)

        # Initial update of chat window
        update_chat_window()

        root.mainloop()

        # After GUI is closed, output the chat history
        is_end_node = self.properties.get('is_end_node', {}).get('default', False)
        output_key = 'final_output' if is_end_node else 'chat_history'
        return {output_key: self.chat_history_output}

    def send_to_api(self, chat_history, api_details):
        # Prepare the prompt
        prompt = '\n'.join([f"{msg['role']}: {msg['content']}" for msg in chat_history])

        # Call the API
        api_response_content = process_api_request(api_details, prompt)

        if 'error' in api_response_content:
            print(f"[ChatNode] API Error: {api_response_content['error']}")
            return None

        # Extract the response based on API type
        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            response = api_response_content.get('response', 'No response available')
        else:
            response = 'Unsupported API type.'

        return response

    def requires_api_call(self):
        return False  # API call is handled within the node

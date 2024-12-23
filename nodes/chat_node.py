# nodes/chat_node.py
from .base_node import BaseNode
from node_registry import register_node
from api_handler import process_api_request
from db_tools import DatabaseManager
import tkinter as tk
from tkinter import END
from tkinter import ttk
from formatting_utils import apply_formatting
import threading
import re

@register_node('ChatNode')
class ChatNode(BaseNode):
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
                'default': default_api_endpoint
            },
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False},
            'database': {
                'type': 'dropdown',
                'options': self.get_databases(),
                'default': self.get_databases()[0] if self.get_databases() else ''
            },
        })
        return props

    def get_api_endpoints(self):
        interfaces = self.config.get('interfaces', {})
        return list(interfaces.keys())

    def get_databases(self):
        db_manager = DatabaseManager()
        return db_manager.list_databases()

    def process(self, inputs):
        self.chat_history_output = ''
        self.window_closed = False  # Track whether the window is closed
        api_endpoint_property = self.properties.get('api_endpoint', {})
        api_endpoint_name = api_endpoint_property.get('value') or api_endpoint_property.get('default', '')
        if not api_endpoint_name:
            api_endpoints = self.get_api_endpoints()
            api_endpoint_name = api_endpoints[0] if api_endpoints else ''
            api_endpoint_property['default'] = api_endpoint_name

        api_details = self.config['interfaces'].get(api_endpoint_name)
        if not api_details:
            return {}

        database_property = self.properties.get('database', {})
        selected_database = database_property.get('value') or database_property.get('default', '')
        db_manager = DatabaseManager()
        chat_history = []
        initial_input = inputs.get('input', '').strip()
        if initial_input:
            chat_history.append({'role': 'user', 'content': initial_input})
            modified_input = self.prepare_input_with_search(initial_input, db_manager, selected_database)
            response = self.send_to_api(chat_history, modified_input, api_details)
            if response:
                chat_history.append({'role': 'assistant', 'content': response})

        def update_chat_window():
            if not self.window_closed:  # Ensure window is still open before updating UI
                chat_output_widget.config(state=tk.NORMAL)
                chat_output_widget.delete('1.0', END)
                for message in chat_history:
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

        def submit_input(event=None):
            user_input = user_input_text.get('1.0', END).strip()
            if user_input:
                chat_history.append({'role': 'user', 'content': user_input})
                user_input_text.delete('1.0', END)
                update_chat_window()
                submit_button.config(state=tk.DISABLED)
                threading.Thread(target=handle_api_request, args=(user_input,), daemon=True).start()

        def handle_api_request(user_input):
            if self.window_closed:  # Avoid running if window is closed
                return
            modified_input = self.prepare_input_with_search(user_input, db_manager, selected_database)
            if modified_input != user_input:
                chat_history.append({'role': 'system', 'content': modified_input})
                if not self.window_closed:
                    chat_output_widget.after(0, update_chat_window)

            if self.window_closed:  # Avoid processing if window is closed
                return

            response = self.send_to_api(chat_history, modified_input, api_details)
            if response and not self.window_closed:
                chat_history.append({'role': 'assistant', 'content': response})
                chat_output_widget.after(0, update_chat_window)

            if not self.window_closed:
                submit_button.after(0, lambda: submit_button.config(state=tk.NORMAL))

        def close_chat():
            self.window_closed = True  # Mark window as closed
            self.chat_history_output = '\n'.join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
            chat_history.clear()  # Reset chat history
            root.quit()  # Ensure mainloop is exited
            root.destroy()  # Properly destroy the Tkinter window

        root = tk.Tk()
        root.title("Interactive Chat")
        root.geometry("500x700")
        root.protocol("WM_DELETE_WINDOW", close_chat)  # For 'X' button

        api_options = self.get_api_endpoints()
        api_var = tk.StringVar(value=api_endpoint_name)

        def on_api_change(event):
            nonlocal api_details, api_endpoint_name
            new_api_name = api_var.get()
            if new_api_name not in api_options:
                return
            api_endpoint_name = new_api_name
            api_details = self.config['interfaces'].get(new_api_name)
            self.properties['api_endpoint']['value'] = new_api_name

        api_dropdown = ttk.Combobox(root, textvariable=api_var, values=api_options, state="readonly")
        api_dropdown.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        api_dropdown.bind("<<ComboboxSelected>>", on_api_change)
        api_dropdown.set(api_endpoint_name)

        db_options = self.get_databases()
        db_var = tk.StringVar(value=selected_database)

        def on_db_change(event):
            nonlocal selected_database
            new_db = db_var.get()
            if new_db not in db_options:
                return
            selected_database = new_db
            self.properties['database']['value'] = new_db

        db_dropdown = ttk.Combobox(root, textvariable=db_var, values=db_options, state="readonly")
        db_dropdown.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        db_dropdown.bind("<<ComboboxSelected>>", on_db_change)
        db_dropdown.set(selected_database)

        chat_output_widget = tk.Text(root, wrap=tk.WORD, state=tk.DISABLED)
        chat_output_widget.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        chat_output_widget.tag_configure('role', font=('Helvetica', 10, 'bold'))
        chat_output_widget.tag_configure('system', font=('Helvetica', 10, 'italic'), foreground='green')
        chat_output_widget.tag_configure('user_content', foreground='black')
        chat_output_widget.tag_configure('assistant_content', foreground='dark blue')
        chat_output_widget.tag_configure('system_content', foreground='dark green')

        # Adjusted input_frame layout
        input_frame = tk.Frame(root)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        user_input_text = tk.Text(input_frame, height=4)
        user_input_text.pack(side=tk.TOP, fill=tk.X, expand=True, padx=(0, 5), pady=(0, 5))

        # Bind Ctrl+Enter to submit the input
        user_input_text.bind("<Control-Return>", submit_input)

        # Buttons frame
        buttons_frame = tk.Frame(input_frame)
        buttons_frame.pack(side=tk.BOTTOM, fill=tk.X)

        submit_button = tk.Button(buttons_frame, text="Submit", command=submit_input)
        submit_button.pack(side=tk.TOP, fill=tk.X, padx=(0, 5), pady=(0, 5))

        close_button = tk.Button(buttons_frame, text="Close", command=close_chat)  # Close button uses close_chat
        close_button.pack(side=tk.TOP, fill=tk.X, padx=(0, 5))

        update_chat_window()
        root.mainloop()

        is_end_node = self.properties.get('is_end_node', {}).get('default', False)
        output_key = 'final_output' if is_end_node else 'chat_history'
        return {output_key: self.chat_history_output}

    def prepare_input_with_search(self, user_input, db_manager, selected_database):
        pattern = r'/doc\s+(.+)'
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            search_query = match.group(1).strip()
            if search_query:
                results = db_manager.search(selected_database, search_query, top_k=3)
                if results:
                    search_results = "\n".join([
                        f"Document: {res['source']}\nSimilarity Score: {res['similarity']:.4f}\nContent: {res['content']}\n"
                        for res in results
                    ])
                    modified_input = re.sub(pattern, '', user_input).strip()
                    combined_input = f"Search Results for '{search_query}':\n{search_results}"
                    return combined_input
        return user_input

    def send_to_api(self, chat_history, combined_input, api_details):
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
        api_response_content = process_api_request(api_details, prompt)
        if 'error' in api_response_content:
            return None

        api_type = api_details.get('api_type')
        if api_type == "OpenAI":
            return api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
        elif api_type == "Ollama":
            if isinstance(api_response_content, dict):
                message = api_response_content.get('message', {})
                return message.get('content', 'No response available')
            elif isinstance(api_response_content, str):
                return api_response_content
            else:
                return 'No response available'

    def requires_api_call(self):
        return False

import sys
import subprocess
import os

def install(package):
    """Install a package using pip."""
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def check_dependencies():
    """
    Check for required dependencies and install any that are missing.
    For non-pip-installable packages like tkinter, notify the user.
    """
    dependencies = {
        'requests': 'requests',
        'yaml': 'PyYAML',
        'ollama': 'ollama',  # Needed for Client
        'pygments': 'Pygments',  # For syntax highlighting
    }

    for module, package in dependencies.items():
        try:
            __import__(module)
        except ImportError:
            print(f"Dependency '{package}' not found. Installing...")
            try:
                install(package)
                print(f"'{package}' installed successfully.")
            except subprocess.CalledProcessError:
                print(f"Failed to install '{package}'. Please install it manually.")
                sys.exit(1)

    # Check for tkinter separately as it cannot be installed via pip
    try:
        import tkinter
    except ImportError:
        print("The 'tkinter' module is not installed.")
        print("Please install it manually:")
        if sys.platform.startswith('linux'):
            print("For Debian/Ubuntu: sudo apt-get install python3-tk")
            print("For Fedora: sudo dnf install python3-tkinter")
            print("For Arch: sudo pacman -S tk")
        elif sys.platform == 'darwin':
            print("For macOS with Homebrew: brew install python-tk")
        elif sys.platform == 'win32':
            print("Please ensure that Tkinter is included in your Python installation.")
        sys.exit(1)

# Perform dependency check before importing other modules
check_dependencies()

import tkinter as tk
from tkinter import ttk, messagebox, Menu, Toplevel, Label, Entry, Button, Scrollbar, END, SINGLE
import requests
import yaml
import threading
import uuid
import math
import re  # For parsing markdown-like formatting
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

# Import NodeEditor module
# Ensure that you have a module named 'node_editor.py' in the same directory or adjust the import accordingly
from node_editor import NodeEditor

from ollama import Client

def load_config(config_file='config.yaml'):
    """Load configuration from a YAML file."""
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        config = {'interfaces': {}, 'seed_prompts': []}

    # Ensure seed_prompts is a list
    if 'seed_prompts' not in config or not isinstance(config['seed_prompts'], list):
        config['seed_prompts'] = []

    return config

def save_config(config, config_file='config.yaml'):
    """Save the updated config to the YAML file."""
    with open(config_file, 'w') as file:
        yaml.safe_dump(config, file)

# Initialize a dictionary to keep track of open NodeEditor instances
open_editors = {}

def add_instruction_prompt(config, chat_instruction_listbox):
    """Add a new instruction prompt using NodeEditor."""
    def on_save(editor):
        graph_data = editor.get_configured_graph()
        name = editor.get_instruction_name()
        if graph_data and name:
            # Check for duplicate names
            if any(item['name'] == name for item in config['seed_prompts']):
                messagebox.showerror("Error", "An instruction prompt with this name already exists.")
                return
            config['seed_prompts'].append({'name': name, 'graph': graph_data})
            save_config(config)
            chat_instruction_listbox.insert(END, name)
            messagebox.showinfo("Success", "New instruction prompt added.")

    def on_close(editor):
        # Remove editor from open_editors if it's there
        if editor.instruction_name in open_editors:
            del open_editors[editor.instruction_name]

    editor = NodeEditor(root, config, config['interfaces'], save_callback=on_save, close_callback=on_close)
    # For new prompts, we can't assign a name yet; skip adding to open_editors

def edit_instruction_prompt(config, chat_instruction_listbox):
    """Edit an existing instruction prompt using NodeEditor."""
    selected_indices = chat_instruction_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("Selection Required", "Please select an instruction prompt to edit.")
        return
    index = selected_indices[0]
    selected_item = config['seed_prompts'][index]
    selected_name = selected_item['name']
    graph_data = selected_item.get('graph', {})

    def on_save(editor):
        new_graph_data = editor.get_configured_graph()
        new_name = editor.get_instruction_name()
        if new_graph_data and new_name:
            # Check for duplicate names (if name has changed)
            if new_name != selected_name and any(item['name'] == new_name for item in config['seed_prompts']):
                messagebox.showerror("Error", "An instruction prompt with this name already exists.")
                return
            config['seed_prompts'][index] = {'name': new_name, 'graph': new_graph_data}
            save_config(config)
            chat_instruction_listbox.delete(index)
            chat_instruction_listbox.insert(index, new_name)
            messagebox.showinfo("Success", "Instruction prompt updated.")
            # Update open_editors with the new name
            if selected_name in open_editors:
                open_editors[new_name] = open_editors.pop(selected_name)
                open_editors[new_name].instruction_name = new_name

    def on_close(editor):
        # Remove editor from open_editors if it's there
        if editor.instruction_name in open_editors:
            del open_editors[editor.instruction_name]

    editor = NodeEditor(root, config, config['interfaces'], existing_graph=graph_data, existing_name=selected_name, save_callback=on_save, close_callback=on_close)
    open_editors[selected_name] = editor

def delete_instruction_prompt(config, chat_instruction_listbox):
    """Delete an existing instruction prompt."""
    selected_indices = chat_instruction_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("Selection Required", "Please select an instruction prompt to delete.")
        return
    index = selected_indices[0]
    selected_prompt = config['seed_prompts'][index]
    selected_name = selected_prompt['name']
    confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the instruction prompt '{selected_name}'?")
    if confirm:
        config['seed_prompts'].pop(index)
        save_config(config)
        chat_instruction_listbox.delete(index)
        # Close the editor if it's open
        if selected_name in open_editors:
            open_editors[selected_name].editor_window.destroy()
            del open_editors[selected_name]
        messagebox.showinfo("Success", f"Instruction prompt '{selected_name}' has been deleted.")

def manage_apis(config):
    """Manage APIs (Add/Edit/Delete) in a separate window."""
    manage_window = Toplevel()
    manage_window.title("Manage APIs")
    manage_window.geometry("250x400")
    manage_window.resizable(True, True)

    # Frame for API Listbox
    api_manage_frame = ttk.Frame(manage_window)
    api_manage_frame.pack(padx=10, pady=10, fill='both', expand=True)

    api_manage_scrollbar = Scrollbar(api_manage_frame)
    api_manage_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    api_manage_listbox = tk.Listbox(api_manage_frame, selectmode=SINGLE, yscrollcommand=api_manage_scrollbar.set, width=50, height=15, exportselection=False)
    for key in config['interfaces']:
        api_manage_listbox.insert(END, key)
    api_manage_listbox.pack(side=tk.LEFT, fill='both', expand=True)
    api_manage_scrollbar.config(command=api_manage_listbox.yview)

    # Frame for Add, Edit, Delete buttons
    api_manage_buttons_frame = ttk.Frame(manage_window)
    api_manage_buttons_frame.pack(pady=10)

    add_api_button = ttk.Button(api_manage_buttons_frame, text="Add", width=10, command=lambda: add_api_interface_manage(config, api_manage_listbox))
    add_api_button.grid(row=0, column=0, padx=5)

    edit_api_button = ttk.Button(api_manage_buttons_frame, text="Edit", width=10, command=lambda: edit_api_interface_manage(config, api_manage_listbox))
    edit_api_button.grid(row=0, column=1, padx=5)

    delete_api_button = ttk.Button(api_manage_buttons_frame, text="Delete", width=10, command=lambda: delete_api_interface_manage(config, api_manage_listbox))
    delete_api_button.grid(row=0, column=2, padx=5)

def fetch_models(api_url, api_key, api_type):
    """Fetch available models from the provided API URL using the API key and API type."""
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        if api_type == "OpenAI":
            response = requests.get(api_url.rstrip('/') + "/v1/models", headers=headers)
            if response.status_code == 200:
                models = response.json()
                model_names = [model['id'] for model in models['data']]
                return model_names
            else:
                print(f"Error fetching models: {response.status_code} - {response.text}")
                return []
        elif api_type == "Ollama":
            response = requests.get(api_url.rstrip('/') + "/api/tags", headers=headers)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [model['name'] for model in models]
                return model_names
            else:
                print(f"Error fetching models: {response.status_code} - {response.text}")
                return []
        else:
            messagebox.showerror("Error", f"Unsupported API Type '{api_type}'.")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

def add_api_interface_manage(config, api_manage_listbox):
    """Add a new API interface from Manage APIs window."""
    def save_new_interface():
        name = name_entry.get().strip()
        url = url_entry.get().strip()
        api_key = api_key_entry.get().strip()
        model = model_dropdown.get().strip()  # Use model from dropdown
        max_tokens = max_tokens_entry.get().strip()
        api_type = api_type_dropdown.get().strip()

        if not name or not url or not model or not api_type:
            messagebox.showwarning("Input Required", "Please fill in all required fields.")
            return

        if name in config['interfaces']:
            messagebox.showerror("Error", "An API Interface with this name already exists.")
            return

        # Update models endpoint based on API type
        if api_type == "OpenAI":
            models_endpoint = "/v1/chat/completions"
        elif api_type == "Ollama":
            models_endpoint = "/api/tags"
        else:
            messagebox.showerror("Error", f"Unsupported API Type '{api_type}'.")
            return

        config['interfaces'][name] = {
            'url': url,
            'api_key': api_key,
            'model': model,
            'models_endpoint': models_endpoint,
            'api_type': api_type,
            'max_tokens': int(max_tokens) if max_tokens else None
        }
        save_config(config)
        api_manage_listbox.insert(END, name)
        add_window.destroy()
        messagebox.showinfo("Success", "New API Interface added.")

    def update_models_dropdown():
        """Fetch models from the provided API URL and update the model dropdown."""
        api_url = url_entry.get().strip()
        api_key = api_key_entry.get().strip()
        api_type = api_type_dropdown.get().strip()

        if not api_url or not api_type:
            messagebox.showwarning("Input Required", "Please enter URL and select API Type.")
            return

        if api_type == "OpenAI" and not api_key:
            messagebox.showwarning("Input Required", "API Key is required for OpenAI API.")
            return

        models = fetch_models(api_url, api_key, api_type)

        if models:
            model_dropdown['values'] = models
            if len(models) == 1:
                model_dropdown.set(models[0])
            else:
                model_dropdown.set('')
        else:
            messagebox.showerror("Error", "Failed to fetch models. Check the URL, API key, or network connection.")

    add_window = Toplevel()
    add_window.title("Add New API Interface")
    add_window.geometry("600x500")
    add_window.resizable(True, True)

    Label(add_window, text="Name:").pack(pady=5)
    name_entry = Entry(add_window, width=60)
    name_entry.pack(pady=5)

    Label(add_window, text="URL:").pack(pady=5)
    url_entry = Entry(add_window, width=60)
    url_entry.pack(pady=5)

    Label(add_window, text="API Key (Optional):").pack(pady=5)
    api_key_entry = Entry(add_window, width=60, show='*')
    api_key_entry.pack(pady=5)

    Label(add_window, text="API Type:").pack(pady=5)
    api_type_dropdown = ttk.Combobox(add_window, values=["OpenAI", "Ollama"], state="readonly", width=60)
    api_type_dropdown.set("OpenAI")  # Default to OpenAI
    api_type_dropdown.pack(pady=5)

    # Add a button to fetch models once API Key and URL are entered
    fetch_models_button = Button(add_window, text="Fetch Models", command=update_models_dropdown)
    fetch_models_button.pack(pady=5)

    Label(add_window, text="Model:").pack(pady=5)
    model_dropdown = ttk.Combobox(add_window, state="readonly", width=60)
    model_dropdown.pack(pady=5)

    Label(add_window, text="Max Tokens (Optional):").pack(pady=5)
    max_tokens_entry = Entry(add_window, width=60)
    max_tokens_entry.pack(pady=5)

    save_button = Button(add_window, text="Save", command=save_new_interface)
    save_button.pack(pady=20)

def edit_api_interface_manage(config, api_manage_listbox):
    """Edit an existing API interface from Manage APIs window."""
    selected_indices = api_manage_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("Selection Required", "Please select an API Interface to edit.")
        return
    index = selected_indices[0]
    selected_interface = api_manage_listbox.get(index)
    interface_details = config['interfaces'][selected_interface]

    def save_edited_interface():
        new_name = name_entry.get().strip()
        new_url = url_entry.get().strip()
        new_api_key = api_key_entry.get().strip()
        new_model = model_dropdown.get().strip()
        new_max_tokens = max_tokens_entry.get().strip()
        new_api_type = api_type_dropdown.get().strip()

        if not new_name or not new_url or not new_model or not new_api_type:
            messagebox.showwarning("Input Required", "Please fill in all required fields.")
            return

        if new_name != selected_interface and new_name in config['interfaces']:
            messagebox.showerror("Error", "An API Interface with this name already exists.")
            return

        # Determine models_endpoint based on API type
        if new_api_type == "OpenAI":
            new_models_endpoint = "/v1/chat/completions"
        elif new_api_type == "Ollama":
            new_models_endpoint = "/api/tags"
        else:
            messagebox.showerror("Error", "Unsupported API Type selected.")
            return

        # Update the interface
        config['interfaces'].pop(selected_interface)
        config['interfaces'][new_name] = {
            'url': new_url,
            'api_key': new_api_key,
            'model': new_model,
            'models_endpoint': new_models_endpoint,
            'api_type': new_api_type,
            'max_tokens': int(new_max_tokens) if new_max_tokens else None
        }
        save_config(config)
        api_manage_listbox.delete(index)
        api_manage_listbox.insert(index, new_name)
        edit_window.destroy()
        messagebox.showinfo("Success", "API Interface updated successfully.")

    def update_models_dropdown():
        """Fetch models from the provided API URL and update the model dropdown."""
        api_url = url_entry.get().strip()
        api_key = api_key_entry.get().strip()
        api_type = api_type_dropdown.get().strip()

        if not api_url or not api_type:
            messagebox.showwarning("Input Required", "Please enter URL and select API Type.")
            return

        if api_type == "OpenAI" and not api_key:
            messagebox.showwarning("Input Required", "API Key is required for OpenAI API.")
            return

        models = fetch_models(api_url, api_key, api_type)

        if models:
            model_dropdown['values'] = models
            if interface_details.get('model') in models:
                model_dropdown.set(interface_details.get('model'))
            else:
                model_dropdown.set('')
        else:
            messagebox.showerror("Error", "Failed to fetch models. Check the URL, API key, or network connection.")

    edit_window = Toplevel()
    edit_window.title("Edit API Interface")
    edit_window.geometry("600x500")
    edit_window.resizable(True, True)

    Label(edit_window, text="Name:").pack(pady=5)
    name_entry = Entry(edit_window, width=60)
    name_entry.pack(pady=5)
    name_entry.insert(0, selected_interface)

    Label(edit_window, text="URL:").pack(pady=5)
    url_entry = Entry(edit_window, width=60)
    url_entry.pack(pady=5)
    url_entry.insert(0, interface_details['url'])

    Label(edit_window, text="API Key (Optional):").pack(pady=5)
    api_key_entry = Entry(edit_window, width=60, show='*')
    api_key_entry.pack(pady=5)
    api_key_entry.insert(0, interface_details.get('api_key', ''))

    Label(edit_window, text="API Type:").pack(pady=5)
    api_type_dropdown = ttk.Combobox(edit_window, values=["OpenAI", "Ollama"], state="readonly", width=60)
    api_type_dropdown.set(interface_details.get('api_type', 'OpenAI'))  # Default to OpenAI
    api_type_dropdown.pack(pady=5)

    # Add a button to fetch models once API Key and URL are entered
    fetch_models_button = Button(edit_window, text="Fetch Models", command=update_models_dropdown)
    fetch_models_button.pack(pady=5)

    Label(edit_window, text="Model:").pack(pady=5)
    model_dropdown = ttk.Combobox(edit_window, state="readonly", width=60)
    model_dropdown.pack(pady=5)

    Label(edit_window, text="Max Tokens (Optional):").pack(pady=5)
    max_tokens_entry = Entry(edit_window, width=60)
    max_tokens_entry.pack(pady=5)
    max_tokens_entry.insert(0, str(interface_details.get('max_tokens', '')))

    save_button = Button(edit_window, text="Save", command=save_edited_interface)
    save_button.pack(pady=20)

    # Set initial values
    update_models_dropdown()
    # Set the model if it's available
    if interface_details.get('model'):
        model_dropdown.set(interface_details.get('model'))

def delete_api_interface_manage(config, api_manage_listbox):
    """Delete an existing API interface from Manage APIs window."""
    selected_indices = api_manage_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("Selection Required", "Please select an API Interface to delete.")
        return
    index = selected_indices[0]
    selected_interface = api_manage_listbox.get(index)
    confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the API Interface '{selected_interface}'?")
    if confirm:
        config['interfaces'].pop(selected_interface)
        save_config(config)
        api_manage_listbox.delete(index)
        messagebox.showinfo("Success", f"API Interface '{selected_interface}' has been deleted.")

def send_openai_request(api_url, headers, data):
    """Send request to OpenAI API with logging."""
    try:
        # Log the request details
        print(f"Sending request to OpenAI API at {api_url}")
        print(f"Request Headers: {headers}")
        print(f"Request Payload: {data}")

        response = requests.post(api_url, json=data, headers=headers)

        if response.status_code == 200:
            print("Response received from OpenAI API")
            return response.json()['choices'][0]['message']['content']
        else:
            raise Exception(f"Error: {response.status_code}\n{response.text}")
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        messagebox.showerror("Error", str(e))
        return ""

def send_ollama_request(client, model, messages):
    """Send request to Ollama API with logging."""
    try:
        # Log the request details
        print(f"Sending request to Ollama API with model {model}")
        print(f"Request Messages: {messages}")

        response = client.chat(model=model, messages=messages)
        print("Response received from Ollama API")
        return response['message']['content']
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        messagebox.showerror("Error", str(e))
        return ""

def apply_formatting(text_widget, text):
    """
    Parses markdown-like syntax in the text and applies formatting tags to the Text widget.

    Supported formats:
    - Headings: # Heading 1, ## Heading 2, etc.
    - Bold: **bold text**
    - Italic: *italic text*
    - Bullet points: - item, * item, + item
    - Code blocks: ```language\ncode\n```
    """
    # Clear existing text
    text_widget.config(state=tk.NORMAL)
    text_widget.delete('1.0', END)

    # Define tags for formatting
    text_widget.tag_configure("heading1", font=("Helvetica", 16, "bold"))
    text_widget.tag_configure("heading2", font=("Helvetica", 14, "bold"))
    text_widget.tag_configure("heading3", font=("Helvetica", 12, "bold"))
    text_widget.tag_configure("bold", font=("Helvetica", 12, "bold"))
    text_widget.tag_configure("italic", font=("Helvetica", 12, "italic"))
    text_widget.tag_configure("code", font=("Courier", 12), background="#f0f0f0")
    text_widget.tag_configure("bullet", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("numbered", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("blockquote", lmargin1=25, lmargin2=25, foreground="#555555")

    # Additional tags for syntax highlighting in code blocks
    text_widget.tag_configure("keyword", foreground="#0000FF")
    text_widget.tag_configure("string", foreground="#008000")
    text_widget.tag_configure("comment", foreground="#808080")
    text_widget.tag_configure("operator", foreground="#FF00FF")

    # Regular expressions
    code_block_pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    heading_pattern = re.compile(r'^(#{1,6})\s*(.*)$', re.MULTILINE)
    bold_pattern = re.compile(r'\*\*(.*?)\*\*')
    italic_pattern = re.compile(r'\*(?!\*)(.*?)\*')

    bullet_pattern = re.compile(r'^(\s*[-*+])\s+(.*)$', re.MULTILINE)
    numbered_pattern = re.compile(r'^(\s*\d+\.)\s+(.*)$', re.MULTILINE)
    blockquote_pattern = re.compile(r'^>\s+(.*)$', re.MULTILINE)

    # Split the text into code blocks and other text
    def split_text(text):
        # This function splits the text into segments, separating code blocks
        segments = []
        pos = 0
        for match in code_block_pattern.finditer(text):
            start, end = match.span()
            # Text before the code block
            if start > pos:
                segments.append(('text', text[pos:start]))
            # The code block
            segments.append(('code', match.group()))
            pos = end
        # Any remaining text after the last code block
        if pos < len(text):
            segments.append(('text', text[pos:]))
        return segments

    # Define process_inline_formatting before it's used
    def process_inline_formatting(text_widget, text_line):
        """
        Processes a line of text for inline formatting like bold and italic.
        """
        pos = 0
        while pos < len(text_line):
            bold_match = bold_pattern.search(text_line, pos)
            italic_match = italic_pattern.search(text_line, pos)
            next_match = None
            if bold_match and italic_match:
                if bold_match.start() <= italic_match.start():
                    next_match = ('bold', bold_match)
                else:
                    next_match = ('italic', italic_match)
            elif bold_match:
                next_match = ('bold', bold_match)
            elif italic_match:
                next_match = ('italic', italic_match)

            if next_match:
                tag_type, match = next_match
                # Text before the match
                if match.start() > pos:
                    text_widget.insert(END, text_line[pos:match.start()])
                # Matched text
                text_widget.insert(END, match.group(1), tag_type)
                pos = match.end()
            else:
                # No more formatting
                text_widget.insert(END, text_line[pos:])
                break

    # Define create_copy_button before it's used
    def create_copy_button(code_text):
        def copy_code():
            root.clipboard_clear()
            root.clipboard_append(code_text)
            messagebox.showinfo("Copied", "Code block copied to clipboard.")
        return Button(text_widget, text="Copy Code", command=copy_code)

    segments = split_text(text)

    for segment_type, segment_text in segments:
        if segment_type == 'text':
            # Process the text for headings, bold, italic, etc.
            lines = segment_text.split('\n')
            for line in lines:
                # Check for heading
                heading_match = heading_pattern.match(line)
                if heading_match:
                    level = len(heading_match.group(1))
                    content = heading_match.group(2)
                    tag = f"heading{level}" if level <=3 else "heading3"
                    text_widget.insert(END, content + '\n', tag)
                    continue
                # Check for bullet points
                bullet_match = bullet_pattern.match(line)
                if bullet_match:
                    content = bullet_match.group(2)
                    text_widget.insert(END, u'\u2022 ' + content + '\n', "bullet")
                    continue
                # Check for numbered list
                numbered_match = numbered_pattern.match(line)
                if numbered_match:
                    content = numbered_match.group(2)
                    text_widget.insert(END, numbered_match.group(1) + ' ' + content + '\n', "numbered")
                    continue
                # Check for blockquote
                blockquote_match = blockquote_pattern.match(line)
                if blockquote_match:
                    content = blockquote_match.group(1)
                    text_widget.insert(END, content + '\n', "blockquote")
                    continue
                # Process inline formatting for the line
                process_inline_formatting(text_widget, line)
                text_widget.insert(END, '\n')
        elif segment_type == 'code':
            code_match = code_block_pattern.match(segment_text)
            if code_match:
                language = code_match.group(1)
                code_content = code_match.group(2)
                # Insert the "Copy Code" button
                copy_button = create_copy_button(code_content)
                text_widget.window_create(END, window=copy_button)
                text_widget.insert(END, "\n")
                # Insert the code block with syntax highlighting
                lexer = get_lexer_by_name(language, stripall=True) if language else TextLexer()
                tokens = lex(code_content, lexer)
                for ttype, value in tokens:
                    if ttype in Token.Keyword:
                        tag = "keyword"
                    elif ttype in Token.String:
                        tag = "string"
                    elif ttype in Token.Comment:
                        tag = "comment"
                    elif ttype in Token.Operator:
                        tag = "operator"
                    else:
                        tag = "code"
                    text_widget.insert(END, value, tag)
                text_widget.insert(END, "\n")
    text_widget.config(state=tk.DISABLED)

def submit_request(config, selected_prompt_index, user_input, output_box, submit_button, stop_button, chat_tab, chat_instruction_listbox):
    """Handle submitting the request."""
    if not user_input.strip():
        messagebox.showwarning("Input Required", "Please enter some text in the input box.")
        return

    # Always assume that an Instruction Prompt is selected
    if selected_prompt_index is None:
        messagebox.showerror("Error", "Please select an instruction prompt from the list.")
        return
    # Retrieve the node graph based on the selected index
    selected_prompt = config['seed_prompts'][selected_prompt_index]
    node_graph = selected_prompt.get('graph', None)
    if not node_graph:
        messagebox.showerror("Error", "Selected instruction prompt is not properly configured.")
        return
    # We will process the node graph using the APIs specified in the nodes
    api_details = None

    # Get the selected prompt name
    selected_prompt_name = chat_tab.selected_prompt_name

    # Reset the stop_event
    chat_tab.stop_event.clear()

    # Disable the submit button and enable the stop button
    submit_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)

    # Use threading to avoid blocking the GUI while making API requests
    thread = threading.Thread(target=process_node_graph, args=(
        config, api_details, user_input, output_box, submit_button, stop_button, chat_tab.stop_event,
        node_graph, selected_prompt_name))
    thread.start()

def process_node_graph(config, default_api_details, user_input, output_box, submit_button, stop_button, stop_event, node_graph, selected_prompt_name):
    """Process the node graph and execute the instructions."""
    try:
        if not node_graph:
            # No instruction prompts, proceed to send the request directly
            if not default_api_details:
                messagebox.showerror("Error", "No API interface specified.")
                return
            api_type = default_api_details.get('api_type', 'OpenAI')
            model = default_api_details['model']
            max_tokens = default_api_details.get('max_tokens', 100)
            messages = [{"role": "user", "content": user_input}]

            if api_type == "OpenAI":
                api_url = default_api_details['url'].rstrip('/') + default_api_details['models_endpoint']
                headers = {
                    'Authorization': f'Bearer {default_api_details.get("api_key", "")}',
                    'Content-Type': 'application/json'
                }
                data = {
                    'model': model,
                    'messages': messages,
                    'max_tokens': max_tokens
                }
                response = send_openai_request(api_url, headers, data)
            else:
                client = Client(host=default_api_details['url'])
                response = send_ollama_request(client, model, messages)

            # Apply formatting and display the response
            root.after(0, lambda: apply_formatting(output_box, response))
        else:
            # Process the node graph
            nodes = node_graph['nodes']
            connections = node_graph['connections']

            # Create a lookup for nodes by id
            node_lookup = {nid: node for nid, node in nodes.items()}

            # Find the Start Node
            start_node = next((node for node in nodes.values() if node['type'] == 'Start'), None)
            if not start_node:
                messagebox.showerror("Error", "No Start Node found in the instruction prompt.")
                return

            current_node = start_node
            input_data = user_input
            response = None

            # Get the editor if it's open
            editor = open_editors.get(selected_prompt_name)

            while True:
                if stop_event.is_set():
                    # Exiting due to stop request
                    print("Process was stopped by the user.")
                    return

                # Highlight the current node in the editor if it's open
                if editor and editor.is_open():
                    node_id = current_node['id']
                    # Schedule the highlight on the main thread
                    root.after(0, lambda nid=node_id: editor.highlight_node(nid))

                # Get API details for the node
                api_name = current_node.get('api')
                api_details = config['interfaces'].get(api_name)
                if not api_details:
                    messagebox.showerror("Error", f"API Interface '{api_name}' not found.")
                    return

                api_type = api_details.get('api_type', 'OpenAI')
                model = api_details['model']
                max_tokens = api_details.get('max_tokens', 100)

                # Prepare messages
                prompt = current_node['prompt'] + "\n" + input_data
                messages = [{"role": "user", "content": prompt}]

                if stop_event.is_set():
                    # Exiting due to stop request
                    print("Process was stopped by the user.")
                    return

                # Send request
                if api_type == "OpenAI":
                    api_url = api_details['url'].rstrip('/') + api_details['models_endpoint']
                    headers = {
                        'Authorization': f'Bearer {api_details.get("api_key", "")}',
                        'Content-Type': 'application/json'
                    }
                    data = {
                        'model': model,
                        'messages': messages,
                        'max_tokens': max_tokens
                    }
                    response = send_openai_request(api_url, headers, data)
                else:
                    client = Client(host=api_details['url'])
                    response = send_ollama_request(client, model, messages)

                if stop_event.is_set():
                    # Exiting due to stop request
                    print("Process was stopped by the user.")
                    return

                # Determine next node based on test criteria
                test_criteria = current_node.get('test_criteria', '').strip()
                if test_criteria:
                    # Test criteria is specified
                    if test_criteria in response:
                        # Move to the node connected to True output
                        next_conn = next((conn for conn in connections if conn['from_node'] == current_node['id'] and conn['from_output'] == 'true'), None)
                        if not next_conn:
                            # No True output connection; try False output
                            next_conn = next((conn for conn in connections if conn['from_node'] == current_node['id'] and conn['from_output'] == 'false'), None)
                    else:
                        # Move to the node connected to False output
                        next_conn = next((conn for conn in connections if conn['from_node'] == current_node['id'] and conn['from_output'] == 'false'), None)
                        if not next_conn:
                            # No False output connection; try True output
                            next_conn = next((conn for conn in connections if conn['from_node'] == current_node['id'] and conn['from_output'] == 'true'), None)
                else:
                    # No test criteria; proceed to True output by default
                    next_conn = next((conn for conn in connections if conn['from_node'] == current_node['id'] and conn['from_output'] == 'true'), None)
                    if not next_conn:
                        # No True output; try False output
                        next_conn = next((conn for conn in connections if conn['from_node'] == current_node['id'] and conn['from_output'] == 'false'), None)

                if not next_conn:
                    # No further nodes; check if current node is connected to Finish Node
                    finish_node_connected = any(
                        node_lookup.get(conn['to_node'])['type'] == 'Finish'
                        for conn in connections if conn['from_node'] == current_node['id']
                    )
                    if finish_node_connected:
                        # Reached Finish Node
                        break
                    else:
                        # No connected nodes; exit loop
                        break

                next_node = node_lookup.get(next_conn['to_node'])
                if not next_node:
                    messagebox.showerror("Error", "Next node not found in the graph.")
                    return

                if next_node['type'] == 'Finish':
                    # Reached Finish Node
                    break

                # Prepare for next iteration
                current_node = next_node
                input_data = response

            # Apply formatting and display the final response
            final_response = response if response else "No response generated."
            root.after(0, lambda: apply_formatting(output_box, final_response))
    finally:
        # Re-enable the submit button and disable the stop button
        root.after(0, lambda: [submit_button.config(state=tk.NORMAL), stop_button.config(state=tk.DISABLED)])

def stop_process(chat_tab):
    """Stop the ongoing process."""
    if hasattr(chat_tab, 'stop_event'):
        chat_tab.stop_event.set()
        # Disable the Stop Process button to prevent multiple clicks
        chat_tab.stop_button.config(state=tk.DISABLED)
        print("Stop process requested by the user.")

def create_gui(config):
    """Create and run the GUI."""
    # Create the main window
    global root
    root = tk.Tk()
    root.title("LLM Requester")
    root.geometry("400x500")  # Increased size to accommodate buttons and layout
    root.minsize(400, 500)  # Set minimum size

    # Create a Notebook (tabbed interface)
    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True)

    # ------------------ Chat Tab ------------------
    chat_tab = ttk.Frame(notebook)
    notebook.add(chat_tab, text='Chat')

    # Initialize stop_event and stop_button
    chat_tab.stop_event = threading.Event()

    # Create a frame for the Instruction Prompt selection
    instruction_selection_frame = ttk.Frame(chat_tab)
    instruction_selection_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nw")  # Align to top-left

    # Instruction Prompt Selection in Chat Tab
    instruction_label = ttk.Label(instruction_selection_frame, text="Select Instruction Prompt:")
    instruction_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    chat_instruction_frame = ttk.Frame(instruction_selection_frame)
    chat_instruction_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")  # Changed to 'ew' for horizontal expansion

    chat_instruction_scrollbar = Scrollbar(chat_instruction_frame)
    chat_instruction_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    chat_instruction_listbox = tk.Listbox(chat_instruction_frame, selectmode=SINGLE, yscrollcommand=chat_instruction_scrollbar.set, height=5, exportselection=False)
    for item in config['seed_prompts']:
        chat_instruction_listbox.insert(END, item['name'])
    chat_instruction_listbox.pack(side=tk.LEFT, fill='both', expand=True)  # Changed to fill='both' for dynamic resizing
    chat_instruction_scrollbar.config(command=chat_instruction_listbox.yview)

    # Add Instruction Prompt Management Buttons beneath the Instruction listbox
    instruction_buttons_frame = ttk.Frame(instruction_selection_frame)
    instruction_buttons_frame.grid(row=2, column=0, padx=5, pady=5, sticky="w")

    add_instruction_button = ttk.Button(instruction_buttons_frame, text="Add", width=5, command=lambda: add_instruction_prompt(config, chat_instruction_listbox))
    add_instruction_button.pack(side=tk.LEFT, padx=2)

    edit_instruction_button = ttk.Button(instruction_buttons_frame, text="Edit", width=5, command=lambda: edit_instruction_prompt(config, chat_instruction_listbox))
    edit_instruction_button.pack(side=tk.LEFT, padx=2)

    delete_instruction_button = ttk.Button(instruction_buttons_frame, text="Delete", width=5, command=lambda: delete_instruction_prompt(config, chat_instruction_listbox))
    delete_instruction_button.pack(side=tk.LEFT, padx=2)

    # Handle selection to store selected prompt index and name
    def on_select_chat_instruction(event):
        selected_indices = chat_instruction_listbox.curselection()
        if selected_indices:
            index = selected_indices[0]
            selected_name = chat_instruction_listbox.get(index)
            chat_tab.selected_prompt_index = index  # Store the index
            chat_tab.selected_prompt_name = selected_name  # Store the name
        else:
            chat_tab.selected_prompt_index = None
            chat_tab.selected_prompt_name = None

    chat_instruction_listbox.bind('<<ListboxSelect>>', on_select_chat_instruction)
    chat_tab.selected_prompt_index = None  # Initialize attribute
    chat_tab.selected_prompt_name = None  # Initialize attribute

    # Input Text Box
    input_label = ttk.Label(chat_tab, text="Enter your prompt:")
    input_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")

    input_box = tk.Text(chat_tab, height=8)
    input_box.grid(row=4, column=0, padx=5, pady=5, sticky="ew")

    # Create a frame for Submit, Stop Process, and Clear All buttons
    buttons_frame = ttk.Frame(chat_tab)
    buttons_frame.grid(row=5, column=0, columnspan=2, padx=5, pady=10, sticky='ew')

    # Configure the frame's grid to have three equally weighted columns
    buttons_frame.columnconfigure(0, weight=1)
    buttons_frame.columnconfigure(1, weight=1)
    buttons_frame.columnconfigure(2, weight=1)

    # Submit Button
    submit_button = ttk.Button(buttons_frame, text="Submit",
                               command=lambda: submit_request(
                                   config,
                                   chat_tab.selected_prompt_index,
                                   input_box.get("1.0", tk.END),
                                   output_box,
                                   submit_button,
                                   stop_button,
                                   chat_tab,
                                   chat_instruction_listbox))
    submit_button.grid(row=0, column=0, padx=5, sticky='ew')

    # Stop Process Button
    stop_button = ttk.Button(buttons_frame, text="Stop Process", state=tk.DISABLED,
                             command=lambda: stop_process(chat_tab))
    stop_button.grid(row=0, column=1, padx=5, sticky='ew')

    # Store the stop_button in chat_tab
    chat_tab.stop_button = stop_button

    # Clear All Button
    clear_button = ttk.Button(buttons_frame, text="Clear All", command=lambda: clear_all(chat_instruction_listbox, input_box, output_box))
    clear_button.grid(row=0, column=2, padx=5, sticky='ew')

    # Function to clear all selections and text boxes
    def clear_all(chat_instruction_listbox, input_box, output_box):
        """Clear Instruction Prompt selection and input/output text boxes."""
        # Clear Instruction Prompt selection
        chat_instruction_listbox.selection_clear(0, tk.END)
        chat_tab.selected_prompt_index = None
        chat_tab.selected_prompt_name = None

        # Clear the input and output text boxes
        input_box.delete('1.0', tk.END)
        output_box.config(state=tk.NORMAL)
        output_box.delete('1.0', tk.END)
        output_box.config(state=tk.DISABLED)

    # Output Text Box with formatting
    output_label = ttk.Label(chat_tab, text="Response:")
    output_label.grid(row=6, column=0, padx=5, pady=5, sticky="w")

    output_box = tk.Text(chat_tab, height=15, wrap=tk.WORD)
    output_box.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
    output_box.config(state=tk.DISABLED)  # Make it read-only

    # Configure grid weights for dynamic resizing
    chat_tab.columnconfigure(0, weight=1)
    chat_tab.rowconfigure(4, weight=1)
    chat_tab.rowconfigure(7, weight=1)

    # ------------------ Removed Settings Tab ------------------
    # All settings related functionalities are now moved to the File menu.

    # Create a menu bar
    menubar = Menu(root)
    root.config(menu=menubar)

    # Add file menu
    filemenu = Menu(menubar, tearoff=0)
    menubar.add_cascade(label="File", menu=filemenu)
    filemenu.add_command(label="Manage APIs", command=lambda: manage_apis(config))
    filemenu.add_separator()
    filemenu.add_command(label="Exit", command=root.quit)

    # Run the main event loop
    root.mainloop()

# Entry point
if __name__ == "__main__":
    # Load configuration from YAML file
    config = load_config()

    # Create and start the GUI
    create_gui(config)

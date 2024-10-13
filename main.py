# main.py

import sys
import subprocess
import os
from pathlib import Path
import importlib
import pkgutil
import traceback
import threading
import uuid
import math
import re  # For parsing markdown-like formatting

from node_registry import register_node, NODE_REGISTRY  # Import from node_registry.py
from db_tools import DatabaseManager  # Import from db_tools.py
from config_utils import load_config, save_config  # Importing from config_utils.py

# Import separated functions
from manage_apis_window import manage_apis_window
from manage_databases_window import manage_databases_window
from manage_documents_window import manage_documents_window
from manage_settings import manage_settings_window
from process_node_graph import process_node_graph

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
        'faiss': 'faiss-cpu',
        'langchain': 'langchain',
        'langchain_huggingface': 'langchain-huggingface',
        'langchain_community': 'langchain-community',
        'sentence_transformers': 'sentence-transformers',
        'pandas': 'pandas',
        'numpy': 'numpy',
        'transformers': 'transformers',
        'urllib3': 'urllib3<2.0.0',
        'beautifulsoup4': 'beautifulsoup4',  # Added to handle bs4 dependencies
        'pypdf': 'pypdf',  # Added to handle PDF documents
    }

    for module, package in dependencies.items():
        try:
            __import__(module)
        except ImportError:
            try:
                install(package)
            except subprocess.CalledProcessError:
                if package == 'ollama':
                    print(f"Failed to install '{package}'. Please install it manually.")
                else:
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
from tkinter import ttk, messagebox, Menu, Toplevel, Label, Entry, Button, Scrollbar, END, SINGLE, filedialog
import requests
import yaml
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

# Import NodeEditor module
from node_editor import NodeEditor

from ollama import Client

# Import the base node class
from nodes.base_node import BaseNode

# Import formatting utilities
from formatting_utils import append_formatted_text

# Setup logging for main.py
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

import logging

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "main.log"),
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize the Database Manager
db_manager = DatabaseManager()

def load_nodes():
    """
    Dynamically load all node modules from the 'nodes' directory.
    """
    nodes_package = 'nodes'
    try:
        package = importlib.import_module(nodes_package)
    except ImportError:
        sys.exit(1)

    package_path = package.__path__

    for _, module_name, _ in pkgutil.iter_modules(package_path):
        try:
            importlib.import_module(f"{nodes_package}.{module_name}")
        except Exception as e:
            traceback.print_exc()

def load_workflows(workflow_dir='workflows'):
    """Load all workflow files from the workflow directory."""
    workflows = []
    workflow_path = Path(workflow_dir)
    
    if not workflow_path.exists():
        workflow_path.mkdir(parents=True, exist_ok=True)

    for workflow_file in workflow_path.glob("*.yaml"):
        try:
            with open(workflow_file, 'r') as file:
                workflow = yaml.safe_load(file)
                if workflow:
                    workflows.append({'name': workflow_file.stem, 'graph': workflow.get('graph', {})})
        except Exception as e:
            print(f"Error loading workflow from {workflow_file}: {e}")
    
    return workflows
    
def save_workflow(workflow, workflow_dir='workflows'):
    """Save a single workflow to a YAML file in the workflow directory."""
    workflow_path = Path(workflow_dir)
    
    if not workflow_path.exists():
        workflow_path.mkdir(parents=True, exist_ok=True)
    
    workflow_file = workflow_path / f"{workflow['name']}.yaml"
    
    try:
        with open(workflow_file, "w") as file:
            yaml.safe_dump(workflow, file)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save workflow '{workflow['name']}': {e}")

# Initialize a dictionary to keep track of open NodeEditor instances
open_editors = {}

def add_instruction_prompt(config, chat_instruction_listbox):
    """Add a new instruction prompt using NodeEditor."""
    def on_save(editor):
        graph_data = editor.configured_graph
        name = editor.configured_name
        if graph_data and name:
            existing_workflows = [wf['name'] for wf in load_workflows()]
            if name in existing_workflows:
                messagebox.showerror("Error", "A workflow with this name already exists.")
                return
            save_workflow({'name': name, 'graph': graph_data})
            chat_instruction_listbox.insert(END, name)
            update_workflow_list(chat_instruction_listbox)  # Dynamically update the list

    def on_close(editor):
        if editor.instruction_name in open_editors:
            del open_editors[editor.instruction_name]

    editor = NodeEditor(root, config, config['interfaces'], save_callback=on_save, close_callback=on_close)

def edit_instruction_prompt(config, chat_instruction_listbox):
    """Edit an existing instruction prompt using NodeEditor."""
    selected_indices = chat_instruction_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("Selection Required", "Please select an instruction prompt to edit.")
        return
    index = selected_indices[0]
    workflows = load_workflows()
    if index >= len(workflows):
        messagebox.showerror("Error", "Selected workflow index is out of range.")
        return
    selected_item = workflows[index]
    selected_name = selected_item['name']
    graph_data = selected_item.get('graph', {})

    def on_save(editor):
        new_graph_data = editor.configured_graph
        new_name = editor.configured_name
        if new_graph_data and new_name:
            existing_workflows = [wf['name'] for wf in load_workflows()]
            if new_name != selected_name and new_name in existing_workflows:
                messagebox.showerror("Error", "A workflow with this name already exists.")
                return
            save_workflow({'name': new_name, 'graph': new_graph_data})
            chat_instruction_listbox.delete(index)
            chat_instruction_listbox.insert(index, new_name)
            update_workflow_list(chat_instruction_listbox)  # Dynamically update the list

    def on_close(editor):
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
    workflows = load_workflows()
    if index >= len(workflows):
        messagebox.showerror("Error", "Selected workflow index is out of range.")
        return
    selected_prompt = workflows[index]
    selected_name = selected_prompt['name']
    confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the workflow '{selected_name}'?")
    if confirm:
        workflow_file = Path('workflows') / f"{selected_name}.yaml"
        if workflow_file.exists():
            workflow_file.unlink()
            chat_instruction_listbox.delete(index)
            update_workflow_list(chat_instruction_listbox)  # Dynamically update the list
        else:
            messagebox.showerror("Error", f"Workflow file '{selected_name}.yaml' not found.")

def update_workflow_list(chat_instruction_listbox):
    """Dynamically update the instruction prompt list based on available workflows."""
    chat_instruction_listbox.delete(0, END)
    workflows = load_workflows()
    for workflow in workflows:
        chat_instruction_listbox.insert(END, workflow['name'])

def perform_search(config, db_name, query, output_box, top_k_str="10"):
    """Perform search and display results in the output box."""
    logging.info(f"Initiating search for query '{query}' in database '{db_name}'.")
    if not db_name:
        messagebox.showwarning("Input Required", "Please select a database.")
        logging.warning("Search aborted: No database selected.")
        return
    if not query.strip():
        messagebox.showwarning("Input Required", "Please enter a search query.")
        logging.warning("Search aborted: Empty query.")
        return

    try:
        top_k = int(top_k_str)
        if top_k <= 0:
            raise ValueError("Top K must be a positive integer.")
    except ValueError:
        messagebox.showwarning("Invalid Input", "Please enter a valid positive integer for Top K Results.")
        logging.warning("Search aborted: Invalid Top K value.")
        return

    def search_thread():
        try:
            results = db_manager.search(db_name, query, top_k=top_k)
            logging.info(f"Search returned {len(results)} results.")
            output_box.config(state=tk.NORMAL)
            output_box.delete('1.0', tk.END)
            if not results:
                output_box.insert(tk.END, "No results found.")
            else:
                for idx, res in enumerate(results, start=1):
                    doc = res.get("source", "Unknown")
                    similarity = res.get("similarity", 0)
                    content = res.get("content", "")
                    output_box.insert(tk.END, f"Result {idx}:\n")
                    output_box.insert(tk.END, f"Document: {doc}\n")
                    output_box.insert(tk.END, f"Similarity Score: {similarity:.4f}\n")
                    output_box.insert(tk.END, f"Content:\n{content}\n\n")
            output_box.config(state=tk.DISABLED)
        except Exception as e:
            logging.error(f"Exception during perform_search: {e}")
            messagebox.showerror("Error", f"An error occurred during search: {e}")

    threading.Thread(target=search_thread).start()

def refresh_instruction_list(chat_instruction_listbox):
    """Refresh the instruction prompt list based on available workflows."""
    update_workflow_list(chat_instruction_listbox)

def create_gui(config):
    """Create and run the GUI."""
    global root
    root = tk.Tk()
    root.title("XeroFlow")
    root.geometry("500x700")
    root.minsize(450, 600)
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True)

    chat_tab = ttk.Frame(notebook)
    notebook.add(chat_tab, text='Chat')

    chat_tab.stop_event = threading.Event()

    chat_tab.columnconfigure(0, weight=1)
    chat_tab.rowconfigure(0, weight=0)
    chat_tab.rowconfigure(1, weight=0)
    chat_tab.rowconfigure(2, weight=1)
    chat_tab.rowconfigure(3, weight=0)
    chat_tab.rowconfigure(4, weight=0)
    chat_tab.rowconfigure(5, weight=2)

    top_container = ttk.Frame(chat_tab)
    top_container.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
    top_container.columnconfigure(0, weight=1)
    top_container.columnconfigure(1, weight=1)
    top_container.rowconfigure(0, weight=1)

    instruction_selection_frame = ttk.LabelFrame(top_container, text="Instruction Prompt")
    instruction_selection_frame.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
    instruction_selection_frame.columnconfigure(0, weight=1)
    instruction_selection_frame.rowconfigure(1, weight=1)

    instruction_label = ttk.Label(instruction_selection_frame, text="Select Instruction Prompt:")
    instruction_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    chat_instruction_frame = ttk.Frame(instruction_selection_frame)
    chat_instruction_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
    chat_instruction_frame.columnconfigure(0, weight=1)
    chat_instruction_frame.rowconfigure(0, weight=1)

    chat_instruction_scrollbar = Scrollbar(chat_instruction_frame, orient=tk.VERTICAL)
    chat_instruction_scrollbar.grid(row=0, column=1, sticky="ns")

    chat_instruction_listbox = tk.Listbox(
        chat_instruction_frame,
        selectmode=SINGLE,
        yscrollcommand=chat_instruction_scrollbar.set,
        exportselection=False
    )
    chat_instruction_listbox.grid(row=0, column=0, sticky="nsew")
    chat_instruction_scrollbar.config(command=chat_instruction_listbox.yview)

    update_workflow_list(chat_instruction_listbox)

    instruction_buttons_frame = ttk.Frame(instruction_selection_frame)
    instruction_buttons_frame.grid(row=2, column=0, padx=5, pady=5, sticky="w")

    add_instruction_button = ttk.Button(
        instruction_buttons_frame,
        text="Add",
        width=5,
        command=lambda: add_instruction_prompt(config, chat_instruction_listbox)
    )
    add_instruction_button.pack(side=tk.LEFT, padx=2)

    edit_instruction_button = ttk.Button(
        instruction_buttons_frame,
        text="Edit",
        width=5,
        command=lambda: edit_instruction_prompt(config, chat_instruction_listbox)
    )
    edit_instruction_button.pack(side=tk.LEFT, padx=2)

    delete_instruction_button = ttk.Button(
        instruction_buttons_frame,
        text="Delete",
        width=5,
        command=lambda: delete_instruction_prompt(config, chat_instruction_listbox)
    )
    delete_instruction_button.pack(side=tk.LEFT, padx=2)

    refresh_instruction_button = ttk.Button(
        instruction_buttons_frame,
        text="Refresh",
        width=6,
        command=lambda: refresh_instruction_list(chat_instruction_listbox)
    )
    refresh_instruction_button.pack(side=tk.LEFT, padx=2)

    def on_select_chat_instruction(event):
        selected_indices = chat_instruction_listbox.curselection()
        if selected_indices:
            index = selected_indices[0]
            selected_name = chat_instruction_listbox.get(index)
            chat_tab.selected_prompt_index = index
            chat_tab.selected_prompt_name = selected_name
        else:
            chat_tab.selected_prompt_index = None
            chat_tab.selected_prompt_name = None

    chat_instruction_listbox.bind('<<ListboxSelect>>', on_select_chat_instruction)
    chat_tab.selected_prompt_index = None
    chat_tab.selected_prompt_name = None

    db_search_frame = ttk.LabelFrame(top_container, text="Database Search")
    db_search_frame.grid(row=0, column=1, padx=(10, 0), pady=5, sticky="nsew")
    db_search_frame.columnconfigure(1, weight=1)
    db_search_frame.rowconfigure(3, weight=1)

    db_label = ttk.Label(db_search_frame, text="Select Database:")
    db_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    db_manager_list = ttk.Combobox(db_search_frame, state="readonly")
    db_manager_list['values'] = db_manager.list_databases()
    if db_manager_list['values']:
        db_manager_list.current(0)
    db_manager_list.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    search_label = ttk.Label(db_search_frame, text="Search Documents:")
    search_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")

    search_entry = ttk.Entry(db_search_frame)
    search_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

    top_k_label = ttk.Label(db_search_frame, text="Top K Results:")
    top_k_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")

    top_k_entry = ttk.Entry(db_search_frame, width=5)
    top_k_entry.insert(0, "10")
    top_k_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

    search_button = ttk.Button(
        db_search_frame,
        text="Search",
        command=lambda: perform_search(
            config,
            db_manager_list.get(),
            search_entry.get(),
            output_box,
            top_k_entry.get()
        )
    )
    search_button.grid(row=3, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

    input_label = ttk.Label(chat_tab, text="Enter your prompt:")
    input_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")

    input_box = tk.Text(chat_tab, height=8)
    input_box.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")
    chat_tab.rowconfigure(2, weight=1)

    buttons_frame = ttk.Frame(chat_tab)
    buttons_frame.grid(row=3, column=0, columnspan=1, padx=5, pady=10, sticky='ew')
    buttons_frame.columnconfigure(0, weight=1)
    buttons_frame.columnconfigure(1, weight=1)
    buttons_frame.columnconfigure(2, weight=1)

    submit_button = ttk.Button(
        buttons_frame,
        text="Submit",
        command=lambda: submit_request(
            config,
            chat_tab.selected_prompt_index,
            input_box.get("1.0", tk.END),
            output_box,
            submit_button,
            stop_button,
            chat_tab,
            chat_instruction_listbox
        )
    )
    submit_button.grid(row=0, column=0, padx=5, sticky='ew')

    stop_button = ttk.Button(
        buttons_frame,
        text="Stop Process",
        state=tk.DISABLED,
        command=lambda: stop_process(chat_tab)
    )
    stop_button.grid(row=0, column=1, padx=5, sticky='ew')

    chat_tab.stop_button = stop_button

    clear_button = ttk.Button(
        buttons_frame,
        text="Clear All",
        command=lambda: clear_all(chat_instruction_listbox, input_box, output_box)
    )
    clear_button.grid(row=0, column=2, padx=5, sticky='ew')

    def clear_all(chat_instruction_listbox, input_box, output_box):
        chat_instruction_listbox.selection_clear(0, tk.END)
        chat_tab.selected_prompt_index = None
        chat_tab.selected_prompt_name = None
        input_box.delete('1.0', tk.END)
        output_box.config(state=tk.NORMAL)
        output_box.delete('1.0', END)
        output_box.config(state=tk.DISABLED)

    output_label = ttk.Label(chat_tab, text="Response:")
    output_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")

    output_box = tk.Text(chat_tab, height=15, wrap=tk.WORD)
    output_box.grid(row=5, column=0, columnspan=1, padx=5, pady=5, sticky="nsew")
    output_box.config(state=tk.DISABLED)

    chat_tab.rowconfigure(2, weight=1)
    chat_tab.rowconfigure(5, weight=2)
    chat_tab.columnconfigure(0, weight=1)

    menubar = Menu(root)
    root.config(menu=menubar)

    filemenu = Menu(menubar, tearoff=0)
    menubar.add_cascade(label="File", menu=filemenu)

    def refresh_database_dropdown():
        dbs = db_manager.list_databases()
        db_manager_list['values'] = dbs
        if dbs:
            db_manager_list.current(0)
        else:
            db_manager_list.set('')

        for widget in root.winfo_children():
            if isinstance(widget, Toplevel):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Notebook):
                        for tab_id in child.tabs():
                            tab_widget = child.nametowidget(tab_id)
                            for sub_child in tab_widget.winfo_children():
                                if isinstance(sub_child, ttk.Combobox):
                                    sub_child['values'] = dbs
                                    if dbs:
                                        sub_child.current(0)
                                    else:
                                        sub_child.set('')

    filemenu.add_command(
        label="Manage Settings",
        command=lambda: manage_settings_window(config, root, refresh_database_dropdown)
    )
    filemenu.add_separator()
    filemenu.add_command(label="Exit", command=root.quit)

    root.mainloop()
    
def submit_request(config, selected_prompt_index, user_input, output_box, submit_button, stop_button, chat_tab, chat_instruction_listbox):
    """Handle submitting the request."""
    if not user_input.strip():
        messagebox.showwarning("Input Required", "Please enter some text in the input box.")
        return

    if selected_prompt_index is None:
        messagebox.showerror("Error", "Please select an instruction prompt from the list.")
        return
    
    workflows = load_workflows()

    try:
        selected_prompt = workflows[selected_prompt_index]
    except IndexError:
        messagebox.showerror("Error", "Selected workflow is out of range.")
        return

    node_graph = selected_prompt.get('graph', None)
    if not node_graph:
        messagebox.showerror("Error", "Selected workflow is not properly configured.")
        return

    # Retrieve the selected API endpoint from config
    api_endpoint = config.get("api_endpoint")  # Fetch selected endpoint dynamically

    selected_prompt_name = selected_prompt['name']

    if not hasattr(chat_tab, 'stop_event') or not isinstance(chat_tab.stop_event, threading.Event):
        chat_tab.stop_event = threading.Event()
    chat_tab.stop_event.clear()

    submit_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)

    thread = threading.Thread(target=process_node_graph, args=(
        config, api_endpoint, user_input, output_box, submit_button, stop_button, chat_tab.stop_event,
        node_graph, selected_prompt_name, root, open_editors))
    thread.start()


def stop_process(chat_tab):
    """Stop the ongoing process."""
    if hasattr(chat_tab, 'stop_event'):
        chat_tab.stop_event.set()
        chat_tab.stop_button.config(state=tk.DISABLED)

def main():
    load_nodes()

    config = load_config()

    create_gui(config)

    sys.modules['your_api_module'] = sys.modules[__name__]

if __name__ == "__main__":
    main()

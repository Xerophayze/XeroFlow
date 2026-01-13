# main.py

import sys
print(f"Python executable: {sys.executable}")
print(f"Python path: {sys.path}")
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
import queue  # Add this import at the top
try:
    import torch
except ImportError:
    torch = None
from utils.ffmpeg_installer import ensure_ffmpeg_available  # Ensure ffmpeg/avconv is available

from node_registry import register_node, NODE_REGISTRY  # Import from node_registry.py
from db_tools import DatabaseManager  # Import from db_tools.py
from config_utils import load_config, save_config  # Importing from config_utils.py
from workflow_manager import workflow_manager, create_workflow_management_tab  # Import from workflow_manager.py

# Import separated functions
from manage_apis_window import manage_apis_window
from manage_databases_window import manage_databases_window
from manage_documents_window import manage_documents_window
from manage_settings import manage_settings_window
from process_node_graph import process_node_graph

import tkinter as tk
import _tkinter
from tkinter import ttk, messagebox, Menu, Toplevel, Label, Entry, Button, Scrollbar, END, SINGLE, filedialog, BooleanVar
import requests
import yaml
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

# Import NodeEditor module (using modern version)
from node_editor_modern import ModernNodeEditor as NodeEditor

from ollama import Client

# Import the base node class
from nodes.base_node import BaseNode

# Import formatting utilities
from formatting_utils import append_formatted_text, set_formatting_enabled  # Import set_formatting_enabled

# Import the Word export function
from ExportWord import convert_markdown_to_docx  # Ensure ExportWord.py is in the same directory

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


def log_accelerator_status():
    """Emit diagnostic information about accelerator availability."""
    if torch is None:
        message = "PyTorch not installed; GPU status unavailable. Defaulting to CPU."
        print(message)
        logging.info(message)
        return

    try:
        torch_version = torch.__version__
    except AttributeError:
        torch_version = "unknown"

    logging.info("Detected PyTorch version: %s", torch_version)
    if torch.cuda.is_available():
        try:
            device_index = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(device_index)
            capability = torch.cuda.get_device_capability(device_index)
            message = (
                f"CUDA available - GPU {device_index}: {device_name} "
                f"(compute capability {capability[0]}.{capability[1]})"
            )
        except Exception as cuda_error:
            message = f"CUDA available but failed to query device details: {cuda_error}"
            logging.warning(message)
            print(message)
            return
        logging.info(message)
        print(message)
    else:
        message = "CUDA not available. Running on CPU."
        logging.info(message)
        print(message)


log_accelerator_status()

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
    """Add a new Workflow using NodeEditor."""
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
    """Edit an existing Workflow using NodeEditor."""
    selected_indices = chat_instruction_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("Selection Required", "Please select an Workflow to edit.")
        return
    index = selected_indices[0]
    selected_name = chat_instruction_listbox.get(index)
    workflows = load_workflows()
    # Find the workflow with the selected name
    selected_item = next((wf for wf in workflows if wf['name'] == selected_name), None)
    if not selected_item:
        messagebox.showerror("Error", f"Workflow '{selected_name}' not found.")
        return
    graph_data = selected_item.get('graph', {})
    
    def on_save(editor):
        new_graph_data = editor.configured_graph
        new_name = editor.configured_name
        if new_graph_data and new_name:
            existing_workflows = [wf['name'] for wf in load_workflows()]
            if new_name != selected_name and new_name in existing_workflows:
                messagebox.showerror("Error", "A workflow with this name already exists.")
                return
            # Delete old file if the name has changed
            if new_name != selected_name:
                old_file = Path('workflows') / f"{selected_name}.yaml"
                if old_file.exists():
                    old_file.unlink()
            save_workflow({'name': new_name, 'graph': new_graph_data})
            # Update the listbox
            chat_instruction_listbox.delete(index)
            chat_instruction_listbox.insert(index, new_name)
            chat_instruction_listbox.selection_set(index)
    
    def on_close(editor):
        if editor.instruction_name in open_editors:
            del open_editors[editor.instruction_name]
    
    editor = NodeEditor(root, config, config['interfaces'], existing_graph=graph_data, existing_name=selected_name, save_callback=on_save, close_callback=on_close)
    open_editors[selected_name] = editor

def delete_instruction_prompt(config, chat_instruction_listbox):
    """Delete an existing Workflow."""
    selected_indices = chat_instruction_listbox.curselection()
    if not selected_indices:
        return
    index = selected_indices[0]
    selected_name = chat_instruction_listbox.get(index)
    workflow_file = Path('workflows') / f"{selected_name}.yaml"
    if workflow_file.exists():
        try:
            workflow_file.unlink()
            chat_instruction_listbox.delete(index)
        except Exception as e:
            logging.error(f"Error deleting workflow '{selected_name}': {e}")

def on_mouse_wheel(event):
    try:
        event.widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
    except tk.TclError:
        # The widget no longer exists; ignore the event
        pass

def update_workflow_list(chat_instruction_listbox):
    """Dynamically update the Workflow list based on available workflows."""
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
                    doc_meta = res.get("document", {})
                    doc_name = doc_meta.get("source") or res.get("source", "Unknown")
                    similarity = res.get("similarity", 0)
                    content = res.get("content", "")
                    meta = res.get("metadata", {})
                    page = meta.get("page")
                    section = meta.get("section")
                    output_box.insert(tk.END, f"Result {idx}:\n")
                    output_box.insert(tk.END, f"Document: {doc_name}\n")
                    if page is not None:
                        output_box.insert(tk.END, f"Page: {page}\n")
                    if section:
                        output_box.insert(tk.END, f"Section: {section}\n")
                    output_box.insert(tk.END, f"Similarity Score: {similarity:.4f}\n")
                    output_box.insert(tk.END, f"Content:\n{content}\n\n")
            output_box.config(state=tk.DISABLED)
        except Exception as e:
            logging.error(f"Exception during perform_search: {e}")
            messagebox.showerror("Error", f"An error occurred during search: {e}")

    threading.Thread(target=search_thread).start()

def refresh_instruction_list(chat_instruction_listbox):
    """Refresh the Workflow list based on available workflows."""
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

    gui_queue = queue.Queue()  # Initialize the queue for GUI updates

    def process_gui_queue():
        try:
            while True:
                try:
                    func = gui_queue.get_nowait()
                    func()
                except queue.Empty:
                    break  # Exit the while loop if queue is empty
                except Exception as e:
                    # Log the exception and continue processing other tasks
                    print(f"Error executing GUI task: {e}")
                    traceback.print_exc() # Print traceback to console
                    logging.error(f"Error executing GUI task: {e}\n{traceback.format_exc()}")
        finally:
            # Always reschedule the next check, even if an error occurred in the try block
            # (though specific task errors are caught inside the loop now)
            root.after(100, process_gui_queue)

    # Start processing the GUI queue
    root.after(100, process_gui_queue)

    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True)

    chat_tab = ttk.Frame(notebook)
    notebook.add(chat_tab, text='Chat')
    
    # Create the Workflow Management tab
    workflow_tab = create_workflow_management_tab(notebook, config, gui_queue)

    chat_tab.stop_event = threading.Event()

    chat_tab.columnconfigure(0, weight=1)
    chat_tab.rowconfigure(0, weight=0)
    chat_tab.rowconfigure(1, weight=0)
    chat_tab.rowconfigure(2, weight=1)
    chat_tab.rowconfigure(3, weight=0)
    chat_tab.rowconfigure(4, weight=0)
    chat_tab.rowconfigure(5, weight=2)
    chat_tab.rowconfigure(6, weight=0)  # Added for formatting checkbox

    chat_tab.response_content = ""  # Initialize variable to store original content

    top_container = ttk.Frame(chat_tab)
    top_container.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
    top_container.columnconfigure(0, weight=1)
    top_container.columnconfigure(1, weight=1)
    top_container.rowconfigure(0, weight=1)

    instruction_selection_frame = ttk.LabelFrame(top_container, text="Workflow")
    instruction_selection_frame.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
    instruction_selection_frame.columnconfigure(0, weight=1)
    instruction_selection_frame.rowconfigure(1, weight=1)

    instruction_label = ttk.Label(instruction_selection_frame, text="Select Workflow:")
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

    output_box = None  # Initialize output_box before usage

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

    input_box_frame = ttk.Frame(chat_tab)
    input_box_frame.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")
    chat_tab.rowconfigure(2, weight=1)

    input_box = tk.Text(input_box_frame, height=8)
    input_box.pack(side=tk.LEFT, fill='both', expand=True)

    input_scrollbar = Scrollbar(input_box_frame, orient=tk.VERTICAL, command=input_box.yview)
    input_scrollbar.pack(side=tk.RIGHT, fill='y')
    input_box.configure(yscrollcommand=input_scrollbar.set)

    # Context menu for input_box
    input_context_menu = Menu(root, tearoff=0)
    input_context_menu.add_command(label="Cut", command=lambda: input_box.event_generate("<<Cut>>"))
    input_context_menu.add_command(label="Copy", command=lambda: input_box.event_generate("<<Copy>>"))
    input_context_menu.add_command(label="Paste", command=lambda: input_box.event_generate("<<Paste>>"))
    input_context_menu.add_separator()
    input_context_menu.add_command(label="Select All", command=lambda: input_box.tag_add('sel', '1.0', 'end'))

    def show_input_context_menu(event):
        input_box.focus_set()
        input_context_menu.tk_popup(event.x_root, event.y_root)

    input_box.bind("<Button-3>", show_input_context_menu)

    buttons_frame = ttk.Frame(chat_tab)
    buttons_frame.grid(row=3, column=0, columnspan=1, padx=5, pady=10, sticky='ew')
    buttons_frame.columnconfigure(0, weight=1)
    buttons_frame.columnconfigure(1, weight=1)
    buttons_frame.columnconfigure(2, weight=1)

    stop_button = ttk.Button(
        buttons_frame,
        text="Stop Process",
        state=tk.DISABLED,
        command=lambda: stop_process(chat_tab)
    )
    stop_button.grid(row=0, column=1, padx=5, sticky='ew')

    def clear_all(chat_instruction_listbox, input_box, output_box):
        chat_instruction_listbox.selection_clear(0, tk.END)
        chat_tab.selected_prompt_index = None
        chat_tab.selected_prompt_name = None
        input_box.delete('1.0', tk.END)
        output_box.config(state=tk.NORMAL)
        output_box.delete('1.0', END)
        output_box.config(state=tk.DISABLED)
        chat_tab.response_content = ""  # Clear stored response content

    clear_button = ttk.Button(
        buttons_frame,
        text="Clear All",
        command=lambda: clear_all(chat_instruction_listbox, input_box, output_box)
    )
    clear_button.grid(row=0, column=2, padx=5, sticky='ew')

    output_label = ttk.Label(chat_tab, text="Response:")
    output_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")

    output_box_frame = ttk.Frame(chat_tab)
    output_box_frame.grid(row=5, column=0, columnspan=1, padx=5, pady=5, sticky="nsew")
    chat_tab.rowconfigure(5, weight=2)
    chat_tab.columnconfigure(0, weight=1)

    output_box = tk.Text(output_box_frame, height=15, wrap=tk.WORD, state=tk.DISABLED)
    output_box.pack(side=tk.LEFT, fill='both', expand=True)

    output_scrollbar = Scrollbar(output_box_frame, orient=tk.VERTICAL, command=output_box.yview)
    output_scrollbar.pack(side=tk.RIGHT, fill='y')
    output_box.configure(yscrollcommand=output_scrollbar.set)

    # Context menu for output_box
    output_context_menu = Menu(root, tearoff=0)
    output_context_menu.add_command(label="Cut", command=lambda: output_box.event_generate("<<Cut>>"))
    output_context_menu.add_command(label="Copy", command=lambda: output_box.event_generate("<<Copy>>"))
    output_context_menu.add_command(label="Paste", command=lambda: output_box.event_generate("<<Paste>>"))
    output_context_menu.add_separator()
    output_context_menu.add_command(label="Select All", command=lambda: output_box.tag_add('sel', '1.0', 'end'))

    def show_output_context_menu(event):
        output_box.focus_set()
        output_context_menu.tk_popup(event.x_root, event.y_root)

    output_box.bind("<Button-3>", show_output_context_menu)

    # Add formatting checkbox and Export Docx button
    export_frame = ttk.Frame(chat_tab)
    export_frame.grid(row=6, column=0, padx=5, pady=5, sticky='w')

    formatting_var = BooleanVar(value=True)  # Renamed to avoid confusion with imported variable
    formatting_checkbox = ttk.Checkbutton(
        export_frame,
        text="Enable Formatting",
        variable=formatting_var
    )
    formatting_checkbox.pack(side=tk.LEFT)

    def export_to_docx(chat_tab, formatting_enabled):
        """
        Retrieves the raw content from chat_tab.response_content and exports it to a Word document.
        Args:
            chat_tab: The chat tab containing the response content
            formatting_enabled: Boolean indicating whether to apply markdown formatting
        """
        content = chat_tab.response_content
        if not content or not isinstance(content, str):
            return
        try:
            convert_markdown_to_docx(content, formatting_enabled=formatting_enabled)
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while exporting to Word: {e}")

    def open_admin_console():
        """
        Launch the admin console as a separate application.
        Uses the same Python executable as the main application to ensure compatibility.
        """
        try:
            python_executable = sys.executable
            subprocess.Popen([python_executable, "adminconsole.py"], 
                            shell=True, 
                            cwd=os.path.dirname(os.path.abspath(__file__)))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Admin Console: {e}")

    export_button = ttk.Button(
        export_frame,
        text="Export Docx",
        command=lambda: export_to_docx(chat_tab, formatting_var.get())  # Pass the formatting state
    )
    export_button.pack(side=tk.LEFT, padx=(10, 0))

    admin_console_button = ttk.Button(
        export_frame,
        text="Admin Console",
        command=open_admin_console
    )
    admin_console_button.pack(side=tk.LEFT, padx=(10, 0))

    # Update formatting state when checkbox is toggled
    def on_formatting_toggle():
        set_formatting_enabled(formatting_var.get())
        # Get original content
        content = chat_tab.response_content
        if content:
            # Clear the output box
            output_box.config(state=tk.NORMAL)
            output_box.delete('1.0', tk.END)
            output_box.config(state=tk.DISABLED)
            # Re-insert the content with or without formatting
            append_formatted_text(output_box, content)

    formatting_checkbox.config(command=on_formatting_toggle)

    # Set initial formatting state
    set_formatting_enabled(formatting_var.get())

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
            chat_instruction_listbox,
            gui_queue,
            formatting_var  # Pass the formatting flag as a BooleanVar
        )
    )
    submit_button.grid(row=0, column=0, padx=5, sticky='ew')

    chat_tab.stop_button = stop_button

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
            if isinstance(widget, tk.Toplevel):
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
    filemenu.add_command(
        label="Manage Auto-Startup Workflows",
        command=lambda: open_auto_startup_manager(root, config)
    )
    filemenu.add_separator()
    filemenu.add_command(label="Exit", command=root.quit)

    def open_auto_startup_manager(parent, config):
        """Open the auto-startup manager window."""
        # Import here to avoid circular imports
        from auto_startup_manager import create_auto_startup_manager_window
        create_auto_startup_manager_window(parent, config, load_workflows)

    def start_auto_startup_workflows(config, output_box, submit_button, stop_button, chat_tab, chat_instruction_listbox, gui_queue, formatting_enabled_var):
        """Start all workflows configured for auto-startup."""
        # Import here to avoid circular imports
        from auto_startup_manager import auto_startup_manager
        
        # Use a small delay to ensure the GUI is fully loaded before starting workflows
        root.after(1000, lambda: auto_startup_manager.start_auto_startup_workflows(
            submit_request,  # Pass the submit_request function
            config, 
            output_box, 
            submit_button, 
            stop_button, 
            chat_tab, 
            chat_instruction_listbox, 
            gui_queue, 
            formatting_enabled_var
        ))

    start_auto_startup_workflows(config, output_box, submit_button, stop_button, chat_tab, chat_instruction_listbox, gui_queue, formatting_var)

    # Start processing the GUI queue
    process_gui_queue()

    root.mainloop()
    
def submit_request(config, selected_prompt_index, user_input, output_box, submit_button, stop_button, chat_tab, chat_instruction_listbox, gui_queue, formatting_enabled_var):
    """Handle submitting the request."""
    if not user_input.strip():
        messagebox.showwarning("Input Required", "Please enter some text in the input box.")
        return

    if selected_prompt_index is None:
        messagebox.showerror("Error", "Please select an Workflow from the list.")
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

    # Clear the output box before displaying new output
    output_box.config(state=tk.NORMAL)
    output_box.delete('1.0', tk.END)
    output_box.config(state=tk.DISABLED)
    chat_tab.response_content = ""  # Clear stored response content

    # Retrieve the selected API endpoint from config
    api_endpoint = config.get("api_endpoint")  # Fetch selected endpoint dynamically

    selected_prompt_name = selected_prompt['name']

    # Create a new stop event for this workflow
    stop_event = threading.Event()
    
    # Create a workflow instance in the workflow manager
    workflow = workflow_manager.create_workflow(selected_prompt_name, user_input)
    
    # No need to disable the submit button anymore
    # submit_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)

    # Define a callback function to handle workflow completion
    def on_workflow_complete(output_content):
        workflow_manager.complete_workflow(workflow.id, output_content)
        # No need to re-enable the submit button here
        stop_button.config(state=tk.DISABLED)
    
    # Define a callback function to handle workflow errors
    def on_workflow_error(error_msg):
        workflow_manager.set_workflow_error(workflow.id, error_msg)
        # No need to re-enable the submit button here
        stop_button.config(state=tk.DISABLED)

    thread = threading.Thread(target=process_node_graph, args=(
        config, api_endpoint, user_input, output_box, submit_button, stop_button, workflow.stop_event,
        node_graph, selected_prompt_name, root, open_editors, gui_queue, formatting_enabled_var.get(), chat_tab,
        workflow.id, on_workflow_complete, on_workflow_error))  # Pass workflow ID and callbacks
    
    # Store the thread in the workflow instance
    workflow.thread = thread
    
    thread.start()

def stop_process(chat_tab):
    """Stop the ongoing process."""
    if hasattr(chat_tab, 'stop_event') and isinstance(chat_tab.stop_event, threading.Event):
        chat_tab.stop_event.set()
        print("Stop event has been set.")
        
    # Get the active workflows from the workflow manager and stop the most recent one
    active_workflows = workflow_manager.get_active_workflows()
    if active_workflows:
        # Get the most recent workflow (assuming the most recent is the one we want to stop)
        workflow_id = list(active_workflows.keys())[0]
        workflow_manager.stop_workflow(workflow_id)
        print(f"Stopped workflow: {workflow_id}")

def main():
    # Ensure ffmpeg is available for any audio/video operations that may be used by nodes/utilities
    try:
        ff_path = ensure_ffmpeg_available(auto_install=True)
        if ff_path:
            # Help libraries like imageio/moviepy find the binary consistently
            os.environ["IMAGEIO_FFMPEG_EXE"] = ff_path
    except Exception as e:
        logging.warning(f"ffmpeg auto-install failed or not available: {e}")

    load_nodes()

    config = load_config()

    create_gui(config)

    sys.modules['your_api_module'] = sys.modules[__name__]

if __name__ == "__main__":
    main()

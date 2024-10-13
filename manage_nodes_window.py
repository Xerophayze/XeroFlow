# manage_nodes_window.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from node_registry import NODE_REGISTRY, reload_nodes
from db_tools import DatabaseManager  # If needed for node management
import logging
import threading
import os
import shutil
import importlib
from pathlib import Path

def manage_nodes_window(parent, config, refresh_callback):
    """
    Create a Manage Nodes tab within the settings window.

    Args:
        parent (tk.Frame): The parent frame where the tab will be placed.
        config (dict): Configuration settings (if needed).
        refresh_callback (function): Function to refresh other parts of the application after changes.
    """

    # Create a frame for the Manage Nodes tab
    nodes_tab = ttk.Frame(parent)
    nodes_tab.pack(fill='both', expand=True)

    # Internal list to map listbox indices to node types
    node_types = list(NODE_REGISTRY.keys())

    # ------------------ Nodes List Frame ------------------
    list_frame = ttk.LabelFrame(nodes_tab, text="Available Nodes")
    list_frame.pack(fill='both', expand=True, padx=10, pady=10)

    # Adding a scrollbar to the Listbox
    listbox_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
    nodes_listbox = tk.Listbox(list_frame, height=15, yscrollcommand=listbox_scrollbar.set)
    listbox_scrollbar.config(command=nodes_listbox.yview)
    nodes_listbox.grid(row=0, column=0, sticky="nsew", padx=(5,0), pady=5)
    listbox_scrollbar.grid(row=0, column=1, sticky="ns", pady=5, padx=(0,5))

    list_frame.columnconfigure(0, weight=1)
    list_frame.rowconfigure(0, weight=1)

    # Populate the Listbox with node types
    def populate_nodes_list():
        nodes_listbox.delete(0, tk.END)
        node_types.clear()
        node_types.extend(NODE_REGISTRY.keys())
        for node_type in node_types:
            nodes_listbox.insert(tk.END, node_type)

    populate_nodes_list()

    # ------------------ Node Description Frame ------------------
    description_frame = ttk.LabelFrame(nodes_tab, text="Node Description")
    description_frame.pack(fill='both', expand=True, padx=10, pady=5)

    description_text = tk.Text(description_frame, wrap='word', state='disabled', height=10)
    description_text.pack(fill='both', expand=True, padx=5, pady=5)

    # ------------------ Buttons Frame ------------------
    buttons_frame = ttk.Frame(nodes_tab)
    buttons_frame.pack(fill='x', padx=10, pady=10)

    add_button = ttk.Button(buttons_frame, text="Add Node", command=lambda: threading.Thread(target=add_node).start())
    add_button.pack(side='left', padx=5)

    delete_button = ttk.Button(buttons_frame, text="Delete Node", command=lambda: threading.Thread(target=delete_node).start())
    delete_button.pack(side='left', padx=5)

    refresh_button = ttk.Button(buttons_frame, text="Refresh", command=lambda: threading.Thread(target=refresh_nodes).start())
    refresh_button.pack(side='left', padx=5)

    # ------------------ Busy Indicator ------------------
    busy_indicator = ttk.Frame(nodes_tab)
    busy_indicator.pack(fill='x', padx=10, pady=5)
    busy_progress = ttk.Progressbar(busy_indicator, mode='indeterminate')
    busy_progress.pack(side='left', fill='x', expand=True, padx=(0,5))
    busy_label = ttk.Label(busy_indicator, text="Processing...")
    busy_label.pack(side='left')
    busy_indicator.pack_forget()  # Hide initially

    def start_busy():
        busy_indicator.pack(fill='x', padx=10, pady=5)
        busy_progress.start()
        # Disable buttons to prevent multiple operations
        add_button.config(state='disabled')
        delete_button.config(state='disabled')
        refresh_button.config(state='disabled')

    def stop_busy():
        busy_progress.stop()
        busy_indicator.pack_forget()
        # Enable buttons after operation
        add_button.config(state='normal')
        delete_button.config(state='normal')
        refresh_button.config(state='normal')

    # ------------------ Event Bindings ------------------
    def on_node_select(event):
        selection = nodes_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        node_type = nodes_listbox.get(index)
        node_class = NODE_REGISTRY.get(node_type)
        if node_class and node_class.__doc__:
            description = node_class.__doc__.strip()
        else:
            description = "No description available for this node."
        description_text.config(state='normal')
        description_text.delete('1.0', tk.END)
        description_text.insert(tk.END, description)
        description_text.config(state='disabled')

    nodes_listbox.bind('<<ListboxSelect>>', on_node_select)

    # ------------------ Add Node Function ------------------
    def add_node():
        """
        Add a new node by selecting a .py file from the file system.
        The file is copied to the 'nodes' directory and dynamically loaded.
        """
        try:
            start_busy()
            file_path = filedialog.askopenfilename(
                title="Select Node File",
                filetypes=[("Python Files", "*.py")]
            )
            if not file_path:
                stop_busy()
                return

            # Validate the selected file
            if not os.path.isfile(file_path):
                messagebox.showerror("Invalid File", "Selected file does not exist.")
                stop_busy()
                return
            if not file_path.endswith('.py'):
                messagebox.showerror("Invalid File", "Please select a Python (.py) file.")
                stop_busy()
                return

            # Copy the file to the 'nodes' directory
            nodes_dir = Path(__file__).parent / 'nodes'
            shutil.copy(file_path, nodes_dir)
            copied_file_name = os.path.basename(file_path)
            copied_file_path = nodes_dir / copied_file_name

            # Import the new node module
            module_name = f'nodes.{copied_file_name[:-3]}'
            try:
                importlib.import_module(module_name)
                messagebox.showinfo("Success", f"Node '{copied_file_name}' added successfully.")
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to import the node module:\n{e}")
                # Remove the copied file if import fails
                os.remove(copied_file_path)
                stop_busy()
                return

            # Refresh the nodes list
            populate_nodes_list()
            stop_busy()
        except Exception as e:
            logging.error(f"Exception during add_node: {e}")
            messagebox.showerror("Error", f"An error occurred while adding the node:\n{e}")
            stop_busy()

    # ------------------ Delete Node Function ------------------
    def delete_node():
        """
        Delete the selected node by removing its file from the 'nodes' directory.
        """
        try:
            selection = nodes_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a node to delete.")
                return
            index = selection[0]
            node_type = nodes_listbox.get(index)
            node_class = NODE_REGISTRY.get(node_type)
            if not node_class:
                messagebox.showerror("Error", "Selected node does not exist.")
                return

            confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the node '{node_type}'?")
            if not confirm:
                return

            # Find the file path of the node
            module = node_class.__module__
            module_path = module.replace('.', os.sep) + '.py'
            node_file_path = Path(__file__).parent / module_path

            if not node_file_path.exists():
                messagebox.showerror("Error", f"Node file '{node_file_path}' does not exist.")
                return

            # Remove the node from NODE_REGISTRY
            del NODE_REGISTRY[node_type]

            # Delete the node file
            os.remove(node_file_path)

            # Inform the user
            messagebox.showinfo("Success", f"Node '{node_type}' deleted successfully.")

            # Refresh the nodes list
            populate_nodes_list()
            description_text.config(state='normal')
            description_text.delete('1.0', tk.END)
            description_text.config(state='disabled')
        except Exception as e:
            logging.error(f"Exception during delete_node: {e}")
            messagebox.showerror("Error", f"An error occurred while deleting the node:\n{e}")

    # ------------------ Refresh Nodes Function ------------------
    def refresh_nodes():
        """
        Refresh the nodes list by reloading all node modules.
        """
        try:
            start_busy()
            reload_nodes()
            populate_nodes_list()
            description_text.config(state='normal')
            description_text.delete('1.0', tk.END)
            description_text.config(state='disabled')
            messagebox.showinfo("Success", "Nodes refreshed successfully.")
            stop_busy()
        except Exception as e:
            logging.error(f"Exception during refresh_nodes: {e}")
            messagebox.showerror("Error", f"An error occurred while refreshing nodes:\n{e}")
            stop_busy()

    # ------------------ Initial Populate ------------------
    populate_nodes_list()

# manage_settings.py

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

# Import the existing management functions
from src.ui.dialogs.manage_apis import manage_apis_window
from src.ui.dialogs.manage_databases import manage_databases_window
from src.ui.dialogs.manage_documents import manage_documents_window
from src.ui.dialogs.manage_nodes import manage_nodes_window  # Import the new manage_nodes_window

def manage_settings_window(config, parent, refresh_callback):
    """
    Open a Manage Settings window with four tabs:
    - Manage APIs
    - Manage Databases
    - Manage Documents
    - Manage Nodes

    Args:
        config (dict): Configuration settings.
        parent (tk.Tk or tk.Toplevel): Parent window.
        refresh_callback (function): Function to refresh dropdowns after changes.
    """
    # Create a new top-level window
    settings_window = tk.Toplevel(parent)
    settings_window.title("Manage Settings")
    settings_window.geometry("600x800")  # Adjusted size for an additional tab
    settings_window.grab_set()  # Make this window modal

    # Create a Notebook for tabs
    notebook = ttk.Notebook(settings_window)
    notebook.pack(fill='both', expand=True, padx=10, pady=10)

    # ------------------ APIs Tab ------------------
    apis_tab = ttk.Frame(notebook)
    notebook.add(apis_tab, text='Manage APIs')

    # Call the manage_apis_window function within the APIs tab
    try:
        manage_apis_window(apis_tab, config, refresh_callback)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load Manage APIs tab:\n{e}")

    # ------------------ Databases Tab ------------------
    databases_tab = ttk.Frame(notebook)
    notebook.add(databases_tab, text='Manage Databases')

    # Call the manage_databases_window function within the Databases tab
    try:
        manage_databases_window(databases_tab, config, refresh_callback)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load Manage Databases tab:\n{e}")

    # ------------------ Documents Tab ------------------
    documents_tab = ttk.Frame(notebook)
    notebook.add(documents_tab, text='Manage Documents')

    # Call the manage_documents_window function within the Documents tab
    try:
        manage_documents_window(documents_tab, config, refresh_callback)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load Manage Documents tab:\n{e}")

    # ------------------ Nodes Tab ------------------
    nodes_tab = ttk.Frame(notebook)
    notebook.add(nodes_tab, text='Manage Nodes')

    # Call the manage_nodes_window function within the Nodes tab
    try:
        manage_nodes_window(nodes_tab, config, refresh_callback)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load Manage Nodes tab:\n{e}")

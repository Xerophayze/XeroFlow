# auto_startup_manager.py

import tkinter as tk
from tkinter import ttk, messagebox, Listbox, END, SINGLE, Scrollbar
import threading
import queue
import os
from pathlib import Path
import yaml
from src.utils.config import load_config, save_config

class AutoStartupManager:
    """Manages workflows that should automatically start when XeroFlow launches."""
    
    def __init__(self):
        """Initialize the auto-startup manager."""
        self.config = load_config()
        
    def get_auto_startup_workflows(self):
        """Get the list of workflow names configured for auto-startup."""
        return self.config.get('auto_startup_workflows', [])
    
    def add_workflow_to_auto_startup(self, workflow_name):
        """Add a workflow to the auto-startup list."""
        auto_startup_workflows = self.get_auto_startup_workflows()
        if workflow_name not in auto_startup_workflows:
            auto_startup_workflows.append(workflow_name)
            self.config['auto_startup_workflows'] = auto_startup_workflows
            save_config(self.config)
            return True
        return False
    
    def remove_workflow_from_auto_startup(self, workflow_name):
        """Remove a workflow from the auto-startup list."""
        auto_startup_workflows = self.get_auto_startup_workflows()
        if workflow_name in auto_startup_workflows:
            auto_startup_workflows.remove(workflow_name)
            self.config['auto_startup_workflows'] = auto_startup_workflows
            save_config(self.config)
            return True
        return False
    
    def load_workflows(self, workflow_dir='workflows'):
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
    
    def start_auto_startup_workflows(self, submit_func, config, output_box, submit_button, stop_button, chat_tab, chat_instruction_listbox, gui_queue, formatting_enabled_var):
        """Start all workflows configured for auto-startup."""
        auto_startup_workflows = self.get_auto_startup_workflows()
        workflows = self.load_workflows()
        workflow_names = [wf['name'] for wf in workflows]
        
        for workflow_name in auto_startup_workflows:
            if workflow_name in workflow_names:
                # Find the index of the workflow in the list
                workflow_index = workflow_names.index(workflow_name)
                
                # Select the workflow in the listbox
                chat_instruction_listbox.selection_clear(0, END)
                chat_instruction_listbox.selection_set(workflow_index)
                chat_instruction_listbox.see(workflow_index)
                chat_tab.selected_prompt_index = workflow_index
                chat_tab.selected_prompt_name = workflow_name
                
                # Submit the workflow with default input
                default_input = f"Auto-startup workflow: {workflow_name}"
                submit_func(
                    config,
                    workflow_index,
                    default_input,
                    output_box,
                    submit_button,
                    stop_button,
                    chat_tab,
                    chat_instruction_listbox,
                    gui_queue,
                    formatting_enabled_var
                )
                
                # Log the auto-startup
                print(f"Auto-started workflow: {workflow_name}")
            else:
                print(f"Warning: Auto-startup workflow '{workflow_name}' not found")

def create_auto_startup_manager_window(parent, config, load_workflows_func=None):
    """Create a window to manage auto-startup workflows."""
    auto_startup_manager = AutoStartupManager()
    
    window = tk.Toplevel(parent)
    window.title("Auto-Startup Workflow Manager")
    window.geometry("500x400")
    window.minsize(400, 300)
    window.transient(parent)
    window.grab_set()
    
    # Center the window
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
    
    # Create frames
    available_frame = ttk.LabelFrame(window, text="Available Workflows")
    available_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    auto_startup_frame = ttk.LabelFrame(window, text="Auto-Startup Workflows")
    auto_startup_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # Available workflows listbox
    available_scrollbar = Scrollbar(available_frame)
    available_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    available_listbox = Listbox(available_frame, selectmode=SINGLE, yscrollcommand=available_scrollbar.set)
    available_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    available_scrollbar.config(command=available_listbox.yview)
    
    # Auto-startup workflows listbox
    auto_startup_scrollbar = Scrollbar(auto_startup_frame)
    auto_startup_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    auto_startup_listbox = Listbox(auto_startup_frame, selectmode=SINGLE, yscrollcommand=auto_startup_scrollbar.set)
    auto_startup_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    auto_startup_scrollbar.config(command=auto_startup_listbox.yview)
    
    # Buttons frame
    buttons_frame = ttk.Frame(window)
    buttons_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
    
    # Populate listboxes
    def update_listboxes():
        available_listbox.delete(0, END)
        auto_startup_listbox.delete(0, END)
        
        if load_workflows_func:
            workflows = load_workflows_func()
        else:
            workflows = auto_startup_manager.load_workflows()
            
        workflow_names = [wf['name'] for wf in workflows]
        auto_startup_workflows = auto_startup_manager.get_auto_startup_workflows()
        
        for name in workflow_names:
            if name not in auto_startup_workflows:
                available_listbox.insert(END, name)
        
        for name in auto_startup_workflows:
            if name in workflow_names:  # Only show existing workflows
                auto_startup_listbox.insert(END, name)
    
    update_listboxes()
    
    # Add button
    def add_to_auto_startup():
        selected_indices = available_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Selection Required", "Please select a workflow to add.")
            return
        
        index = selected_indices[0]
        workflow_name = available_listbox.get(index)
        
        if auto_startup_manager.add_workflow_to_auto_startup(workflow_name):
            update_listboxes()
            messagebox.showinfo("Success", f"Added '{workflow_name}' to auto-startup workflows.")
        else:
            messagebox.showinfo("Already Added", f"'{workflow_name}' is already in auto-startup workflows.")
    
    add_button = ttk.Button(buttons_frame, text="Add >>", command=add_to_auto_startup)
    add_button.pack(side=tk.LEFT, padx=5)
    
    # Remove button
    def remove_from_auto_startup():
        selected_indices = auto_startup_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Selection Required", "Please select a workflow to remove.")
            return
        
        index = selected_indices[0]
        workflow_name = auto_startup_listbox.get(index)
        
        if auto_startup_manager.remove_workflow_from_auto_startup(workflow_name):
            update_listboxes()
            messagebox.showinfo("Success", f"Removed '{workflow_name}' from auto-startup workflows.")
        else:
            messagebox.showinfo("Not Found", f"'{workflow_name}' is not in auto-startup workflows.")
    
    remove_button = ttk.Button(buttons_frame, text="<< Remove", command=remove_from_auto_startup)
    remove_button.pack(side=tk.LEFT, padx=5)
    
    # Close button
    close_button = ttk.Button(buttons_frame, text="Close", command=window.destroy)
    close_button.pack(side=tk.RIGHT, padx=5)
    
    # Double-click handlers
    def on_available_double_click(event):
        add_to_auto_startup()
    
    def on_auto_startup_double_click(event):
        remove_from_auto_startup()
    
    available_listbox.bind('<Double-1>', on_available_double_click)
    auto_startup_listbox.bind('<Double-1>', on_auto_startup_double_click)
    
    window.wait_window()

# Create a singleton instance
auto_startup_manager = AutoStartupManager()

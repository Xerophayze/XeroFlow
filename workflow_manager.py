# workflow_manager.py

import tkinter as tk
from tkinter import ttk, messagebox, Menu, BooleanVar
import threading
import queue
import uuid
import datetime
import time
import json
import os
from ExportWord import convert_markdown_to_docx

class WorkflowInstance:
    """Represents a single workflow instance with its state and data."""
    
    def __init__(self, workflow_name, user_input, thread=None):
        self.id = str(uuid.uuid4())
        self.workflow_name = workflow_name
        self.user_input = user_input
        self.start_time = datetime.datetime.now()
        self.end_time = None
        self.status = "running"  # "running", "completed", "stopped", "error"
        self.thread = thread
        self.stop_event = threading.Event()
        self.output = ""
        self.error = None
    
    def complete(self, output):
        """Mark the workflow as completed with the given output."""
        self.end_time = datetime.datetime.now()
        self.status = "completed"
        self.output = output
    
    def stop(self):
        """Stop the workflow execution."""
        self.stop_event.set()
        self.end_time = datetime.datetime.now()
        self.status = "stopped"
    
    def set_error(self, error):
        """Mark the workflow as failed with the given error."""
        self.end_time = datetime.datetime.now()
        self.status = "error"
        self.error = error
    
    def get_duration(self):
        """Get the duration of the workflow execution."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.datetime.now() - self.start_time).total_seconds()
    
    def get_formatted_duration(self):
        """Get a formatted string of the workflow duration."""
        seconds = self.get_duration()
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        elif minutes > 0:
            return f"{int(minutes)}m {int(seconds)}s"
        else:
            return f"{int(seconds)}s"
    
    def get_status_display(self):
        """Get a display-friendly status string."""
        if self.status == "running":
            return f"Running ({self.get_formatted_duration()})"
        elif self.status == "completed":
            return f"Completed ({self.get_formatted_duration()})"
        elif self.status == "stopped":
            return "Stopped"
        elif self.status == "error":
            return "Error"
        return self.status

class WorkflowManager:
    """Manages multiple workflow instances."""
    
    def __init__(self):
        self.workflows = {}  # Dictionary of workflow instances by ID
        self.listeners = []  # List of callback functions to notify of changes
        
        # Create directories for storing workflow data
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_data")
        self.history_dir = os.path.join(self.data_dir, "history")
        self.log_file = os.path.join(self.data_dir, "workflow_history.json")
        
        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)
        
        self.load_workflow_history()
    
    def create_workflow(self, workflow_name, user_input, thread=None):
        """Create a new workflow instance and return its ID."""
        workflow = WorkflowInstance(workflow_name, user_input, thread)
        self.workflows[workflow.id] = workflow
        self._notify_listeners()
        return workflow
    
    def get_workflow(self, workflow_id):
        """Get a workflow instance by ID."""
        return self.workflows.get(workflow_id)
    
    def get_active_workflows(self):
        """Get all active (running) workflow instances."""
        return {wf_id: wf for wf_id, wf in self.workflows.items() if wf.status == "running"}
    
    def get_completed_workflows(self):
        """Get all completed workflow instances."""
        return {wf_id: wf for wf_id, wf in self.workflows.items() 
                if wf.status in ["completed", "stopped", "error"]}
    
    def stop_workflow(self, workflow_id):
        """Stop a running workflow by ID."""
        workflow = self.get_workflow(workflow_id)
        if workflow and workflow.status == "running":
            workflow.stop()
            self._notify_listeners()
            self.save_workflow_history()  # Save history after workflow is stopped
            return True
        return False
    
    def complete_workflow(self, workflow_id, output):
        """Mark a workflow as completed with the given output."""
        workflow = self.get_workflow(workflow_id)
        if workflow:
            workflow.complete(output)
            self._notify_listeners()
            self.save_workflow_history()  # Save history after workflow is completed
            return True
        return False
    
    def set_workflow_error(self, workflow_id, error):
        """Mark a workflow as failed with the given error."""
        workflow = self.get_workflow(workflow_id)
        if workflow:
            workflow.set_error(error)
            self._notify_listeners()
            self.save_workflow_history()  # Save history after workflow error
            return True
        return False
    
    def add_listener(self, callback):
        """Add a listener function to be called when workflows change."""
        if callback not in self.listeners:
            self.listeners.append(callback)
    
    def remove_listener(self, callback):
        """Remove a listener function."""
        if callback in self.listeners:
            self.listeners.remove(callback)
    
    def _notify_listeners(self):
        """Notify all listeners of a change in workflows."""
        for callback in self.listeners:
            try:
                callback()
            except Exception as e:
                print(f"Error in workflow listener callback: {e}")
    
    def clear_completed_workflows(self):
        """Remove all completed workflows."""
        workflow_ids = list(self.workflows.keys())
        for wf_id in workflow_ids:
            if self.workflows[wf_id].status != "running":
                del self.workflows[wf_id]
        self._notify_listeners()
        self.save_workflow_history()  # Save history after clearing completed workflows
    
    def delete_workflow(self, workflow_id):
        """Delete a specific workflow by ID."""
        if workflow_id in self.workflows:
            # Don't allow deleting running workflows
            if self.workflows[workflow_id].status == "running":
                return False
                
            # Delete associated files
            try:
                input_file = os.path.join(self.history_dir, f"{workflow_id}_input.txt")
                output_file = os.path.join(self.history_dir, f"{workflow_id}_output.txt")
                error_file = os.path.join(self.history_dir, f"{workflow_id}_error.txt")
                
                # Remove files if they exist
                if os.path.exists(input_file):
                    os.remove(input_file)
                if os.path.exists(output_file):
                    os.remove(output_file)
                if os.path.exists(error_file):
                    os.remove(error_file)
            except Exception as e:
                print(f"Error deleting workflow files: {e}")
            
            # Delete the workflow
            del self.workflows[workflow_id]
            self._notify_listeners()
            self.save_workflow_history()  # Save history after deleting workflow
            return True
        return False
    
    def _save_history_threaded(self):
        """Internal method to save history in a separate thread."""
        try:
            # Ensure directories exist
            os.makedirs(self.data_dir, exist_ok=True)
            os.makedirs(self.history_dir, exist_ok=True)

            history_data = []
            # Load existing history to append
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, 'r', encoding='utf-8') as f:
                        history_data = json.load(f)
                except json.JSONDecodeError:
                    print(f"Warning: Could not decode existing history log: {self.log_file}")
                    history_data = [] # Start fresh if corrupted
                except Exception as e:
                    print(f"Error reading history log {self.log_file}: {e}")
                    history_data = []

            # Create a set of existing IDs in the log to avoid duplicates
            existing_ids_in_log = {item.get('id') for item in history_data}

            new_entries_added = False
            for wf_id, wf in list(self.workflows.items()): # Iterate over a copy in case self.workflows changes
                if wf.status in ["completed", "error", "stopped"] and wf_id not in existing_ids_in_log:
                    content_filename = os.path.join(self.history_dir, f"{wf_id}.txt")
                    content_to_save = wf.output if wf.status == "completed" else wf.error if wf.status == "error" else "Workflow stopped by user."
                    
                    try:
                        with open(content_filename, 'w', encoding='utf-8') as f_content:
                            f_content.write(str(content_to_save))
                    except Exception as e:
                        print(f"Error saving content for workflow {wf_id} to {content_filename}: {e}")
                        # Continue, don't let one file error stop all history saving

                    history_entry = {
                        'id': wf.id,
                        'workflow_name': wf.workflow_name,
                        'user_input': wf.user_input,
                        'start_time': wf.start_time.isoformat() if wf.start_time else None,
                        'end_time': wf.end_time.isoformat() if wf.end_time else None,
                        'status': wf.status,
                        'duration': wf.get_formatted_duration(),
                        'content_file': content_filename
                    }
                    history_data.append(history_entry)
                    existing_ids_in_log.add(wf_id) # Add to set to prevent re-adding if called multiple times quickly
                    new_entries_added = True
            
            if new_entries_added:
                try:
                    with open(self.log_file, 'w', encoding='utf-8') as f:
                        json.dump(history_data, f, indent=4)
                except Exception as e:
                    print(f"Error writing workflow history log {self.log_file}: {e}")

        except Exception as e:
            print(f"Error in _save_history_threaded: {e}")
            # Consider more formal logging here

    def save_workflow_history(self):
        """Save completed workflows to a log file and their content to text files asynchronously."""
        save_thread = threading.Thread(target=self._save_history_threaded)
        save_thread.daemon = True # Allow main program to exit even if this thread is running
        save_thread.start()

    def load_workflow_history(self):
        """Load completed workflows from log file and their content from text files."""
        try:
            if not os.path.exists(self.log_file):
                print(f"No workflow history file found at: {self.log_file}")
                return
            
            with open(self.log_file, 'r') as f:
                history_data = json.load(f)
            
            # Convert serialized data back to workflow instances
            for workflow_data in history_data:
                # Create a new workflow instance
                workflow = WorkflowInstance(
                    workflow_data["workflow_name"],
                    ""  # Empty user_input initially
                )
                
                # Set the ID to match the saved ID
                workflow.id = workflow_data["id"]
                
                # Set status
                workflow.status = workflow_data["status"]
                
                # Parse dates
                workflow.start_time = datetime.datetime.fromisoformat(workflow_data["start_time"])
                if workflow_data["end_time"]:
                    workflow.end_time = datetime.datetime.fromisoformat(workflow_data["end_time"])
                
                # Load input from file
                input_file = os.path.join(self.history_dir, workflow_data["input_file"])
                if os.path.exists(input_file):
                    try:
                        with open(input_file, 'r', encoding='utf-8') as f:
                            workflow.user_input = f.read()
                    except Exception as e:
                        print(f"Error reading input file {input_file}: {e}")
                        workflow.user_input = workflow_data.get("input_preview", "")
                else:
                    # Fallback to preview if file doesn't exist
                    workflow.user_input = workflow_data.get("input_preview", "")
                
                # Load output from file if it exists
                if workflow_data["output_file"]:
                    output_file = os.path.join(self.history_dir, workflow_data["output_file"])
                    if os.path.exists(output_file):
                        try:
                            with open(output_file, 'r', encoding='utf-8') as f:
                                workflow.output = f.read()
                        except Exception as e:
                            print(f"Error reading output file {output_file}: {e}")
                            workflow.output = "Error loading output file"
                
                # Load error from file if it exists
                if workflow_data["error_file"]:
                    error_file = os.path.join(self.history_dir, workflow_data["error_file"])
                    if os.path.exists(error_file):
                        try:
                            with open(error_file, 'r', encoding='utf-8') as f:
                                workflow.error = f.read()
                        except Exception as e:
                            print(f"Error reading error file {error_file}: {e}")
                            workflow.error = "Error loading error file"
                
                # Add to workflows dictionary
                self.workflows[workflow.id] = workflow
            
            print(f"Loaded {len(history_data)} workflows from history log: {self.log_file}")
        except Exception as e:
            print(f"Error loading workflow history: {e}")
    
    def export_workflows_to_csv(self, filepath):
        """Export all completed workflows to a CSV file."""
        try:
            import csv
            completed_workflows = self.get_completed_workflows()
            
            # Define CSV headers
            headers = [
                "ID", "Workflow Name", "Input Preview", "Status", 
                "Start Time", "End Time", "Duration"
            ]
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                for wf_id, workflow in completed_workflows.items():
                    # Format dates for CSV
                    start_time = workflow.start_time.strftime("%Y-%m-%d %H:%M:%S") if workflow.start_time else ""
                    end_time = workflow.end_time.strftime("%Y-%m-%d %H:%M:%S") if workflow.end_time else ""
                    
                    # Create input preview
                    input_preview = workflow.user_input[:100] + "..." if len(workflow.user_input) > 100 else workflow.user_input
                    
                    # Prepare row data
                    row = [
                        workflow.id,
                        workflow.workflow_name,
                        input_preview,
                        workflow.status,
                        start_time,
                        end_time,
                        workflow.get_formatted_duration()
                    ]
                    writer.writerow(row)
                
            print(f"Exported {len(completed_workflows)} workflows to: {filepath}")
            return True
        except Exception as e:
            print(f"Error exporting workflows to CSV: {e}")
            return False
    
    def update_workflow_trees(self, active_tree, completed_tree, workflow_tab=None):
        """Update the workflow trees with current data."""
        # Update active workflows
        active_workflows = self.get_active_workflows()
        
        # Remember selected items
        active_selected = active_tree.selection()
        completed_selected = completed_tree.selection()
        
        # Clear current items
        for item in active_tree.get_children():
            active_tree.delete(item)
        
        # Add active workflows
        for wf_id, workflow in active_workflows.items():
            active_tree.insert(
                "", "end", iid=wf_id,
                values=(
                    workflow.workflow_name,
                    workflow.user_input[:50] + "..." if len(workflow.user_input) > 50 else workflow.user_input,
                    workflow.get_formatted_duration(),
                    workflow.get_status_display()
                )
            )
        
        # Restore active selection if possible
        for item_id in active_selected:
            if item_id in active_workflows:
                active_tree.selection_set(item_id)
        
        # Update completed workflows
        completed_workflows = self.get_completed_workflows()
        
        # Clear current items
        for item in completed_tree.get_children():
            completed_tree.delete(item)
        
        # Add completed workflows (most recent first)
        sorted_completed = sorted(
            completed_workflows.values(),
            key=lambda wf: wf.end_time if wf.end_time else datetime.datetime.now(),
            reverse=True
        )
        
        for workflow in sorted_completed:
            completed_tree.insert(
                "", "end", iid=workflow.id,
                values=(
                    workflow.workflow_name,
                    workflow.user_input[:50] + "..." if len(workflow.user_input) > 50 else workflow.user_input,
                    workflow.get_formatted_duration(),
                    workflow.get_status_display()
                )
            )
        
        # Restore completed selection if possible
        for item_id in completed_selected:
            if item_id in completed_workflows:
                completed_tree.selection_set(item_id)

def create_workflow_management_tab(notebook, config, gui_queue):
    """Create and configure the Workflow Management tab."""
    workflow_tab = ttk.Frame(notebook)
    notebook.add(workflow_tab, text='Workflow Management')
    
    workflow_tab.columnconfigure(0, weight=1)
    workflow_tab.rowconfigure(0, weight=0)  # Active Workflows label
    workflow_tab.rowconfigure(1, weight=6)  # Active Workflows tree
    workflow_tab.rowconfigure(2, weight=0)  # Active Workflows buttons
    workflow_tab.rowconfigure(3, weight=0)  # Completed Workflows label
    workflow_tab.rowconfigure(4, weight=4)  # Completed Workflows section
    workflow_tab.rowconfigure(5, weight=0)  # Completed Workflows buttons
    
    # Active workflows section
    active_label = ttk.Label(workflow_tab, text="Active Workflows", font=("", 12, "bold"))
    active_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
    
    # Create treeview for active workflows
    active_frame = ttk.Frame(workflow_tab)
    active_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
    
    active_columns = ("Workflow", "Input", "Time", "Status")
    active_tree = ttk.Treeview(active_frame, columns=active_columns, show="headings", selectmode="browse")
    
    for col, width in zip(active_columns, [150, 300, 100, 100]):
        active_tree.heading(col, text=col)
        active_tree.column(col, width=width)
    
    active_tree.pack(side="left", fill="both", expand=True)
    
    active_scrollbar = ttk.Scrollbar(active_frame, orient="vertical", command=active_tree.yview)
    active_scrollbar.pack(side="right", fill="y")
    active_tree.configure(yscrollcommand=active_scrollbar.set)
    
    # Buttons for active workflows
    active_buttons_frame = ttk.Frame(workflow_tab)
    active_buttons_frame.grid(row=2, column=0, padx=10, pady=5, sticky="w")
    
    stop_button = ttk.Button(
        active_buttons_frame,
        text="Stop Selected",
        command=lambda: stop_selected_workflow(active_tree)
    )
    stop_button.pack(side="left")
    
    # Completed workflows section
    completed_label = ttk.Label(workflow_tab, text="Completed Workflows", font=("", 12, "bold"))
    completed_label.grid(row=3, column=0, sticky="w", padx=10, pady=(20, 5))
    
    # Create a horizontal paned window for completed workflows and details
    completed_paned = ttk.PanedWindow(workflow_tab, orient=tk.HORIZONTAL)
    completed_paned.grid(row=4, column=0, sticky="nsew", padx=10, pady=5)
    
    # Left pane: completed workflows list
    completed_frame = ttk.Frame(completed_paned)
    completed_paned.add(completed_frame, weight=1)
    
    completed_columns = ("Workflow", "Input")
    completed_tree = ttk.Treeview(completed_frame, columns=completed_columns, show="headings", selectmode="browse")
    
    for col, width in zip(completed_columns, [150, 300]):
        completed_tree.heading(col, text=col)
        completed_tree.column(col, width=width)
    
    completed_tree.pack(side="left", fill="both", expand=True)
    
    completed_scrollbar = ttk.Scrollbar(completed_frame, orient="vertical", command=completed_tree.yview)
    completed_scrollbar.pack(side="right", fill="y")
    completed_tree.configure(yscrollcommand=completed_scrollbar.set)
    
    # Right pane: workflow details
    details_frame = ttk.LabelFrame(completed_paned, text="Workflow Details")
    completed_paned.add(details_frame, weight=1)
    
    # Workflow details content
    info_frame = ttk.Frame(details_frame)
    info_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
    
    # Create labels for workflow information
    ttk.Label(info_frame, text="Name:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
    name_label = ttk.Label(info_frame, text="")
    name_label.grid(row=0, column=1, sticky="w", padx=5, pady=2)
    
    ttk.Label(info_frame, text="Status:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
    status_label = ttk.Label(info_frame, text="")
    status_label.grid(row=1, column=1, sticky="w", padx=5, pady=2)
    
    ttk.Label(info_frame, text="Started:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
    started_label = ttk.Label(info_frame, text="")
    started_label.grid(row=2, column=1, sticky="w", padx=5, pady=2)
    
    ttk.Label(info_frame, text="Ended:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
    ended_label = ttk.Label(info_frame, text="")
    ended_label.grid(row=3, column=1, sticky="w", padx=5, pady=2)
    
    # Input section
    ttk.Label(details_frame, text="User Input").grid(row=1, column=0, sticky="w", padx=5, pady=(10, 0))
    
    input_frame = ttk.Frame(details_frame)
    input_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
    details_frame.rowconfigure(2, weight=1)
    
    input_text = tk.Text(input_frame, height=4, wrap="word")
    input_text.pack(side="left", fill="both", expand=True)
    input_text.config(state="disabled")
    
    input_scrollbar = ttk.Scrollbar(input_frame, orient="vertical", command=input_text.yview)
    input_scrollbar.pack(side="right", fill="y")
    input_text.config(yscrollcommand=input_scrollbar.set)
    
    # Output section
    ttk.Label(details_frame, text="Output").grid(row=3, column=0, sticky="w", padx=5, pady=(10, 0))
    
    output_frame = ttk.Frame(details_frame)
    output_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
    details_frame.rowconfigure(4, weight=2)
    
    output_text = tk.Text(output_frame, wrap="word", height=8)
    output_text.pack(side="left", fill="both", expand=True)
    output_text.config(state="disabled")
    
    output_scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=output_text.yview)
    output_scrollbar.pack(side="right", fill="y")
    output_text.config(yscrollcommand=output_scrollbar.set)
    
    # Add mouse event tracking to detect when user is interacting with text boxes
    workflow_tab.user_interacting = False
    workflow_tab.last_refresh_time = time.time()
    
    def on_text_mouse_down(event):
        workflow_tab.user_interacting = True
        
    def on_text_mouse_up(event):
        # Don't immediately set user_interacting to False
        # Keep it True for a while to prevent refresh right after mouse up
        workflow_tab.after(5000, lambda: setattr(workflow_tab, 'user_interacting', False))
    
    def on_scroll(event):
        # Consider scrolling as user interaction
        workflow_tab.user_interacting = True
        workflow_tab.after(5000, lambda: setattr(workflow_tab, 'user_interacting', False))
    
    # Bind mouse events to text widgets
    input_text.bind("<Button-1>", on_text_mouse_down)
    input_text.bind("<ButtonRelease-1>", on_text_mouse_up)
    input_text.bind("<B1-Motion>", lambda e: setattr(workflow_tab, 'user_interacting', True))
    input_text.bind("<MouseWheel>", on_scroll)
    
    output_text.bind("<Button-1>", on_text_mouse_down)
    output_text.bind("<ButtonRelease-1>", on_text_mouse_up)
    output_text.bind("<B1-Motion>", lambda e: setattr(workflow_tab, 'user_interacting', True))
    output_text.bind("<MouseWheel>", on_scroll)
    
    # Formatting checkbox and Export to Word button
    export_frame = ttk.Frame(details_frame)
    export_frame.grid(row=5, column=0, padx=5, pady=5, sticky="w")
    
    formatting_var = tk.BooleanVar(value=True)
    formatting_checkbox = ttk.Checkbutton(
        export_frame,
        text="Enable Formatting",
        variable=formatting_var,
        command=lambda: update_workflow_details(workflow_tab, workflow_tab.last_selected_workflow_id, formatting_var)
    )
    formatting_checkbox.pack(side="left")
    
    export_button = ttk.Button(
        export_frame,
        text="Export Docx",
        command=lambda: export_to_docx(workflow_tab, workflow_tab.last_selected_workflow_id, formatting_var)
    )
    export_button.pack(side="left", padx=(10, 0))
    
    # Buttons for completed workflows
    completed_buttons_frame = ttk.Frame(workflow_tab)
    completed_buttons_frame.grid(row=5, column=0, padx=10, pady=5, sticky="w")
    
    clear_button = ttk.Button(
        completed_buttons_frame,
        text="Clear All Completed",
        command=clear_completed_workflows
    )
    clear_button.pack(side="left")
    
    delete_button = ttk.Button(
        completed_buttons_frame,
        text="Delete Selected",
        command=lambda: delete_selected_workflow(workflow_tab, completed_tree)
    )
    delete_button.pack(side="left", padx=(10, 0))
    
    export_csv_button = ttk.Button(
        completed_buttons_frame,
        text="Export CSV",
        command=lambda: export_workflows_to_csv(workflow_tab)
    )
    export_csv_button.pack(side="left", padx=(10, 0))
    
    # Store elements for later access
    workflow_tab.elements = {
        'active_tree': active_tree,
        'completed_tree': completed_tree,
        'name_label': name_label,
        'status_label': status_label,
        'started_label': started_label,
        'ended_label': ended_label,
        'input_text': input_text,
        'output_text': output_text,
        'formatting_var': formatting_var
    }
    
    # Store the last selected workflow ID
    workflow_tab.last_selected_workflow_id = None
    
    # Set up selection change event
    completed_tree.bind("<<TreeviewSelect>>", lambda event: on_completed_workflow_selected(event, workflow_tab, formatting_var))
    
    # Set up periodic refresh
    def refresh_trees():
        current_time = time.time()
        
        # Skip refresh if user is interacting with text boxes
        if hasattr(workflow_tab, 'user_interacting') and workflow_tab.user_interacting:
            workflow_tab.after(1000, refresh_trees)
            return
            
        # Don't refresh too frequently
        if hasattr(workflow_tab, 'last_refresh_time') and current_time - workflow_tab.last_refresh_time < 2:
            workflow_tab.after(1000, refresh_trees)
            return
            
        workflow_tab.last_refresh_time = current_time
        
        # Remember the last selected workflow in completed tree
        last_selected_id = None
        if completed_tree.selection():
            last_selected_id = completed_tree.selection()[0]
            workflow_tab.last_selected_workflow_id = last_selected_id
        
        # Save text selections and scroll positions
        try:
            # Save text selections
            input_selection = None
            output_selection = None
            
            if input_text.tag_ranges("sel"):
                input_selection = (
                    input_text.index("sel.first"),
                    input_text.index("sel.last")
                )
            
            if output_text.tag_ranges("sel"):
                output_selection = (
                    output_text.index("sel.first"),
                    output_text.index("sel.last")
                )
                
            # Save scroll positions
            input_scroll = None
            output_scroll = None
            completed_scroll = None
            
            if input_text.winfo_viewable():
                input_scroll = input_text.yview()
                
            if output_text.winfo_viewable():
                output_scroll = output_text.yview()
                
            if completed_tree.winfo_viewable():
                completed_scroll = completed_tree.yview()
                
            # Update the trees using the workflow manager's method
            workflow_manager.update_workflow_trees(active_tree, completed_tree, workflow_tab)
            
            # Restore the last selected workflow if it still exists
            if last_selected_id and last_selected_id in completed_tree.get_children():
                completed_tree.selection_set(last_selected_id)
                completed_tree.see(last_selected_id)
                update_workflow_details(workflow_tab, last_selected_id, formatting_var)
            
            # Restore text selections
            if input_selection:
                input_text.tag_add("sel", input_selection[0], input_selection[1])
                
            if output_selection:
                output_text.tag_add("sel", output_selection[0], output_selection[1])
                
            # Restore scroll positions
            if input_scroll:
                input_text.yview_moveto(input_scroll[0])
                
            if output_scroll:
                output_text.yview_moveto(output_scroll[0])
                
            if completed_scroll:
                completed_tree.yview_moveto(completed_scroll[0])
        except:
            # If there's any error restoring selection or scroll position, just continue
            pass
    
        workflow_tab.after(1000, refresh_trees)
    
    workflow_tab.after(1000, refresh_trees)
    
    return workflow_tab

def update_workflow_trees(active_tree, completed_tree, workflow_tab=None):
    """Update the workflow trees with current data."""
    # Update active workflows
    active_workflows = workflow_manager.get_active_workflows()
    
    # Remember selected items
    active_selected = active_tree.selection()
    completed_selected = completed_tree.selection()
    
    # Clear current items
    for item in active_tree.get_children():
        active_tree.delete(item)
    
    # Add active workflows
    for wf_id, workflow in active_workflows.items():
        active_tree.insert(
            "", "end", iid=wf_id,
            values=(
                workflow.workflow_name,
                workflow.user_input[:50] + "..." if len(workflow.user_input) > 50 else workflow.user_input,
                workflow.get_formatted_duration(),
                workflow.get_status_display()
            )
        )
    
    # Restore active selection if possible
    for item_id in active_selected:
        if item_id in active_workflows:
            active_tree.selection_set(item_id)
    
    # Update completed workflows
    completed_workflows = workflow_manager.get_completed_workflows()
    
    # Clear current items
    for item in completed_tree.get_children():
        completed_tree.delete(item)
    
    # Add completed workflows (most recent first)
    sorted_completed = sorted(
        completed_workflows.values(),
        key=lambda wf: wf.end_time if wf.end_time else datetime.datetime.now(),
        reverse=True
    )
    
    for workflow in sorted_completed:
        completed_tree.insert(
            "", "end", iid=workflow.id,
            values=(
                workflow.workflow_name,
                workflow.user_input[:50] + "..." if len(workflow.user_input) > 50 else workflow.user_input,
                workflow.get_formatted_duration(),
                workflow.get_status_display()
            )
        )
    
    # Restore completed selection if possible
    for item_id in completed_selected:
        if item_id in completed_workflows:
            completed_tree.selection_set(item_id)

def update_workflow_details(workflow_tab, workflow_id, formatting_var=None):
    """Update the details panel with the selected workflow information."""
    workflow = workflow_manager.get_workflow(workflow_id)
    if not workflow:
        clear_workflow_details(workflow_tab)
        return
    
    elements = workflow_tab.elements
    
    # Update labels
    elements['name_label'].config(text=workflow.workflow_name)
    elements['status_label'].config(text=workflow.get_status_display())
    elements['started_label'].config(text=workflow.start_time.strftime('%Y-%m-%d %H:%M:%S'))
    
    if workflow.end_time:
        elements['ended_label'].config(text=workflow.end_time.strftime('%Y-%m-%d %H:%M:%S'))
    else:
        elements['ended_label'].config(text="N/A")
    
    # Update input text
    elements['input_text'].config(state="normal")
    elements['input_text'].delete("1.0", tk.END)
    elements['input_text'].insert("1.0", workflow.user_input)
    elements['input_text'].config(state="disabled")
    
    # Update output text
    elements['output_text'].config(state="normal")
    elements['output_text'].delete("1.0", tk.END)
    
    if workflow.status == "error" and workflow.error:
        elements['output_text'].insert("1.0", f"ERROR: {workflow.error}")
        elements['output_text'].tag_configure("error", foreground="red")
        elements['output_text'].tag_add("error", "1.0", "end")
    else:
        if formatting_var and formatting_var.get():
            # Apply formatting
            elements['output_text'].insert("1.0", workflow.output)
        else:
            elements['output_text'].insert("1.0", workflow.output)
    
    elements['output_text'].config(state="disabled")

def clear_workflow_details(workflow_tab):
    """Clear the details panel."""
    elements = workflow_tab.elements
    
    # Clear labels
    elements['name_label'].config(text="")
    elements['status_label'].config(text="")
    elements['started_label'].config(text="")
    elements['ended_label'].config(text="")
    
    # Clear text widgets
    elements['input_text'].config(state="normal")
    elements['input_text'].delete("1.0", tk.END)
    elements['input_text'].config(state="disabled")
    
    elements['output_text'].config(state="normal")
    elements['output_text'].delete("1.0", tk.END)
    elements['output_text'].config(state="disabled")

def stop_selected_workflow(active_tree):
    """Stop the selected workflow."""
    selected_items = active_tree.selection()
    if not selected_items:
        messagebox.showinfo("Selection Required", "Please select a workflow to stop.")
        return
    
    workflow_id = selected_items[0]
    if workflow_manager.stop_workflow(workflow_id):
        messagebox.showinfo("Success", "Workflow has been stopped.")
    else:
        messagebox.showerror("Error", "Failed to stop workflow.")

def delete_selected_workflow(workflow_tab, completed_tree):
    """Delete the selected workflow."""
    selected_items = completed_tree.selection()
    if not selected_items:
        messagebox.showinfo("Selection Required", "Please select a workflow to delete.")
        return
    
    workflow_id = selected_items[0]
    if workflow_manager.delete_workflow(workflow_id):
        messagebox.showinfo("Success", "Workflow has been deleted.")
    else:
        messagebox.showerror("Error", "Failed to delete workflow.")

def clear_completed_workflows():
    """Clear all completed workflows."""
    if messagebox.askyesno("Confirm", "Are you sure you want to clear all completed workflows?"):
        workflow_manager.clear_completed_workflows()

def export_to_docx(workflow_tab, workflow_id, formatting_var):
    """Export the selected workflow output to a Word document."""
    workflow = workflow_manager.get_workflow(workflow_id)
    if not workflow or not workflow.output:
        messagebox.showinfo("Export", "No content to export.")
        return
            
    try:
        convert_markdown_to_docx(workflow.output, formatting_enabled=formatting_var.get())
        messagebox.showinfo("Export", "Workflow output exported to Word document successfully.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while exporting to Word: {e}")

def export_workflows_to_csv(workflow_tab):
    """Export all completed workflows to a CSV file."""
    from tkinter import filedialog
    import os
    
    # Get default filename based on current date
    default_filename = f"workflow_history_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # Ask user for save location
    filepath = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialfile=default_filename,
        title="Export Workflows to CSV"
    )
    
    if not filepath:  # User cancelled
        return
    
    if workflow_manager.export_workflows_to_csv(filepath):
        messagebox.showinfo("Export Successful", f"Workflows exported to:\n{filepath}")
    else:
        messagebox.showerror("Export Failed", "Failed to export workflows. Check console for details.")

def on_completed_workflow_selected(event, workflow_tab, formatting_var):
    """Handle selection of a completed workflow."""
    selected_items = workflow_tab.elements['completed_tree'].selection()
    if selected_items:
        workflow_id = selected_items[0]
        workflow_tab.last_selected_workflow_id = workflow_id
        update_workflow_details(workflow_tab, workflow_id, formatting_var)

# Create a singleton instance
workflow_manager = WorkflowManager()

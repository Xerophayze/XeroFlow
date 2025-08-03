import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
import os
import shutil
import uuid
import json
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageTk  # Add PIL for image handling

# Import TkinterDnD2 if available
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False

class XeroFlowClient:
    def __init__(self, root):
        self.root = root
        self.root.title("XeroFlow Client")
        self.root.geometry("900x700")
        self.root.minsize(700, 600)
        
        # Initialize variables
        self.project_files = []
        self.inbox_folders = {}  # Dictionary of name: path for input folders
        self.outbox_folder = ""
        self.current_inbox_folder = ""  # Currently selected inbox folder
        self.load_settings()
        
        # Configure grid weights
        self.root.grid_rowconfigure(0, weight=0)  # Changed to 0 for logo row
        self.root.grid_rowconfigure(1, weight=1)  # Added for notebook
        self.root.grid_columnconfigure(0, weight=1)
        
        # Add logo at the top
        self.add_logo()
        
        # Create a notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)  # Changed to row=1
        
        # Create tabs
        self.settings_tab = ttk.Frame(self.notebook)
        self.submit_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.settings_tab, text="Settings")
        self.notebook.add(self.submit_tab, text="Project")
        self.notebook.add(self.results_tab, text="Results")
        
        # Setup tabs
        self.setup_settings_tab()
        self.setup_submit_tab()
        self.setup_results_tab()
        
        # Set Project tab as the default
        self.notebook.select(1)  # Index 1 is the Project tab
        
        # Bind tab change event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
    
    def add_logo(self):
        """Add logo to the top of the application"""
        try:
            # Get the script directory
            script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            logo_path = script_dir / "logo.png"
            
            if logo_path.exists():
                # Create a frame for the logo
                logo_frame = ttk.Frame(self.root)
                logo_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
                logo_frame.grid_columnconfigure(0, weight=1)
                
                # Load and resize the logo while maintaining aspect ratio
                original_img = Image.open(logo_path)
                # Set a maximum width and height
                max_width = 200
                max_height = 80
                
                # Calculate new dimensions while preserving aspect ratio
                width, height = original_img.size
                ratio = min(max_width/width, max_height/height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                
                # Resize the image
                resized_img = original_img.resize((new_width, new_height), Image.LANCZOS)
                
                # Convert to PhotoImage
                self.logo_img = ImageTk.PhotoImage(resized_img)
                
                # Create and place the logo label
                logo_label = ttk.Label(logo_frame, image=self.logo_img)
                logo_label.grid(row=0, column=0)
                
                # Add a separator below the logo
                separator = ttk.Separator(self.root, orient='horizontal')
                separator.grid(row=0, column=0, sticky="ews", padx=5, pady=(80, 0))
                
        except Exception as e:
            print(f"Error loading logo: {str(e)}")
            # If logo can't be loaded, add a text header instead
            header_label = ttk.Label(self.root, text="XeroFlow Client", font=("Helvetica", 16, "bold"))
            header_label.grid(row=0, column=0, sticky="ew", padx=5, pady=10)
        
    def load_settings(self):
        """Load settings from config file"""
        # Get the script directory
        script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        config_path = script_dir / "xeroflow_client_config.json"
        
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    self.inbox_folders = config.get("inbox_folders", {})
                    self.outbox_folder = config.get("outbox_folder", "")
                    
                    # Set current inbox folder to the first one if available
                    if self.inbox_folders:
                        self.current_inbox_folder = next(iter(self.inbox_folders.values()))
            except Exception as e:
                print(f"Error loading config: {str(e)}")
        
    def save_settings(self):
        """Save settings to config file"""
        config = {
            "inbox_folders": self.inbox_folders,
            "outbox_folder": self.outbox_folder
        }
        
        # Get the script directory
        script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        config_path = script_dir / "xeroflow_client_config.json"
        
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {str(e)}")
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")
    
    def setup_settings_tab(self):
        """Setup the settings tab"""
        # Configure grid weights
        self.settings_tab.grid_rowconfigure(4, weight=1)
        self.settings_tab.grid_columnconfigure(1, weight=1)
        
        # Input folders section
        ttk.Label(self.settings_tab, text="Input Folders:").grid(row=0, column=0, sticky="w", padx=5, pady=10)
        
        # Frame for input folders list and buttons
        input_frame = ttk.Frame(self.settings_tab)
        input_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=5, pady=5)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(0, weight=1)
        
        # Create a frame for the listbox and its scrollbar
        list_frame = ttk.Frame(input_frame)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # Listbox for input folders with scrollbar
        self.input_folders_listbox = tk.Listbox(list_frame, height=5)
        self.input_folders_listbox.grid(row=0, column=0, sticky="nsew")
        
        folders_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.input_folders_listbox.yview)
        folders_scrollbar.grid(row=0, column=1, sticky="ns")
        self.input_folders_listbox.config(yscrollcommand=folders_scrollbar.set)
        
        # Populate the listbox with saved input folders
        self.refresh_input_folders_list()
        
        # Buttons for input folder management
        buttons_frame = ttk.Frame(input_frame)
        buttons_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        add_folder_button = ttk.Button(buttons_frame, text="Add Folder", command=self.add_input_folder)
        add_folder_button.pack(side=tk.LEFT, padx=5)
        
        remove_folder_button = ttk.Button(buttons_frame, text="Remove Selected", command=self.remove_input_folder)
        remove_folder_button.pack(side=tk.LEFT, padx=5)
        
        edit_folder_button = ttk.Button(buttons_frame, text="Edit Selected", command=self.edit_input_folder)
        edit_folder_button.pack(side=tk.LEFT, padx=5)
        
        # Outbox folder
        ttk.Label(self.settings_tab, text="Outbox Folder:").grid(row=3, column=0, sticky="w", padx=5, pady=10)
        self.outbox_entry = ttk.Entry(self.settings_tab, width=50)
        self.outbox_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=10)
        self.outbox_entry.insert(0, self.outbox_folder)
        ttk.Button(self.settings_tab, text="Browse...", command=self.browse_outbox).grid(row=3, column=2, padx=5, pady=10)
        
        # Save button
        save_button = ttk.Button(self.settings_tab, text="Save Settings", command=self.save_settings_from_ui)
        save_button.grid(row=5, column=1, pady=20)
        
        # Information text
        info_frame = ttk.LabelFrame(self.settings_tab, text="Information")
        info_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=10, pady=10)
        info_frame.grid_columnconfigure(0, weight=1)
        info_frame.grid_rowconfigure(0, weight=1)
        
        info_text = scrolledtext.ScrolledText(info_frame, wrap=tk.WORD, height=10)
        info_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        info_text.insert(tk.END, "XeroFlow Client\n\n")
        info_text.insert(tk.END, "This application allows you to submit projects to XeroFlow.\n\n")
        info_text.insert(tk.END, "1. Add input folders with descriptive names in the Settings tab.\n")
        info_text.insert(tk.END, "2. Create new projects in the Project tab by selecting an input folder.\n")
        info_text.insert(tk.END, "3. View results in the Results tab.\n\n")
        info_text.insert(tk.END, "Input folders are where new projects are submitted.\n")
        info_text.insert(tk.END, "The outbox folder is where completed projects appear.")
        info_text.config(state=tk.DISABLED)
    
    def refresh_input_folders_list(self):
        """Refresh the list of input folders in the listbox"""
        self.input_folders_listbox.delete(0, tk.END)
        for name, path in self.inbox_folders.items():
            self.input_folders_listbox.insert(tk.END, f"{name} ({path})")
    
    def add_input_folder(self):
        """Add a new input folder"""
        folder = filedialog.askdirectory(title="Select Input Folder")
        if not folder:
            return
            
        # Ask for a name for this folder
        name = simpledialog.askstring("Input Folder Name", "Enter a name for this input folder:")
        if not name:
            return
            
        # Check if name already exists
        if name in self.inbox_folders:
            messagebox.showerror("Error", f"A folder with the name '{name}' already exists.")
            return
            
        # Add to the dictionary
        self.inbox_folders[name] = folder
        
        # Update the listbox
        self.refresh_input_folders_list()
        
        # Set as current if it's the first one
        if len(self.inbox_folders) == 1:
            self.current_inbox_folder = folder
            
        # Refresh the input folder dropdown in the Project tab
        self.refresh_input_folder_combo()
        
    def remove_input_folder(self):
        """Remove the selected input folder"""
        selected = self.input_folders_listbox.curselection()
        if not selected:
            messagebox.showinfo("Info", "No folder selected to remove.")
            return
            
        # Get the selected item
        index = selected[0]
        item_text = self.input_folders_listbox.get(index)
        
        # Extract the name from the item text (format: "name (path)")
        name = item_text.split(" (")[0]
        
        # Remove from dictionary
        if name in self.inbox_folders:
            del self.inbox_folders[name]
            
            # Update the listbox
            self.refresh_input_folders_list()
            
            # Update current inbox folder if needed
            if self.inbox_folders:
                self.current_inbox_folder = next(iter(self.inbox_folders.values()))
            else:
                self.current_inbox_folder = ""
                
            # Refresh the input folder dropdown in the Project tab
            self.refresh_input_folder_combo()
    
    def edit_input_folder(self):
        """Edit the selected input folder"""
        selected = self.input_folders_listbox.curselection()
        if not selected:
            messagebox.showinfo("Info", "No folder selected to edit.")
            return
            
        # Get the selected item
        index = selected[0]
        item_text = self.input_folders_listbox.get(index)
        
        # Extract the name from the item text (format: "name (path)")
        name = item_text.split(" (")[0]
        
        # Ask for a new name
        new_name = simpledialog.askstring("Edit Folder Name", "Enter a new name for this input folder:", initialvalue=name)
        if not new_name or new_name == name:
            return
            
        # Check if new name already exists
        if new_name in self.inbox_folders and new_name != name:
            messagebox.showerror("Error", f"A folder with the name '{new_name}' already exists.")
            return
            
        # Update the dictionary
        path = self.inbox_folders[name]
        del self.inbox_folders[name]
        self.inbox_folders[new_name] = path
        
        # Update the listbox
        self.refresh_input_folders_list()
        
        # Refresh the input folder dropdown in the Project tab
        self.refresh_input_folder_combo()
    
    def browse_outbox(self):
        """Browse for outbox folder"""
        folder = filedialog.askdirectory(title="Select Outbox Folder")
        if folder:
            self.outbox_entry.delete(0, tk.END)
            self.outbox_entry.insert(0, folder)
    
    def save_settings_from_ui(self):
        """Save settings from UI fields"""
        self.outbox_folder = self.outbox_entry.get()
        
        # Validate folders
        if not self.inbox_folders:
            messagebox.showerror("Error", "Please add at least one input folder.")
            return
        
        if not self.outbox_folder:
            messagebox.showerror("Error", "Please select an outbox folder.")
            return
        
        # Create folders if they don't exist
        for path in self.inbox_folders.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        
        Path(self.outbox_folder).mkdir(parents=True, exist_ok=True)
        
        self.save_settings()
        
        # Refresh the input folder dropdown in the Project tab
        self.refresh_input_folder_combo()
        
        messagebox.showinfo("Success", "Settings saved successfully.")
    
    def setup_submit_tab(self):
        """Setup the submit project tab"""
        # Configure grid weights
        self.submit_tab.grid_rowconfigure(0, weight=0)  # Input folder selection
        self.submit_tab.grid_rowconfigure(1, weight=0)  # Project name label
        self.submit_tab.grid_rowconfigure(2, weight=0)  # Project name entry
        self.submit_tab.grid_rowconfigure(3, weight=0)  # Instructions label
        self.submit_tab.grid_rowconfigure(4, weight=2)  # Instructions text
        self.submit_tab.grid_rowconfigure(5, weight=0)  # Files label
        self.submit_tab.grid_rowconfigure(6, weight=1)  # Files list
        self.submit_tab.grid_columnconfigure(0, weight=1)
        
        # Input folder selection
        folder_frame = ttk.Frame(self.submit_tab)
        folder_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        ttk.Label(folder_frame, text="Select Input Folder:").pack(side=tk.LEFT, padx=5)
        
        # Create a combobox for input folder selection
        self.input_folder_var = tk.StringVar()
        self.input_folder_combo = ttk.Combobox(folder_frame, textvariable=self.input_folder_var, state="readonly")
        self.input_folder_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.input_folder_combo.bind("<<ComboboxSelected>>", self.on_input_folder_selected)
        
        # Refresh the input folder combobox
        self.refresh_input_folder_combo()
        
        # Project name section
        ttk.Label(self.submit_tab, text="Project Name (optional):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        
        # Entry for project name
        self.project_name_var = tk.StringVar()
        self.project_name_entry = ttk.Entry(self.submit_tab, textvariable=self.project_name_var, width=80)
        self.project_name_entry.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        # Instructions section
        ttk.Label(self.submit_tab, text="Instructions:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        
        # Text area for instructions
        self.instructions_text = scrolledtext.ScrolledText(self.submit_tab, wrap=tk.WORD, height=10)
        self.instructions_text.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
        
        # Files section
        ttk.Label(self.submit_tab, text="Files:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        
        # Frame for files list and buttons
        files_frame = ttk.Frame(self.submit_tab)
        files_frame.grid(row=6, column=0, sticky="nsew", padx=5, pady=5)
        files_frame.grid_columnconfigure(0, weight=1)
        files_frame.grid_rowconfigure(0, weight=1)
        
        # Create a frame for the listbox and its scrollbar
        list_frame = ttk.Frame(files_frame)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # Listbox for files with scrollbar
        self.files_listbox = tk.Listbox(list_frame, height=5)
        self.files_listbox.grid(row=0, column=0, sticky="nsew")
        
        # Add scrollbar to the listbox
        listbox_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.files_listbox.yview)
        listbox_scrollbar.grid(row=0, column=1, sticky="ns")
        self.files_listbox.config(yscrollcommand=listbox_scrollbar.set)
        
        # Buttons frame
        buttons_frame = ttk.Frame(files_frame)
        buttons_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        add_button = ttk.Button(buttons_frame, text="Add Files", command=self.add_files)
        add_button.pack(side=tk.LEFT, padx=5)
        
        remove_button = ttk.Button(buttons_frame, text="Remove Selected", command=self.remove_selected_file)
        remove_button.pack(side=tk.LEFT, padx=5)
        
        clear_button = ttk.Button(buttons_frame, text="Clear All", command=self.clear_files)
        clear_button.pack(side=tk.LEFT, padx=5)
        
        # Add some space between file buttons and submit button
        ttk.Separator(buttons_frame, orient='vertical').pack(side=tk.LEFT, fill='y', padx=15, pady=5)
        
        submit_button = ttk.Button(buttons_frame, text="Submit Project", command=self.submit_project)
        submit_button.pack(side=tk.LEFT, padx=5)
        
        # Setup drag and drop for files
        if TKDND_AVAILABLE:
            try:
                self.files_listbox.drop_target_register(DND_FILES)
                self.files_listbox.dnd_bind('<<Drop>>', self.handle_drop)
                # Add a label to indicate drag and drop is available
                drag_label = ttk.Label(files_frame, text="Drag and drop files here", font=("Helvetica", 9, "italic"))
                drag_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)
            except Exception as e:
                print(f"Error setting up drag and drop: {str(e)}")
        else:
            # Add a label to indicate drag and drop is not available
            no_drag_label = ttk.Label(files_frame, text="Drag and drop not available - install tkinterdnd2", 
                                      font=("Helvetica", 9, "italic"), foreground="gray")
            no_drag_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)
    
    def refresh_input_folder_combo(self):
        """Refresh the input folder combobox"""
        self.input_folder_combo['values'] = list(self.inbox_folders.keys())
        
        # Set the current selection if available
        if self.inbox_folders:
            for name, path in self.inbox_folders.items():
                if path == self.current_inbox_folder:
                    self.input_folder_var.set(name)
                    break
            else:
                # If current folder not found, select the first one
                self.input_folder_var.set(next(iter(self.inbox_folders.keys())))
    
    def on_input_folder_selected(self, event):
        """Handle input folder selection"""
        selected_name = self.input_folder_var.get()
        if selected_name in self.inbox_folders:
            self.current_inbox_folder = self.inbox_folders[selected_name]
    
    def submit_project(self):
        """Submit the project for processing"""
        # Get the instructions text
        instructions = self.instructions_text.get(1.0, tk.END).strip()
        
        if not instructions:
            messagebox.showerror("Error", "Please enter instructions before submitting.")
            return
            
        # Validate input folder
        if not self.current_inbox_folder:
            messagebox.showerror("Error", "No input folder selected. Please select an input folder from the dropdown.")
            return
            
        inbox_folder = Path(self.current_inbox_folder)
        if not inbox_folder.exists():
            messagebox.showerror("Error", f"Input folder does not exist: {inbox_folder}")
            return
            
        # Create a timestamp for the project folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate a unique ID (first 8 chars of a UUID)
        unique_id = str(uuid.uuid4())[:8]
        
        # Get custom project name if provided
        custom_name = self.project_name_var.get().strip()
        
        # Create a project folder in the inbox with custom name (if provided) plus timestamp and unique ID
        if custom_name:
            project_name = f"{custom_name}_{timestamp}_{unique_id}"
        else:
            project_name = f"Assistant_Project_{timestamp}_{unique_id}"
            
        project_folder = inbox_folder / project_name
        project_folder.mkdir(exist_ok=True)
        
        # Create the instructions file with file references
        instructions_file = project_folder / "Assistant_instructions.txt"
        
        with open(instructions_file, 'w', encoding='utf-8') as f:
            # Write project name meta tag if custom name is set
            if custom_name:
                f.write(f"#PROJECT_NAME: {custom_name}\n")
            f.write(instructions)
            
            # Add file references if there are any
            if self.project_files:
                f.write("\n\n")
                for file_path in self.project_files:
                    file_name = Path(file_path).name
                    f.write(f"[{file_name}]\n")
        
        # Copy all project files to the project folder
        for file_path in self.project_files:
            source_path = Path(file_path)
            if source_path.exists() and source_path.is_file():
                # Copy the file to the project folder
                target_path = project_folder / source_path.name
                shutil.copy2(str(source_path), str(target_path))
            else:
                messagebox.showerror("Error", f"File not found, skipping: {source_path}")
        
        # Clear the form after submission
        self.instructions_text.delete(1.0, tk.END)
        self.project_name_var.set("")  # Clear the project name field
        self.clear_files()
        
        messagebox.showinfo("Success", f"Project submitted successfully to: {project_folder}")
    
    def on_tab_changed(self, event):
        """Handle tab change events"""
        selected_tab = self.notebook.index(self.notebook.select())
        if selected_tab == 1:  # Project tab
            # Refresh the input folder dropdown when switching to Project tab
            self.refresh_input_folder_combo()
        elif selected_tab == 2:  # Results tab
            self.refresh_file_tree()
    
    def setup_results_tab(self):
        """Setup the results tab with file browser"""
        # Configure grid weights
        self.results_tab.grid_rowconfigure(1, weight=1)
        self.results_tab.grid_columnconfigure(0, weight=1)
        
        # Controls frame
        controls_frame = ttk.Frame(self.results_tab)
        controls_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        refresh_button = ttk.Button(controls_frame, text="Refresh", command=self.refresh_file_tree)
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        delete_button = ttk.Button(controls_frame, text="Delete Selected", command=self.delete_selected_items)
        delete_button.pack(side=tk.LEFT, padx=5)
        
        # File tree frame
        tree_frame = ttk.Frame(self.results_tab)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create treeview with scrollbars
        self.file_tree = ttk.Treeview(tree_frame, selectmode="extended")  # Allow multiple selection
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tree_scrollbar_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        tree_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree_scrollbar_x = ttk.Scrollbar(self.results_tab, orient="horizontal", command=self.file_tree.xview)
        tree_scrollbar_x.grid(row=2, column=0, sticky="ew", padx=5)
        
        self.file_tree.configure(yscrollcommand=tree_scrollbar_y.set, xscrollcommand=tree_scrollbar_x.set)
        
        # Configure treeview
        self.file_tree["columns"] = ("size", "modified")
        self.file_tree.column("#0", width=300, minwidth=200)
        self.file_tree.column("size", width=100, minwidth=80)
        self.file_tree.column("modified", width=150, minwidth=120)
        
        # Create separate functions for each column header to avoid lambda issues
        self.file_tree.heading("#0", text="Name", command=self.sort_by_name)
        self.file_tree.heading("size", text="Size", command=self.sort_by_size)
        self.file_tree.heading("modified", text="Modified", command=self.sort_by_modified)
        
        # Track sorting state
        self.sort_column = None
        self.sort_reverse = False
        
        # Bind events - use a custom double-click handler that checks the click target
        self.file_tree.bind("<Double-1>", self.handle_double_click)
        self.file_tree.bind("<Button-3>", self.on_file_right_click)
        
        # Create context menu
        self.file_context_menu = tk.Menu(self.root, tearoff=0)
        self.file_context_menu.add_command(label="Open", command=self.open_file)
        self.file_context_menu.add_command(label="Open Containing Folder", command=self.open_containing_folder)
        self.file_context_menu.add_separator()
        self.file_context_menu.add_command(label="Delete", command=self.delete_file)
        self.file_context_menu.add_separator()
        self.file_context_menu.add_command(label="Copy Path", command=self.copy_file_path)
    
    def refresh_file_tree(self):
        """Refresh the file tree with the current outbox folder contents"""
        # Clear existing items
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # Check if outbox folder is set
        if not self.outbox_folder:
            return
        
        outbox_path = Path(self.outbox_folder)
        if not outbox_path.exists():
            return
        
        # Populate the tree directly with outbox contents (not showing outbox as root)
        try:
            # Sort the items by name initially (directories first)
            items = sorted(outbox_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            
            # Add each item to the tree
            for path in items:
                # Skip hidden files and folders
                if path.name.startswith('.'):
                    continue
                    
                # Get file/folder info
                info = path.stat()
                size = info.st_size
                modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                # Format size
                if path.is_file():
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                else:
                    size_str = ""
                
                # Insert into tree
                item_id = self.file_tree.insert(
                    "", 
                    "end", 
                    text=path.name, 
                    values=(size_str, modified),
                    open=False
                )
                
                # Store the full path as a tag
                self.file_tree.item(item_id, tags=(str(path),))
                
                # If it's a directory, add its children
                if path.is_dir():
                    self.populate_tree(item_id, path)
            
            # After populating the tree, sort by modified date (newest first)
            self.sort_column = "modified"
            self.sort_reverse = True  # True for descending order (newest first)
            
            # Force the sorting to be newest first by setting the reverse flag correctly
            # and updating the column header to show the correct direction
            self.file_tree.heading("modified", text=self.get_column_title("modified") + " ▼", 
                                  command=self.sort_by_modified)
            
            # Sort all items in the tree
            for parent_id in self.get_all_parents():
                self.sort_children(parent_id, "modified")
                    
        except Exception as e:
            print(f"Error accessing outbox folder: {str(e)}")
            messagebox.showerror("Error", f"Error accessing outbox folder: {str(e)}")
    
    def populate_tree(self, parent, path):
        """Recursively populate the tree with folder contents"""
        try:
            # Sort the items by name initially (directories first)
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            
            # Add each item to the tree
            for child_path in items:
                # Skip hidden files and folders
                if child_path.name.startswith('.'):
                    continue
                    
                # Get file/folder info
                info = child_path.stat()
                size = info.st_size
                modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                # Format size
                if child_path.is_file():
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                else:
                    size_str = ""
                
                # Insert into tree
                item_id = self.file_tree.insert(
                    parent, 
                    "end", 
                    text=child_path.name, 
                    values=(size_str, modified),
                    open=False
                )
                
                # Store the full path as a tag
                self.file_tree.item(item_id, tags=(str(child_path),))
                
                # If it's a directory, add its children recursively
                if child_path.is_dir():
                    self.populate_tree(item_id, child_path)
                    
        except Exception as e:
            print(f"Error accessing {path}: {str(e)}")
    
    def get_full_path(self, item_id):
        """Get the full path for a tree item"""
        tags = self.file_tree.item(item_id, "tags")
        if tags:
            return Path(tags[0])
        return None
    
    def handle_double_click(self, event):
        """Handle double-click events, distinguishing between column headers and tree items"""
        region = self.file_tree.identify_region(event.x, event.y)
        
        # If clicking on a column header, ignore the double-click
        if region == "heading":
            return "break"
            
        # Otherwise, process as a normal double-click on a tree item
        self.on_file_double_click(event)
        return "break"
    
    def on_file_double_click(self, event):
        """Handle double-click event on a file"""
        self.open_file()
    
    def on_file_right_click(self, event):
        """Handle right-click event on a file"""
        # Select the item under the cursor without clearing the current selection
        item_id = self.file_tree.identify_row(event.y)
        if item_id:
            # If the item under cursor is not already selected, select only this item
            if item_id not in self.file_tree.selection():
                # If holding Ctrl, add to selection, otherwise replace selection
                if event.state & 0x0004:  # Check if Ctrl key is pressed
                    self.file_tree.selection_add(item_id)
                else:
                    self.file_tree.selection_set(item_id)
            
            # Show context menu
            self.file_context_menu.post(event.x_root, event.y_root)
    
    def open_file(self):
        """Open the selected file with the default application"""
        # Get the selected item
        selected = self.file_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "No file selected.")
            return
            
        # Get the full path
        item_path = self.get_full_path(selected[0])
        
        if not item_path or not item_path.exists():
            messagebox.showerror("Error", f"File not found: {item_path}")
            return
            
        # Open the file with the default application
        if item_path.is_file():
            try:
                os.startfile(str(item_path))
            except:
                # Fallback for non-Windows platforms
                if sys.platform == 'darwin':  # macOS
                    subprocess.call(('open', str(item_path)))
                else:  # Linux and other Unix-like
                    subprocess.call(('xdg-open', str(item_path)))
        else:
            # If it's a directory, expand/collapse it
            if self.file_tree.item(selected[0], "open"):
                self.file_tree.item(selected[0], open=False)
            else:
                self.file_tree.item(selected[0], open=True)
    
    def open_containing_folder(self):
        """Open the folder containing the selected file"""
        # Get the selected item
        selected = self.file_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "No file selected.")
            return
            
        # Get the full path
        item_path = self.get_full_path(selected[0])
        
        if not item_path or not item_path.exists():
            messagebox.showerror("Error", f"Path not found: {item_path}")
            return
            
        # If it's a file, get its parent folder
        if item_path.is_file():
            folder_path = item_path.parent
        else:
            folder_path = item_path
            
        # Open the folder in file explorer
        try:
            os.startfile(str(folder_path))
        except:
            # Fallback for non-Windows platforms
            if sys.platform == 'darwin':  # macOS
                subprocess.call(('open', str(folder_path)))
            else:  # Linux and other Unix-like
                subprocess.call(('xdg-open', str(folder_path)))
    
    def delete_file(self):
        """Delete the selected file or folder"""
        # Get all selected items
        selected = self.file_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "No file selected.")
            return
            
        # If only one item is selected, handle it as before
        if len(selected) == 1:
            self.delete_single_item(selected[0])
        else:
            # Handle multiple selection
            self.delete_multiple_items(selected)
    
    def delete_single_item(self, item_id):
        """Delete a single file or folder"""
        # Get the full path
        item_path = self.get_full_path(item_id)
        
        if not item_path or not item_path.exists():
            messagebox.showerror("Error", f"Path not found: {item_path}")
            return
            
        # Confirm deletion
        if item_path.is_dir():
            confirm = messagebox.askyesno("Confirm", f"Are you sure you want to delete the folder '{item_path.name}' and all its contents?")
        else:
            confirm = messagebox.askyesno("Confirm", f"Are you sure you want to delete the file '{item_path.name}'?")
            
        if not confirm:
            return
            
        # Delete the file or folder
        try:
            if item_path.is_dir():
                shutil.rmtree(str(item_path))
            else:
                item_path.unlink()
                
            # Remove from tree
            self.file_tree.delete(item_id)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error deleting: {str(e)}")
    
    def delete_multiple_items(self, item_ids):
        """Delete multiple files and/or folders"""
        # Collect items to delete (only the directly selected items)
        items_to_delete = []
        
        for item_id in item_ids:
            item_path = self.get_full_path(item_id)
            if item_path:
                items_to_delete.append((item_id, item_path))
        
        if not items_to_delete:
            messagebox.showinfo("Info", "No valid items selected.")
            return
        
        # Filter out items that are inside selected folders to avoid double deletion
        filtered_items = []
        folder_paths = [str(path) for _, path in items_to_delete if path.exists() and path.is_dir()]
        
        for item_id, item_path in items_to_delete:
            # Check if this item is inside any of the selected folders
            is_inside_selected_folder = False
            item_path_str = str(item_path)
            
            for folder_path in folder_paths:
                # Check if the item's path starts with the folder path plus a separator
                if item_path_str.startswith(folder_path + os.sep) and item_path_str != folder_path:
                    is_inside_selected_folder = True
                    break
            
            # Only include the item if it's not inside a selected folder
            if not is_inside_selected_folder:
                filtered_items.append((item_id, item_path))
        
        # Count files and folders for the confirmation message
        file_count = sum(1 for _, path in filtered_items if path.exists() and path.is_file())
        folder_count = sum(1 for _, path in filtered_items if path.exists() and path.is_dir())
        
        # Confirm deletion with counts
        message = f"Are you sure you want to delete {file_count} file(s) and {folder_count} folder(s)?"
        confirm = messagebox.askyesno("Confirm Multiple Deletion", message)
        
        if not confirm:
            return
        
        # Delete all items
        errors = []
        deleted_count = 0
        
        for item_id, item_path in filtered_items:
            try:
                # Only try to delete if the path exists
                if item_path.exists():
                    if item_path.is_dir():
                        shutil.rmtree(str(item_path))
                    else:
                        item_path.unlink()
                    deleted_count += 1
                
                # Always remove from tree
                self.file_tree.delete(item_id)
                
            except Exception as e:
                # Still remove from tree even if deletion fails
                try:
                    self.file_tree.delete(item_id)
                except:
                    pass
                
                # Add to errors list
                error_msg = str(e)
                # Truncate very long error messages
                if len(error_msg) > 100:
                    error_msg = error_msg[:97] + "..."
                errors.append(f"{item_path.name}: {error_msg}")
        
        # Report results
        if errors:
            if deleted_count > 0:
                message = f"Successfully deleted {deleted_count} item(s).\n\nErrors occurred with {len(errors)} item(s):"
            else:
                message = "Errors occurred while deleting:"
                
            # Limit the number of errors shown to prevent extremely large dialog boxes
            if len(errors) > 5:
                error_message = message + "\n\n" + "\n".join(errors[:5]) + f"\n\n...and {len(errors) - 5} more errors."
            else:
                error_message = message + "\n\n" + "\n".join(errors)
                
            messagebox.showerror("Deletion Errors", error_message)
        elif deleted_count > 0:
            messagebox.showinfo("Success", f"Successfully deleted {deleted_count} item(s).")
    
    def delete_selected_items(self):
        """Delete all selected items (called from Delete button)"""
        self.delete_file()  # Reuse existing delete logic
    
    def copy_file_path(self):
        """Copy the path of the selected file to the clipboard"""
        # Get the selected item
        selected = self.file_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "No file selected.")
            return
            
        # If multiple items are selected, copy the first one
        item_id = selected[0]
        
        # Get the full path
        item_path = self.get_full_path(item_id)
        
        if not item_path:
            messagebox.showerror("Error", "Could not determine file path.")
            return
            
        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(str(item_path))
        
        messagebox.showinfo("Success", "Path copied to clipboard.")
    
    def sort_by_name(self):
        """Sort by name column"""
        # Explicitly handle the event to prevent it from propagating to double-click
        self.sort_tree_column("#0", False)
        return "break"  # Stop event propagation
    
    def sort_by_size(self):
        """Sort by size column"""
        # Explicitly handle the event to prevent it from propagating to double-click
        self.sort_tree_column("size", False)
        return "break"  # Stop event propagation
    
    def sort_by_modified(self):
        """Sort by modified column"""
        # Explicitly handle the event to prevent it from propagating to double-click
        self.sort_tree_column("modified", False)
        return "break"  # Stop event propagation
        
    def sort_tree_column(self, column, reset_sort):
        """Sort tree contents when a column header is clicked"""
        # If clicking the same column, reverse the sort order
        if self.sort_column == column and not reset_sort:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        
        # Update the column header to show sort direction
        for col in ["#0", "size", "modified"]:
            if col == column:
                direction = " ▼" if not self.sort_reverse else " ▲"
                if col == "#0":
                    self.file_tree.heading(col, text=self.get_column_title(col) + direction, command=self.sort_by_name)
                elif col == "size":
                    self.file_tree.heading(col, text=self.get_column_title(col) + direction, command=self.sort_by_size)
                elif col == "modified":
                    self.file_tree.heading(col, text=self.get_column_title(col) + direction, command=self.sort_by_modified)
            else:
                if col == "#0":
                    self.file_tree.heading(col, text=self.get_column_title(col), command=self.sort_by_name)
                elif col == "size":
                    self.file_tree.heading(col, text=self.get_column_title(col), command=self.sort_by_size)
                elif col == "modified":
                    self.file_tree.heading(col, text=self.get_column_title(col), command=self.sort_by_modified)
        
        # Sort each parent's children
        for parent_id in self.get_all_parents():
            self.sort_children(parent_id, column)
    
    def get_column_title(self, column):
        """Get the base column title without sort indicators"""
        titles = {"#0": "Name", "size": "Size", "modified": "Modified"}
        return titles.get(column, column)
    
    def get_all_parents(self):
        """Get all parent items in the tree, including the root"""
        parents = [""]  # Root is an empty string
        for item_id in self.file_tree.get_children():
            if self.file_tree.get_children(item_id):
                parents.append(item_id)
                # Add any nested parents
                parents.extend(self.get_nested_parents(item_id))
        return parents
    
    def get_nested_parents(self, parent_id):
        """Recursively get all nested parent items"""
        parents = []
        for item_id in self.file_tree.get_children(parent_id):
            if self.file_tree.get_children(item_id):
                parents.append(item_id)
                parents.extend(self.get_nested_parents(item_id))
        return parents
    
    def sort_children(self, parent_id, column):
        """Sort the children of a parent item"""
        # Get all children of this parent
        children = list(self.file_tree.get_children(parent_id))
        if not children:
            return
        
        # Prepare items for sorting
        items_with_values = []
        for item_id in children:
            # Get the value to sort by
            if column == "#0":
                # Sort by name
                value = self.file_tree.item(item_id, "text").lower()
                # Directories first
                is_dir = bool(self.file_tree.get_children(item_id))
                items_with_values.append((item_id, (not is_dir, value)))
            elif column == "size":
                # Sort by size
                size_str = self.file_tree.item(item_id, "values")[0]
                # Convert size string to numeric value for sorting
                if size_str.endswith(" B"):
                    size_val = float(size_str.replace(" B", ""))
                elif size_str.endswith(" KB"):
                    size_val = float(size_str.replace(" KB", "")) * 1024
                elif size_str.endswith(" MB"):
                    size_val = float(size_str.replace(" MB", "")) * 1024 * 1024
                else:
                    size_val = 0
                # Directories first
                is_dir = bool(self.file_tree.get_children(item_id))
                items_with_values.append((item_id, (not is_dir, size_val)))
            elif column == "modified":
                # Sort by modification date
                modified_str = self.file_tree.item(item_id, "values")[1]
                # Directories first
                is_dir = bool(self.file_tree.get_children(item_id))
                items_with_values.append((item_id, (not is_dir, modified_str)))
        
        # Sort the items
        items_with_values.sort(key=lambda x: x[1], reverse=self.sort_reverse)
        
        # Rearrange items in the tree
        for idx, (item_id, _) in enumerate(items_with_values):
            self.file_tree.move(item_id, parent_id, idx)

    def add_files(self):
        """Open a file dialog to add files to the project"""
        files = filedialog.askopenfilenames(
            title="Select files to add to the project",
            filetypes=[
                ("All Files", "*.*"),
                ("Text Files", "*.txt"),
                ("PDF Files", "*.pdf"),
                ("Word Documents", "*.docx"),
                ("Excel Files", "*.xlsx *.xls"),
                ("CSV Files", "*.csv"),
                ("Audio Files", "*.mp3 *.wav *.m4a *.ogg"),
                ("Video Files", "*.mp4 *.avi *.mov *.mkv")
            ]
        )
        
        # Add each selected file to the project
        for file_path in files:
            self.add_file_to_project(file_path)
    
    def add_file_to_project(self, file_path):
        """Add a file to the project list"""
        file_path = Path(file_path)
        
        # Check if file exists
        if not file_path.exists() or not file_path.is_file():
            messagebox.showerror("Error", f"File not found: {file_path}")
            return
            
        # Check if file is already in the list
        if str(file_path) in self.project_files:
            messagebox.showinfo("Info", f"File already added: {file_path.name}")
            return
            
        # Add to the list of project files
        self.project_files.append(str(file_path))
        
        # Add to the listbox
        self.files_listbox.insert(tk.END, f"{file_path.name} ({file_path})")
    
    def handle_drop(self, event):
        """Handle files dropped onto the widget"""
        try:
            # Get the dropped data
            data = event.data
            print(f"Raw drop data: {data}")  # Debug print
            
            # Check if it's a file path or paths
            if data:
                # TkinterDnD2 returns paths differently depending on the platform
                if sys.platform == 'win32':
                    # Special case: Check if this is a single file path with spaces
                    # If the path exists as-is, treat it as a single file
                    if os.path.exists(data) or os.path.exists(data.strip()):
                        # It's a single file path, add it directly
                        clean_path = data.strip()
                        print(f"Single file detected: {clean_path}")
                        self.add_file_to_project(clean_path)
                        return
                    
                    # First, handle the case where the entire data is enclosed in curly braces
                    if data.startswith('{') and data.endswith('}'):
                        # Check if this is a single path in braces
                        inner_data = data[1:-1]
                        if os.path.exists(inner_data):
                            # It's a single file path in braces
                            print(f"Single file in braces: {inner_data}")
                            self.add_file_to_project(inner_data)
                            return
                        # Otherwise, continue with normal processing
                        data = inner_data
                    
                    # For Windows, we need to handle multiple paths carefully
                    # The data might look like: {C:/path with spaces/file1.txt} {C:/another path/file2.txt}
                    # or "C:/path with spaces/file1.txt" "C:/another path/file2.txt"
                    
                    paths = []
                    # Use a more robust approach to extract paths
                    i = 0
                    current_path = ""
                    in_braces = False
                    in_quotes = False
                    
                    while i < len(data):
                        char = data[i]
                        
                        # Handle opening/closing braces
                        if char == '{' and not in_quotes:
                            in_braces = True
                            i += 1
                            continue
                        elif char == '}' and not in_quotes and in_braces:
                            in_braces = False
                            if current_path:
                                paths.append(current_path)
                                current_path = ""
                            i += 1
                            continue
                        
                        # Handle quotes
                        elif char == '"' and not in_braces:
                            in_quotes = not in_quotes
                            if not in_quotes and current_path:  # End of quoted path
                                paths.append(current_path)
                                current_path = ""
                            i += 1
                            continue
                        
                        # Handle spaces outside of braces/quotes as separators
                        elif char == ' ' and not in_braces and not in_quotes:
                            if current_path:
                                paths.append(current_path)
                                current_path = ""
                            i += 1
                            continue
                        
                        # Add character to current path
                        current_path += char
                        i += 1
                    
                    # Add the last path if there is one
                    if current_path:
                        paths.append(current_path)
                    
                    # Clean up paths (remove any remaining quotes)
                    cleaned_paths = []
                    for path in paths:
                        path = path.strip()
                        if path.startswith('"') and path.endswith('"'):
                            path = path[1:-1]
                        cleaned_paths.append(path)
                    
                    # If we have multiple path fragments but none of them exist as files,
                    # try to reconstruct the original path with spaces
                    if len(cleaned_paths) > 1 and not any(os.path.exists(p) for p in cleaned_paths):
                        original_path = data.strip()
                        if os.path.exists(original_path):
                            print(f"Reconstructed path: {original_path}")
                            self.add_file_to_project(original_path)
                            return
                    
                    # Add each file to the project
                    files_added = 0
                    for path in cleaned_paths:
                        if path and os.path.exists(path):  # Only add if path exists
                            print(f"Adding file: {path}")  # Debug print
                            self.add_file_to_project(path)
                            files_added += 1
                    
                    # If no valid files were found, try the original data as a single path
                    if files_added == 0 and os.path.exists(data):
                        print(f"Fallback to original path: {data}")
                        self.add_file_to_project(data)
                        files_added = 1
                else:
                    # On macOS and Linux, paths are usually separated by newlines
                    paths = data.split('\n')
                    files_added = 0
                    for path in paths:
                        path = path.strip()
                        if path and os.path.exists(path):  # Skip empty paths and check existence
                            self.add_file_to_project(path)
                            files_added += 1
                
                # Show a success message if files were added
                if files_added > 0:
                    messagebox.showinfo("Success", f"{files_added} file(s) added to the project successfully.")
        except Exception as e:
            print(f"Error handling dropped files: {str(e)}")
            messagebox.showerror("Error", f"Error handling dropped files: {str(e)}")
    
    def remove_selected_file(self):
        """Remove the selected file from the project"""
        # Get selected index
        selected = self.files_listbox.curselection()
        
        if not selected:
            messagebox.showinfo("Info", "No file selected to remove.")
            return
            
        # Get the index
        index = selected[0]
        
        # Remove from the project files list
        if 0 <= index < len(self.project_files):
            file_path = self.project_files.pop(index)
            
            # Remove from the listbox
            self.files_listbox.delete(index)
    
    def clear_files(self):
        """Clear all files from the project"""
        # Clear the project files list
        self.project_files = []
        
        # Clear the listbox
        self.files_listbox.delete(0, tk.END)

def main():
    if TKDND_AVAILABLE:
        # Use TkinterDnD.Tk instead of tk.Tk if available
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = XeroFlowClient(root)
    root.mainloop()

if __name__ == "__main__":
    main()

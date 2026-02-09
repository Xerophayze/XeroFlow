"""
Manage Modules Window for XeroFlow.
This module provides a UI for managing module settings.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
from pathlib import Path
import os

def manage_modules_window(parent_frame, config, refresh_callback=None):
    """
    Create a window for managing module settings.
    
    Args:
        parent_frame: The parent frame to place the window in
        config: The application configuration
        refresh_callback: Callback function to refresh the UI after changes
    """
    # Create main frame
    main_frame = ttk.Frame(parent_frame)
    main_frame.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Create module selection frame
    selection_frame = ttk.LabelFrame(main_frame, text="Select Module")
    selection_frame.pack(fill='x', padx=5, pady=5)
    
    # Get available modules
    try:
        from modules.preprocess import PreProcess
        preprocess = PreProcess(config)
        modules = preprocess.get_available_modules()
    except Exception as e:
        modules = ["PreProcess"]  # Default if module not available
        print(f"Error loading modules: {str(e)}")
    
    # Create module selection dropdown
    selected_module = tk.StringVar(value=modules[0] if modules else "")
    module_dropdown = ttk.Combobox(selection_frame, textvariable=selected_module, values=modules, state="readonly")
    module_dropdown.pack(fill='x', padx=5, pady=5)
    
    # Create settings frame
    settings_frame = ttk.LabelFrame(main_frame, text="Module Settings")
    settings_frame.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Create prompt label and text area
    prompt_label = ttk.Label(settings_frame, text="Prompt Template:")
    prompt_label.pack(anchor='w', padx=5, pady=(5, 0))
    
    prompt_text = scrolledtext.ScrolledText(settings_frame, height=10, wrap=tk.WORD)
    prompt_text.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Create API endpoint selection
    api_label = ttk.Label(settings_frame, text="API Endpoint:")
    api_label.pack(anchor='w', padx=5, pady=(5, 0))
    
    # Get available API endpoints
    api_endpoints = list(config.get('interfaces', {}).keys())
    selected_api = tk.StringVar(value=api_endpoints[0] if api_endpoints else "")
    api_dropdown = ttk.Combobox(settings_frame, textvariable=selected_api, values=api_endpoints, state="readonly")
    api_dropdown.pack(fill='x', padx=5, pady=5)
    
    # Function to load module settings
    def load_module_settings(event=None):
        module_name = selected_module.get()
        if not module_name:
            return
        
        try:
            # Get module settings
            module_settings = preprocess.get_module_settings(module_name)
            
            # Update UI with settings
            prompt_text.delete(1.0, tk.END)
            prompt_text.insert(tk.END, module_settings.get("prompt", ""))
            
            api_endpoint = module_settings.get("api_endpoint", "")
            if api_endpoint in api_endpoints:
                selected_api.set(api_endpoint)
            elif api_endpoints:
                selected_api.set(api_endpoints[0])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load module settings: {str(e)}")
    
    # Function to save module settings
    def save_module_settings():
        module_name = selected_module.get()
        if not module_name:
            messagebox.showwarning("Warning", "Please select a module")
            return
        
        # Get settings from UI
        prompt = prompt_text.get(1.0, tk.END).strip()
        api_endpoint = selected_api.get()
        
        # Create settings dictionary
        settings = {
            "prompt": prompt,
            "api_endpoint": api_endpoint
        }
        
        try:
            # Save settings
            success = preprocess.save_module_config(module_name, settings)
            
            if success:
                # messagebox.showinfo("Success", f"Settings for {module_name} saved successfully")
                if refresh_callback:
                    refresh_callback()
            else:
                messagebox.showerror("Error", f"Failed to save settings for {module_name}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save module settings: {str(e)}")
    
    # Function to add a new module
    def add_new_module():
        # Create a new dialog window
        dialog = tk.Toplevel(parent_frame)
        dialog.title("Add New Module")
        dialog.geometry("300x150")
        dialog.transient(parent_frame)
        dialog.grab_set()
        
        # Create a label and entry for module name
        ttk.Label(dialog, text="Module Name:").pack(padx=10, pady=(10, 5))
        module_name_var = tk.StringVar()
        module_name_entry = ttk.Entry(dialog, textvariable=module_name_var)
        module_name_entry.pack(fill='x', padx=10, pady=5)
        
        # Create buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        def on_cancel():
            dialog.destroy()
        
        def on_add():
            module_name = module_name_var.get().strip()
            if not module_name:
                messagebox.showwarning("Warning", "Please enter a module name", parent=dialog)
                return
            
            # Check if module already exists
            if module_name in modules:
                messagebox.showwarning("Warning", f"Module '{module_name}' already exists", parent=dialog)
                return
            
            # Create default settings for new module
            settings = {
                "prompt": "Process the following text: ",
                "api_endpoint": api_endpoints[0] if api_endpoints else ""
            }
            
            try:
                # Save settings
                success = preprocess.save_module_config(module_name, settings)
                
                if success:
                    # messagebox.showinfo("Success", f"Module '{module_name}' added successfully")
                    # Update modules list
                    modules.append(module_name)
                    module_dropdown['values'] = modules
                    selected_module.set(module_name)
                    load_module_settings()
                    if refresh_callback:
                        refresh_callback()
                else:
                    messagebox.showerror("Error", f"Failed to add module '{module_name}'")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add module: {str(e)}")
            
            dialog.destroy()
        
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Add", command=on_add).pack(side='right', padx=5)
        
        # Focus on the entry
        module_name_entry.focus_set()
    
    # Function to delete a module
    def delete_module():
        module_name = selected_module.get()
        if not module_name:
            messagebox.showwarning("Warning", "Please select a module")
            return
        
        # Confirm deletion
        if not messagebox.askyesno("Confirm", f"Are you sure you want to delete module '{module_name}'?"):
            return
        
        try:
            # Load existing settings
            config_dir = Path("config")
            config_file = config_dir / "module_settings.json"
            
            if not config_file.exists():
                messagebox.showwarning("Warning", "No module settings file found")
                return
            
            with open(config_file, 'r') as f:
                module_settings = json.load(f)
            
            # Remove module
            if "modules" in module_settings and module_name in module_settings["modules"]:
                del module_settings["modules"][module_name]
                
                # Save updated settings
                with open(config_file, 'w') as f:
                    json.dump(module_settings, f, indent=4)
                
                # Update modules list
                modules.remove(module_name)
                module_dropdown['values'] = modules
                if modules:
                    selected_module.set(modules[0])
                    load_module_settings()
                else:
                    prompt_text.delete(1.0, tk.END)
                    if api_endpoints:
                        selected_api.set(api_endpoints[0])
                
                # messagebox.showinfo("Success", f"Module '{module_name}' deleted successfully")
                if refresh_callback:
                    refresh_callback()
            else:
                messagebox.showwarning("Warning", f"Module '{module_name}' not found in settings")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete module: {str(e)}")
    
    # Create buttons frame
    buttons_frame = ttk.Frame(main_frame)
    buttons_frame.pack(fill='x', padx=5, pady=10)
    
    # Add buttons
    ttk.Button(buttons_frame, text="Add Module", command=add_new_module).pack(side='left', padx=5)
    ttk.Button(buttons_frame, text="Delete Module", command=delete_module).pack(side='left', padx=5)
    ttk.Button(buttons_frame, text="Save Settings", command=save_module_settings).pack(side='right', padx=5)
    
    # Bind module selection to load settings
    module_dropdown.bind("<<ComboboxSelected>>", load_module_settings)
    
    # Load initial settings
    load_module_settings()
    
    return main_frame

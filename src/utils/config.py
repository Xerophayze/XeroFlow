# config_utils.py

import yaml
import os
from tkinter import messagebox, Text
import tkinter as tk

def load_config(config_file='config.yaml'):
    """Load configuration from a YAML file."""
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            print(f"Loaded configuration from '{config_file}'.")
    except FileNotFoundError:
        config = {'interfaces': {}, 'seed_prompts': [], 'auto_startup_workflows': []}
        print(f"Configuration file '{config_file}' not found. Using default configuration.")

    # Ensure seed_prompts is a list
    if 'seed_prompts' not in config or not isinstance(config['seed_prompts'], list):
        config['seed_prompts'] = []
        print("Initialized 'seed_prompts' as an empty list.")

    # Ensure interfaces is a dictionary
    if 'interfaces' not in config or not isinstance(config['interfaces'], dict):
        config['interfaces'] = {}
        print("Initialized 'interfaces' as an empty dictionary.")
        
    # Ensure auto_startup_workflows is a list
    if 'auto_startup_workflows' not in config or not isinstance(config['auto_startup_workflows'], list):
        config['auto_startup_workflows'] = []
        print("Initialized 'auto_startup_workflows' as an empty list.")

    # Print loaded interfaces for debugging
    print(f"Available API Interfaces: {list(config['interfaces'].keys())}")

    return config

def save_config(config, config_file='config.yaml'):
    """Save the updated config to the YAML file."""
    try:
        with open(config_file, 'w') as file:
            yaml.safe_dump(config, file)
            print(f"Configuration saved to '{config_file}'.")
    except Exception as e:
        print(f"Failed to save configuration to '{config_file}': {e}")
        messagebox.showerror("Error", f"Failed to save configuration: {e}")

def apply_formatting(output_box: Text, text: str):
    """Apply formatting to the output_box and insert the text."""
    output_box.config(state=tk.NORMAL)
    output_box.delete('1.0', tk.END)
    output_box.insert(tk.END, text)
    
    # Example: Simple bold formatting for specific keywords
    # Modify this section based on your actual formatting needs
    # Here's a placeholder for adding text formatting
    # For more complex formatting, consider using Pygments or other libraries
    
    # Example: Make "Error" bold and red
    start_index = "1.0"
    while True:
        pos = output_box.search("Error", start_index, stopindex=tk.END)
        if not pos:
            break
        end_pos = f"{pos}+{len('Error')}c"
        output_box.tag_add("error", pos, end_pos)
        start_index = end_pos
    output_box.tag_config("error", foreground="red", font=("Helvetica", 10, "bold"))
    
    output_box.config(state=tk.DISABLED)

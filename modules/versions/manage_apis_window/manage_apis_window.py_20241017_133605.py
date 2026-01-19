# manage_apis_window.py

import tkinter as tk
from tkinter import ttk, messagebox
import requests
from src.utils.config import save_config  # Importing from config_utils.py
import logging

def manage_apis_window(parent, config, refresh_callback):
    """Embed the Manage APIs interface within the given parent frame."""

    def refresh_api_list():
        api_manage_listbox.delete(0, tk.END)
        for key in config['interfaces']:
            api_manage_listbox.insert(tk.END, key)

    def add_api_interface():
        clear_form()
        api_manage_listbox.selection_clear(0, tk.END)
        save_button.config(text="Add API Interface", command=save_new_interface)

    def edit_api_interface():
        selected = api_manage_listbox.curselection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select an API Interface to edit.")
            return
        index = selected[0]
        selected_interface = api_manage_listbox.get(index)
        interface_details = config['interfaces'][selected_interface]

        # Ensure values are strings and handle None values
        name_entry.delete(0, tk.END)
        name_entry.insert(0, selected_interface)
        url_entry.delete(0, tk.END)
        url_entry.insert(0, interface_details.get('url', ''))
        api_key_entry.delete(0, tk.END)
        api_key_value = interface_details.get('api_key', '') or ''
        api_key_entry.insert(0, api_key_value)
        api_type_dropdown.set(interface_details.get('api_type', 'OpenAI'))
        max_tokens_entry.delete(0, tk.END)
        max_tokens_value = str(interface_details.get('max_tokens', '')) or ''
        max_tokens_entry.insert(0, max_tokens_value)

        update_models_dropdown(default_model=interface_details.get('model', ''))

        save_button.config(text="Save Changes", command=lambda: save_edited_interface(selected_interface))

    def delete_api_interface():
        selected = api_manage_listbox.curselection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select an API Interface to delete.")
            return
        index = selected[0]
        selected_interface = api_manage_listbox.get(index)
        confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the API Interface '{selected_interface}'?")
        if confirm:
            config['interfaces'].pop(selected_interface)
            save_config(config)
            refresh_api_list()
            clear_form()
            refresh_callback()  # Notify main app to refresh dropdowns if necessary
            messagebox.showinfo("Success", f"API Interface '{selected_interface}' has been deleted.")

    def save_new_interface():
        name = name_entry.get().strip()
        url = url_entry.get().strip()
        api_key = api_key_entry.get().strip()
        api_type = api_type_dropdown.get().strip()
        model = model_dropdown.get().strip()
        max_tokens = max_tokens_entry.get().strip()

        if not name or not url or not api_type or not model:
            messagebox.showwarning("Input Required", "Please fill in all required fields.")
            return

        if name in config['interfaces']:
            messagebox.showerror("Error", "An API Interface with this name already exists.")
            return

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
        refresh_api_list()
        clear_form()
        refresh_callback()  # Notify main app to refresh dropdowns if necessary
        messagebox.showinfo("Success", "New API Interface added.")

    def save_edited_interface(original_name):
        new_name = name_entry.get().strip()
        url = url_entry.get().strip()
        api_key = api_key_entry.get().strip()
        api_type = api_type_dropdown.get().strip()
        model = model_dropdown.get().strip()
        max_tokens = max_tokens_entry.get().strip()

        if not new_name or not url or not api_type or not model:
            messagebox.showwarning("Input Required", "Please fill in all required fields.")
            return

        if new_name != original_name and new_name in config['interfaces']:
            messagebox.showerror("Error", "An API Interface with this name already exists.")
            return

        if api_type == "OpenAI":
            models_endpoint = "/v1/chat/completions"
        elif api_type == "Ollama":
            models_endpoint = "/api/tags"
        else:
            messagebox.showerror("Error", f"Unsupported API Type '{api_type}'.")
            return

        # Remove the old entry and add the new/edited one
        config['interfaces'].pop(original_name)
        config['interfaces'][new_name] = {
            'url': url,
            'api_key': api_key,
            'model': model,
            'models_endpoint': models_endpoint,
            'api_type': api_type,
            'max_tokens': int(max_tokens) if max_tokens else None
        }
        save_config(config)
        refresh_api_list()
        clear_form()
        refresh_callback()  # Notify main app to refresh dropdowns if necessary
        messagebox.showinfo("Success", "API Interface updated successfully.")

    def update_models_dropdown(default_model=None):
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
            if default_model and default_model in models:
                model_dropdown.set(default_model)
            else:
                model_dropdown.set(models[0])
        else:
            model_dropdown['values'] = []
            model_dropdown.set('')
            messagebox.showerror("Error", "Failed to fetch models. Check the URL, API key, or network connection.")

    def fetch_models(api_url, api_key, api_type):
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
                    logging.error(f"Error fetching models: {response.status_code} - {response.text}")
                    return []
            elif api_type == "Ollama":
                response = requests.get(api_url.rstrip('/') + "/api/tags", headers=headers)
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_names = [model['name'] for model in models]
                    return model_names
                else:
                    logging.error(f"Error fetching models: {response.status_code} - {response.text}")
                    return []
            else:
                messagebox.showerror("Error", f"Unsupported API Type '{api_type}'.")
                return []
        except Exception as e:
            logging.error(f"Error: {e}")
            return []

    def clear_form():
        name_entry.delete(0, tk.END)
        url_entry.delete(0, tk.END)
        api_key_entry.delete(0, tk.END)
        api_type_dropdown.set("OpenAI")
        model_dropdown['values'] = []
        model_dropdown.set('')
        max_tokens_entry.delete(0, tk.END)
        save_button.config(text="Add API Interface", command=save_new_interface)

    # Configure the parent frame's grid to allow dynamic resizing
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)  # API List
    parent.rowconfigure(1, weight=0)  # Buttons
    parent.rowconfigure(2, weight=2)  # API Details Form

    # ------------------ API List Frame ------------------
    api_list_frame = ttk.LabelFrame(parent, text="API Interfaces")
    api_list_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
    api_list_frame.columnconfigure(0, weight=1)
    api_list_frame.rowconfigure(0, weight=1)

    api_manage_scrollbar = ttk.Scrollbar(api_list_frame, orient=tk.VERTICAL)
    api_manage_listbox = tk.Listbox(
        api_list_frame,
        selectmode=tk.SINGLE,
        yscrollcommand=api_manage_scrollbar.set,
        exportselection=False
    )
    for key in config['interfaces']:
        api_manage_listbox.insert(tk.END, key)
    api_manage_listbox.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)
    api_manage_scrollbar.config(command=api_manage_listbox.yview)
    api_manage_scrollbar.grid(row=0, column=1, sticky="ns", pady=5, padx=(0, 5))

    # ------------------ Buttons Frame ------------------
    buttons_frame = ttk.Frame(parent)
    buttons_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
    buttons_frame.columnconfigure((0, 1, 2), weight=1)

    add_api_button = ttk.Button(buttons_frame, text="Add", command=add_api_interface)
    add_api_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

    edit_api_button = ttk.Button(buttons_frame, text="Edit", command=edit_api_interface)
    edit_api_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    delete_api_button = ttk.Button(buttons_frame, text="Delete", command=delete_api_interface)
    delete_api_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

    # ------------------ API Details Form Frame ------------------
    form_frame = ttk.LabelFrame(parent, text="API Interface Details")
    form_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
    form_frame.columnconfigure(1, weight=1)

    # Name
    ttk.Label(form_frame, text="Name:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
    name_entry = ttk.Entry(form_frame)
    name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    # URL
    ttk.Label(form_frame, text="URL:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
    url_entry = ttk.Entry(form_frame)
    url_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

    # API Key
    ttk.Label(form_frame, text="API Key (Optional):").grid(row=2, column=0, padx=5, pady=5, sticky="e")
    api_key_entry = ttk.Entry(form_frame, show='*')
    api_key_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

    # API Type
    ttk.Label(form_frame, text="API Type:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
    api_type_dropdown = ttk.Combobox(form_frame, values=["OpenAI", "Ollama"], state="readonly")
    api_type_dropdown.set("OpenAI")
    api_type_dropdown.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

    # Fetch Models Button
    fetch_models_button = ttk.Button(form_frame, text="Fetch Models", command=lambda: update_models_dropdown())
    fetch_models_button.grid(row=4, column=1, padx=5, pady=5, sticky="w")

    # Model
    ttk.Label(form_frame, text="Model:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
    model_dropdown = ttk.Combobox(form_frame, state="readonly")
    model_dropdown.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

    # Max Tokens
    ttk.Label(form_frame, text="Max Tokens (Optional):").grid(row=6, column=0, padx=5, pady=5, sticky="e")
    max_tokens_entry = ttk.Entry(form_frame)
    max_tokens_entry.grid(row=6, column=1, padx=5, pady=5, sticky="ew")

    # Save Button
    save_button = ttk.Button(form_frame, text="Add API Interface", command=save_new_interface)
    save_button.grid(row=7, column=0, columnspan=2, pady=20)

    def on_select(event):
        selected = api_manage_listbox.curselection()
        if selected:
            index = selected[0]
            selected_interface = api_manage_listbox.get(index)
            interface_details = config['interfaces'][selected_interface]

            # Ensure values are strings and handle None values
            name_entry.delete(0, tk.END)
            name_entry.insert(0, selected_interface)
            url_entry.delete(0, tk.END)
            url_entry.insert(0, interface_details.get('url', ''))
            api_key_entry.delete(0, tk.END)
            api_key_value = interface_details.get('api_key', '') or ''
            api_key_entry.insert(0, api_key_value)
            api_type_dropdown.set(interface_details.get('api_type', 'OpenAI'))
            max_tokens_entry.delete(0, tk.END)
            max_tokens_value = str(interface_details.get('max_tokens', '')) or ''
            max_tokens_entry.insert(0, max_tokens_value)

            update_models_dropdown(default_model=interface_details.get('model', ''))
            save_button.config(text="Save Changes", command=lambda: save_edited_interface(selected_interface))

    api_manage_listbox.bind('<<ListboxSelect>>', on_select)

    # Initial population of the API list
    refresh_api_list()


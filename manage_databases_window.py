# manage_databases_window.py

import tkinter as tk
from tkinter import ttk, messagebox
from db_tools import DatabaseManager
import logging

def manage_databases_window(parent, config, refresh_callback):
    """Embed the Manage Databases interface within the given parent frame."""

    db_manager = DatabaseManager()
    
    def refresh_db_list():
        db_listbox.delete(0, tk.END)
        databases = db_manager.list_databases()
        for db in databases:
            db_listbox.insert(tk.END, db)

    def add_database():
        db_name = db_name_entry.get().strip()
        if not db_name:
            messagebox.showwarning("Input Required", "Please enter a database name.")
            return
        try:
            result = db_manager.create_database(db_name)
            if result:
                messagebox.showinfo("Success", f"Database '{db_name}' created successfully!")
                refresh_db_list()
                refresh_callback()  # Refresh the dropdown in main.py
                db_name_entry.delete(0, tk.END)
            else:
                messagebox.showerror("Error", f"Database '{db_name}' already exists.")
        except Exception as e:
            logging.error(f"Exception during add_database: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    def delete_database():
        selected = db_listbox.curselection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select a database to delete.")
            return
        db_name = db_listbox.get(selected[0])
        confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the database '{db_name}'? This action cannot be undone.")
        if confirm:
            try:
                result = db_manager.delete_database(db_name)
                if result.get("success"):
                    messagebox.showinfo("Success", f"Database '{db_name}' deleted successfully!")
                    refresh_db_list()
                    refresh_callback()  # Refresh the dropdown in main.py
                else:
                    error_message = result.get("error", "Unknown error occurred.")
                    messagebox.showerror("Error", f"Failed to delete database: {error_message}")
            except Exception as e:
                logging.error(f"Exception during delete_database: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    # Configure the parent frame's grid to allow dynamic resizing
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=0)  # Add Database
    parent.rowconfigure(1, weight=1)  # Manage Databases

    # ------------------ Add Database Frame ------------------
    add_db_frame = ttk.LabelFrame(parent, text="Add Database")
    add_db_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
    add_db_frame.columnconfigure(1, weight=1)

    ttk.Label(add_db_frame, text="Database Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

    db_name_entry = ttk.Entry(add_db_frame)
    db_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    add_db_button = ttk.Button(add_db_frame, text="Add Database", command=add_database)
    add_db_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

    # ------------------ Manage Databases Frame ------------------
    manage_db_frame = ttk.LabelFrame(parent, text="Manage Databases")
    manage_db_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
    manage_db_frame.columnconfigure(0, weight=1)
    manage_db_frame.rowconfigure(0, weight=1)  # Listbox
    manage_db_frame.rowconfigure(1, weight=0)  # Buttons

    # Adding a scrollbar to the Listbox
    listbox_scrollbar = ttk.Scrollbar(manage_db_frame, orient=tk.VERTICAL)
    db_listbox = tk.Listbox(manage_db_frame, yscrollcommand=listbox_scrollbar.set)
    listbox_scrollbar.config(command=db_listbox.yview)
    db_listbox.grid(row=0, column=0, sticky="nsew", padx=(5,0), pady=5)
    listbox_scrollbar.grid(row=0, column=1, sticky="ns", pady=5, padx=(0,5))

    # Frame for buttons
    db_buttons_frame = ttk.Frame(manage_db_frame)
    db_buttons_frame.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="ew")
    db_buttons_frame.columnconfigure(0, weight=1)
    db_buttons_frame.columnconfigure(1, weight=1)

    # Delete Database Button
    delete_db_button = ttk.Button(db_buttons_frame, text="Delete Selected Database", command=delete_database)
    delete_db_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

    # Initial population of the database list
    refresh_db_list()

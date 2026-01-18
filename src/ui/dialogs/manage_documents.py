# manage_documents_window.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from src.database.db_tools import DatabaseManager
import logging
import threading
import os  # Import os for path manipulations

def manage_documents_window(parent, config, refresh_callback):
    """Embed the Manage Documents interface within the given parent frame."""

    db_manager = DatabaseManager()
    document_records = []  # Map listbox indices to full metadata records

    def refresh_doc_list():
        db = selected_db.get()
        if not db:
            messagebox.showwarning("Input Required", "Please select a database.")
            return
        doc_listbox.delete(0, tk.END)
        document_records.clear()
        try:
            docs = db_manager.list_document_records(db)
            for doc in docs:
                doc_name = os.path.basename(doc.get('source', 'Unknown'))
                doc_listbox.insert(tk.END, doc_name)
                document_records.append(doc)
        except Exception as e:
            logging.error(f"Exception during refresh_doc_list: {e}")
            messagebox.showerror("Error", f"An error occurred while fetching documents: {e}")

    def add_documents():
        db = selected_db.get()
        if not db:
            messagebox.showwarning("Input Required", "Please select a database.")
            return
        files = filedialog.askopenfilenames(
            title="Select Documents",
            filetypes=[
                ("All Supported Files", "*.pdf;*.csv;*.txt;*.doc;*.docx"),
                ("PDF files", "*.pdf"),
                ("CSV files", "*.csv"),
                ("Text files", "*.txt"),
                ("Word Documents", "*.doc;*.docx")
            ]
        )
        if not files:
            return
        # Open the selected files in binary mode and pass file objects
        file_objects = [open(f, 'rb') for f in files]
        try:
            # Start the busy indicator
            start_busy()

            # Perform the add operation
            result = db_manager.add_documents(db, file_objects)
            if result.get("success"):
                messagebox.showinfo("Success", "Documents added successfully!")
                refresh_doc_list()
                refresh_callback()  # Refresh the dropdown in main.py
            else:
                error_message = result.get("error", "Unknown error occurred.")
                messagebox.showerror("Error", f"Failed to add documents: {error_message}")
        except Exception as e:
            logging.error(f"Exception during add_documents: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")
        finally:
            # Ensure all file objects are closed
            for f in file_objects:
                f.close()
            # Stop the busy indicator
            stop_busy()

    def delete_document():
        db = selected_db.get()
        if not db:
            messagebox.showwarning("Input Required", "Please select a database.")
            return
        selected = doc_listbox.curselection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select a document to delete.")
            return
        index = selected[0]
        doc_name = doc_listbox.get(index)
        doc_record = document_records[index]
        doc_name = doc_record.get('source', doc_name)
        confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete the document '{doc_name}'?")
        if confirm:
            try:
                # Start the busy indicator
                start_busy()

                result = db_manager.delete_document(db, doc_name)
                if result.get("success"):
                    messagebox.showinfo("Success", f"Document '{doc_name}' deleted successfully!")
                    refresh_doc_list()
                    refresh_callback()  # Refresh the dropdown in main.py
                else:
                    error_message = result.get("error", "Unknown error occurred.")
                    messagebox.showerror("Error", f"Failed to delete document: {error_message}")
            except Exception as e:
                logging.error(f"Exception during delete_document: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")
            finally:
                # Stop the busy indicator
                stop_busy()

    def perform_search(config, db_name, query, output_box):
        """Perform search and display results in the output box."""
        if not db_name:
            messagebox.showwarning("Input Required", "Please select a database.")
            return
        if not query.strip():
            messagebox.showwarning("Input Required", "Please enter a search query.")
            return

        def search_thread():
            try:
                results = db_manager.search(db_name, query, top_k=10)
                output_box.config(state=tk.NORMAL)
                output_box.delete('1.0', tk.END)
                if not results:
                    output_box.insert(tk.END, "No results found.")
                else:
                    for res in results:
                        doc_meta = res.get("document", {})
                        doc_name = doc_meta.get("source") or res.get("source", "Unknown")
                        similarity = res.get("similarity", 0)
                        content = res.get("content", "")
                        page = res.get("metadata", {}).get("page")
                        section = res.get("metadata", {}).get("section")
                        output_box.insert(tk.END, f"Document: {doc_name}\n")
                        if page is not None:
                            output_box.insert(tk.END, f"Page: {page}\n")
                        if section:
                            output_box.insert(tk.END, f"Section: {section}\n")
                        output_box.insert(tk.END, f"Similarity Score: {similarity:.4f}\n")
                        output_box.insert(tk.END, f"Content: {content[:700]}\n\n")
                output_box.config(state=tk.DISABLED)
            except Exception as e:
                logging.error(f"Exception during perform_search: {e}")
                messagebox.showerror("Error", f"An error occurred during search: {e}")

        threading.Thread(target=search_thread).start()

    # ------------------ Busy Indicator Functions ------------------
    def start_busy():
        """Start the busy indicator and disable buttons."""
        busy_indicator.grid(row=3, column=0, columnspan=2, pady=5)
        busy_progress.start()
        # Disable buttons to prevent multiple operations
        add_btn.config(state=tk.DISABLED)
        delete_btn_doc.config(state=tk.DISABLED)

    def stop_busy():
        """Stop the busy indicator and enable buttons."""
        busy_progress.stop()
        busy_indicator.grid_remove()
        # Enable buttons after operation
        add_btn.config(state=tk.NORMAL)
        delete_btn_doc.config(state=tk.NORMAL)

    # Configure the parent frame's grid to allow dynamic resizing
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=0)  # Database Selection
    parent.rowconfigure(1, weight=1)  # Manage Documents
    parent.rowconfigure(2, weight=2)  # Search Documents
    parent.rowconfigure(3, weight=0)  # Busy Indicator

    # ------------------ Database Selection Frame ------------------
    db_selection_frame = ttk.LabelFrame(parent, text="Database Selection")
    db_selection_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
    db_selection_frame.columnconfigure(1, weight=1)  # Allow combobox to expand

    ttk.Label(db_selection_frame, text="Select Database:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

    selected_db = ttk.Combobox(db_selection_frame, state="readonly")
    databases = db_manager.list_databases()
    selected_db['values'] = databases
    if databases:
        selected_db.current(0)  # Select the first database by default
    selected_db.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    refresh_db_button = ttk.Button(db_selection_frame, text="Refresh", command=lambda: refresh_db_selection())
    refresh_db_button.grid(row=0, column=2, padx=5, pady=5)

    def refresh_db_selection():
        """Refresh the list of databases in the Combobox."""
        current_selection = selected_db.get()
        try:
            databases = db_manager.list_databases()
        except Exception as e:
            logging.error(f"Exception during refresh_db_selection: {e}")
            messagebox.showerror("Error", f"An error occurred while fetching databases: {e}")
            return

        selected_db['values'] = databases
        if current_selection in databases:
            selected_db.set(current_selection)
        elif databases:
            selected_db.current(0)
        else:
            selected_db.set('')  # No databases available
        refresh_callback()  # Also refresh the main.py dropdown if necessary
        refresh_doc_list()  # Refresh documents for the newly selected database

    # Bind the Combobox selection event to refresh_doc_list
    selected_db.bind("<<ComboboxSelected>>", lambda event: refresh_doc_list())

    # ------------------ Manage Documents Section ------------------
    manage_frame = ttk.LabelFrame(parent, text="Manage Documents")
    manage_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
    manage_frame.columnconfigure(0, weight=1)
    manage_frame.rowconfigure(0, weight=1)  # Listbox
    manage_frame.rowconfigure(1, weight=0)  # Buttons

    # Adding a scrollbar to the Listbox
    listbox_scrollbar = ttk.Scrollbar(manage_frame, orient=tk.VERTICAL)
    doc_listbox = tk.Listbox(manage_frame, height=10, yscrollcommand=listbox_scrollbar.set)
    listbox_scrollbar.config(command=doc_listbox.yview)
    doc_listbox.grid(row=0, column=0, sticky="nsew", padx=(5,0), pady=5)
    listbox_scrollbar.grid(row=0, column=1, sticky="ns", pady=5, padx=(0,5))

    list_buttons_frame = ttk.Frame(manage_frame)
    list_buttons_frame.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="ew")
    list_buttons_frame.columnconfigure(0, weight=1)
    list_buttons_frame.columnconfigure(1, weight=1)

    # Add Documents Button
    add_btn = ttk.Button(list_buttons_frame, text="Add Documents", command=lambda: threading.Thread(target=add_documents).start())
    add_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

    # Delete Selected Document Button
    delete_btn_doc = ttk.Button(list_buttons_frame, text="Delete Selected Document", command=lambda: threading.Thread(target=delete_document).start())
    delete_btn_doc.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    # ------------------ Search Documents Section ------------------
    search_frame = ttk.LabelFrame(parent, text="Search Documents")
    search_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
    search_frame.columnconfigure(0, weight=1)
    search_frame.rowconfigure(1, weight=1)  # Output box

    # Search Input
    search_input_frame = ttk.Frame(search_frame)
    search_input_frame.grid(row=0, column=0, pady=5, padx=5, sticky="ew")
    search_input_frame.columnconfigure(1, weight=1)

    ttk.Label(search_input_frame, text="Enter Search Query:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

    search_entry_doc = ttk.Entry(search_input_frame)
    search_entry_doc.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    search_btn_doc = ttk.Button(search_input_frame, text="Search", command=lambda: threading.Thread(target=lambda: perform_search(config, selected_db.get(), search_entry_doc.get(), output_box)).start())
    search_btn_doc.grid(row=0, column=2, padx=5, pady=5)

    # Output Box with Scrollbar
    output_box_frame = ttk.Frame(search_frame)
    output_box_frame.grid(row=1, column=0, pady=5, padx=5, sticky="nsew")
    output_box_frame.columnconfigure(0, weight=1)
    output_box_frame.rowconfigure(0, weight=1)

    output_box = tk.Text(output_box_frame, wrap=tk.WORD, state=tk.DISABLED)
    output_box.grid(row=0, column=0, sticky="nsew")

    output_scrollbar = ttk.Scrollbar(output_box_frame, orient=tk.VERTICAL, command=output_box.yview)
    output_box.config(yscrollcommand=output_scrollbar.set)
    output_scrollbar.grid(row=0, column=1, sticky="ns")

    # ------------------ Busy Indicator Section ------------------
    # Create a frame for the busy indicator
    busy_indicator = ttk.Frame(parent)
    busy_indicator.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
    busy_indicator.columnconfigure(0, weight=1)

    # Add a Progressbar in indeterminate mode
    busy_progress = ttk.Progressbar(busy_indicator, mode='indeterminate')
    busy_progress.grid(row=0, column=0, sticky="ew", pady=5)

    # Optionally, add a label next to the progress bar
    busy_label = ttk.Label(busy_indicator, text="Processing...")
    busy_label.grid(row=0, column=1, padx=5, sticky="w")

    # Initially hide the busy indicator
    busy_indicator.grid_remove()

    # ------------------ Initial population of documents ------------------
    refresh_doc_list()

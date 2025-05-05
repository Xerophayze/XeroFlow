import tkinter as tk
from tkinter import ttk
import textwrap

class ArrayReviewWindow:
    def __init__(self, array_items):
        self.root = tk.Tk()
        self.root.title("Review Array Items")
        self.root.geometry("900x700")  # Increased window size for better content display
        
        self.array_items = array_items
        self.modified_items = array_items.copy()
        self.result = None
        self.current_selection = None
        
        # Configure the root window to expand
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights for main frame
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)  # Preview frame should expand
        main_frame.rowconfigure(1, weight=2)  # Edit frame should expand more
        main_frame.rowconfigure(2, weight=0)  # Button frame doesn't need to expand
        
        # Create preview frame with better spacing
        preview_frame = ttk.LabelFrame(main_frame, text="Array Items (Preview)", padding="10")
        preview_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Configure grid weights for preview frame
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        
        # Listbox with scrollbar - increased height
        self.listbox = tk.Listbox(preview_frame, width=80, height=12, font=('TkDefaultFont', 10))
        scrollbar = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=2, pady=2)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Populate listbox with previews
        for item in self.array_items:
            # Get first few lines and truncate if too long
            preview = self.get_preview(item)
            self.listbox.insert(tk.END, preview)
        
        # Create edit frame with better spacing
        edit_frame = ttk.LabelFrame(main_frame, text="Edit Selected Item", padding="10")
        edit_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Configure grid weights for edit frame
        edit_frame.columnconfigure(0, weight=1)
        edit_frame.rowconfigure(0, weight=1)
        
        # Text widget with scrollbar for editing - increased font size for better readability
        self.edit_text = tk.Text(edit_frame, wrap=tk.WORD, font=('TkDefaultFont', 11))
        edit_scrollbar = ttk.Scrollbar(edit_frame, orient=tk.VERTICAL, command=self.edit_text.yview)
        self.edit_text.configure(yscrollcommand=edit_scrollbar.set)
        
        self.edit_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=2, pady=2)
        edit_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Buttons frame with better spacing
        button_frame = ttk.Frame(main_frame, padding="5")
        button_frame.grid(row=2, column=0, sticky=(tk.E, tk.S), pady=10)
        
        # Save button
        self.save_button = ttk.Button(button_frame, text="Save Changes", command=self.save_changes, width=15)
        self.save_button.grid(row=0, column=0, padx=5)
        
        # Cancel button
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self.cancel, width=15)
        cancel_button.grid(row=0, column=1, padx=5)
        
        # Approve button
        approve_button = ttk.Button(button_frame, text="Approve", command=self.approve, width=15)
        approve_button.grid(row=0, column=2, padx=5)
        
        # Bind listbox selection
        self.listbox.bind('<<ListboxSelect>>', self.on_select)
        
        # Disable save button initially
        self.save_button.state(['disabled'])
        
        # Make window modal
        self.root.transient()
        self.root.grab_set()
        
        # Center the window on screen
        self.center_window()

    def center_window(self):
        """Center the window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def get_preview(self, text, max_lines=3, max_length=100):
        """Generate a preview of the text content."""
        lines = text.split('\n')
        preview_lines = lines[:max_lines]
        preview = '\n'.join(preview_lines)
        if len(preview) > max_length:
            preview = preview[:max_length] + '...'
        if len(lines) > max_lines:
            preview += f'\n... ({len(lines)} lines total)'
        return preview

    def on_select(self, event):
        """Handle selection in the listbox."""
        if not self.listbox.curselection():
            return
            
        self.current_selection = self.listbox.curselection()[0]
        # Get the full text of the selected item
        full_text = self.modified_items[self.current_selection]
        
        # Clear and update the edit text widget
        self.edit_text.delete('1.0', tk.END)
        self.edit_text.insert('1.0', full_text)
        
        # Enable the save button
        self.save_button.state(['!disabled'])

    def save_changes(self):
        """Save changes to the current item."""
        if self.current_selection is not None:
            # Get the modified text
            modified_text = self.edit_text.get('1.0', tk.END).rstrip()
            
            # Update the modified items array
            self.modified_items[self.current_selection] = modified_text
            
            # Update the preview in the listbox
            self.listbox.delete(self.current_selection)
            self.listbox.insert(self.current_selection, self.get_preview(modified_text))
            
            # Reselect the item
            self.listbox.selection_set(self.current_selection)

    def cancel(self):
        """Cancel the review process."""
        self.result = None
        self.root.destroy()

    def approve(self):
        """Approve the modified array."""
        self.result = self.modified_items
        self.root.destroy()

    def show(self):
        """Show the window and return the result."""
        self.root.mainloop()
        return self.result

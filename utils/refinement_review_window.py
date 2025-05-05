import tkinter as tk
from tkinter import ttk, messagebox
import textwrap

class RefinementReviewWindow:
    def __init__(self, refinement_results, validation_results, refine_callback=None):
        """
        Initialize the review window with refinement and validation results.
        Each item in refinement_results should correspond to the same index in validation_results.
        """
        self.root = tk.Tk()
        self.root.title("Review Refinement Results")
        
        # Store results and callback
        self.refinement_results = refinement_results
        self.validation_results = validation_results
        self.refine_callback = refine_callback
        self.approved = False
        self.final_output = ""
        self.is_refining = False
        
        # Configure the root window for resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Create main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(fill=tk.BOTH, expand=True, row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        
        # Configure main frame for resizing
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=0)  # List section
        main_frame.rowconfigure(2, weight=0)  # Refinement controls
        main_frame.rowconfigure(3, weight=1)  # Validation section
        main_frame.rowconfigure(4, weight=2)  # Refinement section
        main_frame.rowconfigure(5, weight=0)  # Button section
        
        # Top section - Title
        title_label = ttk.Label(main_frame, text="Review and Refine Results", font=("TkDefaultFont", 14, "bold"))
        title_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # Top section - Listbox
        list_frame = ttk.LabelFrame(main_frame, text="Refinement Results (Click to view details)", padding="10")
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=5)
        
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.listbox = tk.Listbox(list_frame, width=80, height=5, font=("TkDefaultFont", 10))
        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        list_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.listbox.configure(yscrollcommand=list_scrollbar.set)
        
        for result in refinement_results:
            preview = "\n".join(result.split("\n")[:2]) + "..."
            self.listbox.insert(tk.END, preview)
        
        # Refinement controls section
        refine_control_frame = ttk.LabelFrame(main_frame, text="Refinement Controls", padding="10")
        refine_control_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=5)
        
        refine_control_frame.columnconfigure(0, weight=1)
        refine_control_frame.columnconfigure(1, weight=1)
        
        # Rating frame
        rating_frame = ttk.Frame(refine_control_frame)
        rating_frame.grid(row=0, column=0, sticky=tk.W, pady=5)
        
        rating_label = ttk.Label(rating_frame, text="Minimum Rating:", font=("TkDefaultFont", 10))
        rating_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Create entry field directly without StringVar
        self.rating_entry = ttk.Entry(rating_frame, width=10)
        self.rating_entry.pack(side=tk.LEFT)
        self.rating_entry.insert(0, "8.0")  # Set default value
        
        # Button frame
        button_frame = ttk.Frame(refine_control_frame)
        button_frame.grid(row=0, column=1, sticky=tk.E, pady=5)
        
        self.refine_button = ttk.Button(button_frame, text="Start Refinement", command=self.start_refinement, width=15)
        self.refine_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(button_frame, text="Stop Refinement", command=self.stop_refinement, state=tk.DISABLED, width=15)
        self.stop_button.pack(side=tk.LEFT)
        
        # Middle section - Validation
        validation_frame = ttk.LabelFrame(main_frame, text="Validation Result", padding="10")
        validation_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10), padx=5)
        
        validation_frame.columnconfigure(0, weight=1)
        validation_frame.rowconfigure(0, weight=1)
        
        self.validation_text = tk.Text(validation_frame, width=80, height=6, font=("TkDefaultFont", 10), wrap=tk.WORD)
        validation_scrollbar = ttk.Scrollbar(validation_frame, orient=tk.VERTICAL, command=self.validation_text.yview)
        
        self.validation_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        validation_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.validation_text.configure(yscrollcommand=validation_scrollbar.set)
        
        # Bottom section - Refinement
        refinement_frame = ttk.LabelFrame(main_frame, text="Refinement Result (Editable)", padding="10")
        refinement_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10), padx=5)
        
        refinement_frame.columnconfigure(0, weight=1)
        refinement_frame.rowconfigure(0, weight=1)
        
        self.refinement_text = tk.Text(refinement_frame, width=80, height=10, font=("TkDefaultFont", 10), wrap=tk.WORD)
        refinement_scrollbar = ttk.Scrollbar(refinement_frame, orient=tk.VERTICAL, command=self.refinement_text.yview)
        
        self.refinement_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        refinement_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.refinement_text.configure(yscrollcommand=refinement_scrollbar.set)
        
        # Button frame
        action_button_frame = ttk.Frame(main_frame)
        action_button_frame.grid(row=5, column=0, sticky=tk.E, pady=(0, 5), padx=5)
        
        cancel_button = ttk.Button(action_button_frame, text="Cancel", command=self.cancel, width=15)
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        approve_button = ttk.Button(action_button_frame, text="Approve", command=self.approve, width=15)
        approve_button.pack(side=tk.RIGHT)
        
        # Bind listbox selection event
        self.listbox.bind('<<ListboxSelect>>', self.on_select)
        
        # Select first item by default
        if refinement_results:
            self.listbox.selection_set(0)
            self.on_select(None)
            
        # Set window size and center it
        self.center_window(1000, 800)
    
    def center_window(self, width, height):
        """Center the window on the screen with the given dimensions."""
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calculate position
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        # Set window size and position
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def on_select(self, event):
        """Handle selection in listbox"""
        if not self.listbox.curselection():
            return
            
        # Get selected index
        index = self.listbox.curselection()[0]
        
        # Update validation and refinement text boxes
        self.validation_text.delete(1.0, tk.END)
        self.validation_text.insert(tk.END, self.validation_results[index])
        
        self.refinement_text.delete(1.0, tk.END)
        self.refinement_text.insert(tk.END, self.refinement_results[index])
    
    def cancel(self):
        """Handle cancel button click"""
        self.approved = False
        self.root.destroy()
    
    def approve(self):
        """Handle approve button click"""
        self.approved = True
        # Collect all refinement results, including any edits
        final_results = []
        current_selection = self.listbox.curselection()
        
        for i in range(len(self.refinement_results)):
            if current_selection and i == current_selection[0]:
                # Get potentially edited text from the text box
                final_results.append(self.refinement_text.get(1.0, tk.END).strip())
            else:
                final_results.append(self.refinement_results[i])
        
        self.final_output = "\n\n".join(final_results)
        self.root.destroy()
    
    def start_refinement(self):
        """Start refinement of selected result"""
        if not self.listbox.curselection():
            messagebox.showerror("Selection Required", "Please select a result to refine")
            return
        
        # Get rating value directly from entry
        min_rating_str = self.rating_entry.get().strip()
        
        if not min_rating_str:
            messagebox.showerror("Invalid Rating", "Please enter a minimum rating")
            return
        
        try:
            min_rating = float(min_rating_str)
            if min_rating <= 0 or min_rating > 10:
                messagebox.showerror("Invalid Rating", "Rating must be between 0 and 10")
                return
        except ValueError:
            messagebox.showerror("Invalid Rating", "Please enter a valid number for minimum rating")
            return
        
        index = self.listbox.curselection()[0]
        current_refinement = self.refinement_results[index]
        current_validation = self.validation_results[index]
        
        if self.refine_callback:
            self.is_refining = True
            self.refine_button.configure(state=tk.DISABLED)
            self.stop_button.configure(state=tk.NORMAL)
            self.refine_callback(current_refinement, current_validation, min_rating, self.update_refinement)
    
    def stop_refinement(self):
        """Stop ongoing refinement"""
        self.is_refining = False
        self.refine_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
    
    def update_refinement(self, new_refinement, new_validation):
        """Update the results with new refinement results"""
        if not self.is_refining:
            return
            
        def update_ui():
            # Add new results to the lists
            self.refinement_results.append(new_refinement)
            self.validation_results.append(new_validation)
            
            # Add new result to listbox
            preview = "\n".join(new_refinement.split("\n")[:2]) + "..."
            self.listbox.insert(tk.END, preview)
            
            # Select and show the new result
            last_index = self.listbox.size() - 1
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(last_index)
            self.listbox.see(last_index)
            self.on_select(None)
        
        # Schedule the UI update on the main thread
        self.root.after(0, update_ui)
    
    def show(self):
        """Show the window and return whether results were approved and the final output"""
        self.root.mainloop()
        return self.approved, self.final_output

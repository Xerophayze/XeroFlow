import tkinter as tk
from tkinter import ttk
import time
import threading

class ProgressWindow:
    def __init__(self, max_value=100, title="Processing", parent=None):
        # Use Toplevel if parent provided, otherwise create Tk root
        # This helps avoid Tcl_AsyncDelete errors in threaded contexts
        if parent:
            self.root = tk.Toplevel(parent)
            self._owns_root = False
        else:
            # Try to get existing Tk instance or create new one
            try:
                self.root = tk.Toplevel()
                self._owns_root = False
            except tk.TclError:
                self.root = tk.Tk()
                self._owns_root = True
        
        self.root.title(title)
        self.cancelled = False
        self.max_value = max_value
        
        # Set window size and position it in the center of the screen
        window_width = 650
        window_height = 400
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Initialize timing variables
        self.start_time = None
        self.item_times = []
        self.completed_items = 0
        
        # Configure style for progress bar
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "custom.Horizontal.TProgressbar",
            foreground='#4caf50',
            background='#4caf50',
            troughcolor='#d9d9d9',
            lightcolor='#4caf50',
            darkcolor='#4caf50'
        )
        
        # Create main frame with padding
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Title label with larger font
        title_label = ttk.Label(main_frame, text=title, font=("TkDefaultFont", 14, "bold"))
        title_label.grid(row=0, column=0, pady=(0, 15), sticky='w')
        
        # Progress frame
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        progress_frame.columnconfigure(0, weight=1)
        
        # Progress bar - made wider
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            style="custom.Horizontal.TProgressbar",
            length=600,
            mode='determinate',
            variable=self.progress_var,
            maximum=max_value
        )
        self.progress_bar.grid(row=0, column=0, pady=10, padx=10, sticky='ew')
        
        # Progress label with larger font
        self.progress_label = ttk.Label(progress_frame, text="0%", width=8, font=("TkDefaultFont", 12))
        self.progress_label.grid(row=0, column=1, pady=10, padx=5)
        
        # Time estimation label with better formatting
        time_frame = ttk.LabelFrame(main_frame, text="Time Information", padding="10")
        time_frame.grid(row=2, column=0, pady=10, padx=5, sticky='ew')
        time_frame.columnconfigure(0, weight=1)
        
        self.time_label = ttk.Label(time_frame, text="", wraplength=600, font=("TkDefaultFont", 10))
        self.time_label.grid(row=0, column=0, pady=5, padx=5, sticky='w')
        
        self.item_details = {}
        self.item_labels = [f"Item {i + 1}" for i in range(max_value)]

        list_frame = ttk.LabelFrame(main_frame, text="Processed Items", padding="10")
        list_frame.grid(row=3, column=0, pady=10, padx=5, sticky='nsew')
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.item_listbox = tk.Listbox(list_frame, height=6)
        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.item_listbox.yview)
        self.item_listbox.configure(yscrollcommand=list_scrollbar.set)

        self.item_listbox.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        list_scrollbar.grid(row=0, column=1, sticky='ns')

        for label in self.item_labels:
            self.item_listbox.insert(tk.END, label)

        self.item_listbox.bind("<<ListboxSelect>>", self._on_item_select)

        # Current item label with better formatting
        item_frame = ttk.LabelFrame(main_frame, text="Current Item", padding="10")
        item_frame.grid(row=4, column=0, pady=10, padx=5, sticky='nsew')
        item_frame.columnconfigure(0, weight=1)
        item_frame.rowconfigure(0, weight=1)
        
        # Scrollable text widget for current item instead of label
        self.item_text = tk.Text(item_frame, wrap=tk.WORD, height=8, font=("TkDefaultFont", 10))
        item_scrollbar = ttk.Scrollbar(item_frame, orient=tk.VERTICAL, command=self.item_text.yview)
        self.item_text.configure(yscrollcommand=item_scrollbar.set)
        self.item_text.config(state=tk.DISABLED)  # Make read-only by default
        
        self.item_text.grid(row=0, column=0, pady=5, padx=5, sticky='nsew')
        item_scrollbar.grid(row=0, column=1, pady=5, sticky='ns')
        
        # Cancel button with better styling
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, pady=10, sticky='e')
        
        self.skip_event = threading.Event()
        self.skip_button = ttk.Button(button_frame, text="Skip", command=self.skip, width=15)
        self.skip_button.grid(row=0, column=0, pady=5, padx=(0, 8))

        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.cancel, width=15)
        self.cancel_button.grid(row=0, column=1, pady=5)
        
        # Keep window on top
        self.root.attributes('-topmost', True)
        
        # Handle window close button
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        
        # Configure grid weights
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)  # Make the item frame expandable
        
        # Update the window
        self.root.update()

    def cancel(self):
        """Handle cancellation"""
        self.cancelled = True
        self.close()
    
    def update_progress(self, current_value, current_item="", detail_text=""):
        """Update the progress bar and labels"""
        if not self.cancelled:
            # Initialize start time if not set
            if self.start_time is None:
                self.start_time = time.time()
            
            # Calculate item completion time
            if self.completed_items < current_value:
                item_time = time.time() - (self.start_time + sum(self.item_times))
                self.item_times.append(item_time)
                self.completed_items = current_value
            
            # Update progress bar based on items completed
            self.progress_bar['value'] = current_value
            
            # Calculate percentage based on items completed
            percentage = int((current_value / self.max_value) * 100)
            self.progress_label.config(text=f"{percentage}%")
            
            # Update time estimation
            if len(self.item_times) > 0:
                # Calculate average time per item from actual completion times
                avg_time_per_item = sum(self.item_times) / len(self.item_times)
                
                # Calculate elapsed and remaining time
                elapsed_time = sum(self.item_times)
                remaining_items = self.max_value - current_value
                estimated_remaining = remaining_items * avg_time_per_item
                
                # Format time strings
                elapsed_str = self._format_time(elapsed_time)
                remaining_str = self._format_time(estimated_remaining)
                avg_str = self._format_time(avg_time_per_item)
                
                time_text = f"Elapsed: {elapsed_str} | Remaining: {remaining_str} | Avg per item: {avg_str}"
                self.time_label.config(text=time_text)
            
            # Update current item text
            if current_item or detail_text:
                combined_text = current_item
                if detail_text:
                    if combined_text:
                        combined_text += "\n\n"
                    combined_text += detail_text
                self.update_current_item(combined_text)
                if 0 <= current_value < self.max_value:
                    self.update_item_entry(current_value, label=current_item, detail_text=combined_text, set_current=True)
            
            # Force update
            self.root.update_idletasks()
            self.root.update()

    def update_current_item(self, text):
        """Update the current item text"""
        self.item_text.config(state=tk.NORMAL)
        self.item_text.delete(1.0, tk.END)
        self.item_text.insert(tk.END, text)
        self.item_text.see(tk.END)  # Scroll to show the latest text
        self.item_text.config(state=tk.DISABLED)  # Make read-only
        self.root.update_idletasks()

    def update_item_entry(self, index, label=None, detail_text=None, set_current=False):
        if index < 0 or index >= self.max_value:
            return

        if label:
            short_label = label.replace("\n", " ")
            if len(short_label) > 80:
                short_label = f"{short_label[:77]}..."
            self.item_labels[index] = short_label
            self.item_listbox.delete(index)
            self.item_listbox.insert(index, short_label)

        if detail_text is not None:
            self.item_details[index] = detail_text

        if set_current:
            self.item_listbox.selection_clear(0, tk.END)
            self.item_listbox.selection_set(index)
            self.item_listbox.see(index)

    def _on_item_select(self, event=None):
        selection = self.item_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        detail_text = self.item_details.get(index) or self.item_labels[index]
        self.update_current_item(detail_text)

    def _format_time(self, seconds):
        """Format seconds into a readable time string"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            seconds = int(seconds % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def close(self):
        """Close the progress window safely across threads"""
        def do_close():
            try:
                self.root.destroy()
            except:
                pass  # Window might already be destroyed
        
        # Schedule destruction on the main thread to avoid Tcl_AsyncDelete errors
        try:
            if self.root.winfo_exists():
                self.root.after(0, do_close)
        except:
            pass  # Window might already be destroyed
    
    def is_cancelled(self):
        """Check if the operation was cancelled"""
        return self.cancelled

    def skip(self):
        """Signal skip for the current item"""
        self.skip_event.set()

    def clear_skip(self):
        """Clear skip flag (call when starting a new item)"""
        self.skip_event.clear()

    def is_skip_requested(self):
        """Check if skip has been requested"""
        return self.skip_event.is_set()

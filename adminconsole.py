"""
XeroFlow Admin Console
A standalone tool for managing and analyzing token usage log files.
"""

import os
import sys
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Add pricing service import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from services.pricing_service import PricingService

class AdminConsole:
    def __init__(self, root):
        self.root = root
        self.root.title("XeroFlow Admin Console")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Set the theme (if ttk theme extension is available)
        try:
            self.root.tk.call("source", "azure.tcl")
            self.root.tk.call("set_theme", "dark")
        except tk.TclError:
            pass  # Theme not available, use default
            
        # Define paths
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes", "Logs")
        self.current_file = None
        self.data = None
        self.filtered_data = None
        self.date_filter_active = False
        self.start_date = None
        self.end_date = None
        
        # Create main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create a paned window to divide the UI
        self.paned_window = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - File browser
        self.file_frame = ttk.LabelFrame(self.paned_window, text="Log Files")
        self.paned_window.add(self.file_frame, weight=1)
        
        # Right panel - Log data view
        self.data_frame = ttk.LabelFrame(self.paned_window, text="Log Data")
        self.paned_window.add(self.data_frame, weight=5)
        
        # Setup file browser
        self.setup_file_browser()
        
        # Setup data view
        self.setup_data_view()
        
        # Populate file list
        self.refresh_file_list()
        
    def setup_file_browser(self):
        # File tools frame
        tools_frame = ttk.Frame(self.file_frame)
        tools_frame.pack(fill=tk.X, pady=5)
        
        # Refresh button
        refresh_btn = ttk.Button(tools_frame, text="Refresh", command=self.refresh_file_list)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Delete button
        delete_btn = ttk.Button(tools_frame, text="Delete", command=self.delete_selected_file)
        delete_btn.pack(side=tk.LEFT, padx=5)
        
        # Export button
        export_btn = ttk.Button(tools_frame, text="Export CSV", command=self.export_selected_file)
        export_btn.pack(side=tk.LEFT, padx=5)
        
        # File tree
        tree_frame = ttk.Frame(self.file_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Scrollbar for file tree
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # File treeview
        self.file_tree = ttk.Treeview(tree_frame, yscrollcommand=scrollbar.set)
        self.file_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_tree.yview)
        
        # Configure tree columns
        self.file_tree["columns"] = ("size", "date")
        self.file_tree.column("#0", width=150, minwidth=80)
        self.file_tree.column("size", width=50, minwidth=30)
        self.file_tree.column("date", width=90, minwidth=50)
        
        self.file_tree.heading("#0", text="Name")
        self.file_tree.heading("size", text="Size")
        self.file_tree.heading("date", text="Modified")
        
        # Bind file selection
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_select)
        
    def setup_data_view(self):
        # Create notebook for different views
        self.notebook = ttk.Notebook(self.data_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Add date filter frame at the top
        filter_frame = ttk.LabelFrame(self.data_frame, text="Date Filter")
        filter_frame.pack(fill=tk.X, padx=5, pady=5, before=self.notebook)
        
        # Date filter controls
        # Start Date
        start_frame = ttk.Frame(filter_frame)
        start_frame.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        ttk.Label(start_frame, text="Start Date:").pack(side=tk.LEFT, padx=(0,5))
        
        self.start_year_var = tk.StringVar()
        self.start_year = ttk.Combobox(start_frame, textvariable=self.start_year_var, width=5, state="readonly")
        self.start_year.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(start_frame, text="/").pack(side=tk.LEFT)
        
        self.start_month_var = tk.StringVar()
        self.start_month = ttk.Combobox(start_frame, textvariable=self.start_month_var, width=3, state="readonly")
        self.start_month.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(start_frame, text="/").pack(side=tk.LEFT)
        
        self.start_day_var = tk.StringVar()
        self.start_day = ttk.Combobox(start_frame, textvariable=self.start_day_var, width=3, state="readonly")
        self.start_day.pack(side=tk.LEFT, padx=2)
        
        # End Date
        end_frame = ttk.Frame(filter_frame)
        end_frame.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(end_frame, text="End Date:").pack(side=tk.LEFT, padx=(10,5))
        
        self.end_year_var = tk.StringVar()
        self.end_year = ttk.Combobox(end_frame, textvariable=self.end_year_var, width=5, state="readonly")
        self.end_year.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(end_frame, text="/").pack(side=tk.LEFT)
        
        self.end_month_var = tk.StringVar()
        self.end_month = ttk.Combobox(end_frame, textvariable=self.end_month_var, width=3, state="readonly")
        self.end_month.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(end_frame, text="/").pack(side=tk.LEFT)
        
        self.end_day_var = tk.StringVar()
        self.end_day = ttk.Combobox(end_frame, textvariable=self.end_day_var, width=3, state="readonly")
        self.end_day.pack(side=tk.LEFT, padx=2)
        
        # Filter buttons
        buttons_frame = ttk.Frame(filter_frame)
        buttons_frame.grid(row=0, column=2, padx=5, pady=5, sticky="e")
        
        apply_filter_btn = ttk.Button(buttons_frame, text="Apply Filter", command=self.apply_date_filter)
        apply_filter_btn.pack(side=tk.LEFT, padx=5)
        
        clear_filter_btn = ttk.Button(buttons_frame, text="Clear Filter", command=self.clear_date_filter)
        clear_filter_btn.pack(side=tk.LEFT, padx=5)
        
        # Quick filter buttons
        quick_filter_frame = ttk.LabelFrame(filter_frame, text="Quick Filters")
        quick_filter_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        
        # Year filter
        year_frame = ttk.Frame(quick_filter_frame)
        year_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        ttk.Label(year_frame, text="Year:").pack(side=tk.LEFT, padx=(0, 5))
        self.quick_year_var = tk.StringVar()
        self.quick_year = ttk.Combobox(year_frame, textvariable=self.quick_year_var, width=5, state="readonly")
        self.quick_year.pack(side=tk.LEFT, padx=5)
        
        year_button = ttk.Button(year_frame, text="Show Year", command=self.show_year)
        year_button.pack(side=tk.LEFT, padx=5)
        
        # Month filter
        month_frame = ttk.Frame(quick_filter_frame)
        month_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        ttk.Label(month_frame, text="Year:").pack(side=tk.LEFT, padx=(0, 5))
        self.quick_month_year_var = tk.StringVar()
        self.quick_month_year = ttk.Combobox(month_frame, textvariable=self.quick_month_year_var, width=5, state="readonly")
        self.quick_month_year.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(month_frame, text="Month:").pack(side=tk.LEFT, padx=(10, 5))
        self.quick_month_var = tk.StringVar()
        self.quick_month = ttk.Combobox(month_frame, textvariable=self.quick_month_var, width=3, state="readonly")
        self.quick_month.pack(side=tk.LEFT, padx=5)
        
        month_button = ttk.Button(month_frame, text="Show Month", command=self.show_month)
        month_button.pack(side=tk.LEFT, padx=5)
        
        # Common filters
        common_frame = ttk.Frame(quick_filter_frame)
        common_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        current_month_btn = ttk.Button(common_frame, text="Current Month", command=self.show_current_month)
        current_month_btn.pack(side=tk.LEFT, padx=5)
        
        last_30_days_btn = ttk.Button(common_frame, text="Last 30 Days", command=self.show_last_30_days)
        last_30_days_btn.pack(side=tk.LEFT, padx=5)
        
        # Create tabs
        self.tab_raw = ttk.Frame(self.notebook)
        self.tab_summary = ttk.Frame(self.notebook)
        self.tab_charts = ttk.Frame(self.notebook)
        self.tab_costs = ttk.Frame(self.notebook)
        self.tab_pricing = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_raw, text="Raw Data")
        self.notebook.add(self.tab_summary, text="Summary")
        self.notebook.add(self.tab_charts, text="Charts")
        self.notebook.add(self.tab_costs, text="Costs")
        self.notebook.add(self.tab_pricing, text="Pricing Config")
        
        # Raw data treeview
        raw_frame = ttk.Frame(self.tab_raw)
        raw_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars for raw data
        y_scrollbar = ttk.Scrollbar(raw_frame)
        y_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        x_scrollbar = ttk.Scrollbar(raw_frame, orient=tk.HORIZONTAL)
        x_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Raw data treeview
        self.raw_tree = ttk.Treeview(raw_frame, yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        self.raw_tree.pack(fill=tk.BOTH, expand=True)
        
        y_scrollbar.config(command=self.raw_tree.yview)
        x_scrollbar.config(command=self.raw_tree.xview)
        
        # Configure raw data treeview
        self.raw_tree["columns"] = []  # Will be set dynamically
        
        # Hide the first column (treeview default column)
        self.raw_tree.column("#0", width=0, stretch=tk.NO)
        
        # Summary view
        self.summary_frame = ttk.Frame(self.tab_summary)
        self.summary_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Charts view
        self.charts_frame = ttk.Frame(self.tab_charts)
        self.charts_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Costs view
        self.costs_frame = ttk.Frame(self.tab_costs)
        self.costs_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Pricing config view
        self.pricing_config_frame = ttk.Frame(self.tab_pricing)
        self.pricing_config_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.setup_pricing_config_view()
        
    def setup_pricing_config_view(self):
        """Set up the pricing configuration tab"""
        # Refresh pricing data to ensure we have the latest models
        PricingService.refresh_pricing_data()
        
        # Create main frame with padding
        main_frame = ttk.Frame(self.pricing_config_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create provider selection frame
        provider_frame = ttk.LabelFrame(main_frame, text="Select Provider")
        provider_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Provider selection
        self.provider_var = tk.StringVar(value="openai")
        ttk.Radiobutton(provider_frame, text="OpenAI", variable=self.provider_var, 
                       value="openai", command=self.load_provider_models).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(provider_frame, text="Groq", variable=self.provider_var, 
                       value="groq", command=self.load_provider_models).pack(side=tk.LEFT, padx=10)
        
        # Create model selection frame
        model_frame = ttk.LabelFrame(main_frame, text="Select Model")
        model_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Model selection dropdown
        self.model_var = tk.StringVar()
        self.model_dropdown = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", width=40)
        self.model_dropdown.pack(side=tk.LEFT, padx=10, pady=5)
        self.model_dropdown.bind("<<ComboboxSelected>>", self.load_model_pricing)
        
        # Load button
        ttk.Button(model_frame, text="Load", command=self.load_model_pricing).pack(side=tk.LEFT, padx=10, pady=5)
        
        # Create pricing details frame
        pricing_details_frame = ttk.LabelFrame(main_frame, text="Pricing Details")
        pricing_details_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create a frame for text model pricing
        self.text_pricing_frame = ttk.Frame(pricing_details_frame)
        self.text_pricing_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Input token pricing
        ttk.Label(self.text_pricing_frame, text="Input Cost (per million tokens):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.input_cost_var = tk.DoubleVar()
        self.input_cost_entry = ttk.Entry(self.text_pricing_frame, textvariable=self.input_cost_var, width=15)
        self.input_cost_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Output token pricing
        ttk.Label(self.text_pricing_frame, text="Output Cost (per million tokens):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.output_cost_var = tk.DoubleVar()
        self.output_cost_entry = ttk.Entry(self.text_pricing_frame, textvariable=self.output_cost_var, width=15)
        self.output_cost_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Create a frame for audio model pricing
        self.audio_pricing_frame = ttk.Frame(pricing_details_frame)
        
        # Per minute pricing for audio models
        ttk.Label(self.audio_pricing_frame, text="Cost per minute:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.per_minute_var = tk.DoubleVar()
        self.per_minute_entry = ttk.Entry(self.audio_pricing_frame, textvariable=self.per_minute_var, width=15)
        self.per_minute_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Create a frame for TTS model pricing
        self.tts_pricing_frame = ttk.Frame(pricing_details_frame)
        
        # Per million characters pricing for TTS models
        ttk.Label(self.tts_pricing_frame, text="Cost per million characters:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.per_million_chars_var = tk.DoubleVar()
        self.per_million_chars_entry = ttk.Entry(self.tts_pricing_frame, textvariable=self.per_million_chars_var, width=15)
        self.per_million_chars_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Create a frame for audio token model pricing (special audio token rates)
        self.audio_token_pricing_frame = ttk.Frame(pricing_details_frame)
        
        # Input token pricing for audio tokens
        ttk.Label(self.audio_token_pricing_frame, text="Audio Input Cost (per million tokens):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.audio_input_cost_var = tk.DoubleVar()
        self.audio_input_cost_entry = ttk.Entry(self.audio_token_pricing_frame, textvariable=self.audio_input_cost_var, width=15)
        self.audio_input_cost_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Output token pricing for audio tokens
        ttk.Label(self.audio_token_pricing_frame, text="Audio Output Cost (per million tokens):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.audio_output_cost_var = tk.DoubleVar()
        self.audio_output_cost_entry = ttk.Entry(self.audio_token_pricing_frame, textvariable=self.audio_output_cost_var, width=15)
        self.audio_output_cost_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Save button
        ttk.Button(buttons_frame, text="Save Changes", command=self.save_model_pricing).pack(side=tk.LEFT, padx=10)
        
        # Reset to defaults button
        ttk.Button(buttons_frame, text="Reset to Default", command=self.reset_model_pricing).pack(side=tk.LEFT, padx=10)
        
        # Load initial models
        self.load_provider_models()
        
    def load_provider_models(self):
        """Load models for the selected provider"""
        provider = self.provider_var.get()
        models = PricingService.get_models_by_provider(provider)
        
        # Update dropdown with models
        self.model_dropdown['values'] = models
        if models:
            self.model_dropdown.current(0)
            self.load_model_pricing()
    
    def load_model_pricing(self, event=None):
        """Load pricing details for the selected model"""
        model = self.model_var.get()
        if not model:
            return
            
        pricing = PricingService.get_model_pricing(model)
        
        # Hide all pricing frames first
        self.text_pricing_frame.pack_forget()
        self.audio_pricing_frame.pack_forget()
        self.tts_pricing_frame.pack_forget()
        self.audio_token_pricing_frame.pack_forget()
        
        # Check model type and show appropriate frame
        if "per_minute" in pricing:
            # This is an audio model
            self.audio_pricing_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.per_minute_var.set(pricing.get("per_minute", 0))
        elif "per_million_chars" in pricing:
            # This is a TTS model
            self.tts_pricing_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.per_million_chars_var.set(pricing.get("per_million_chars", 0))
        elif "audio_input_per_million" in pricing:
            # This is an audio token model
            self.audio_token_pricing_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.audio_input_cost_var.set(pricing.get("audio_input_per_million", 0))
            self.audio_output_cost_var.set(pricing.get("audio_output_per_million", 0))
        else:
            # This is a text model
            self.text_pricing_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.input_cost_var.set(pricing.get("input_per_million", 0))
            self.output_cost_var.set(pricing.get("output_per_million", 0))
    
    def save_model_pricing(self):
        """Save the pricing details for the selected model"""
        model = self.model_var.get()
        if not model:
            messagebox.showwarning("Warning", "No model selected")
            return
            
        pricing = PricingService.get_model_pricing(model)
        
        # Check if this is an audio model or text model
        if "per_minute" in pricing:
            # This is an audio model
            per_minute = self.per_minute_var.get()
            success = PricingService.update_model_pricing(model, per_minute=per_minute)
        elif "per_million_chars" in pricing:
            # This is a TTS model
            per_million_chars = self.per_million_chars_var.get()
            success = PricingService.update_model_pricing(model, per_million_chars=per_million_chars)
        elif "audio_input_per_million" in pricing:
            # This is an audio token model
            audio_input_cost = self.audio_input_cost_var.get()
            audio_output_cost = self.audio_output_cost_var.get()
            success = PricingService.update_model_pricing(model, audio_input_cost=audio_input_cost, audio_output_cost=audio_output_cost)
        else:
            # This is a text model
            input_cost = self.input_cost_var.get()
            output_cost = self.output_cost_var.get()
            success = PricingService.update_model_pricing(model, input_cost=input_cost, output_cost=output_cost)
        
        if success:
            messagebox.showinfo("Success", f"Pricing updated for {model}")
            
            # Refresh any cost views
            if self.data is not None:
                self.update_summary_view()
                self.update_costs_view()
        else:
            messagebox.showerror("Error", f"Failed to update pricing for {model}")
    
    def reset_model_pricing(self):
        """Reset the pricing to default for the selected model"""
        model = self.model_var.get()
        if not model:
            messagebox.showwarning("Warning", "No model selected")
            return
            
        # Get the default pricing
        default_pricing = PricingService.DEFAULT_PRICING.get(model, {})
        
        # Check if this is an audio model or text model
        if "per_minute" in default_pricing:
            # This is an audio model
            per_minute = default_pricing.get("per_minute", 0)
            self.per_minute_var.set(per_minute)
            success = PricingService.update_model_pricing(model, per_minute=per_minute)
        elif "per_million_chars" in default_pricing:
            # This is a TTS model
            per_million_chars = default_pricing.get("per_million_chars", 0)
            self.per_million_chars_var.set(per_million_chars)
            success = PricingService.update_model_pricing(model, per_million_chars=per_million_chars)
        elif "audio_input_per_million" in default_pricing:
            # This is an audio token model
            audio_input_cost = default_pricing.get("audio_input_per_million", 0)
            audio_output_cost = default_pricing.get("audio_output_per_million", 0)
            self.audio_input_cost_var.set(audio_input_cost)
            self.audio_output_cost_var.set(audio_output_cost)
            success = PricingService.update_model_pricing(model, audio_input_cost=audio_input_cost, audio_output_cost=audio_output_cost)
        else:
            # This is a text model
            input_cost = default_pricing.get("input_per_million", 0)
            output_cost = default_pricing.get("output_per_million", 0)
            self.input_cost_var.set(input_cost)
            self.output_cost_var.set(output_cost)
            success = PricingService.update_model_pricing(model, input_cost=input_cost, output_cost=output_cost)
        
        if success:
            messagebox.showinfo("Success", f"Pricing reset to default for {model}")
            
            # Refresh any cost views
            if self.data is not None:
                self.update_summary_view()
                self.update_costs_view()
        else:
            messagebox.showerror("Error", f"Failed to reset pricing for {model}")
        
    def refresh_file_list(self):
        # Clear existing items
        self.file_tree.delete(*self.file_tree.get_children())
        
        # Check if log directory exists
        if not os.path.exists(self.log_dir):
            messagebox.showinfo("Info", f"Log directory not found: {self.log_dir}")
            return
        
        # Add root directories
        for item in os.listdir(self.log_dir):
            item_path = os.path.join(self.log_dir, item)
            if os.path.isdir(item_path):
                # Add project folder
                folder_id = self.file_tree.insert("", "end", text=item, values=("", ""))
                
                # Add log files within folder
                for file in os.listdir(item_path):
                    file_path = os.path.join(item_path, file)
                    if os.path.isfile(file_path) and file.endswith('.csv'):
                        size = f"{os.path.getsize(file_path) / 1024:.1f} KB"
                        modified = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M")
                        self.file_tree.insert(folder_id, "end", text=file, 
                                            values=(size, modified),
                                            tags=(file_path,))
                            
    def on_file_select(self, event):
        selected_items = self.file_tree.selection()
        if not selected_items:
            return
            
        item_id = selected_items[0]
        
        # Get item tags (which contains the file path)
        tags = self.file_tree.item(item_id, "tags")
        
        # If tags is not empty, it's a file
        if tags:
            file_path = tags[0]
            self.load_log_file(file_path)
        
    def load_log_file(self, file_path):
        try:
            # Load data with pandas
            self.data = pd.read_csv(file_path)
            self.current_file = file_path
            
            # Ensure Date column is properly formatted
            if 'Date' in self.data.columns:
                self.data['Date'] = pd.to_datetime(self.data['Date']).dt.date
            
            # Populate date filter dropdowns
            self.populate_date_filters()
            
            # Show data in raw view
            self.update_raw_view()
            
            # Generate summary stats
            self.update_summary_view()
            
            # Generate charts
            self.update_charts_view()
            
            # Generate costs analysis
            self.update_costs_view()
            
            # Set focus to notebook
            self.notebook.select(1)  # Select Summary tab
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load log file: {str(e)}")
    
    def populate_date_filters(self):
        """Populate date filter dropdowns with values from the data"""
        if self.data is None or 'Date' not in self.data.columns:
            return
            
        # Get unique dates from data
        dates = pd.to_datetime(self.data['Date']).dt.date.unique()
        
        if len(dates) == 0:
            return
            
        # Extract unique years, months, days
        years = sorted(set(d.year for d in dates))
        months = sorted(set(d.month for d in dates))
        days = sorted(set(d.day for d in dates))
        
        # Update comboboxes
        self.start_year['values'] = years
        self.start_month['values'] = months
        self.start_day['values'] = days
        
        self.end_year['values'] = years
        self.end_month['values'] = months
        self.end_day['values'] = days
        
        # Update quick filter comboboxes
        self.quick_year['values'] = years
        if years:
            self.quick_year.set(str(years[-1]))  # Set to latest year by default
            
        self.quick_month_year['values'] = years
        if years:
            self.quick_month_year.set(str(years[-1]))  # Set to latest year by default
            
        self.quick_month['values'] = months
        if months:
            self.quick_month.set(str(datetime.now().month))  # Set to current month if available
        
        # Set default values to earliest and latest dates
        min_date = min(dates)
        max_date = max(dates)
        
        self.start_year.set(str(min_date.year))
        self.start_month.set(str(min_date.month))
        self.start_day.set(str(min_date.day))
        
        self.end_year.set(str(max_date.year))
        self.end_month.set(str(max_date.month))
        self.end_day.set(str(max_date.day))
        
    def update_raw_view(self):
        # Clear existing data
        self.raw_tree.delete(*self.raw_tree.get_children())
        
        # Use filtered data if filter is active, otherwise use all data
        display_data = self.filtered_data if self.date_filter_active else self.data
        
        if display_data is None or len(display_data) == 0:
            return
        
        # Configure columns
        columns = list(display_data.columns)
        self.raw_tree["columns"] = columns
        
        # Configure column display
        for col in columns:
            self.raw_tree.column(col, width=100, minwidth=50)
            self.raw_tree.heading(col, text=col)
            
        # Hide the first column (treeview default column)
        self.raw_tree.column("#0", width=0, stretch=tk.NO)
        
        # Add data rows
        for i, row in display_data.iterrows():
            values = [row[col] for col in columns]
            self.raw_tree.insert("", "end", text="", values=values)
            
    def update_summary_view(self):
        # Clear existing widgets
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
            
        try:
            # Use filtered data if filter is active, otherwise use all data
            display_data = self.filtered_data if self.date_filter_active else self.data
            
            if display_data is None or len(display_data) == 0:
                ttk.Label(self.summary_frame, text="No data to display").pack(padx=20, pady=20)
                return
            
            # Create a scrollable frame for the summary view
            summary_canvas = tk.Canvas(self.summary_frame)
            scrollbar = ttk.Scrollbar(self.summary_frame, orient="vertical", command=summary_canvas.yview)
            scrollable_frame = ttk.Frame(summary_canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: summary_canvas.configure(scrollregion=summary_canvas.bbox("all"))
            )
            
            summary_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            summary_canvas.configure(yscrollcommand=scrollbar.set)
            
            summary_canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            # Total counts
            total_records = len(display_data)
            total_tokens = display_data['TotalTokens'].sum()
            total_submit_tokens = display_data['SubmitTokens'].sum()
            total_reply_tokens = display_data['ReplyTokens'].sum()
            
            # Calculate total audio duration
            if 'AudioDuration(s)' in display_data.columns:
                total_audio_duration = display_data['AudioDuration(s)'].sum()
                audio_hours = total_audio_duration / 3600
            else:
                total_audio_duration = 0
                audio_hours = 0
            
            # Calculate total costs
            total_text_cost = 0
            total_audio_cost = 0
            
            # Process each row for cost calculation
            for _, row in display_data.iterrows():
                model = row['Model']
                submit_tokens = row['SubmitTokens']
                reply_tokens = row['ReplyTokens']
                
                # Calculate text model costs
                if model != 'whisper-1':  # Skip whisper model for text cost calculation
                    _, _, row_text_cost = PricingService.get_text_model_cost(model, submit_tokens, reply_tokens)
                    total_text_cost += row_text_cost
                
                # Calculate audio costs if applicable
                if model == 'whisper-1' and 'AudioDuration(s)' in row and row['AudioDuration(s)'] > 0:
                    row_audio_cost = PricingService.get_whisper_cost(row['AudioDuration(s)'])
                    total_audio_cost += row_audio_cost
            
            total_cost = total_text_cost + total_audio_cost
                
            # Model summaries
            model_summary = display_data.groupby('Model').agg({
                'SubmitTokens': 'sum',
                'ReplyTokens': 'sum',
                'TotalTokens': 'sum',
                'ID': 'count'
            }).reset_index()
            
            # Add audio duration if available
            if 'AudioDuration(s)' in display_data.columns:
                audio_by_model = display_data.groupby('Model')['AudioDuration(s)'].sum().reset_index()
                model_summary = pd.merge(model_summary, audio_by_model, on='Model', how='left')
                model_summary['AudioDuration(s)'] = model_summary['AudioDuration(s)'].fillna(0)
            
            # Calculate cost for each model
            model_summary['InputCost'] = 0.0
            model_summary['OutputCost'] = 0.0
            model_summary['TotalCost'] = 0.0
            
            for idx, row in model_summary.iterrows():
                model = row['Model']
                submit_tokens = row['SubmitTokens']
                reply_tokens = row['ReplyTokens']
                
                if model == 'whisper-1' and 'AudioDuration(s)' in row:
                    # For Whisper, calculate cost based on audio duration
                    audio_duration = row['AudioDuration(s)']
                    cost = PricingService.get_whisper_cost(audio_duration)
                    model_summary.at[idx, 'TotalCost'] = cost
                else:
                    # For text models, calculate based on tokens
                    input_cost, output_cost, total_cost = PricingService.get_text_model_cost(
                        model, submit_tokens, reply_tokens
                    )
                    model_summary.at[idx, 'InputCost'] = input_cost
                    model_summary.at[idx, 'OutputCost'] = output_cost
                    model_summary.at[idx, 'TotalCost'] = total_cost
            
            model_summary = model_summary.rename(columns={'ID': 'Count'})
            
            # API Endpoint summaries
            endpoint_summary = display_data.groupby('API_Endpoint').agg({
                'SubmitTokens': 'sum',
                'ReplyTokens': 'sum',
                'TotalTokens': 'sum',
                'ID': 'count'
            }).reset_index()
            
            # Add audio duration if available
            if 'AudioDuration(s)' in display_data.columns:
                audio_by_endpoint = display_data.groupby('API_Endpoint')['AudioDuration(s)'].sum().reset_index()
                endpoint_summary = pd.merge(endpoint_summary, audio_by_endpoint, on='API_Endpoint', how='left')
                endpoint_summary['AudioDuration(s)'] = endpoint_summary['AudioDuration(s)'].fillna(0)
            
            # Calculate cost for each endpoint
            endpoint_summary['TotalCost'] = 0.0
            
            for idx, row in endpoint_summary.iterrows():
                endpoint = row['API_Endpoint']
                submit_tokens = row['SubmitTokens']
                reply_tokens = row['ReplyTokens']
                
                # Get all models used with this endpoint
                endpoint_models = display_data[display_data['API_Endpoint'] == endpoint]['Model'].unique()
                
                endpoint_cost = 0.0
                
                for model in endpoint_models:
                    # Get tokens for this model and endpoint
                    model_data = display_data[(display_data['API_Endpoint'] == endpoint) & (display_data['Model'] == model)]
                    model_submit_tokens = model_data['SubmitTokens'].sum()
                    model_reply_tokens = model_data['ReplyTokens'].sum()
                    
                    if model == 'whisper-1' and 'AudioDuration(s)' in model_data.columns:
                        # For Whisper, calculate cost based on audio duration
                        audio_duration = model_data['AudioDuration(s)'].sum()
                        model_cost = PricingService.get_whisper_cost(audio_duration)
                    else:
                        # For text models, calculate based on tokens
                        _, _, model_cost = PricingService.get_text_model_cost(
                            model, model_submit_tokens, model_reply_tokens
                        )
                    
                    endpoint_cost += model_cost
                
                endpoint_summary.at[idx, 'TotalCost'] = endpoint_cost
            
            endpoint_summary = endpoint_summary.rename(columns={'ID': 'Count'})
            
            # Node summaries - Extract node name from file path
            if 'NodeName' not in display_data.columns:
                # Extract node name from the file path
                node_name = os.path.basename(os.path.dirname(self.current_file))
                display_data['NodeName'] = node_name
            
            node_summary = display_data.groupby('NodeName').agg({
                'SubmitTokens': 'sum',
                'ReplyTokens': 'sum',
                'TotalTokens': 'sum',
                'ID': 'count'
            }).reset_index()
            
            # Add audio duration if available
            if 'AudioDuration(s)' in display_data.columns:
                audio_by_node = display_data.groupby('NodeName')['AudioDuration(s)'].sum().reset_index()
                node_summary = pd.merge(node_summary, audio_by_node, on='NodeName', how='left')
                node_summary['AudioDuration(s)'] = node_summary['AudioDuration(s)'].fillna(0)
            
            # Calculate cost for each node
            node_summary['TotalCost'] = 0.0
            
            for idx, row in node_summary.iterrows():
                node = row['NodeName']
                node_data = display_data[display_data['NodeName'] == node]
                
                node_cost = 0.0
                
                for _, token_row in node_data.iterrows():
                    model = token_row['Model']
                    submit_tokens = token_row['SubmitTokens']
                    reply_tokens = token_row['ReplyTokens']
                    
                    if model == 'whisper-1' and 'AudioDuration(s)' in token_row and token_row['AudioDuration(s)'] > 0:
                        # For Whisper, calculate cost based on audio duration
                        audio_duration = token_row['AudioDuration(s)']
                        row_cost = PricingService.get_whisper_cost(audio_duration)
                    else:
                        # For text models, calculate based on tokens
                        _, _, row_cost = PricingService.get_text_model_cost(
                            model, submit_tokens, reply_tokens
                        )
                    
                    node_cost += row_cost
                
                node_summary.at[idx, 'TotalCost'] = node_cost
            
            node_summary = node_summary.rename(columns={'ID': 'Count'})
            
            # Create summary treeviews with labels
            summaries = [
                {"title": "By Model", "data": model_summary},
                {"title": "By API Endpoint", "data": endpoint_summary},
                {"title": "By Node", "data": node_summary}
            ]
            
            # Add overall summary at the top
            overall_frame = ttk.LabelFrame(scrollable_frame, text="Overall Summary")
            overall_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # Summary stats in a grid
            ttk.Label(overall_frame, text="Total Records:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=str(total_records)).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(overall_frame, text="Total Submit Tokens:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"{total_submit_tokens:,}").grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(overall_frame, text="Total Reply Tokens:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"{total_reply_tokens:,}").grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(overall_frame, text="Total Tokens:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"{total_tokens:,}").grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(overall_frame, text="Total Audio Duration:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"{total_audio_duration:.2f} seconds ({audio_hours:.2f} hours)").grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
            
            # Add cost information
            ttk.Label(overall_frame, text="Total Text Model Cost:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"${total_text_cost:.4f}").grid(row=5, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(overall_frame, text="Total Audio Transcription Cost:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"${total_audio_cost:.4f}").grid(row=6, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(overall_frame, text="Total Cost:").grid(row=7, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(overall_frame, text=f"${(total_text_cost + total_audio_cost):.4f}").grid(row=7, column=1, sticky=tk.W, padx=5, pady=2)
            
            # Create frame for detailed summaries
            details_frame = ttk.Frame(scrollable_frame)
            details_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Configure row and column weights
            details_frame.columnconfigure(0, weight=1)
            for i in range(len(summaries)):
                details_frame.rowconfigure(i, weight=1)
        
            # Create subframes for each summary type
            for i, summary in enumerate(summaries):
                frame = ttk.LabelFrame(details_frame, text=summary["title"])
                frame.grid(row=i, column=0, padx=5, pady=5, sticky="nsew")
                
                # Create a treeview for the summary
                # Add both vertical and horizontal scrollbars
                scrollbar_y = ttk.Scrollbar(frame)
                scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
                
                scrollbar_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
                scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
                
                tree = ttk.Treeview(frame, yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
                tree.pack(fill=tk.BOTH, expand=True)
                scrollbar_y.config(command=tree.yview)
                scrollbar_x.config(command=tree.xview)
                
                # Configure columns
                columns = list(summary["data"].columns)
                tree["columns"] = columns
                
                # Hide the default column
                tree.column("#0", width=0, stretch=tk.NO)
                
                # Configure column display with specific sizing based on content type
                for col in columns:
                    if col in ['Model', 'API_Endpoint', 'NodeName']:
                        # These are text columns, give them more space
                        tree.column(col, width=180, minwidth=100)
                    elif col in ['Count']:
                        # Count columns can be narrow
                        tree.column(col, width=70, minwidth=50)
                    elif col in ['AudioDuration(s)']:
                        # Audio duration column
                        tree.column(col, width=140, minwidth=90)
                    elif col in ['InputCost', 'OutputCost', 'TotalCost']:
                        # Cost columns
                        tree.column(col, width=100, minwidth=80)
                    else:
                        # Token columns
                        tree.column(col, width=120, minwidth=80)
                    tree.heading(col, text=col)
                    
                # Add data rows
                for j, row in summary["data"].iterrows():
                    values = [row[col] for col in columns]
                    tree.insert("", "end", text="", values=values)
                    
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate summary: {str(e)}")
            
    def update_charts_view(self):
        # Clear existing widgets
        for widget in self.charts_frame.winfo_children():
            widget.destroy()
            
        try:
            # Use filtered data if filter is active, otherwise use all data
            display_data = self.filtered_data if self.date_filter_active else self.data
            
            if display_data is None or len(display_data) == 0:
                ttk.Label(self.charts_frame, text="No data to display").pack(padx=20, pady=20)
                return
            
            # Create a figure with subplots
            fig = plt.figure(figsize=(12, 8))
            
            # 1. Pie chart of token usage by model
            ax1 = fig.add_subplot(221)
            model_data = display_data.groupby('Model')['TotalTokens'].sum()
            ax1.pie(model_data, labels=model_data.index, autopct='%1.1f%%', startangle=90)
            ax1.axis('equal')
            ax1.set_title('Token Usage by Model')
            
            # 2. Bar chart of token types by model
            ax2 = fig.add_subplot(222)
            model_token_types = display_data.groupby('Model').agg({
                'SubmitTokens': 'sum',
                'ReplyTokens': 'sum'
            })
            model_token_types.plot(kind='bar', ax=ax2)
            ax2.set_title('Token Types by Model')
            ax2.set_ylabel('Tokens')
            
            # 3. Line chart of usage over time (by date)
            ax3 = fig.add_subplot(223)
            date_usage = display_data.groupby('Date')['TotalTokens'].sum()
            date_usage.plot(kind='line', marker='o', ax=ax3)
            ax3.set_title('Token Usage Over Time')
            ax3.set_xlabel('Date')
            ax3.set_ylabel('Total Tokens')
            
            # 4. Bar chart of request counts by API endpoint
            ax4 = fig.add_subplot(224)
            endpoint_counts = display_data.groupby('API_Endpoint').size()
            endpoint_counts.plot(kind='bar', ax=ax4)
            ax4.set_title('Request Count by API Endpoint')
            ax4.set_ylabel('Number of Requests')
            
            # Adjust layout
            plt.tight_layout()
            
            # Create a canvas to display the plots
            canvas = FigureCanvasTkAgg(fig, master=self.charts_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate charts: {str(e)}")
            
    def update_costs_view(self):
        # Clear existing widgets
        for widget in self.costs_frame.winfo_children():
            widget.destroy()
            
        try:
            # Use filtered data if filter is active, otherwise use all data
            display_data = self.filtered_data if self.date_filter_active else self.data
            
            if display_data is None or len(display_data) == 0:
                ttk.Label(self.costs_frame, text="No data to display").pack(padx=20, pady=20)
                return
            
            # Calculate costs for each row
            costs_data = display_data.copy()
            costs_data['InputCost'] = 0.0
            costs_data['OutputCost'] = 0.0
            costs_data['TotalCost'] = 0.0
            
            for idx, row in costs_data.iterrows():
                model = row['Model']
                submit_tokens = row['SubmitTokens']
                reply_tokens = row['ReplyTokens']
                
                if model == 'whisper-1' and 'AudioDuration(s)' in row and row['AudioDuration(s)'] > 0:
                    # For Whisper, calculate cost based on audio duration
                    audio_duration = row['AudioDuration(s)']
                    cost = PricingService.get_whisper_cost(audio_duration)
                    costs_data.at[idx, 'TotalCost'] = cost
                else:
                    # For text models, calculate based on tokens
                    input_cost, output_cost, total_cost = PricingService.get_text_model_cost(
                        model, submit_tokens, reply_tokens
                    )
                    costs_data.at[idx, 'InputCost'] = input_cost
                    costs_data.at[idx, 'OutputCost'] = output_cost
                    costs_data.at[idx, 'TotalCost'] = total_cost
            
            # Create a frame for cost summary
            summary_frame = ttk.LabelFrame(self.costs_frame, text="Cost Summary")
            summary_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # Calculate total costs
            total_input_cost = costs_data['InputCost'].sum()
            total_output_cost = costs_data['OutputCost'].sum()
            total_cost = costs_data['TotalCost'].sum()
            
            # Calculate total audio duration if available
            has_audio = 'AudioDuration(s)' in costs_data.columns
            total_audio_duration = costs_data['AudioDuration(s)'].sum() if has_audio else 0
            audio_hours = total_audio_duration / 3600 if has_audio else 0
            
            # Calculate model-specific costs
            model_costs = costs_data.groupby('Model').agg({
                'InputCost': 'sum',
                'OutputCost': 'sum',
                'TotalCost': 'sum'
            }).reset_index()
            
            # Add audio duration if available
            if has_audio:
                audio_by_model = costs_data.groupby('Model')['AudioDuration(s)'].sum().reset_index()
                model_costs = pd.merge(model_costs, audio_by_model, on='Model', how='left')
                model_costs['AudioDuration(s)'] = model_costs['AudioDuration(s)'].fillna(0)
            
            # Calculate date-specific costs
            date_costs = costs_data.groupby('Date').agg({
                'TotalCost': 'sum'
            }).reset_index()
            
            # Add audio duration by date if available
            if has_audio:
                audio_by_date = costs_data.groupby('Date')['AudioDuration(s)'].sum().reset_index()
                date_costs = pd.merge(date_costs, audio_by_date, on='Date', how='left')
                date_costs['AudioDuration(s)'] = date_costs['AudioDuration(s)'].fillna(0)
            
            # Calculate endpoint-specific costs
            endpoint_costs = costs_data.groupby('API_Endpoint').agg({
                'TotalCost': 'sum'
            }).reset_index()
            
            # Add audio duration by endpoint if available
            if has_audio:
                audio_by_endpoint = costs_data.groupby('API_Endpoint')['AudioDuration(s)'].sum().reset_index()
                endpoint_costs = pd.merge(endpoint_costs, audio_by_endpoint, on='API_Endpoint', how='left')
                endpoint_costs['AudioDuration(s)'] = endpoint_costs['AudioDuration(s)'].fillna(0)
            
            # Display cost summary
            ttk.Label(summary_frame, text="Total Input Cost:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(summary_frame, text=f"${total_input_cost:.4f}").grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(summary_frame, text="Total Output Cost:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(summary_frame, text=f"${total_output_cost:.4f}").grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
            
            ttk.Label(summary_frame, text="Total API Cost:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(summary_frame, text=f"${total_cost:.4f}").grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
            
            if has_audio:
                ttk.Label(summary_frame, text="Total Audio Duration:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
                ttk.Label(summary_frame, text=f"{total_audio_duration:.2f} seconds ({audio_hours:.2f} hours)").grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
            
            # Create a figure with subplots for cost charts
            if has_audio:
                # Create a figure with 6 subplots (3x2 grid) when audio data is available
                fig = plt.figure(figsize=(14, 12))
                
                # 1. Pie chart of costs by model
                ax1 = fig.add_subplot(321)
                model_cost_data = model_costs.set_index('Model')['TotalCost']
                ax1.pie(model_cost_data, labels=model_cost_data.index, autopct='%1.1f%%', startangle=90)
                ax1.axis('equal')
                ax1.set_title('Cost Distribution by Model')
                
                # 2. Bar chart of input vs output costs by model
                ax2 = fig.add_subplot(322)
                model_cost_types = model_costs.set_index('Model')[['InputCost', 'OutputCost']]
                model_cost_types.plot(kind='bar', ax=ax2)
                ax2.set_title('Input vs Output Costs by Model')
                ax2.set_ylabel('Cost ($)')
                
                # 3. Line chart of costs over time (by date)
                ax3 = fig.add_subplot(323)
                date_costs.set_index('Date')['TotalCost'].plot(kind='line', marker='o', ax=ax3)
                ax3.set_title('Cost Trend Over Time')
                ax3.set_xlabel('Date')
                ax3.set_ylabel('Total Cost ($)')
                
                # 4. Bar chart of costs by API endpoint
                ax4 = fig.add_subplot(324)
                endpoint_costs.set_index('API_Endpoint')['TotalCost'].plot(kind='bar', ax=ax4)
                ax4.set_title('Cost by API Endpoint')
                ax4.set_ylabel('Total Cost ($)')
                
                # 5. Bar chart of audio duration by model
                ax5 = fig.add_subplot(325)
                audio_models = model_costs[model_costs['AudioDuration(s)'] > 0]
                if not audio_models.empty:
                    audio_models.set_index('Model')['AudioDuration(s)'].plot(kind='bar', ax=ax5)
                    ax5.set_title('Audio Duration by Model')
                    ax5.set_ylabel('Duration (seconds)')
                else:
                    ax5.set_title('No Audio Data Available')
                
                # 6. Line chart of audio duration over time
                ax6 = fig.add_subplot(326)
                if 'AudioDuration(s)' in date_costs.columns:
                    date_costs.set_index('Date')['AudioDuration(s)'].plot(kind='line', marker='o', ax=ax6)
                    ax6.set_title('Audio Duration Over Time')
                    ax6.set_xlabel('Date')
                    ax6.set_ylabel('Duration (seconds)')
                else:
                    ax6.set_title('No Audio Data Available')
            else:
                # Create a figure with 4 subplots when no audio data is available
                fig = plt.figure(figsize=(12, 10))
                
                # 1. Pie chart of costs by model
                ax1 = fig.add_subplot(221)
                model_cost_data = model_costs.set_index('Model')['TotalCost']
                ax1.pie(model_cost_data, labels=model_cost_data.index, autopct='%1.1f%%', startangle=90)
                ax1.axis('equal')
                ax1.set_title('Cost Distribution by Model')
                
                # 2. Bar chart of input vs output costs by model
                ax2 = fig.add_subplot(222)
                model_cost_types = model_costs.set_index('Model')[['InputCost', 'OutputCost']]
                model_cost_types.plot(kind='bar', ax=ax2)
                ax2.set_title('Input vs Output Costs by Model')
                ax2.set_ylabel('Cost ($)')
                
                # 3. Line chart of costs over time (by date)
                ax3 = fig.add_subplot(223)
                date_costs.set_index('Date')['TotalCost'].plot(kind='line', marker='o', ax=ax3)
                ax3.set_title('Cost Trend Over Time')
                ax3.set_xlabel('Date')
                ax3.set_ylabel('Total Cost ($)')
                
                # 4. Bar chart of costs by API endpoint
                ax4 = fig.add_subplot(224)
                endpoint_costs.set_index('API_Endpoint')['TotalCost'].plot(kind='bar', ax=ax4)
                ax4.set_title('Cost by API Endpoint')
                ax4.set_ylabel('Total Cost ($)')
            
            # Adjust layout
            plt.tight_layout()
            
            # Create a canvas to display the plots
            canvas = FigureCanvasTkAgg(fig, master=self.costs_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            # Add a cost breakdown table
            table_frame = ttk.LabelFrame(self.costs_frame, text="Cost Breakdown by Model")
            table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Create a treeview for the cost breakdown
            scrollbar_y = ttk.Scrollbar(table_frame)
            scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
            
            scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
            scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
            
            tree = ttk.Treeview(table_frame, yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
            tree.pack(fill=tk.BOTH, expand=True)
            scrollbar_y.config(command=tree.yview)
            scrollbar_x.config(command=tree.xview)
            
            # Configure columns
            if has_audio:
                columns = ['Model', 'InputCost', 'OutputCost', 'TotalCost', 'AudioDuration(s)', 'Percentage']
            else:
                columns = ['Model', 'InputCost', 'OutputCost', 'TotalCost', 'Percentage']
                
            tree["columns"] = columns
            
            # Hide the default column
            tree.column("#0", width=0, stretch=tk.NO)
            
            # Configure column display
            tree.column('Model', width=180, minwidth=100)
            tree.column('InputCost', width=100, minwidth=80)
            tree.column('OutputCost', width=100, minwidth=80)
            tree.column('TotalCost', width=100, minwidth=80)
            if has_audio:
                tree.column('AudioDuration(s)', width=120, minwidth=100)
            tree.column('Percentage', width=100, minwidth=80)
            
            tree.heading('Model', text='Model')
            tree.heading('InputCost', text='Input Cost ($)')
            tree.heading('OutputCost', text='Output Cost ($)')
            tree.heading('TotalCost', text='Total Cost ($)')
            if has_audio:
                tree.heading('AudioDuration(s)', text='Audio Duration (s)')
            tree.heading('Percentage', text='% of Total')
            
            # Add data rows
            for idx, row in model_costs.iterrows():
                model = row['Model']
                input_cost = row['InputCost']
                output_cost = row['OutputCost']
                model_total_cost = row['TotalCost']
                percentage = (model_total_cost / total_cost * 100) if total_cost > 0 else 0
                
                if has_audio:
                    audio_duration = row['AudioDuration(s)'] if 'AudioDuration(s)' in row else 0
                    tree.insert("", "end", text="", values=[
                        model,
                        f"${input_cost:.4f}",
                        f"${output_cost:.4f}",
                        f"${model_total_cost:.4f}",
                        f"{audio_duration:.2f}",
                        f"{percentage:.2f}%"
                    ])
                else:
                    tree.insert("", "end", text="", values=[
                        model,
                        f"${input_cost:.4f}",
                        f"${output_cost:.4f}",
                        f"${model_total_cost:.4f}",
                        f"{percentage:.2f}%"
                    ])
                
            # Add a total row
            if has_audio:
                tree.insert("", "end", text="", values=[
                    "TOTAL",
                    f"${total_input_cost:.4f}",
                    f"${total_output_cost:.4f}",
                    f"${total_cost:.4f}",
                    f"{total_audio_duration:.2f}",
                    "100.00%"
                ])
            else:
                tree.insert("", "end", text="", values=[
                    "TOTAL",
                    f"${total_input_cost:.4f}",
                    f"${total_output_cost:.4f}",
                    f"${total_cost:.4f}",
                    "100.00%"
                ])
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate costs: {str(e)}")
            
    def apply_date_filter(self):
        """Apply date filter to the data"""
        if self.data is None:
            messagebox.showinfo("Info", "Please load a log file first")
            return
        
        try:
            # Get date values from comboboxes
            start_year = self.start_year_var.get()
            start_month = self.start_month_var.get()
            start_day = self.start_day_var.get()
            
            end_year = self.end_year_var.get()
            end_month = self.end_month_var.get()
            end_day = self.end_day_var.get()
            
            # Check if we have all components for at least one date
            has_start_date = all([start_year, start_month, start_day])
            has_end_date = all([end_year, end_month, end_day])
            
            if not has_start_date and not has_end_date:
                messagebox.showinfo("Info", "Please select at least one complete date")
                return
            
            # Filter data by date
            self.filtered_data = self.data.copy()
            
            if has_start_date:
                self.start_date = pd.Timestamp(
                    year=int(start_year),
                    month=int(start_month),
                    day=int(start_day)
                ).date()
                
                self.filtered_data = self.filtered_data[
                    pd.to_datetime(self.filtered_data['Date']).dt.date >= self.start_date
                ]
                
            if has_end_date:
                self.end_date = pd.Timestamp(
                    year=int(end_year),
                    month=int(end_month),
                    day=int(end_day)
                ).date()
                
                self.filtered_data = self.filtered_data[
                    pd.to_datetime(self.filtered_data['Date']).dt.date <= self.end_date
                ]
                
            self.date_filter_active = True
                
            # Update all views with filtered data
            self.update_raw_view()
            self.update_summary_view()
            self.update_charts_view()
            self.update_costs_view()
            
            # Show message with filter results
            if len(self.filtered_data) > 0:
                messagebox.showinfo("Filter Applied", f"Found {len(self.filtered_data)} records in the date range")
            else:
                messagebox.showinfo("Filter Applied", "No records found in the selected date range")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error applying filter: {str(e)}")
            
    def clear_date_filter(self):
        """Clear the date filter and show all data"""
        if self.data is None:
            return
            
        # Reset filter state
        self.date_filter_active = False
        self.start_date = None
        self.end_date = None
        self.filtered_data = None
        
        # Reset dropdown selections to default (min and max dates)
        self.populate_date_filters()
        
        # Update all views with original data
        self.update_raw_view()
        self.update_summary_view()
        self.update_charts_view()
        self.update_costs_view()
            
    def delete_selected_file(self):
        selected_items = self.file_tree.selection()
        if not selected_items:
            messagebox.showinfo("Info", "No file selected")
            return
            
        item_id = selected_items[0]
        
        # Get item tags (which contains the file path)
        tags = self.file_tree.item(item_id, "tags")
        
        # If tags is not empty, it's a file
        if tags:
            file_path = tags[0]
            
            # Confirm deletion
            if messagebox.askyesno("Confirm", f"Are you sure you want to delete {os.path.basename(file_path)}?"):
                try:
                    os.remove(file_path)
                    messagebox.showinfo("Success", "File deleted successfully")
                    self.refresh_file_list()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete file: {str(e)}")
                    
    def export_selected_file(self):
        if self.current_file is None or self.data is None:
            messagebox.showinfo("Info", "No file loaded")
            return
            
        try:
            # Ask for save location
            save_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=os.path.basename(self.current_file)
            )
            
            if save_path:
                # Export the data
                self.data.to_csv(save_path, index=False)
                messagebox.showinfo("Success", f"File exported to {save_path}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export file: {str(e)}")
            
    def show_year(self):
        """Quick filter to show an entire year"""
        if self.data is None:
            messagebox.showinfo("Info", "Please load a log file first")
            return
            
        year = self.quick_year_var.get()
        if not year:
            messagebox.showinfo("Info", "Please select a year first")
            return
            
        # Set date range to entire year
        year = int(year)
        self.start_date = pd.Timestamp(year=year, month=1, day=1).date()
        self.end_date = pd.Timestamp(year=year, month=12, day=31).date()
        
        # Update UI to reflect the selection
        self.start_year.set(str(year))
        self.start_month.set("1")
        self.start_day.set("1")
        
        self.end_year.set(str(year))
        self.end_month.set("12")
        self.end_day.set("31")
        
        # Filter the data
        self.filtered_data = self.data[
            (pd.to_datetime(self.data['Date']).dt.year == year)
        ]
        
        self.date_filter_active = True
        
        # Update all views
        self.update_raw_view()
        self.update_summary_view()
        self.update_charts_view()
        self.update_costs_view()
        
        # Show message with filter results
        messagebox.showinfo("Year Filter", f"Showing data for {year}: {len(self.filtered_data)} records")
        
    def show_month(self):
        """Quick filter to show a specific month in a specific year"""
        if self.data is None:
            messagebox.showinfo("Info", "Please load a log file first")
            return
            
        year = self.quick_month_year_var.get()
        month = self.quick_month_var.get()
        
        if not year or not month:
            messagebox.showinfo("Info", "Please select both year and month")
            return
            
        # Set date range to entire month
        year = int(year)
        month = int(month)
        
        # Get last day of month
        if month == 12:
            last_day = 31
        else:
            last_day = (pd.Timestamp(year=year, month=month+1, day=1) - pd.Timedelta(days=1)).day
        
        self.start_date = pd.Timestamp(year=year, month=month, day=1).date()
        self.end_date = pd.Timestamp(year=year, month=month, day=last_day).date()
        
        # Update UI to reflect the selection
        self.start_year.set(str(year))
        self.start_month.set(str(month))
        self.start_day.set("1")
        
        self.end_year.set(str(year))
        self.end_month.set(str(month))
        self.end_day.set(str(last_day))
        
        # Filter the data
        self.filtered_data = self.data[
            (pd.to_datetime(self.data['Date']).dt.year == year) &
            (pd.to_datetime(self.data['Date']).dt.month == month)
        ]
        
        self.date_filter_active = True
        
        # Update all views
        self.update_raw_view()
        self.update_summary_view()
        self.update_charts_view()
        self.update_costs_view()
        
        # Show message with filter results
        month_name = pd.Timestamp(year=year, month=month, day=1).strftime("%B")
        messagebox.showinfo("Month Filter", f"Showing data for {month_name} {year}: {len(self.filtered_data)} records")
    
    def show_current_month(self):
        """Quick filter to show the current month"""
        if self.data is None:
            messagebox.showinfo("Info", "Please load a log file first")
            return
            
        # Get current year and month
        now = datetime.now()
        year = now.year
        month = now.month
        
        # Check if we have this year in our data
        years = sorted(set(pd.to_datetime(self.data['Date']).dt.year))
        if year not in years:
            year = years[-1]  # Use the most recent year in the data
        
        # Set values in the month filter and trigger it
        self.quick_month_year.set(str(year))
        self.quick_month.set(str(month))
        self.show_month()
        
    def show_last_30_days(self):
        """Quick filter to show the last 30 days of data"""
        if self.data is None:
            messagebox.showinfo("Info", "Please load a log file first")
            return
            
        # Get max date in the data
        max_date = pd.to_datetime(self.data['Date']).max().date()
        
        # Calculate date 30 days before
        start_date = max_date - pd.Timedelta(days=30)
        
        # Set the date range
        self.start_date = start_date
        self.end_date = max_date
        
        # Update UI
        self.start_year.set(str(start_date.year))
        self.start_month.set(str(start_date.month))
        self.start_day.set(str(start_date.day))
        
        self.end_year.set(str(max_date.year))
        self.end_month.set(str(max_date.month))
        self.end_day.set(str(max_date.day))
        
        # Filter the data
        self.filtered_data = self.data[
            (pd.to_datetime(self.data['Date']).dt.date >= start_date) &
            (pd.to_datetime(self.data['Date']).dt.date <= max_date)
        ]
        
        self.date_filter_active = True
        
        # Update all views
        self.update_raw_view()
        self.update_summary_view()
        self.update_charts_view()
        self.update_costs_view()
        
        # Show message with filter results
        messagebox.showinfo("Last 30 Days", f"Showing data from {start_date} to {max_date}: {len(self.filtered_data)} records")
        
def main():
    root = tk.Tk()
    app = AdminConsole(root)
    root.mainloop()
    
if __name__ == "__main__":
    main()

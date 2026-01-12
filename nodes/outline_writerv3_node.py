from .base_node import BaseNode
from node_registry import register_node
import sys
import threading
import queue
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import subprocess

# Function to install missing modules
def install_missing_modules(modules):
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            print(f"[OutlineWriterV3Node] Module '{module}' not found. Installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])

# Ensure required modules are installed
required_modules = ['requests', 'bs4']
install_missing_modules(required_modules)

import requests
from bs4 import BeautifulSoup

class WorkflowTerminationRequested(Exception):
    """Exception raised when workflow should be terminated"""
    pass

class ReviewWindow:
    def __init__(self, parent=None, content="", node_instance=None):
        self.result_queue = queue.Queue()
        self.node_instance = node_instance
        
        # Create Tkinter window
        self.root = tk.Toplevel(parent)
        self.root.title("Review Generated Outline")
        self.root.geometry("800x600")
        self.root.minsize(800, 600)
        
        # Make window modal and center it
        self.root.transient(parent)
        self.root.grab_set()
        self.center_window()
        
        self.init_ui(content)
    
    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')
    
    def init_ui(self, content):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Text area for content
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create text widget with scrollbar
        self.text_edit = tk.Text(text_frame, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(text_frame, command=self.text_edit.yview)
        self.text_edit.configure(yscrollcommand=scrollbar.set)
        
        self.text_edit.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Insert content
        self.text_edit.insert(tk.END, content)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        # Accept button
        accept_button = ttk.Button(button_frame, text="Accept", command=self.on_accept)
        accept_button.pack(side=tk.RIGHT, padx=5)
        
        # Edit button
        edit_button = ttk.Button(button_frame, text="Edit & Accept", command=self.on_edit)
        edit_button.pack(side=tk.RIGHT, padx=5)
        
        # Cancel button
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self.on_cancel)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def on_accept(self):
        # Put the original content in the queue
        self.result_queue.put(("accept", self.text_edit.get("1.0", tk.END)))
        self.root.destroy()
    
    def on_edit(self):
        # Put the edited content in the queue
        self.result_queue.put(("edit", self.text_edit.get("1.0", tk.END)))
        self.root.destroy()
    
    def on_cancel(self):
        # Put None in the queue to indicate cancellation
        self.result_queue.put(("cancel", None))
        self.root.destroy()
    
    def show(self):
        self.root.wait_window()

class ChapterConfigDialog:
    def __init__(self, parent=None):
        self.result = None
        self.root = tk.Toplevel(parent)
        self.root.title("Chapter Configuration")
        self.root.geometry("300x200")
        
        # Make dialog modal
        self.root.transient(parent)
        self.root.grab_set()
        
        # Center the dialog
        self.center_window()
        
        self.init_ui()
    
    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')

    def init_ui(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Chapter count input
        chapter_frame = ttk.Frame(main_frame)
        chapter_frame.pack(fill=tk.X, pady=5)
        
        chapter_label = ttk.Label(chapter_frame, text="Number of Chapters:")
        chapter_label.pack(side=tk.LEFT, padx=5)
        
        self.chapter_spin = ttk.Spinbox(chapter_frame, from_=1, to=100, width=5)
        self.chapter_spin.set(10)
        self.chapter_spin.pack(side=tk.RIGHT, padx=5)
        
        # Paragraphs per chapter input
        para_frame = ttk.Frame(main_frame)
        para_frame.pack(fill=tk.X, pady=5)
        
        para_label = ttk.Label(para_frame, text="Paragraphs per Chapter:")
        para_label.pack(side=tk.LEFT, padx=5)
        
        self.para_spin = ttk.Spinbox(para_frame, from_=1, to=10, width=5)
        self.para_spin.set(2)
        self.para_spin.pack(side=tk.RIGHT, padx=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ok_button = ttk.Button(button_frame, text="OK", command=self.on_ok)
        ok_button.pack(side=tk.RIGHT, padx=5)
        
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self.on_cancel)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def on_ok(self):
        try:
            self.result = {
                'num_chapters': int(self.chapter_spin.get()),
                'paragraphs_per_chapter': int(self.para_spin.get())
            }
            self.root.destroy()
        except ValueError:
            tk.messagebox.showerror("Input Error", "Please enter valid numbers")
    
    def on_cancel(self):
        self.root.destroy()
    
    def show(self):
        self.root.wait_window()
        return self.result

class ChapterNavigationWindow:
    """Window for navigating and enhancing individual paragraphs"""
    def __init__(self, parent=None, content="", node_instance=None):
        self.result_queue = queue.Queue()
        self.node_instance = node_instance
        self.chapters = []  # Note: 'chapters' variable name kept for compatibility, but contains paragraphs
        self.current_chapter_index = -1
        
        # Parse content into paragraphs
        self.parse_chapters(content)
        
        # Create Tkinter window
        self.root = tk.Toplevel(parent)
        self.root.title("Paragraph Navigation & Enhancement")
        self.root.geometry("1000x700")
        self.root.minsize(1000, 700)
        
        # Make window modal and center it
        self.root.transient(parent)
        self.root.grab_set()
        self.center_window()
        
        self.init_ui()
    
    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')
    
    def _format_paragraph_title(self, index, paragraph_text):
        """Generate the display title for a paragraph list entry."""
        stripped = paragraph_text.strip()
        if not stripped:
            title = "Untitled"
        else:
            first_line = stripped.split('\n')[0]
            title = first_line[:50] + "..." if len(first_line) > 50 else first_line
        return f"Paragraph {index + 1}: {title}"

    def parse_chapters(self, content):
        """Parse the content into individual paragraphs"""
        # Split content by double newlines (blank lines) to get paragraphs
        paragraphs = content.split('\n\n')
        
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if para:  # Only add non-empty paragraphs
                title = self._format_paragraph_title(i, para)
                self.chapters.append({
                    'title': title,
                    'content': para
                })
    
    def init_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Create horizontal paned window for list and content
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        
        # Left panel - Paragraph list
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="Paragraphs:", font=('Arial', 10, 'bold')).pack(pady=5)
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.chapter_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.chapter_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.chapter_listbox.yview)
        
        # Populate listbox
        for chapter in self.chapters:
            self.chapter_listbox.insert(tk.END, chapter['title'])
        
        self.chapter_listbox.bind('<<ListboxSelect>>', self.on_chapter_select)
        
        # Right panel - Content display and enhancement
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)
        
        ttk.Label(right_frame, text="Paragraph Content:", font=('Arial', 10, 'bold')).pack(pady=5)
        
        # Chapter content display
        content_frame = ttk.Frame(right_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        content_scrollbar = ttk.Scrollbar(content_frame)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.content_text = tk.Text(content_frame, wrap=tk.WORD, yscrollcommand=content_scrollbar.set)
        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scrollbar.config(command=self.content_text.yview)

        save_frame = ttk.Frame(right_frame)
        save_frame.pack(fill=tk.X, pady=(0, 10))
        self.save_button = ttk.Button(save_frame, text="Save Changes", command=self.on_save_paragraph_changes)
        self.save_button.pack(side=tk.LEFT)
        self.save_status_label = ttk.Label(save_frame, text="", foreground="green")
        self.save_status_label.pack(side=tk.LEFT, padx=10)
        
        # Enhancement section
        enhance_frame = ttk.LabelFrame(right_frame, text="Content Enhancement", padding="5")
        enhance_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Enhancement/Search text area
        search_frame = ttk.Frame(enhance_frame)
        search_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        search_scrollbar = ttk.Scrollbar(search_frame)
        search_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.search_text = tk.Text(search_frame, wrap=tk.WORD, height=6, yscrollcommand=search_scrollbar.set)
        self.search_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        search_scrollbar.config(command=self.search_text.yview)
        self.search_text.insert(tk.END, "Enter search terms or view AI enhancement results here...")
        
        # Button frame
        button_frame = ttk.Frame(enhance_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        # Auto Research button (performs AI enhancement + web search)
        self.enhance_button = ttk.Button(button_frame, text="Auto Research", command=self.on_auto_research)
        self.enhance_button.pack(side=tk.LEFT, padx=5)
        
        # Batch input label and entry
        ttk.Label(button_frame, text="Batch:").pack(side=tk.LEFT, padx=(10, 2))
        self.batch_input = ttk.Entry(button_frame, width=20)
        self.batch_input.pack(side=tk.LEFT, padx=2)
        ttk.Label(button_frame, text="(e.g., 1-5 or 2,4,6)", font=('TkDefaultFont', 8)).pack(side=tk.LEFT, padx=2)
        
        # Web Search button
        self.search_button = ttk.Button(button_frame, text="Web Search", command=self.on_web_search)
        self.search_button.pack(side=tk.LEFT, padx=5)
        
        # Bottom buttons
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        
        # Save & Continue button
        save_button = ttk.Button(bottom_frame, text="Save & Continue", command=self.on_save)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        # Cancel button
        cancel_button = ttk.Button(bottom_frame, text="Cancel", command=self.on_cancel)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def on_chapter_select(self, event):
        """Handle paragraph selection from list"""
        selection = self.chapter_listbox.curselection()
        if selection:
            self.current_chapter_index = selection[0]
            paragraph = self.chapters[self.current_chapter_index]
            
            # Display paragraph content
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert(tk.END, paragraph['content'])
            if hasattr(self, 'save_status_label'):
                self.save_status_label.config(text="")

    def on_save_paragraph_changes(self):
        """Persist edits made to the currently selected paragraph."""
        if self.current_chapter_index < 0:
            messagebox.showwarning("No Selection", "Please select a paragraph to save changes.")
            return

        updated_content = self.content_text.get("1.0", tk.END).strip()
        paragraph = self.chapters[self.current_chapter_index]
        paragraph['content'] = updated_content
        new_title = self._format_paragraph_title(self.current_chapter_index, updated_content)
        paragraph['title'] = new_title

        # Update listbox entry to reflect possible title change
        self.chapter_listbox.delete(self.current_chapter_index)
        self.chapter_listbox.insert(self.current_chapter_index, new_title)
        self.chapter_listbox.selection_set(self.current_chapter_index)
        self.chapter_listbox.see(self.current_chapter_index)

        self.save_status_label.config(text="Changes saved")
        self.root.after(2000, lambda: self.save_status_label.config(text=""))
    
    def parse_batch_input(self, batch_str):
        """Parse batch input string into list of indices.
        Supports ranges (1-5) and comma-separated values (2,4,6)
        Returns list of 0-indexed paragraph indices
        """
        if not batch_str or not batch_str.strip():
            return None
        
        indices = set()
        parts = batch_str.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Handle range
                try:
                    start, end = part.split('-')
                    start_idx = int(start.strip()) - 1  # Convert to 0-indexed
                    end_idx = int(end.strip()) - 1
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(self.chapters):
                            indices.add(i)
                except ValueError:
                    continue
            else:
                # Handle single number
                try:
                    idx = int(part) - 1  # Convert to 0-indexed
                    if 0 <= idx < len(self.chapters):
                        indices.add(idx)
                except ValueError:
                    continue
        
        return sorted(list(indices)) if indices else None
    
    def on_auto_research(self):
        """Perform AI enhancement and then web search automatically"""
        if not self.node_instance:
            messagebox.showerror("Error", "Node instance not available.")
            return
        
        # Check if batch input is provided
        batch_str = self.batch_input.get().strip()
        if batch_str:
            # Batch processing mode
            indices = self.parse_batch_input(batch_str)
            if not indices:
                messagebox.showerror("Invalid Input", "Could not parse batch input. Use format like '1-5' or '2,4,6'")
                return
            
            # Process multiple paragraphs with progress window
            self.process_batch_auto_research(indices)
            return
        
        # Single paragraph mode (original behavior)
        if self.current_chapter_index < 0:
            messagebox.showwarning("No Selection", "Please select a paragraph first.")
            return
        
        try:
            # Step 1: AI Enhancement
            # Get the enhancement prompt from node properties
            enhancement_prompt = self.node_instance.properties.get('enhancement_prompt', {}).get('default', '')
            
            # Get current paragraph content
            paragraph = self.chapters[self.current_chapter_index]
            paragraph_content = paragraph['content']
            
            # Combine prompt with paragraph content
            full_prompt = f"{enhancement_prompt}\n\n{paragraph_content}"
            
            # Show processing message
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, "Step 1/2: AI Enhancement... Please wait...")
            self.root.update()
            
            # Call the API through the node instance
            ai_enhancement = self.node_instance.process_with_api(full_prompt)
            
            # Display AI enhancement result
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, ai_enhancement)
            self.root.update()
            
            # Step 2: Web Search using the AI enhancement as search query
            # Show processing message
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, "Step 2/2: Web Search... Please wait...")
            self.root.update()
            
            # Use the AI enhancement result as the search query
            search_query = ai_enhancement.strip()
            
            # Get SearxNG endpoint from node properties
            searxng_endpoint = self.node_instance.properties.get('searxng_endpoint', {}).get('default', '')
            if not searxng_endpoint:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, "Error: No SearxNG endpoint configured. Please select one in node properties.")
                return
            
            # Get the endpoint configuration
            interfaces = self.node_instance.config.get('interfaces', {})
            searxng_config = interfaces.get(searxng_endpoint, {})
            
            # Get the base URL from the API configuration
            base_url = searxng_config.get('api_url', '')
            if not base_url:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, f"Error: No API URL configured for endpoint '{searxng_endpoint}'")
                return
            
            # Ensure the URL ends without a trailing slash, then add /search
            base_url = base_url.rstrip('/')
            searxng_api_url = f"{base_url}/search"
            
            num_results = 5
            
            # Perform web search using SearxNG API
            params = {
                'q': search_query,
                'format': 'json',
                'pageno': 1,
                'language': 'en',
                'n': num_results
            }
            
            print(f"[OutlineWriterV3Node] Auto Research - Searching SearxNG at {searxng_api_url} with query: {search_query[:100]}...")
            response = requests.get(searxng_api_url, params=params, timeout=10)
            
            if response.status_code != 200:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, f"Search API Error: {response.status_code}")
                return
            
            search_results = response.json().get('results', [])
            print(f"[OutlineWriterV3Node] Auto Research - Found {len(search_results)} search results")
            
            if not search_results:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, "No search results found.")
                return
            
            # Scrape content from search results
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, "Scraping content from search results... Please wait...")
            self.root.update()
            
            combined_scraped_text = ''
            for result in search_results[:num_results]:
                url = result.get('url')
                print(f"[OutlineWriterV3Node] Auto Research - Scraping: {url}")
                try:
                    page = requests.get(url, timeout=5)
                    soup = BeautifulSoup(page.content, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    text = soup.get_text(separator=' ', strip=True)
                    # Limit each scraped page to 3000 chars
                    if len(text) > 3000:
                        text = text[:3000]
                    combined_scraped_text += f"\n\n--- Content from {url} ---\n{text}\n"
                except Exception as e:
                    print(f"[OutlineWriterV3Node] Auto Research - Error scraping {url}: {e}")
            
            if not combined_scraped_text.strip():
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, "Failed to scrape any content from search results.")
                return
            
            # Get the web search prompt from node properties
            web_search_prompt = self.node_instance.properties.get('web_search_prompt', {}).get('default', '')
            
            # Get current paragraph content
            current_paragraph = self.chapters[self.current_chapter_index]
            paragraph_content = current_paragraph['content']
            
            # Construct the full prompt: web_search_prompt + paragraph content + scraped content
            full_prompt = f"{web_search_prompt}{paragraph_content}\n\nWeb Search Results:\n{combined_scraped_text}"
            
            # Send to AI for processing
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, "Processing web results with AI... Please wait...")
            self.root.update()
            
            print(f"[OutlineWriterV3Node] Auto Research - Sending to AI with web search prompt")
            ai_response = self.node_instance.process_with_api(full_prompt)
            
            # Append AI response directly to the current paragraph (no empty lines)
            current_paragraph['content'] += f" {ai_response}"
            
            # Update the paragraph content display
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert(tk.END, current_paragraph['content'])
            
            # Show success message in search box
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, f"✓ Auto Research Complete!\n\nAI Enhancement + Web Research added {len(ai_response)} characters.")
            
            print(f"[OutlineWriterV3Node] Auto Research completed successfully")
            
        except Exception as e:
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, f"Error: {str(e)}")
            print(f"[OutlineWriterV3Node] Error in auto research: {str(e)}")
    
    def process_batch_auto_research(self, indices):
        """Process multiple paragraphs with auto research and show progress"""
        total = len(indices)
        
        # Create progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Batch Auto Research Progress")
        progress_window.geometry("500x150")
        progress_window.transient(self.root)
        progress_window.grab_set()
        
        # Center the progress window
        progress_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 150) // 2
        progress_window.geometry(f"+{x}+{y}")
        
        # Progress frame
        frame = ttk.Frame(progress_window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Status label
        status_label = ttk.Label(frame, text="Starting batch auto research...", font=('TkDefaultFont', 10))
        status_label.pack(pady=(0, 10))
        
        # Progress bar
        progress_bar = ttk.Progressbar(frame, length=400, mode='determinate', maximum=total)
        progress_bar.pack(pady=10)
        
        # Progress text
        progress_text = ttk.Label(frame, text=f"0 / {total} paragraphs processed", font=('TkDefaultFont', 9))
        progress_text.pack(pady=(5, 0))
        
        # Current item label
        current_label = ttk.Label(frame, text="", font=('TkDefaultFont', 8), foreground='gray')
        current_label.pack(pady=(5, 0))
        
        # Process each paragraph
        for i, idx in enumerate(indices, 1):
            paragraph = self.chapters[idx]
            paragraph_title = paragraph['title']
            
            # Update progress
            status_label.config(text=f"Processing: {paragraph_title}")
            progress_text.config(text=f"{i} / {total} paragraphs processed")
            current_label.config(text=f"Paragraph {idx + 1}: {paragraph_title[:50]}...")
            progress_bar['value'] = i
            progress_window.update()
            
            try:
                # Perform auto research on this paragraph
                self._perform_auto_research_on_paragraph(idx)
                print(f"[OutlineWriterV3Node] Batch: Completed paragraph {idx + 1}")
                
            except Exception as e:
                print(f"[OutlineWriterV3Node] Batch: Error on paragraph {idx + 1}: {str(e)}")
                # Continue with next paragraph even if one fails
                continue
        
        # Complete
        status_label.config(text="Batch Auto Research Complete!")
        progress_text.config(text=f"{total} / {total} paragraphs processed")
        current_label.config(text="All paragraphs have been processed.")
        progress_window.update()
        
        # Update the listbox and content display to show the last processed item
        if indices:
            last_idx = indices[-1]
            self.current_chapter_index = last_idx
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(last_idx)
            self.chapter_listbox.see(last_idx)
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert(tk.END, self.chapters[last_idx]['content'])
        
        self.search_text.delete("1.0", tk.END)
        self.search_text.insert(tk.END, f"✓ Batch Auto Research Complete!\n\nProcessed {total} paragraphs.")
        
        # Auto-close the progress window after a brief delay
        self.root.after(1000, progress_window.destroy)
    
    def _perform_auto_research_on_paragraph(self, paragraph_idx):
        """Internal method to perform auto research on a specific paragraph by index"""
        # Step 1: AI Enhancement
        enhancement_prompt = self.node_instance.properties.get('enhancement_prompt', {}).get('default', '')
        paragraph = self.chapters[paragraph_idx]
        paragraph_content = paragraph['content']
        
        full_prompt = f"{enhancement_prompt}\n\n{paragraph_content}"
        ai_enhancement = self.node_instance.process_with_api(full_prompt)
        
        # Step 2: Web Search using the AI enhancement as search query
        search_query = ai_enhancement.strip()
        
        # Get SearxNG endpoint from node properties
        searxng_endpoint = self.node_instance.properties.get('searxng_endpoint', {}).get('default', '')
        if not searxng_endpoint:
            raise Exception("No SearxNG endpoint configured")
        
        interfaces = self.node_instance.config.get('interfaces', {})
        searxng_config = interfaces.get(searxng_endpoint, {})
        base_url = searxng_config.get('api_url', '')
        if not base_url:
            raise Exception(f"No API URL configured for endpoint '{searxng_endpoint}'")
        
        base_url = base_url.rstrip('/')
        searxng_api_url = f"{base_url}/search"
        num_results = 5
        
        # Perform web search
        params = {
            'q': search_query,
            'format': 'json',
            'pageno': 1,
            'language': 'en',
            'n': num_results
        }
        
        response = requests.get(searxng_api_url, params=params, timeout=10)
        if response.status_code != 200:
            raise Exception(f"Search API Error: {response.status_code}")
        
        search_results = response.json().get('results', [])
        if not search_results:
            raise Exception("No search results found")
        
        # Scrape content from search results
        combined_scraped_text = ''
        for result in search_results[:num_results]:
            url = result.get('url')
            try:
                page = requests.get(url, timeout=5)
                soup = BeautifulSoup(page.content, 'html.parser')
                
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                text = soup.get_text(separator=' ', strip=True)
                if len(text) > 3000:
                    text = text[:3000]
                combined_scraped_text += f"\n\n--- Content from {url} ---\n{text}\n"
            except Exception as e:
                print(f"[OutlineWriterV3Node] Error scraping {url}: {e}")
        
        if not combined_scraped_text.strip():
            raise Exception("Failed to scrape any content")
        
        # Get web search prompt and process with AI
        web_search_prompt = self.node_instance.properties.get('web_search_prompt', {}).get('default', '')
        full_prompt = f"{web_search_prompt}{paragraph_content}\n\nWeb Search Results:\n{combined_scraped_text}"
        
        ai_response = self.node_instance.process_with_api(full_prompt)
        
        # Append AI response directly to the paragraph
        paragraph['content'] += f" {ai_response}"
    
    def on_web_search(self):
        """Perform web search, scrape results, summarize with AI, and append to current paragraph"""
        if self.current_chapter_index < 0:
            messagebox.showwarning("No Selection", "Please select a paragraph first.")
            return
        
        search_query = self.search_text.get("1.0", tk.END).strip()
        if not search_query or search_query == "Enter search terms or view AI enhancement results here...":
            messagebox.showwarning("No Search Terms", "Please enter search terms in the enhancement box first.")
            return
        
        if not self.node_instance:
            messagebox.showerror("Error", "Node instance not available.")
            return
        
        # Show processing message
        self.search_text.delete("1.0", tk.END)
        self.search_text.insert(tk.END, "Searching web and scraping content... Please wait...")
        self.root.update()
        
        try:
            # Get SearxNG endpoint from node properties
            searxng_endpoint = self.node_instance.properties.get('searxng_endpoint', {}).get('default', '')
            if not searxng_endpoint:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, "Error: No SearxNG endpoint configured. Please select one in node properties.")
                return
            
            # Get the endpoint configuration
            interfaces = self.node_instance.config.get('interfaces', {})
            searxng_config = interfaces.get(searxng_endpoint, {})
            
            # Get the base URL from the API configuration
            base_url = searxng_config.get('api_url', '')
            if not base_url:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, f"Error: No API URL configured for endpoint '{searxng_endpoint}'")
                return
            
            # Ensure the URL ends without a trailing slash, then add /search
            base_url = base_url.rstrip('/')
            searxng_api_url = f"{base_url}/search"
            
            num_results = 5
            
            # Perform web search using SearxNG API
            params = {
                'q': search_query,
                'format': 'json',
                'pageno': 1,
                'language': 'en',
                'n': num_results
            }
            
            print(f"[OutlineWriterV3Node] Searching SearxNG at {searxng_api_url} with query: {search_query}")
            response = requests.get(searxng_api_url, params=params, timeout=10)
            
            if response.status_code != 200:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, f"Search API Error: {response.status_code}")
                return
            
            search_results = response.json().get('results', [])
            print(f"[OutlineWriterV3Node] Found {len(search_results)} search results")
            
            if not search_results:
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, "No search results found.")
                return
            
            # Scrape content from search results
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, "Scraping content from search results... Please wait...")
            self.root.update()
            
            combined_scraped_text = ''
            for result in search_results[:num_results]:
                url = result.get('url')
                print(f"[OutlineWriterV3Node] Scraping: {url}")
                try:
                    page = requests.get(url, timeout=5)
                    soup = BeautifulSoup(page.content, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    text = soup.get_text(separator=' ', strip=True)
                    # Limit each scraped page to 3000 chars
                    if len(text) > 3000:
                        text = text[:3000]
                    combined_scraped_text += f"\n\n--- Content from {url} ---\n{text}\n"
                except Exception as e:
                    print(f"[OutlineWriterV3Node] Error scraping {url}: {e}")
            
            if not combined_scraped_text.strip():
                self.search_text.delete("1.0", tk.END)
                self.search_text.insert(tk.END, "Failed to scrape any content from search results.")
                return
            
            # Get the web search prompt from node properties
            web_search_prompt = self.node_instance.properties.get('web_search_prompt', {}).get('default', '')
            
            # Get current paragraph content
            current_paragraph = self.chapters[self.current_chapter_index]
            paragraph_content = current_paragraph['content']
            
            # Construct the full prompt: web_search_prompt + paragraph content + scraped content
            full_prompt = f"{web_search_prompt}{paragraph_content}\n\nWeb Search Results:\n{combined_scraped_text}"
            
            # Send to AI for processing
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, "Processing with AI... Please wait...")
            self.root.update()
            
            print(f"[OutlineWriterV3Node] Sending to AI with web search prompt")
            ai_response = self.node_instance.process_with_api(full_prompt)
            
            # Append AI response directly to the current paragraph (no empty lines)
            current_paragraph['content'] += f" {ai_response}"
            
            # Update the paragraph content display
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert(tk.END, current_paragraph['content'])
            
            # Show success message in search box
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, f"✓ Content appended to paragraph!\n\nAdded {len(ai_response)} characters.")
            
            print(f"[OutlineWriterV3Node] Web search and summarization completed successfully")
            
        except Exception as e:
            self.search_text.delete("1.0", tk.END)
            self.search_text.insert(tk.END, f"Error: {str(e)}")
            print(f"[OutlineWriterV3Node] Error in web search: {str(e)}")
    
    def on_save(self):
        """Save changes and close"""
        # Reconstruct the full content from paragraphs
        full_content = ""
        for paragraph in self.chapters:
            if full_content:
                full_content += "\n\n"
            full_content += paragraph['content']
        
        self.result_queue.put(("save", full_content))
        self.root.destroy()
    
    def on_cancel(self):
        """Cancel and close"""
        self.result_queue.put(("cancel", None))
        self.root.destroy()
    
    def show(self):
        """Show the window and wait for it to close"""
        self.root.wait_window()

class WorkflowTerminationException(Exception):
    """Exception raised when workflow should be terminated"""
    pass

@register_node('OutlineWriterV3Node')
class OutlineWriterV3Node(BaseNode):
    def define_inputs(self):
        return ['input']

    def define_outputs(self):
        return ['output']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'OutlineWriterV3Node'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input prompt with review capability and content enhancement.'
            },
            'enhancement_prompt': {
                'type': 'textarea',
                'label': 'Content Enhancement Prompt',
                'default': 'Please enhance and expand the following chapter content with additional details and context:\n\n'
            },
            'web_search_prompt': {
                'type': 'textarea',
                'label': 'Web Search Summary Prompt',
                'default': 'Based on the following paragraph and web search results, create additional content that expands on the topic:\n\nOriginal Paragraph:\n'
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'Prompt',
                'default': 'Processing your request...'
            },
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            },
            'searxng_endpoint': {
                'type': 'dropdown',
                'label': 'SearxNG Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_searxng_default()
            },
            'enable_review': {
                'type': 'boolean',
                'label': 'Enable Review',
                'default': True
            },
            'is_start_node': {
                'type': 'boolean',
                'label': 'Start Node',
                'default': False
            },
            'is_end_node': {
                'type': 'boolean',
                'label': 'End Node',
                'default': False
            }
        })
        return props

    def update_node_name(self, new_name):
        self.properties['node_name']['default'] = new_name
        print(f"[OutlineWriterV3Node] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[OutlineWriterV3Node] Available API endpoints: {api_list}")
        return api_list
    
    def get_searxng_default(self):
        """Get the default SearxNG endpoint, preferring 'searxng' if available"""
        endpoints = self.get_api_endpoints()
        print(f"[OutlineWriterV3Node] Looking for SearxNG endpoint in: {endpoints}")
        
        # Look for 'searxng' or 'searxing' endpoint first (case insensitive)
        for endpoint in endpoints:
            endpoint_lower = endpoint.lower()
            if 'searxng' in endpoint_lower or 'searxing' in endpoint_lower:
                print(f"[OutlineWriterV3Node] Found SearxNG endpoint: {endpoint}")
                return endpoint
        
        # Otherwise return first available or empty string
        print(f"[OutlineWriterV3Node] No SearxNG endpoint found, using first: {endpoints[0] if endpoints else 'None'}")
        return endpoints[0] if endpoints else ''

    def process_with_api(self, prompt):
        """Process a prompt with the selected API endpoint."""
        try:
            # Get API endpoint from properties
            api_endpoint = self.properties.get('api_endpoint', {}).get('default', '')
            if not api_endpoint:
                print("[OutlineWriterV3Node] Error: No API endpoint selected")
                return "Error: No API endpoint selected"
                
            # Use the API service from BaseNode
            api_response = self.send_api_request(
                content=prompt,
                api_name=api_endpoint,
                model=self.config['interfaces'][api_endpoint].get('selected_model')
            )
            
            if not api_response.success:
                print(f"[OutlineWriterV3Node] API call failed: {api_response.error}")
                return f"Error: {api_response.error}"
                
            # Return the content directly
            return api_response.content
                
        except Exception as e:
            print(f"[OutlineWriterV3Node] Error in process_with_api: {str(e)}")
            return f"Error: {str(e)}"

    def clean_response(self, response, is_first_batch):
        """Clean the API response by removing title section if not first batch."""
        # First remove any progress text
        if "Generated chapters" in response:
            lines = response.split('\n')
            start_idx = 0
            for i, line in enumerate(lines):
                if "Chapter" in line and not "chapters" in line.lower():
                    start_idx = i
                    break
            response = '\n'.join(lines[start_idx:])

        # For first batch, clean up the title but keep it
        if is_first_batch:
            lines = response.split('\n')
            title_idx = -1
            chapter_idx = -1
            
            # Find title and first chapter indices
            for i, line in enumerate(lines):
                if line.startswith("Title:"):
                    title_idx = i
                elif line.startswith("Chapter"):
                    chapter_idx = i
                    break
            
            if title_idx != -1 and chapter_idx != -1:
                # Get the title line and clean it
                title_line = lines[title_idx]
                # Find where the marker and chapter count info starts
                if "~" in title_line:
                    title_line = title_line[:title_line.index("~")].strip()
                
                # Reconstruct response with cleaned title and blank line
                cleaned_lines = []
                if title_idx > 0:
                    cleaned_lines.extend(lines[:title_idx])
                cleaned_lines.append(title_line)
                cleaned_lines.append("")  # Add blank line after title
                cleaned_lines.extend(lines[chapter_idx:])
                response = '\n'.join(cleaned_lines)
        else:
            # For non-first batches, extract only chapter content
            # Find the first and last chapter markers
            chapter_markers = []
            lines = response.split('\n')
            
            for i, line in enumerate(lines):
                if line.strip().startswith("Chapter"):
                    chapter_markers.append(i)
            
            # If we found chapters, only keep the content between the first chapter and the end
            if chapter_markers:
                first_chapter_idx = chapter_markers[0]
                response = '\n'.join(lines[first_chapter_idx:])
            else:
                # If no chapters found, check if there's a title section to remove
                title_idx = -1
                for i, line in enumerate(lines):
                    if "Title:" in line or (len(line) > 50 and " – " in line):
                        title_idx = i
                        break
                
                # If title found, remove it and everything before it
                if title_idx != -1:
                    # Find the next empty line after title
                    next_empty = title_idx + 1
                    while next_empty < len(lines) and lines[next_empty].strip():
                        next_empty += 1
                    
                    # Skip the title paragraph
                    response = '\n'.join(lines[next_empty:])
        
        return response.strip()

    def clean_for_prompt(self, data):
        """Clean accumulated data before using it in the next prompt - removes title but keeps chapters."""
        if not data:
            return ""
            
        lines = data.split('\n')
        chapter_idx = -1
        
        # Find the first chapter
        for i, line in enumerate(lines):
            if line.startswith("Chapter"):
                chapter_idx = i
                break
        
        if chapter_idx != -1:
            return '\n'.join(lines[chapter_idx:]).strip()
        return data.strip()

    def extract_chapters(self, text):
        """Extract only the chapter content from the text, removing any title sections."""
        if not text:
            return ""
            
        lines = text.split('\n')
        chapter_idx = -1
        
        # Find the first chapter
        for i, line in enumerate(lines):
            if line.startswith("Chapter"):
                chapter_idx = i
                break
        
        if chapter_idx != -1:
            return '\n'.join(lines[chapter_idx:]).strip()
        return text.strip()

    def process_chapters_batch(self, base_prompt, user_input, start_chapter, end_chapter, total_chapters, paragraphs_per_chapter, accumulated_result=""):
        """Process a batch of chapters with appropriate prompt formatting."""
        
        is_first_batch = (start_chapter == 1)
        
        # Clean accumulated result before using it in the prompt - remove title for prompt only
        cleaned_for_prompt = self.clean_for_prompt(accumulated_result) if accumulated_result else ""
        
        # Build the prompt based on the batch position
        if is_first_batch:
            # First batch
            prompt = (f"{base_prompt} {user_input} ~ {total_chapters} chapters long, "
                     f"{paragraphs_per_chapter} paragraphs per chapter, please generate "
                     f"the book title and chapters {start_chapter} to {end_chapter} to get the story started.")
        elif end_chapter == total_chapters:
            # Final batch
            prompt = (f"{base_prompt} {user_input} ~ {total_chapters} chapters long, "
                     f"{paragraphs_per_chapter} paragraphs per chapter, please generate "
                     f"chapters {start_chapter} to {end_chapter} following the last chapter "
                     f"below and finishing the outline\n\n{cleaned_for_prompt}")
        else:
            # Middle batch
            prompt = (f"{base_prompt} {user_input} ~ {total_chapters} chapters long, "
                     f"{paragraphs_per_chapter} paragraphs per chapter, please generate "
                     f"chapters {start_chapter} to {end_chapter} following the last chapter "
                     f"below\n\n{cleaned_for_prompt}")

        # Log the complete prompt
        print(f"\n{'='*80}\nSending prompt to API for chapters {start_chapter}-{end_chapter}:\n{'-'*80}\n{prompt}\n{'='*80}\n")

        # Get response and clean it
        response = self.process_with_api(prompt)
        
        # If the model echoed our provided context, strip it before cleaning (non-first batches)
        if not is_first_batch and cleaned_for_prompt:
            if cleaned_for_prompt in response:
                response = response.replace(cleaned_for_prompt, "", 1)
        cleaned_response = self.clean_response(response, is_first_batch)

        # For non-first batches, ensure we only keep chapters starting from the intended start_chapter
        if not is_first_batch:
            lines = cleaned_response.split('\n')
            keep_idx = None
            target_prefix = f"Chapter {start_chapter}"
            for i, line in enumerate(lines):
                if line.strip().startswith(target_prefix):
                    keep_idx = i
                    break
            if keep_idx is not None:
                cleaned_response = '\n'.join(lines[keep_idx:])
        
        # Log the cleaned response
        print(f"\n{'='*80}\nCleaned response for chapters {start_chapter}-{end_chapter}:\n{'-'*80}\n{cleaned_response}\n{'='*80}\n")
        
        return cleaned_response

    def process(self, inputs):
        try:
            incoming_input = inputs.get('input', '').strip()
            base_prompt = self.properties.get('Prompt', {}).get('default', '').strip()
            
            # Use Tkinter dialog instead of PyQt5
            dialog = ChapterConfigDialog()
            config = dialog.show()
            
            # If dialog was cancelled or closed
            if not config:
                return None
                
            num_chapters = config['num_chapters']
            paragraphs_per_chapter = config['paragraphs_per_chapter']

            # Always process in batches of 5 for consistency
            BATCH_SIZE = 5
            accumulated_result = ""
            
            print(f"\n[OutlineWriterV3Node] Starting generation of {num_chapters} chapters in batches of {BATCH_SIZE}")
            
            for start_chapter in range(1, num_chapters + 1, BATCH_SIZE):
                end_chapter = min(start_chapter + BATCH_SIZE - 1, num_chapters)
                is_first_batch = (start_chapter == 1)
                
                print(f"\n[OutlineWriterV3Node] Processing batch: chapters {start_chapter}-{end_chapter}")

                # Process this batch
                batch_result = self.process_chapters_batch(
                    base_prompt,
                    incoming_input,
                    start_chapter,
                    end_chapter,
                    num_chapters,
                    paragraphs_per_chapter,
                    accumulated_result
                )

                # For first batch, use the result directly (includes title)
                if is_first_batch:
                    accumulated_result = batch_result
                    print(f"[OutlineWriterV3Node] First batch stored. Length: {len(accumulated_result)}")
                else:
                    # For subsequent batches, extract only NEW chapters
                    # First, remove any echoed context from the response
                    prev_chapters = self.clean_for_prompt(accumulated_result)
                    if prev_chapters and prev_chapters in batch_result:
                        batch_result = batch_result.replace(prev_chapters, "", 1).strip()
                        print(f"[OutlineWriterV3Node] Removed echoed context from batch")
                    
                    # Extract only chapter content (no title)
                    new_chapters = self.extract_chapters(batch_result)
                    
                    # Verify we're not duplicating chapters
                    if new_chapters and new_chapters not in accumulated_result:
                        accumulated_result += "\n\n" + new_chapters
                        print(f"[OutlineWriterV3Node] Appended new chapters. Total length: {len(accumulated_result)}")
                    else:
                        print(f"[OutlineWriterV3Node] WARNING: Skipped duplicate content")
            
            # Show initial review window for final editing
            self.review_completed = False
            final_result = accumulated_result
            
            # First review window - Edit & Accept or Accept
            initial_window = ReviewWindow(content=final_result, node_instance=self)
            action, edited_result = None, None
            
            # Show the window and wait for result
            initial_window.show()
            
            try:
                action, edited_result = initial_window.result_queue.get_nowait()
            except queue.Empty:
                return None
                
            if action == "cancel" or edited_result is None:
                return None
            
            # Now show the Chapter Navigation window for detailed editing
            nav_window = ChapterNavigationWindow(content=edited_result.strip(), node_instance=self)
            nav_window.show()
            
            try:
                nav_action, nav_result = nav_window.result_queue.get_nowait()
            except queue.Empty:
                return None
            
            if nav_action == "cancel" or nav_result is None:
                return None
                
            return {'output': nav_result.strip()}
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error in OutlineWriterV3Node: {str(e)}"

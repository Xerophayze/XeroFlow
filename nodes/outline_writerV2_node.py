from .base_node import BaseNode
from node_registry import register_node
import sys
import threading
import queue
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

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

class WorkflowTerminationException(Exception):
    """Exception raised when workflow should be terminated"""
    pass

@register_node('OutlineWriterV2Node')
class OutlineWriterV2Node(BaseNode):
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
                'default': 'OutlineWriterV2Node'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input prompt with review capability.'
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
        print(f"[OutlineWriterV2Node] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[OutlineWriterV2Node] Available API endpoints: {api_list}")
        return api_list

    def process_with_api(self, prompt):
        """Process a prompt with the selected API endpoint."""
        try:
            # Get API endpoint from properties
            api_endpoint = self.properties.get('api_endpoint', {}).get('default', '')
            if not api_endpoint:
                print("[OutlineWriterV2Node] Error: No API endpoint selected")
                return "Error: No API endpoint selected"
                
            # Use the API service from BaseNode
            api_response = self.send_api_request(
                content=prompt,
                api_name=api_endpoint,
                model=self.config['interfaces'][api_endpoint].get('selected_model')
            )
            
            if not api_response.success:
                print(f"[OutlineWriterV2Node] API call failed: {api_response.error}")
                return f"Error: {api_response.error}"
                
            # Return the content directly
            return api_response.content
                
        except Exception as e:
            print(f"[OutlineWriterV2Node] Error in process_with_api: {str(e)}")
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

            # For 10 or fewer chapters, process in one go
            if num_chapters <= 10:
                prompt = (f"{base_prompt} {incoming_input} ~ {num_chapters} chapters long, "
                         f"{paragraphs_per_chapter} paragraphs per chapter, please generate "
                         f"the book title and all {num_chapters} chapters.")
                
                result = self.process_with_api(prompt)
                result = self.clean_response(result, True)  # Clean as first batch
            else:
                # For more than 10 chapters, process in batches
                BATCH_SIZE = 5
                accumulated_result = ""
                
                for start_chapter in range(1, num_chapters + 1, BATCH_SIZE):
                    end_chapter = min(start_chapter + BATCH_SIZE - 1, num_chapters)
                    is_first_batch = (start_chapter == 1)

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

                    # For first batch, clean but keep title
                    # For other batches, remove title section before appending
                    cleaned_batch = batch_result
                    
                    if is_first_batch:
                        accumulated_result = cleaned_batch
                    else:
                        # Strip any echoed prior chapters that may still remain after cleaning
                        prev_for_prompt = self.clean_for_prompt(accumulated_result)
                        if prev_for_prompt and prev_for_prompt in cleaned_batch:
                            cleaned_batch = cleaned_batch.replace(prev_for_prompt, "", 1)

                        # Extract only the new chapters from this batch
                        new_chapters = self.extract_chapters(cleaned_batch)
                        accumulated_result += "\n\n" + new_chapters
            
            # Show review window for final editing
            self.review_completed = False
            final_result = accumulated_result if 'accumulated_result' in locals() else result
            
            # Use Tkinter review window
            final_window = ReviewWindow(content=final_result, node_instance=self)
            action, edited_result = None, None
            
            # Show the window and wait for result
            final_window.show()
            
            try:
                action, edited_result = final_window.result_queue.get_nowait()
            except queue.Empty:
                return None
                
            if action == "cancel" or edited_result is None:
                return None
                
            return {'output': edited_result.strip()}
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error in OutlineWriterV2Node: {str(e)}"

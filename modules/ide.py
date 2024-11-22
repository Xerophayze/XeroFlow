import sys
import subprocess
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
import os
import datetime
import ast
import re

# List of required modules
required_modules = ['pygments', 'jedi']

# Function to check and install missing modules
def check_and_install_modules(modules):
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            print(f"The module '{module}' is not installed.")
            response = input(f"Would you like to install '{module}' now? (yes/no): ").strip().lower()
            if response == 'yes':
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', module])
            else:
                print(f"Cannot proceed without '{module}'. Exiting.")
                sys.exit(1)

# Check and install required modules
check_and_install_modules(required_modules)

# Now import the modules after ensuring they are installed
from pygments import lex
from pygments.lexers import get_lexer_by_name, guess_lexer_for_filename, TextLexer
from pygments.styles import get_style_by_name
from pygments.token import Token
import jedi

class LineNumbers(tk.Canvas):
    def __init__(self, master, text_widget, font, **kwargs):
        super().__init__(master, width=50, background='lightgrey', **kwargs)
        self.text_widget = text_widget
        self.font = font
        self.text_widget.bind("<KeyRelease>", self.redraw)
        self.text_widget.bind("<MouseWheel>", self.schedule_redraw)
        self.text_widget.bind("<Button-4>", self.schedule_redraw)  # For Linux (scroll up)
        self.text_widget.bind("<Button-5>", self.schedule_redraw)  # For Linux (scroll down)
        self.text_widget.bind("<<Change>>", self.redraw)
        self.text_widget.bind("<Configure>", self.redraw)
        self.text_widget.bind("<ButtonRelease-1>", self.redraw)
        self.function_lines = set()
        self.folded_blocks = []  # List of tuples (start_line, end_line)

        # Selection attributes
        self.selection_start = None
        self.selection_end = None

        # Configure 'selected_lines' tag in the Text widget
        self.text_widget.tag_configure('selected_lines', background='lightblue')

        # Bind mouse events for selection
        self.bind("<Button-1>", self.on_mouse_down)
        self.bind("<B1-Motion>", self.on_mouse_drag)
        self.bind("<ButtonRelease-1>", self.on_mouse_up)

        self.redraw()

        # Debounce variables
        self.redraw_after_id = None

    def schedule_redraw(self, event=None):
        if self.redraw_after_id:
            self.after_cancel(self.redraw_after_id)
        self.redraw_after_id = self.after(50, self.redraw)

    def redraw(self, event=None):
        self.redraw_after_id = None
        self.delete("all")
        i = self.text_widget.index("@0,0")
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            linenum = str(i).split(".")[0]
            line_int = int(linenum)

            # Skip line numbers for folded lines
            if any(start < line_int < end for start, end in self.folded_blocks):
                i = self.text_widget.index(f"{i}+1line")
                continue

            # Check if this line is within the 'selected_lines' tag
            if self.is_line_selected(line_int):
                # Highlight the line number area for selected lines
                self.create_rectangle(0, y, 50, y + dline[3], fill='lightblue', outline='')

            if line_int in self.function_lines:
                self.create_text(2, y, anchor="nw", text=linenum, font=self.font, fill='blue')
            else:
                self.create_text(2, y, anchor="nw", text=linenum, font=self.font, fill='black')
            i = self.text_widget.index(f"{i}+1line")

    def highlight_function_lines(self, lines):
        self.function_lines = set(lines)
        self.redraw()

    def is_line_selected(self, line):
        # Check if the given line is tagged with 'selected_lines'
        return 'selected_lines' in self.text_widget.tag_names(f"{line}.0")

    def on_mouse_down(self, event):
        y = event.y
        index = self.text_widget.index(f"@0,{y}")
        line = int(index.split('.')[0])
        self.selection_start = line
        self.selection_end = line
        # Remove any existing 'selected_lines' tags
        self.text_widget.tag_remove('selected_lines', '1.0', 'end')
        # Highlight the starting line
        self.text_widget.tag_add('selected_lines', f"{line}.0", f"{line}.end")
        self.redraw()

    def on_mouse_drag(self, event):
        y = event.y
        index = self.text_widget.index(f"@0,{y}")
        line = int(index.split('.')[0])
        self.selection_end = line
        # Determine range
        start = min(self.selection_start, self.selection_end)
        end = max(self.selection_start, self.selection_end)
        # Remove existing 'selected_lines' tags
        self.text_widget.tag_remove('selected_lines', '1.0', 'end')
        # Add 'selected_lines' tags
        self.text_widget.tag_add('selected_lines', f"{start}.0", f"{end}.end")
        self.redraw()

    def on_mouse_up(self, event):
        # Finalize selection
        self.selection_start = None
        self.selection_end = None

    def update_folded_blocks(self, folded_blocks):
        """Update the list of folded blocks."""
        self.folded_blocks = folded_blocks
        self.redraw()

class FoldingColumn(tk.Canvas):
    def __init__(self, master, text_widget, font, line_numbers, language, **kwargs):
        super().__init__(master, width=20, background='lightgrey', **kwargs)
        self.text_widget = text_widget
        self.font = font
        self.line_numbers = line_numbers  # Reference to LineNumbers instance
        self.folded_functions = {}  # Mapping from start_line to (end_line, is_folded)
        self.language = language
        self.text_widget.bind("<KeyRelease>", self.schedule_update_folding)
        self.text_widget.bind("<MouseWheel>", self.schedule_update_folding)
        self.text_widget.bind("<Button-4>", self.schedule_update_folding)  # For Linux (scroll up)
        self.text_widget.bind("<Button-5>", self.schedule_update_folding)  # For Linux (scroll down)
        self.text_widget.bind("<<Change>>", self.schedule_update_folding)
        self.text_widget.bind("<Configure>", self.schedule_update_folding)
        self.bind("<ButtonRelease-1>", self.handle_click)  # Bind to FoldingColumn itself
        self.update_folding()

        # Debounce variables
        self.update_after_id = None

    def schedule_update_folding(self, event=None):
        if self.update_after_id:
            self.after_cancel(self.update_after_id)
        self.update_after_id = self.after(50, self.update_folding)

    def update_folding(self, event=None):
        self.update_after_id = None
        # Store currently folded start lines
        current_folded = {start for start, (end, is_folded) in self.folded_functions.items() if is_folded}
        self.delete("all")
        self.folded_functions = {}
        code = self.text_widget.get('1.0', 'end-1c')
        try:
            folded_blocks = []
            if self.language == 'python':
                tree = ast.parse(code)
                functions = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        if hasattr(node, 'end_lineno'):
                            functions.append((node.lineno, node.end_lineno))
                        else:
                            functions.append((node.lineno, node.lineno))
                for start, end in functions:
                    is_folded = start in current_folded
                    self.folded_functions[start] = (end, is_folded)
                    self.draw_arrow(start, is_folded)
                    if is_folded:
                        # Fold the function by applying elide
                        self.text_widget.tag_add(f"fold_{start}", f"{start +1}.0", f"{end}.0")
                        self.text_widget.tag_configure(f"fold_{start}", elide=True)
                        folded_blocks.append((start + 1, end))
            elif self.language == 'html':
                # Tag-based folding for HTML
                tag_pattern = re.compile(r'<(\w+)[^>]*?>|</(\w+)>')
                stack = []
                functions = []
                lines = code.split('\n')
                for idx, line in enumerate(lines, start=1):
                    matches = tag_pattern.findall(line)
                    for open_tag, close_tag in matches:
                        if open_tag:
                            stack.append((open_tag, idx))
                        elif close_tag and stack:
                            last_tag, start_idx = stack.pop()
                            if last_tag == close_tag:
                                functions.append((start_idx, idx))
                for start, end in functions:
                    if start == end:
                        continue  # Ignore tags that open and close on the same line
                    is_folded = start in current_folded
                    self.folded_functions[start] = (end, is_folded)
                    self.draw_arrow(start, is_folded)
                    if is_folded:
                        # Fold the block by applying elide
                        self.text_widget.tag_add(f"fold_{start}", f"{start +1}.0", f"{end}.0")
                        self.text_widget.tag_configure(f"fold_{start}", elide=True)
                        folded_blocks.append((start + 1, end))
            else:
                # Brace-based folding for languages like JavaScript, CSS, Batch, PowerShell, Bash
                brace_stack = []
                functions = []
                lines = code.split('\n')
                for idx, line in enumerate(lines, start=1):
                    open_braces = line.count('{')
                    close_braces = line.count('}')
                    for _ in range(open_braces):
                        brace_stack.append(idx)
                    for _ in range(close_braces):
                        if brace_stack:
                            start_idx = brace_stack.pop()
                            end_idx = idx
                            if end_idx > start_idx:
                                functions.append((start_idx, end_idx))
                for start, end in functions:
                    is_folded = start in current_folded
                    self.folded_functions[start] = (end, is_folded)
                    self.draw_arrow(start, is_folded)
                    if is_folded:
                        # Fold the block by applying elide
                        self.text_widget.tag_add(f"fold_{start}", f"{start +1}.0", f"{end}.0")
                        self.text_widget.tag_configure(f"fold_{start}", elide=True)
                        folded_blocks.append((start + 1, end))
            # Update folded blocks in LineNumbers
            self.line_numbers.update_folded_blocks(folded_blocks)
        except:
            pass  # Ignore syntax errors during parsing

    def draw_arrow(self, line, is_folded):
        try:
            dline = self.text_widget.dlineinfo(f"{line}.0")
            if dline is None:
                y = 0
            else:
                y = dline[1]
        except:
            y = 0
        if is_folded:
            symbol = '+'
        else:
            symbol = '-'
        self.create_text(10, y, text=symbol, font=self.font, fill='black', tags=f"arrow_{line}")

    def toggle_fold(self, line):
        if line not in self.folded_functions:
            return
        end_line, is_folded = self.folded_functions[line]
        if not is_folded:
            # Fold the function/block
            self.text_widget.tag_add(f"fold_{line}", f"{line +1}.0", f"{end_line}.0")
            self.text_widget.tag_configure(f"fold_{line}", elide=True)
            self.folded_functions[line] = (end_line, True)
        else:
            # Unfold the function/block
            self.text_widget.tag_remove(f"fold_{line}", f"{line +1}.0", f"{end_line}.0")
            self.folded_functions[line] = (end_line, False)
        # After toggling, update all fold arrows to refresh their positions
        self.update_folding()

    def handle_click(self, event):
        # Determine which line was clicked based on y-coordinate
        y = event.y
        # Iterate through all functions to find if the click is within any function's line area
        for start_line, (end_line, is_folded) in self.folded_functions.items():
            try:
                dline = self.text_widget.dlineinfo(f"{start_line}.0")
                if dline is None:
                    continue
                y_start = dline[1]
                height = dline[3]
                if y_start <= y < y_start + height:
                    self.toggle_fold(start_line)
                    break
            except:
                continue  # Skip lines that can't be fetched

class EditorTab:
    # Define bracket pairs for each language
    BRACKET_PAIRS = {
        'python': [('(', ')'), ('[', ']'), ('{', '}')],
        'javascript': [('(', ')'), ('[', ']'), ('{', '}')],
        'html': [('<', '>')],
        'css': [('(', ')'), ('[', ']'), ('{', '}')],
        'batch': [],
        'powershell': [('(', ')'), ('[', ']'), ('{', '}')],
        'bash': []
    }

    def __init__(self, parent, notebook, filename=None, language='python'):
        self.parent = parent
        self.notebook = notebook
        self.filename = filename
        self.font_styles = {}  # Cache for font styles
        self.pending_changes = []  # Store pending changes
        self.filepath = None  # Current file path
        self.modified = False  # Track unsaved changes
        self.base_font = tkfont.Font(family="Courier", size=10)
        self.language = language
        self.lexer = get_lexer_by_name(self.language, stripall=True) if language != 'text' else TextLexer()
        self.setup_widgets()
        self.bind_events()
        self.setup_versioning()

    def setup_widgets(self):
        self.frame = tk.Frame(self.parent)

        # Toolbar for language selection
        self.toolbar = tk.Frame(self.frame)
        self.toolbar.pack(side='top', fill='x')

        tk.Label(self.toolbar, text="Language:").pack(side='left', padx=5)
        self.language_var = tk.StringVar(value=self.language)
        self.language_dropdown = ttk.Combobox(
            self.toolbar, textvariable=self.language_var,
            values=['python', 'javascript', 'html', 'css', 'batch', 'powershell', 'bash', 'text'],
            state='readonly'
        )
        self.language_dropdown.pack(side='left')
        self.language_dropdown.bind('<<ComboboxSelected>>', self.change_language)

        # Text container
        self.text_container = tk.Frame(self.frame)
        self.text_container.pack(side='top', fill='both', expand=True)

        # Create the scrollbar
        self.scrollbar = ttk.Scrollbar(self.text_container, orient='vertical')
        self.scrollbar.pack(side='right', fill='y')

        # Create the text area
        self.text_area = tk.Text(self.text_container, wrap='none', undo=True, font=self.base_font)
        self.text_area.pack(side='right', fill='both', expand=True)

        # Configure the scrollbar to control the text area
        self.text_area.configure(yscrollcommand=self.on_textscroll)
        self.scrollbar.configure(command=self.on_scrollbar_scroll)

        # Create the LineNumbers widget first to pass its reference to FoldingColumn
        self.line_numbers = LineNumbers(self.text_container, self.text_area, font=self.base_font)
        self.line_numbers.pack(side='left', fill='y')

        # Create the FoldingColumn Canvas
        self.folding_column = FoldingColumn(
            self.text_container, self.text_area, font=self.base_font,
            line_numbers=self.line_numbers, language=self.language
        )
        self.folding_column.pack(side='left', fill='y')

        # Versioning controls and status bar
        self.bottom_frame = tk.Frame(self.frame)
        self.bottom_frame.pack(side='bottom', fill='x')

        # Version dropdown
        self.version_var = tk.StringVar()
        self.version_dropdown = ttk.Combobox(self.bottom_frame, textvariable=self.version_var)
        self.version_dropdown.bind('<<ComboboxSelected>>', self.load_version)
        self.version_dropdown.pack(side='left', padx=5)

        # Save Version button
        self.save_version_button = tk.Button(self.bottom_frame, text='Save Version', command=self.save_version)
        self.save_version_button.pack(side='left', padx=5)

        # Apply Changes button (initially disabled)
        self.apply_changes_button = tk.Button(
            self.bottom_frame, text='Apply Changes',
            command=self.apply_pending_changes, state='disabled'
        )
        self.apply_changes_button.pack(side='left', padx=5)

        # Status bar
        self.status_bar = tk.Label(self.bottom_frame, text='Ready', bd=1, relief='sunken', anchor='w')
        self.status_bar.pack(side='left', fill='x', expand=True)

        # Initialize code style
        self.style = get_style_by_name('default')

        # Setup context menu
        self.setup_context_menu()

    def change_language(self, event=None):
        selected_language = self.language_var.get()
        if selected_language == 'text':
            self.lexer = TextLexer()
        else:
            try:
                self.lexer = get_lexer_by_name(selected_language, stripall=True)
            except:
                self.lexer = TextLexer()
                selected_language = 'text'
                self.language_var.set(selected_language)
        self.language = selected_language
        self.folding_column.language = self.language
        self.folding_column.update_folding()
        self.highlight_syntax()
        self.status_bar.config(text=f'Language changed to {self.language}')
        # Update bracket pairs if needed
        self.update_bracket_pairs()

    def update_bracket_pairs(self):
        # This method can be expanded if more languages require specific bracket pairs
        pass

    def bind_events(self):
        self.text_area.bind('<<Modified>>', self.on_text_change)
        self.text_area.bind('<Control-space>', self.code_complete)
        self.text_area.bind('<MouseWheel>', self.on_mouse_wheel)  # For Windows
        self.text_area.bind('<Button-4>', self.on_mouse_wheel)    # For Linux (scroll up)
        self.text_area.bind('<Button-5>', self.on_mouse_wheel)    # For Linux (scroll down)
        self.text_area.bind("<KeyRelease>", self.match_brackets)
        self.text_area.bind("<ButtonRelease-1>", self.on_mouse_click)  # Unified handler

        # Bind mouse wheel events to the line_numbers widget as well
        self.line_numbers.bind('<MouseWheel>', self.on_mouse_wheel)  # For Windows
        self.line_numbers.bind('<Button-4>', self.on_mouse_wheel)    # For Linux (scroll up)
        self.line_numbers.bind('<Button-5>', self.on_mouse_wheel)    # For Linux (scroll down)

    def on_mouse_click(self, event=None):
        self.match_brackets()
        self.highlight_function()

    def on_text_change(self, event=None):
        if self.text_area.edit_modified():
            self.modified = True  # Mark as modified
            self.highlight_syntax()
            self.check_syntax()
            self.update_fold_arrows()
            self.line_numbers.redraw()
            self.text_area.edit_modified(False)  # Reset the modified flag

    def highlight_syntax(self, event=None):
        code = self.text_area.get('1.0', 'end-1c')
        self.text_area.mark_set("range_start", "1.0")

        # Remove existing tags except 'sel', 'bracket', and pending change tags
        for tag in self.text_area.tag_names():
            if tag not in ('sel', 'pending_new', 'pending_update', 'pending_delete', 'error', 'bracket', 'selected_lines'):
                self.text_area.tag_remove(tag, "1.0", "end")

        # Apply new syntax highlighting
        for token, content in lex(code, self.lexer):
            self.text_area.mark_set("range_end", "range_start + %dc" % len(content))
            token_name = str(token)
            self.text_area.tag_add(token_name, "range_start", "range_end")
            self.text_area.mark_set("range_start", "range_end")

        # Configure tag styles
        for ttype, style in self.style:
            tag_name = str(ttype)
            options = {}
            if style['color']:
                options['foreground'] = '#' + style['color']
            if style['bgcolor']:
                options['background'] = '#' + style['bgcolor']
            if style['bold'] or style['italic']:
                # Create a font based on the base font with bold and/or italic styles
                font_props = {'family': self.base_font.actual('family'), 'size': self.base_font.actual('size')}
                if style['bold']:
                    font_props['weight'] = 'bold'
                else:
                    font_props['weight'] = 'normal'
                if style['italic']:
                    font_props['slant'] = 'italic'
                else:
                    font_props['slant'] = 'roman'
                if tag_name not in self.font_styles:
                    self.font_styles[tag_name] = tkfont.Font(**font_props)
                options['font'] = self.font_styles[tag_name]
            if options:
                self.text_area.tag_config(tag_name, **options)

        # Configure bracket tag
        self.text_area.tag_config('bracket', foreground='red', background='yellow')

        # Apply pending change highlights
        self.highlight_pending_changes()

    def code_complete(self, event=None):
        index = self.text_area.index(tk.INSERT)
        code = self.text_area.get('1.0', 'end-1c')
        script = jedi.Script(code, path=self.filepath if self.filepath else '')
        try:
            line, column = map(int, index.split('.'))
            completions = script.complete(line, column)
            if completions:
                menu = tk.Menu(self.parent, tearoff=0)
                for completion in completions:
                    menu.add_command(label=completion.name, command=lambda c=completion: self.insert_completion(c))
                # Position the menu at the cursor's x,y position
                bbox = self.text_area.bbox(tk.INSERT)
                if bbox:
                    x, y, width, height = bbox
                    menu.post(self.text_area.winfo_rootx() + x, self.text_area.winfo_rooty() + y + height)
        except Exception as e:
            self.status_bar.config(text=f'Code Completion Error: {e}')

    def insert_completion(self, completion):
        self.text_area.insert(tk.INSERT, completion.complete)
        self.text_area.focus()

    def check_syntax(self):
        code = self.text_area.get('1.0', 'end-1c')
        self.text_area.tag_remove('error', '1.0', 'end')
        try:
            if self.language == 'python':
                ast.parse(code)
                self.status_bar.config(text='No syntax errors')
            else:
                # Basic syntax check for other languages can be implemented here
                self.status_bar.config(text='Syntax check not implemented for this language')
        except SyntaxError as e:
            if self.language == 'python':
                line = e.lineno
                if line is None:
                    return
                start = f"{line}.0"
                end = f"{line}.end"
                self.text_area.tag_add('error', start, end)
                self.text_area.tag_config('error', background='red')
                self.status_bar.config(text=f'Syntax Error: Line {line} - {e.msg}')

    def external_input(self, line_number, code_line):
        self.text_area.delete(f"{line_number}.0", f"{line_number}.end")
        self.text_area.insert(f"{line_number}.0", code_line)
        self.on_text_change()

    def output_code_with_line_numbers_and_errors(self):
        code_lines = self.text_area.get('1.0', 'end-1c').split('\n')
        output = ''
        for i, line in enumerate(code_lines, start=1):
            output += f"{i:4}: {line}\n"
        return output

    def on_textscroll(self, *args):
        """Scrolls the text widget and updates the line numbers."""
        self.scrollbar.set(*args)
        self.text_area.yview_moveto(args[0])
        self.line_numbers.redraw()

    def on_scrollbar_scroll(self, *args):
        """Scrolls the text widget and updates the line numbers."""
        self.text_area.yview(*args)
        self.line_numbers.redraw()

    def on_mouse_wheel(self, event):
        """Handles mouse wheel scrolling."""
        if event.num == 4 or event.delta > 0:
            delta = -1
        elif event.num == 5 or event.delta < 0:
            delta = 1
        self.text_area.yview_scroll(delta, "units")
        self.line_numbers.schedule_redraw()
        self.folding_column.schedule_update_folding()
        return "break"

    def process_line_inputs(self, line_inputs):
        """
        Processes a list of line inputs to update the editor's content.

        Parameters:
        - line_inputs: List of dictionaries with keys:
            - 'line_number': int
            - 'code_line': str (optional)
            - 'action': 'new', 'update', or 'delete'
        """
        # Store pending changes
        self.pending_changes = line_inputs
        # Highlight pending changes
        self.highlight_pending_changes()
        # Update the Apply Changes button state
        if self.pending_changes:
            self.apply_changes_button.config(state='normal')
        else:
            self.apply_changes_button.config(state='disabled')

    def highlight_pending_changes(self):
        """Highlights the lines with pending changes."""
        # Remove existing pending change tags
        self.text_area.tag_remove('pending_new', '1.0', 'end')
        self.text_area.tag_remove('pending_update', '1.0', 'end')
        self.text_area.tag_remove('pending_delete', '1.0', 'end')

        # Configure tags
        self.text_area.tag_config('pending_new', background='lightgreen')
        self.text_area.tag_config('pending_update', background='lightyellow')
        self.text_area.tag_config('pending_delete', background='lightcoral')

        for item in self.pending_changes:
            line_number = item.get('line_number')
            action = item.get('action')

            if not isinstance(line_number, int) or line_number < 1:
                continue

            start = f"{line_number}.0"
            end = f"{line_number}.end"

            if action == 'new':
                self.text_area.tag_add('pending_new', start, end)
            elif action == 'update':
                self.text_area.tag_add('pending_update', start, end)
            elif action == 'delete':
                self.text_area.tag_add('pending_delete', start, end)

    def apply_pending_changes(self):
        """Applies the pending changes to the editor content."""
        if not self.pending_changes:
            return  # No changes to apply

        # Begin undo block
        self.text_area.edit_separator()

        # Sort inputs by line_number to maintain order
        self.pending_changes.sort(key=lambda x: x['line_number'], reverse=True)

        for item in self.pending_changes:
            line_number = item.get('line_number')
            code_line = item.get('code_line', '')
            action = item.get('action')

            if not isinstance(line_number, int) or line_number < 1:
                print(f"Invalid line number '{line_number}'. Skipping.")
                continue

            if action == 'new':
                # Insert a new line before the specified line number
                self.text_area.insert(f"{line_number}.0", code_line + '\n')
            elif action == 'update':
                # Ensure the line exists
                last_line = int(self.text_area.index('end-1c').split('.')[0])
                if line_number > last_line:
                    print(f"Line {line_number} does not exist. Cannot update.")
                    continue
                self.text_area.delete(f"{line_number}.0", f"{line_number}.end")
                self.text_area.insert(f"{line_number}.0", code_line)
            elif action == 'delete':
                # Ensure the line exists
                last_line = int(self.text_area.index('end-1c').split('.')[0])
                if line_number > last_line:
                    print(f"Line {line_number} does not exist. Cannot delete.")
                    continue
                self.text_area.delete(f"{line_number}.0", f"{line_number + 1}.0")
            else:
                print(f"Unknown action '{action}' for line {line_number}")

        # Clear pending changes
        self.pending_changes = []
        # Remove pending change highlights
        self.text_area.tag_remove('pending_new', '1.0', 'end')
        self.text_area.tag_remove('pending_update', '1.0', 'end')
        self.text_area.tag_remove('pending_delete', '1.0', 'end')

        # End undo block
        self.text_area.edit_separator()

        # After processing all inputs, update the editor display
        self.on_text_change()

        # Disable the Apply Changes button since there are no more pending changes
        self.apply_changes_button.config(state='disabled')

        # Mark as modified since content has changed
        self.modified = True

    # File menu functionalities
    def new_file(self):
        self.text_area.delete('1.0', tk.END)
        self.filepath = None
        self.language = 'python'
        self.lexer = get_lexer_by_name(self.language, stripall=True)
        self.language_var.set(self.language)
        self.folding_column.language = self.language
        self.folding_column.update_folding()
        self.parent.master.title("Multi-Language IDE - New File")
        self.status_bar.config(text='New file created')
        self.setup_versioning()
        self.modified = False
        self.line_numbers.redraw()
        self.folding_column.update_folding()
        self.apply_changes_button.config(state='disabled')
        self.highlight_function()

    def load_file(self):
        filetypes = [
            ("Python Files", "*.py"),
            ("JavaScript Files", "*.js"),
            ("HTML Files", "*.html;*.htm"),
            ("CSS Files", "*.css"),
            ("Batch Files", "*.bat"),
            ("PowerShell Scripts", "*.ps1"),
            ("Bash Scripts", "*.sh"),
            ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            with open(path, 'r') as file:
                code = file.read()
            self.text_area.delete('1.0', tk.END)
            self.text_area.insert('1.0', code)
            self.filepath = path
            truncated_name = os.path.basename(path)[:20]
            self.notebook.tab(self.frame, text=truncated_name)
            self.parent.master.title(f"Multi-Language IDE - {os.path.basename(path)}")
            self.status_bar.config(text=f'Loaded file: {os.path.basename(path)}')
            self.setup_versioning()
            self.modified = False
            # Detect language based on file extension
            ext = os.path.splitext(path)[1].lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript',
                '.html': 'html',
                '.htm': 'html',
                '.css': 'css',
                '.bat': 'batch',
                '.ps1': 'powershell',
                '.sh': 'bash'
            }
            self.language = language_map.get(ext, 'text')  # Default to 'text' if unknown
            self.language_var.set(self.language)
            try:
                self.lexer = get_lexer_by_name(self.language, stripall=True)
            except:
                self.lexer = TextLexer()
                self.language = 'text'
                self.language_var.set(self.language)
            self.folding_column.language = self.language
            self.highlight_syntax()
            self.check_syntax()
            self.line_numbers.redraw()
            self.folding_column.update_folding()
            self.text_area.edit_modified(False)
            self.apply_changes_button.config(state='disabled')
            self.highlight_function()

            # **Ensure the new tab is focused automatically**
            self.notebook.select(self.frame)

    def save_file(self):
        if self.filepath:
            with open(self.filepath, 'w') as file:
                code = self.text_area.get('1.0', tk.END)
                file.write(code)
            self.status_bar.config(text=f'Saved file: {os.path.basename(self.filepath)}')
            self.setup_versioning()
            self.modified = False
            self.text_area.edit_modified(False)
        else:
            self.save_file_as()

    def save_file_as(self):
        filetypes = [
            ("Python Files", "*.py"),
            ("JavaScript Files", "*.js"),
            ("HTML Files", "*.html;*.htm"),
            ("CSS Files", "*.css"),
            ("Batch Files", "*.bat"),
            ("PowerShell Scripts", "*.ps1"),
            ("Bash Scripts", "*.sh"),
            ("All Files", "*.*")
        ]
        path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=filetypes)
        if path:
            with open(path, 'w') as file:
                code = self.text_area.get('1.0', tk.END)
                file.write(code)
            self.filepath = path
            truncated_name = os.path.basename(path)[:20]
            self.notebook.tab(self.frame, text=truncated_name)
            self.parent.master.title(f"Multi-Language IDE - {os.path.basename(path)}")
            self.status_bar.config(text=f'Saved file: {os.path.basename(path)}')
            self.setup_versioning()
            self.modified = False
            # Detect language based on file extension
            ext = os.path.splitext(path)[1].lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript',
                '.html': 'html',
                '.htm': 'html',
                '.css': 'css',
                '.bat': 'batch',
                '.ps1': 'powershell',
                '.sh': 'bash'
            }
            self.language = language_map.get(ext, 'text')  # Default to 'text' if unknown
            self.language_var.set(self.language)
            try:
                self.lexer = get_lexer_by_name(self.language, stripall=True)
            except:
                self.lexer = TextLexer()
                self.language = 'text'
                self.language_var.set(self.language)
            self.folding_column.language = self.language
            self.highlight_syntax()
            self.check_syntax()
            self.line_numbers.redraw()
            self.folding_column.update_folding()
            self.text_area.edit_modified(False)
            self.highlight_function()

    def exit_application(self):
        for editor in self.open_tabs[:]:
            self.notebook.select(editor.frame)
            self.close_tab(editor)
        if not self.open_tabs:
            self.parent.master.quit()

    # Versioning functionalities
    def setup_versioning(self):
        if self.filepath:
            base_name = os.path.basename(self.filepath)
            base_name_no_ext = os.path.splitext(base_name)[0]
        else:
            base_name_no_ext = 'untitled'
        self.version_folder = os.path.join(os.getcwd(), 'versions', base_name_no_ext)
        if not os.path.exists(self.version_folder):
            os.makedirs(self.version_folder)
        self.update_version_list()

    def save_version(self):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        if self.filepath:
            base_name = os.path.basename(self.filepath)
            ext = os.path.splitext(base_name)[1].lower()
            version_ext = ext if ext else '.txt'
            version_name = f"{base_name}_{timestamp}{version_ext}"
        else:
            version_name = f"version_{timestamp}.txt"
        version_path = os.path.join(self.version_folder, version_name)
        if not os.path.exists(self.version_folder):
            os.makedirs(self.version_folder)
        with open(version_path, 'w') as file:
            code = self.text_area.get('1.0', tk.END)
            file.write(code)
        self.update_version_list()
        self.status_bar.config(text=f'Version saved: {version_name}')

    def update_version_list(self):
        versions = []
        if os.path.exists(self.version_folder):
            # Include files with relevant extensions
            versions = [f for f in os.listdir(self.version_folder)
                       if f.endswith('.py') or f.endswith('.js') or f.endswith('.html') or
                       f.endswith('.htm') or f.endswith('.css') or f.endswith('.bat') or
                       f.endswith('.ps1') or f.endswith('.sh') or f.endswith('.txt')]
            versions.sort(reverse=True)  # Latest versions first
        self.version_dropdown['values'] = versions

    def load_version(self, event=None):
        version_name = self.version_var.get()
        if version_name:
            version_path = os.path.join(self.version_folder, version_name)
            with open(version_path, 'r') as file:
                code = file.read()
            self.text_area.delete('1.0', tk.END)
            self.text_area.insert('1.0', code)
            self.on_text_change()
            self.status_bar.config(text=f'Loaded version: {version_name}')
            self.modified = True
            self.apply_changes_button.config(state='disabled')
            # Detect language based on version file extension
            ext = os.path.splitext(version_name)[1].lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript',
                '.html': 'html',
                '.htm': 'html',
                '.css': 'css',
                '.bat': 'batch',
                '.ps1': 'powershell',
                '.sh': 'bash',
                '.txt': 'text'
            }
            self.language = language_map.get(ext, 'text')  # Default to 'text' if unknown
            self.language_var.set(self.language)
            try:
                self.lexer = get_lexer_by_name(self.language, stripall=True)
            except:
                self.lexer = TextLexer()
                self.language = 'text'
                self.language_var.set(self.language)
            self.folding_column.language = self.language
            self.highlight_syntax()
            self.check_syntax()
            self.folding_column.update_folding()
            self.highlight_function()

    # Bracket Matching
    def match_brackets(self, event=None):
        # Remove previous bracket highlights
        self.text_area.tag_remove('bracket', '1.0', 'end')

        # Define bracket pairs based on language
        brackets = self.BRACKET_PAIRS.get(self.language, [])

        # Convert list of tuples to dictionaries for easy lookup
        bracket_dict = {}
        for open_b, close_b in brackets:
            bracket_dict[open_b] = close_b
            bracket_dict[close_b] = open_b

        # Get current cursor position
        pos = self.text_area.index(tk.INSERT)

        # Check the character before the cursor
        try:
            char_before = self.text_area.get(f"{pos} -1c")
        except tk.TclError:
            char_before = ''

        # Check the character after the cursor
        try:
            char_after = self.text_area.get(pos)
        except tk.TclError:
            char_after = ''

        # Determine if cursor is on a bracket or next to a bracket
        if char_before in bracket_dict:
            bracket_pos = f"{pos} -1c"
            bracket = char_before
        elif char_after in bracket_dict:
            bracket_pos = pos
            bracket = char_after
        else:
            return  # No bracket near cursor

        # Find the matching bracket
        match_pos = self.find_matching_bracket(bracket_pos, bracket, bracket_dict)

        if match_pos:
            # Highlight both brackets
            self.text_area.tag_add('bracket', bracket_pos, f"{bracket_pos}+1c")
            self.text_area.tag_add('bracket', match_pos, f"{match_pos}+1c")

    def find_matching_bracket(self, pos, bracket, bracket_dict):
        match_bracket = bracket_dict.get(bracket)
        if not match_bracket:
            return None

        if bracket in '([{<':
            # Opening bracket: search forward
            search_forward = True
        else:
            # Closing bracket: search backward
            search_forward = False

        stack = 1
        current_pos = self.text_area.index(pos)

        if search_forward:
            # Search forward character by character
            while True:
                try:
                    next_pos = self.text_area.index(f"{current_pos}+1c")
                except tk.TclError:
                    return None
                if next_pos == current_pos:
                    # Reached end of text
                    return None
                char = self.text_area.get(next_pos)
                if char == bracket:
                    stack += 1
                elif char == match_bracket:
                    stack -= 1
                    if stack == 0:
                        return next_pos
                current_pos = next_pos
        else:
            # Search backward character by character
            while True:
                try:
                    prev_pos = self.text_area.index(f"{current_pos}-1c")
                except tk.TclError:
                    return None
                if prev_pos == current_pos:
                    # Reached start of text
                    return None
                char = self.text_area.get(prev_pos)
                if char == bracket:
                    stack += 1
                elif char == match_bracket:
                    stack -= 1
                    if stack == 0:
                        return prev_pos
                current_pos = prev_pos

    # Function Line Number Highlighting
    def highlight_function(self, event=None):
        code = self.text_area.get('1.0', 'end-1c')
        try:
            folded_lines = []
            if self.language == 'python':
                tree = ast.parse(code)
                functions = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # For Python 3.8 and above, end_lineno is available
                        if hasattr(node, 'end_lineno'):
                            functions.append((node.lineno, node.end_lineno))
                        else:
                            # For Python versions < 3.8, estimate end_lineno
                            functions.append((node.lineno, node.lineno))
                cursor_line = int(self.text_area.index(tk.INSERT).split('.')[0])

                # Find all functions that contain the cursor line
                containing_functions = [func for func in functions if func[0] <= cursor_line <= func[1]]

                if containing_functions:
                    # Select the innermost function (the one with the smallest range)
                    innermost_function = min(containing_functions, key=lambda x: (x[1] - x[0]))
                    start, end = innermost_function
                    lines = list(range(start, end + 1))
                    self.line_numbers.highlight_function_lines(lines)
                    folded_lines = [f"{line}.0" for line in lines]
                else:
                    self.line_numbers.highlight_function_lines([])
            elif self.language == 'html':
                # Tag-based highlighting can be implemented similarly if needed
                self.line_numbers.highlight_function_lines([])
            else:
                # Implement function highlighting for other languages if needed
                self.line_numbers.highlight_function_lines([])
        except:
            self.line_numbers.highlight_function_lines([])

    # Update folding arrows based on current functions
    def update_fold_arrows(self):
        self.folding_column.update_folding()

    # Context Menu for Function Operations and Standard Operations
    def setup_context_menu(self):
        # Initialize a single context menu; it will be configured dynamically
        self.context_menu = tk.Menu(self.text_area, tearoff=0)
        self.text_area.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        # Determine the line number where the right-click occurred
        index = self.text_area.index(f"@{event.x},{event.y}")
        line = int(index.split('.')[0])

        # Initialize a new context menu
        menu = tk.Menu(self.text_area, tearoff=0)

        # Add standard context menu options
        menu.add_command(label="Cut", command=self.cut_selection)
        menu.add_command(label="Copy", command=self.copy_selection)
        menu.add_command(label="Paste", command=self.paste_selection)
        menu.add_separator()
        menu.add_command(label="Select All", command=self.select_all)

        # Check if the right-click is on a function's first line (only for Python)
        code = self.text_area.get('1.0', 'end-1c')
        try:
            if self.language == 'python':
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.lineno == line:
                        self.current_function = node
                        # Add function-specific options
                        menu.add_separator()
                        menu.add_command(label="Copy Function", command=self.copy_function)
                        menu.add_command(label="Cut Function", command=self.cut_function)
                        menu.add_command(label="Paste Over Function", command=self.paste_over_function)
                        menu.add_command(label="Select Function", command=self.select_function)
                        break  # Only one function can start at a given line
        except:
            pass  # Ignore syntax errors

        # Display the context menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # Standard Context Menu Operations
    def cut_selection(self):
        try:
            self.text_area.event_generate("<<Cut>>")
            self.status_bar.config(text='Cut selection')
        except:
            pass

    def copy_selection(self):
        try:
            self.text_area.event_generate("<<Copy>>")
            self.status_bar.config(text='Copied selection')
        except:
            pass

    def paste_selection(self):
        try:
            self.text_area.event_generate("<<Paste>>")
            self.status_bar.config(text='Pasted content')
        except:
            pass

    def select_all(self):
        self.text_area.tag_add(tk.SEL, "1.0", tk.END)
        self.text_area.mark_set(tk.INSERT, "1.0")
        self.text_area.see(tk.INSERT)
        self.status_bar.config(text='Selected all text')

    # Function-Specific Context Menu Operations (Only for Python)
    def copy_function(self):
        if hasattr(self, 'current_function'):
            start = f"{self.current_function.lineno}.0"
            end = f"{self.current_function.end_lineno}.end"
            function_text = self.text_area.get(start, end)
            self.text_area.clipboard_clear()
            self.text_area.clipboard_append(function_text)
            self.status_bar.config(text=f'Copied function: {self.current_function.name}')
            del self.current_function

    def cut_function(self):
        if hasattr(self, 'current_function'):
            start = f"{self.current_function.lineno}.0"
            end = f"{self.current_function.end_lineno}.end"
            function_text = self.text_area.get(start, end)
            self.text_area.clipboard_clear()
            self.text_area.clipboard_append(function_text)
            self.text_area.delete(start, end)
            self.status_bar.config(text=f'Cut function: {self.current_function.name}')
            del self.current_function
            self.highlight_function()
            self.folding_column.update_folding()

    def paste_over_function(self):
        if hasattr(self, 'current_function'):
            try:
                function_text = self.text_area.clipboard_get()
            except tk.TclError:
                self.status_bar.config(text='Clipboard is empty.')
                del self.current_function
                return
            start = f"{self.current_function.lineno}.0"
            end = f"{self.current_function.end_lineno}.end"
            self.text_area.delete(start, end)
            self.text_area.insert(start, function_text)
            self.status_bar.config(text=f'Pasted over function: {self.current_function.name}')
            del self.current_function
            self.on_text_change()

    def select_function(self):
        if hasattr(self, 'current_function'):
            start = f"{self.current_function.lineno}.0"
            end = f"{self.current_function.end_lineno}.end"
            self.text_area.tag_add(tk.SEL, start, end)
            self.text_area.mark_set(tk.INSERT, start)
            self.text_area.see(tk.INSERT)
            self.status_bar.config(text=f'Selected function: {self.current_function.name}')
            del self.current_function

class SimpleIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Language IDE")
        self.root.geometry("1200x800")
        self.open_tabs = []
        self.tabs = {}
        self.create_widgets()
        self.bind_events()

    def create_widgets(self):
        # Create menu bar
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)

        # File menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label='File', menu=file_menu)
        file_menu.add_command(label='New', command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label='Open', command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label='Save', command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label='Save As', command=self.save_file_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label='Exit', command=self.exit_application, accelerator="Alt+F4")

        # Bind keyboard shortcuts
        self.root.bind_all("<Control-n>", lambda event: self.new_file())
        self.root.bind_all("<Control-o>", lambda event: self.open_file())
        self.root.bind_all("<Control-s>", lambda event: self.save_file())
        self.root.bind_all("<Control-S>", lambda event: self.save_file_as())

        # Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        self.notebook.bind("<Button-3>", self.on_tab_right_click)  # Right-click on tabs

        # Create first tab
        self.new_file()

    def bind_events(self):
        pass  # Events are bound within each EditorTab

    def new_file(self):
        editor = EditorTab(self.notebook, self.notebook)
        self.open_tabs.append(editor)
        self.add_tab(editor, 'Untitled')
        self.tabs[str(editor.frame)] = editor
        self.notebook.select(editor.frame)

    def open_file(self):
        filetypes = [
            ("Python Files", "*.py"),
            ("JavaScript Files", "*.js"),
            ("HTML Files", "*.html;*.htm"),
            ("CSS Files", "*.css"),
            ("Batch Files", "*.bat"),
            ("PowerShell Scripts", "*.ps1"),
            ("Bash Scripts", "*.sh"),
            ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            editor = EditorTab(self.notebook, self.notebook)
            self.open_tabs.append(editor)
            with open(path, 'r') as file:
                code = file.read()
            editor.text_area.insert('1.0', code)
            editor.filepath = path
            truncated_name = os.path.basename(path)[:20]
            self.add_tab(editor, truncated_name)
            self.tabs[str(editor.frame)] = editor
            self.parent_master_title(editor)
            editor.status_bar.config(text=f'Loaded file: {os.path.basename(path)}')
            editor.setup_versioning()
            editor.modified = False
            # Detect language based on file extension
            ext = os.path.splitext(path)[1].lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript',
                '.html': 'html',
                '.htm': 'html',
                '.css': 'css',
                '.bat': 'batch',
                '.ps1': 'powershell',
                '.sh': 'bash'
            }
            editor.language = language_map.get(ext, 'text')  # Default to 'text' if unknown
            editor.language_var.set(editor.language)
            try:
                editor.lexer = get_lexer_by_name(editor.language, stripall=True)
            except:
                editor.lexer = TextLexer()
                editor.language = 'text'
                editor.language_var.set(editor.language)
            editor.folding_column.language = editor.language
            editor.highlight_syntax()
            editor.check_syntax()
            editor.line_numbers.redraw()
            editor.folding_column.update_folding()
            editor.text_area.edit_modified(False)
            editor.apply_changes_button.config(state='disabled')
            editor.highlight_function()

            # **Ensure the new tab is focused automatically**
            self.notebook.select(editor.frame)

    def add_tab(self, editor, title):
        tab_id = editor.frame
        self.notebook.add(tab_id, text=title)

    def close_tab(self, editor):
        if editor.modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "Do you want to save changes to this file before closing?"
            )
            if result is True:
                editor.save_file()
                self.remove_tab(editor)
            elif result is False:
                self.remove_tab(editor)
            else:
                # Cancelled, do nothing
                return
        else:
            self.remove_tab(editor)

    def remove_tab(self, editor):
        tab_id = editor.frame
        self.notebook.forget(tab_id)
        editor.frame.destroy()
        del self.tabs[str(tab_id)]
        self.open_tabs.remove(editor)

    def save_file(self):
        current_editor = self.get_current_editor()
        if current_editor:
            current_editor.save_file()

    def save_file_as(self):
        current_editor = self.get_current_editor()
        if current_editor:
            current_editor.save_file_as()

    def exit_application(self):
        for editor in self.open_tabs[:]:
            self.notebook.select(editor.frame)
            self.close_tab(editor)
        if not self.open_tabs:
            self.root.quit()

    def on_tab_change(self, event):
        current_tab = self.notebook.select()
        editor = self.tabs.get(current_tab)
        if editor and editor.filepath:
            self.root.title(f"Multi-Language IDE - {os.path.basename(editor.filepath)}")
        else:
            self.root.title("Multi-Language IDE - Untitled")

    def get_current_editor(self):
        current_tab = self.notebook.select()
        return self.tabs.get(current_tab)

    def on_tab_right_click(self, event):
        # Get the index of the tab under the mouse
        x, y = event.x, event.y
        try:
            clicked_tab = self.notebook.index(f"@{x},{y}")
        except tk.TclError:
            return  # Clicked outside of any tab
        editor = self.open_tabs[clicked_tab]
        # Create context menu
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Close Tab", command=lambda: self.close_tab(editor))
        menu.tk_popup(event.x_root, event.y_root)

    def parent_master_title(self, editor):
        if editor.filepath:
            self.root.title(f"Multi-Language IDE - {os.path.basename(editor.filepath)}")
        else:
            self.root.title("Multi-Language IDE - Untitled")

if __name__ == "__main__":
    root = tk.Tk()
    ide = SimpleIDE(root)
    root.mainloop()

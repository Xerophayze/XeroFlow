import sys
import subprocess
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
import os
import datetime

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
from pygments.lexers.python import PythonLexer
from pygments.styles import get_style_by_name
from pygments.token import Token
import jedi
import ast

class LineNumbers(tk.Text):
    def __init__(self, master, text_widget, **kwargs):
        super().__init__(master, width=4, padx=3, takefocus=0, border=0,
                         background='lightgrey', state='disabled', **kwargs)
        self.text_widget = text_widget
        self.text_widget.bind("<<Change>>", self.on_change)
        self.text_widget.bind("<Configure>", self.on_change)
        self.update_line_numbers()

    def on_change(self, event=None):
        self.update_line_numbers()
        return "break"

    def update_line_numbers(self, event=None):
        self.config(state='normal')
        self.delete(1.0, tk.END)
        line_count = self.text_widget.index('end-1c').split('.')[0]
        line_numbers = "\n".join(str(no+1) for no in range(int(line_count)))
        self.insert(1.0, line_numbers)
        self.config(state='disabled')

class SimpleIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Python IDE")
        self.root.geometry("800x600")
        self.font_styles = {}  # Cache for font styles
        self.pending_changes = []  # Store pending changes
        self.filepath = None  # Current file path
        self.create_widgets()
        self.bind_events()
        self.setup_versioning()

    def create_widgets(self):
        # Create menu bar
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)

        # File menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label='File', menu=file_menu)
        file_menu.add_command(label='New', command=self.new_file)
        file_menu.add_command(label='Load', command=self.load_file)
        file_menu.add_command(label='Save', command=self.save_file)
        file_menu.add_separator()
        file_menu.add_command(label='Exit', command=self.exit_application)

        self.style = get_style_by_name('default')
        self.text_frame = tk.Frame(self.root)
        self.text_frame.pack(fill='both', expand=True)

        # Create the scrollbar
        self.scrollbar = ttk.Scrollbar(self.text_frame, orient='vertical')
        self.scrollbar.pack(side='right', fill='y')

        # Create the text area
        self.text_area = tk.Text(self.text_frame, wrap='none', undo=True)
        self.text_area.pack(side='right', fill='both', expand=True)

        # Configure the scrollbar to control both the text area and line numbers
        self.text_area.configure(yscrollcommand=self.on_textscroll)
        self.scrollbar.configure(command=self.on_scrollbar_scroll)

        # Create the line numbers widget
        self.line_numbers = LineNumbers(self.text_frame, self.text_area)
        self.line_numbers.pack(side='left', fill='y')

        # Bottom frame for status bar and version controls
        self.bottom_frame = tk.Frame(self.root)
        self.bottom_frame.pack(side='bottom', fill='x')

        # Version dropdown
        self.version_var = tk.StringVar()
        self.version_dropdown = ttk.Combobox(self.bottom_frame, textvariable=self.version_var)
        self.version_dropdown.bind('<<ComboboxSelected>>', self.load_version)
        self.version_dropdown.pack(side='left', padx=5)

        # Save Version button
        self.save_version_button = tk.Button(self.bottom_frame, text='Save Version', command=self.save_version)
        self.save_version_button.pack(side='left')

        self.status_bar = tk.Label(self.bottom_frame, text='Ready', bd=1, relief='sunken', anchor='w')
        self.status_bar.pack(side='left', fill='x', expand=True)

    def bind_events(self):
        self.text_area.bind('<<Modified>>', self.on_text_change)
        self.text_area.bind('<Control-space>', self.code_complete)
        self.text_area.bind('<MouseWheel>', self.on_mouse_wheel)  # For Windows
        self.text_area.bind('<Button-4>', self.on_mouse_wheel)    # For Linux
        self.text_area.bind('<Button-5>', self.on_mouse_wheel)    # For Linux



    def highlight_syntax(self, event=None):
        code = self.text_area.get('1.0', 'end-1c')
        self.text_area.mark_set("range_start", "1.0")

        # Remove existing tags except 'sel' and pending change tags
        for tag in self.text_area.tag_names():
            if tag not in ('sel', 'pending_new', 'pending_update', 'pending_delete'):
                self.text_area.tag_remove(tag, "1.0", "end")

        # Apply new syntax highlighting
        for token, content in lex(code, PythonLexer()):
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
                # Create a font with bold and/or italic styles
                font_props = {'family': 'TkDefaultFont', 'size': 10}
                if style['bold']:
                    font_props['weight'] = 'bold'
                if style['italic']:
                    font_props['slant'] = 'italic'
                if tag_name not in self.font_styles:
                    self.font_styles[tag_name] = tkfont.Font(**font_props)
                options['font'] = self.font_styles[tag_name]
            if options:
                self.text_area.tag_config(tag_name, **options)

        # Apply pending change highlights
        self.highlight_pending_changes()

    def code_complete(self, event=None):
        index = self.text_area.index(tk.INSERT)
        code = self.text_area.get('1.0', 'end-1c')
        script = jedi.Script(code)
        try:
            line, column = map(int, index.split('.'))
            completions = script.complete(line, column)
            if completions:
                menu = tk.Menu(self.root, tearoff=0)
                for completion in completions:
                    menu.add_command(label=completion.name, command=lambda c=completion: self.insert_completion(c))
                menu.post(event.x_root, event.y_root)
        except Exception as e:
            self.status_bar.config(text=f'Code Completion Error: {e}')

    def insert_completion(self, completion):
        self.text_area.insert(tk.INSERT, completion.complete)
        self.text_area.focus()

    def check_syntax(self):
        code = self.text_area.get('1.0', 'end-1c')
        self.text_area.tag_remove('error', '1.0', 'end')
        try:
            ast.parse(code)
            self.status_bar.config(text='No syntax errors')
        except SyntaxError as e:
            line = e.lineno
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
        """Scrolls both text widgets when the scrollbar moves."""
        self.scrollbar.set(*args)
        self.text_area.yview_moveto(args[0])
        self.line_numbers.yview_moveto(args[0])

    def on_scrollbar_scroll(self, *args):
        """Scrolls both text widgets when the scrollbar is moved."""
        self.text_area.yview(*args)
        self.line_numbers.yview(*args)

    def on_mouse_wheel(self, event):
        """Handles mouse wheel scrolling."""
        delta = 0
        if event.num == 4 or event.delta > 0:
            delta = -1
        elif event.num == 5 or event.delta < 0:
            delta = 1
        self.text_area.yview_scroll(delta, "units")
        self.line_numbers.yview_scroll(delta, "units")
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

    # File menu functionalities
    def new_file(self):
        self.text_area.delete('1.0', tk.END)
        self.filepath = None
        self.root.title("Simple Python IDE - New File")
        self.status_bar.config(text='New file created')

    def load_file(self):
        filetypes = [("Python Files", "*.py"), ("All Files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            with open(path, 'r') as file:
                code = file.read()
            self.text_area.delete('1.0', tk.END)
            self.text_area.insert('1.0', code)
            self.filepath = path
            self.root.title(f"Simple Python IDE - {os.path.basename(path)}")
            self.on_text_change()
            self.status_bar.config(text=f'Loaded file: {os.path.basename(path)}')

    def save_file(self):
        if self.filepath:
            with open(self.filepath, 'w') as file:
                code = self.text_area.get('1.0', tk.END)
                file.write(code)
            self.status_bar.config(text=f'Saved file: {os.path.basename(self.filepath)}')
        else:
            self.save_file_as()

    def save_file_as(self):
        filetypes = [("Python Files", "*.py"), ("All Files", "*.*")]
        path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=filetypes)
        if path:
            with open(path, 'w') as file:
                code = self.text_area.get('1.0', tk.END)
                file.write(code)
            self.filepath = path
            self.root.title(f"Simple Python IDE - {os.path.basename(path)}")
            self.status_bar.config(text=f'Saved file: {os.path.basename(path)}')

    def exit_application(self):
        self.root.quit()

    # Versioning functionalities
    def setup_versioning(self):
        self.version_folder = os.path.join(os.getcwd(), 'versions')
        if not os.path.exists(self.version_folder):
            os.makedirs(self.version_folder)
        self.update_version_list()

    def save_version(self):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        version_name = f"version_{timestamp}.py"
        version_path = os.path.join(self.version_folder, version_name)
        with open(version_path, 'w') as file:
            code = self.text_area.get('1.0', tk.END)
            file.write(code)
        self.update_version_list()
        self.status_bar.config(text=f'Version saved: {version_name}')

    def update_version_list(self):
        versions = [f for f in os.listdir(self.version_folder) if f.endswith('.py')]
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

if __name__ == "__main__":
    root = tk.Tk()
    ide = SimpleIDE(root)

    # Example usage
    # line_changes = [
    #     {'line_number': 1, 'code_line': 'def greet(name):', 'action': 'new'},
    #     {'line_number': 2, 'code_line': '    print(f"Hello, {name}!")', 'action': 'new'},
    #     {'line_number': 1, 'code_line': 'def say_hello():', 'action': 'update'},
    #     {'line_number': 3, 'action': 'delete'},
    # ]
    # ide.process_line_inputs(line_changes)

    root.mainloop()


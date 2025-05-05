import tkinter as tk
from tkinter import END, messagebox
import re
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token
from pygments.util import ClassNotFound  # Import ClassNotFound exception
import requests  # For image fetching
from PIL import Image, ImageTk  # For image handling via Pillow
from io import BytesIO  # For image handling
import tempfile
import os
import logging

# Import for Mermaid diagram support
try:
    import mermaid as md
    from mermaid.graph import Graph
    MERMAID_AVAILABLE = True
except ImportError:
    print("mermaid-py package not available. Mermaid diagrams will be rendered as code blocks.")
    MERMAID_AVAILABLE = False

formatting_enabled = True  # Global flag to control formatting

def set_formatting_enabled(flag):
    """Set the global formatting flag."""
    global formatting_enabled
    formatting_enabled = flag

def append_formatted_text(text_widget, text):
    """
    Appends text to the text_widget with optional formatting applied.
    """
    text_widget.config(state=tk.NORMAL)
    if formatting_enabled:
        apply_formatting(text_widget, text)
    else:
        text_widget.insert(tk.END, text)
    text_widget.config(state=tk.DISABLED)

def apply_formatting(text_widget, text, base_tag=None):
    """
    Parses markdown-like syntax in the text and applies formatting tags to the Text widget.
    Supported block-level and inline markdown includes:
      - Headings, lists, code blocks, blockquotes, horizontal rules, footnotes, tables, etc.
      - Inline styles: **bold**, *italic*, ~~strikethrough~~, `inline code`, and <u>underlined</u>
      - Combined formatting:
            • Bold with strikethrough: **~~text~~** or ~~**text**~~
            • Italic with strikethrough: *~~text~~* or ~~*text*~~
            • Bold + Italic with strikethrough: ***~~text~~*** or ~~***text***~~
            • Underlined emphasis: e.g. <u>**Bold Underlined**</u> or **<u>Bold Underlined</u>**
      - Links: [text](url) plus emphasized links: **[text](url)**, *[text](url)*, or ***[text](url)***
      - Images: ![alt](url) and similarly when wrapped in emphasis markers.
    """
    # Configure standard tags
    text_widget.tag_configure("heading1", font=("Helvetica", 16, "bold"))
    text_widget.tag_configure("heading2", font=("Helvetica", 14, "bold"))
    text_widget.tag_configure("heading3", font=("Helvetica", 12, "bold"))
    text_widget.tag_configure("bold", font=("Helvetica", 12, "bold"))
    text_widget.tag_configure("italic", font=("Helvetica", 12, "italic"))
    text_widget.tag_configure("underline", font=("Helvetica", 12, "underline"))
    text_widget.tag_configure("strikethrough", font=("Helvetica", 12, "overstrike"))
    text_widget.tag_configure("highlight", background="#ffff00")  # Add highlight tag with yellow background
    text_widget.tag_configure("inline_code", font=("Consolas", 12), background="#f0f0f0")
    text_widget.tag_configure("code_block", font=("Consolas", 12), background="#e0e0e0", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("bullet", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("numbered", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("subitem", lmargin1=50, lmargin2=50)  # Add tag for subitems with more indentation
    # Configure blockquote tags for nesting (up to 5 levels)
    for i in range(1, 6):
        text_widget.tag_configure(f"blockquote_{i}", lmargin1=25 * i, lmargin2=25 * i,
                                  foreground="#555555", font=("Helvetica", 12, "italic"))
        
    text_widget.tag_configure("link", foreground="blue", underline=True)
    text_widget.tag_configure("image", foreground="green")  # Placeholder; actual image inserted via window_create
    text_widget.tag_configure("think_block", font=("Helvetica", 12), background="#f8f8f8", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("footnote", font=("Helvetica", 10, "italic"))
    # Table-related tags
    text_widget.tag_configure("table", font=("Consolas", 12))
    text_widget.tag_configure("table_bold", font=("Consolas", 12, "bold"))
    text_widget.tag_configure("table_italic", font=("Consolas", 12, "italic"))
    text_widget.tag_configure("table_strikethrough", font=("Consolas", 12, "overstrike"))
    text_widget.tag_configure("table_inline_code", font=("Consolas", 12), background="#f0f0f0")
    text_widget.tag_configure("table_bold_italic", font=("Consolas", 12, "bold", "italic"))
    
    # Code block syntax highlighting tags
    text_widget.tag_configure("keyword", foreground="#0000FF")
    text_widget.tag_configure("string", foreground="#008000")
    text_widget.tag_configure("comment", foreground="#808080")
    text_widget.tag_configure("operator", foreground="#FF00FF")
    text_widget.tag_configure("code_block_text", foreground="#000000")
    
    # Regular expressions for block-level patterns
    code_block_pattern    = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    heading_pattern       = re.compile(r'^(#{1,6})\s*(.*)$', re.MULTILINE)
    heading_numbered_pattern = re.compile(r'^(#{1,6})\s*(\d+\.)\s*(.*)$', re.MULTILINE)
    bold_pattern          = re.compile(r'\*\*(?!\*)(.+?)(?<!\*)\*\*(?!\*)')
    bold_pattern_us       = re.compile(r'__(?!_)(.+?)(?<!_)__(?!_)')
    italic_pattern        = re.compile(r'\*(?!\*)(.+?)(?<!\*)\*(?!\*)', re.DOTALL)
    italic_pattern_us     = re.compile(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', re.DOTALL)
    strikethrough_pattern = re.compile(r'~~(.*?)~~')
    highlight_pattern     = re.compile(r'==([^=]+?)==')  # Add pattern for highlighted text
    inline_code_pattern   = re.compile(r'`([^`]+)`')
    underline_pattern     = re.compile(r'<u>(.*?)</u>', re.DOTALL)
    link_pattern          = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    image_pattern         = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    footnote_ref_pattern  = re.compile(r'\[\^([^\]]+)\]')
    bullet_pattern        = re.compile(r'^(\s*[-*+])\s+(.*)$', re.MULTILINE)
    numbered_pattern      = re.compile(r'^(\s*\d+\.)\s+(.*)$', re.MULTILINE)
    alpha_subitem_pattern = re.compile(r'^(\s*)([a-z]\.)\s+(.*)$', re.MULTILINE)  # Pattern for alphabetic subitems
    # Updated blockquote pattern with named groups:
    blockquote_pattern    = re.compile(r'^(?P<markers>(?:>\s*)+)(?P<content>.*)$', re.MULTILINE)
    think_block_pattern   = re.compile(r'<think>(.*?)</think>', re.DOTALL)
    footnote_def_pattern  = re.compile(r'^\[\^([^\]]+)\]:\s*(.*)$')
    hr_pattern            = re.compile(r'^\s*([-*_])(?:\s*\1){2,}\s*$')
    combined_pattern      = re.compile(r'\*\*\*(.+?)\*\*\*', re.DOTALL)
    
    # --- NEW INLINE PATTERNS ---
    # Combined formatting with strikethrough:
    bold_italic_strike_pattern_1 = re.compile(r'\*\*\*~~(.+?)~~\*\*\*', re.DOTALL)
    bold_italic_strike_pattern_2 = re.compile(r'~~\*\*\*(.+?)\*\*\*~~', re.DOTALL)
    bold_strike_pattern_1        = re.compile(r'\*\*~~(.+?)~~\*\*', re.DOTALL)
    bold_strike_pattern_2        = re.compile(r'~~\*\*(.+?)\*\*~~', re.DOTALL)
    italic_strike_pattern_1      = re.compile(r'\*~~(.+?)~~\*', re.DOTALL)
    italic_strike_pattern_2      = re.compile(r'~~\*(.+?)\*~~', re.DOTALL)
    # Underline combinations with emphasis:
    underline_bold_italic_pattern_1 = re.compile(r'<u>\*\*\*(.+?)\*\*\*</u>', re.DOTALL)
    underline_bold_italic_pattern_2 = re.compile(r'\*\*\*<u>(.+?)</u>\*\*\*', re.DOTALL)
    underline_bold_pattern_1        = re.compile(r'<u>\*\*(.+?)\*\*</u>', re.DOTALL)
    underline_bold_pattern_2        = re.compile(r'\*\*<u>(.+?)</u>\*\*', re.DOTALL)
    underline_italic_pattern_1      = re.compile(r'<u>\*(.+?)\*</u>', re.DOTALL)
    underline_italic_pattern_2      = re.compile(r'\*<u>(.+?)</u>\*', re.DOTALL)
    # Links with emphasis:
    bold_italic_link_pattern = re.compile(r'\*\*\*\[([^\]]+)\]\(([^)]+)\)\*\*\*')
    bold_link_pattern        = re.compile(r'\*\*\[([^\]]+)\]\(([^)]+)\)\*\*')
    italic_link_pattern      = re.compile(r'\*\[([^\]]+)\]\(([^)]+)\)\*')
    # Images with emphasis:
    bold_italic_image_pattern = re.compile(r'\*\*\*!!\[([^\]]*)\]\(([^)]+)\)\*\*\*')
    bold_image_pattern        = re.compile(r'\*\*!\\?\[([^\]]*)\]\(([^)]+)\)\*\*')
    italic_image_pattern      = re.compile(r'\*\!\[([^\]]*)\]\(([^)]+)\)\*')
    
    # Helper to insert content with base tag
    def insert_with_base_tag(content, *tags):
        tags_to_apply = list(tags)
        if base_tag:
            tags_to_apply.append(base_tag)
        text_widget.insert(END, content, tuple(tags_to_apply))
    
    def add_horizontal_rule():
        width = text_widget.winfo_width() if text_widget.winfo_width() > 20 else 400
        hr_frame = tk.Frame(text_widget, height=2, bd=1, relief=tk.SUNKEN, width=width, bg="black")
        hr_frame.pack_propagate(False)
        text_widget.window_create(END, window=hr_frame)
        text_widget.insert(END, "\n")
    
    # Helper for hyperlinks
    def add_hyperlink_styled(link_text, url, extra_styles=()):
        def callback(event, url=url):
            import webbrowser
            webbrowser.open(url)
        text_widget.insert(END, link_text, ("link",) + extra_styles)
        end_index = text_widget.index(END)
        start_index = f"{end_index} - {len(link_text)}c"
        text_widget.tag_bind("link", "<Button-1>", callback)
    
    # Helper for images
    def add_image(alt_text, url, extra_styles=()):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                image_data = response.content
                image_stream = BytesIO(image_data)
                pil_image = Image.open(image_stream)
                pil_image = pil_image.resize((150, 150), Image.ANTIALIAS)
                tk_image = ImageTk.PhotoImage(pil_image)
                text_widget.image_create(END, image=tk_image)
                if not hasattr(text_widget, 'images'):
                    text_widget.images = []
                text_widget.images.append(tk_image)
                insert_with_base_tag(' ', *extra_styles)
        except Exception as e:
            insert_with_base_tag(f"[Image not available: {alt_text}] ", "italic")
    
    def process_mermaid_diagram(mermaid_code):
        """Process a Mermaid diagram and display it in the text widget"""
        if not MERMAID_AVAILABLE:
            return False
            
        try:
            # Create a Graph object with the Mermaid code
            diagram = Graph('mermaid-diagram', mermaid_code)
            
            # Create a Mermaid renderer
            renderer = md.Mermaid(diagram)
            
            # Get the image bytes using a temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            try:
                # Generate the PNG file
                renderer.to_png(temp_path)
                
                # Read the file content
                with open(temp_path, 'rb') as f:
                    image_bytes = f.read()
                    
                # Clean up the temporary file
                os.unlink(temp_path)
            except Exception as e:
                logging.error(f"Error generating Mermaid PNG: {e}")
                os.unlink(temp_path)  # Clean up even if there's an error
                image_bytes = None
            
            if image_bytes:
                # Convert bytes to image
                image_stream = BytesIO(image_bytes)
                pil_image = Image.open(image_stream)
                
                # Calculate appropriate size (maintain aspect ratio)
                width, height = pil_image.size
                max_width = 500  # Maximum width for the diagram
                if width > max_width:
                    ratio = max_width / width
                    new_width = max_width
                    new_height = int(height * ratio)
                    pil_image = pil_image.resize((new_width, new_height), Image.ANTIALIAS)
                
                # Create Tkinter image and display it
                tk_image = ImageTk.PhotoImage(pil_image)
                text_widget.image_create(END, image=tk_image)
                if not hasattr(text_widget, 'images'):
                    text_widget.images = []
                text_widget.images.append(tk_image)
                text_widget.insert(END, '\n')
                return True
            return False
        except Exception as e:
            print(f"Error processing Mermaid diagram: {e}")
            return False
    
    def create_think_block_toggle(text_widget, think_content):
        frame = tk.Frame(text_widget)
        frame.pack_propagate(False)
        button_frame = tk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=5, pady=(5,0))
        content_frame = tk.Frame(frame, relief=tk.GROOVE, borderwidth=1)
        line_count = len(think_content.split('\n'))
        height = min(max(line_count + 1, 3), 15)
        content_widget = tk.Text(content_frame, 
                                 height=height,
                                 wrap=tk.WORD,
                                 width=80,
                                 font=("Consolas", 10),
                                 bg="#f8f8f8",
                                 relief=tk.FLAT)
        content_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        content_widget.insert("1.0", think_content)
        content_widget.config(state=tk.DISABLED)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        content_frame.pack_forget()
        def toggle_content():
            if content_frame.winfo_manager():
                content_frame.pack_forget()
                toggle_btn.config(text="Show Thoughts")
                frame.configure(height=35)
            else:
                content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
                toggle_btn.config(text="Hide Thoughts")
                required_height = content_widget.winfo_reqheight() + 50
                frame.configure(height=required_height)
        toggle_btn = tk.Button(button_frame, text="Show Thoughts", command=toggle_content)
        toggle_btn.pack(side=tk.LEFT)
        frame.configure(height=35, width=text_widget.winfo_width() - 20)
        def update_frame_width(event):
            frame.configure(width=event.width - 20)
        text_widget.bind('<Configure>', update_frame_width)
        return frame
    
    # === Recursive Inline Formatting Functions ===
    def process_inline_formatting(text_widget, text_line, extra_tags=()):
        # First, break out any combined triple-asterisk segments (fallback behavior)
        segments = []
        pos = 0
        while True:
            m = combined_pattern.search(text_line, pos)
            if not m:
                segments.append(('text', text_line[pos:]))
                break
            segments.append(('text', text_line[pos:m.start()]))
            segments.append(('combined', m.group(1)))
            pos = m.end()
        for seg_type, seg in segments:
            if seg_type == 'text':
                process_inline_formatting_simple(text_widget, seg, extra_tags)
            elif seg_type == 'combined':
                process_inline_formatting(text_widget, seg, extra_tags + ("bold", "italic"))
    
    def process_inline_formatting_simple(text_widget, text_line, extra_tags=()):
        def local_insert(content, *tags):
            combined = list(extra_tags)
            if base_tag:
                combined.append(base_tag)
            combined.extend(tags)
            # Special handling for table inline styles:
            if "table" in combined:
                inline_styles = [t for t in combined if t in ("bold", "italic", "strikethrough", "inline_code")]
                combined = [t for t in combined if t not in ("table", "bold", "italic", "strikethrough", "inline_code")]
                if "bold" in inline_styles and "italic" in inline_styles:
                    inline_styles = [t for t in inline_styles if t not in ("bold", "italic")]
                    combined.append("table_bold_italic")
                else:
                    for style in inline_styles:
                        combined.append("table_" + style)
                if not inline_styles:
                    combined.append("table")
                combined = tuple(combined)
            else:
                combined = tuple(combined)
            text_widget.insert(END, content, combined)
        pos = 0
        length = len(text_line)
        # List of (pattern, type)
        pattern_tuples = [
            (bold_italic_strike_pattern_1, "bold_italic_strike"),
            (bold_italic_strike_pattern_2, "bold_italic_strike"),
            (bold_strike_pattern_1, "bold_strike"),
            (bold_strike_pattern_2, "bold_strike"),
            (italic_strike_pattern_1, "italic_strike"),
            (italic_strike_pattern_2, "italic_strike"),
            (underline_bold_italic_pattern_1, "underline_bold_italic"),
            (underline_bold_italic_pattern_2, "underline_bold_italic"),
            (underline_bold_pattern_1, "underline_bold"),
            (underline_bold_pattern_2, "underline_bold"),
            (underline_italic_pattern_1, "underline_italic"),
            (underline_italic_pattern_2, "underline_italic"),
            (bold_italic_link_pattern, "bold_italic_link"),
            (bold_link_pattern, "bold_link"),
            (italic_link_pattern, "italic_link"),
            (bold_italic_image_pattern, "bold_italic_image"),
            (bold_image_pattern, "bold_image"),
            (italic_image_pattern, "italic_image"),
            (bold_pattern, "bold"),
            (bold_pattern_us, "bold"),
            (italic_pattern, "italic"),
            (italic_pattern_us, "italic"),
            (strikethrough_pattern, "strikethrough"),
            (highlight_pattern, "highlight"),  # Add highlight pattern to the processing list
            (inline_code_pattern, "inline_code"),
            (underline_pattern, "underline"),
            (link_pattern, "link"),
            (image_pattern, "image"),
            (footnote_ref_pattern, "footnote_ref")
        ]
        while pos < length:
            next_matches = []
            for pat, pat_type in pattern_tuples:
                m = pat.search(text_line, pos)
                if m:
                    next_matches.append((m.start(), m, pat_type))
            if not next_matches:
                local_insert(text_line[pos:])
                break
            next_matches.sort(key=lambda x: x[0])
            earliest_pos, earliest_match, pat_type = next_matches[0]
            if earliest_pos > pos:
                local_insert(text_line[pos:earliest_pos])
            if pat_type == "bold_italic_strike":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("bold", "italic", "strikethrough"))
            elif pat_type == "bold_strike":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("bold", "strikethrough"))
            elif pat_type == "italic_strike":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("italic", "strikethrough"))
            elif pat_type == "underline_bold_italic":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("underline", "bold", "italic"))
            elif pat_type == "underline_bold":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("underline", "bold"))
            elif pat_type == "underline_italic":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("underline", "italic"))
            elif pat_type == "bold_italic_link":
                link_text, url = earliest_match.groups()
                add_hyperlink_styled(link_text, url, extra_styles=("bold", "italic"))
            elif pat_type == "bold_link":
                link_text, url = earliest_match.groups()
                add_hyperlink_styled(link_text, url, extra_styles=("bold",))
            elif pat_type == "italic_link":
                link_text, url = earliest_match.groups()
                add_hyperlink_styled(link_text, url, extra_styles=("italic",))
            elif pat_type == "bold_italic_image":
                alt_text, url = earliest_match.groups()
                add_image(alt_text, url, extra_styles=("bold", "italic"))
            elif pat_type == "bold_image":
                alt_text, url = earliest_match.groups()
                add_image(alt_text, url, extra_styles=("bold",))
            elif pat_type == "italic_image":
                alt_text, url = earliest_match.groups()
                add_image(alt_text, url, extra_styles=("italic",))
            elif pat_type == "bold":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("bold",))
            elif pat_type == "italic":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("italic",))
            elif pat_type == "strikethrough":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("strikethrough",))
            elif pat_type == "highlight":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("highlight",))
            elif pat_type == "inline_code":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("inline_code",))
            elif pat_type == "underline":
                process_inline_formatting(text_widget, earliest_match.group(1),
                                          extra_tags + ("underline",))
            elif pat_type == "link":
                link_text, url = earliest_match.groups()
                add_hyperlink_styled(link_text, url)
            elif pat_type == "image":
                alt_text, url = earliest_match.groups()
                add_image(alt_text, url)
            elif pat_type == "footnote_ref":
                footnote_id = earliest_match.group(1)
                footnote_tag = f"footnote_{footnote_id}"
                text_widget.tag_configure(footnote_tag, foreground="blue", underline=True)
                text_widget.tag_bind(footnote_tag, "<Button-1>", 
                            lambda e, fid=footnote_id: scroll_to_footnote(text_widget, fid))
                local_insert(f"[^{footnote_id}]", "footnote_ref", footnote_tag)
            pos = earliest_match.end()
    
    def process_table_block(table_lines):
        for row in table_lines:
            if re.match(r'^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$', row):
                insert_with_base_tag(row.strip() + "\n", "table")
            else:
                row = row.strip()
                if row.startswith("|"):
                    row = row[1:]
                if row.endswith("|"):
                    row = row[:-1]
                cells = row.split("|")
                for idx, cell in enumerate(cells):
                    cell_text = cell.strip()
                    if idx > 0:
                        text_widget.insert(END, " | ", "table")
                    # Check if cell begins with a blockquote marker (one or more ">")
                    bq_match = re.match(r'^(>+)\s*(.*)$', cell_text)
                    if bq_match:
                        markers = bq_match.group(1)
                        quote_level = len(markers)
                        content = bq_match.group(2)
                        process_inline_formatting(text_widget, content, ("table", f"blockquote_{quote_level}"))
                    else:
                        process_inline_formatting(text_widget, cell_text, ("table",))
                text_widget.insert(END, "\n")
    
    # --- UPDATED BLOCKQUOTE AND HEADING HANDLING ---
    def process_line(line):
        if hr_pattern.match(line):
            add_horizontal_rule()
            return
        footnote_def_match = footnote_def_pattern.match(line)
        if footnote_def_match:
            number = footnote_def_match.group(1)
            content = footnote_def_match.group(2)
            insert_with_base_tag(f"[^{number}]: {content}\n", "footnote")
            return
        # Process headings by applying inline formatting on the content
        heading_match = heading_pattern.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            content = heading_match.group(2)
            tag = f"heading{level}" if level <= 3 else "heading3"
            process_inline_formatting(text_widget, content, (tag,))
            text_widget.insert(END, '\n')
            return
        
        # Handle combined heading with numbered item (e.g., "#### 7. **Title**")
        heading_numbered_match = heading_numbered_pattern.match(line)
        if heading_numbered_match:
            level = len(heading_numbered_match.group(1))
            number = heading_numbered_match.group(2)
            content = heading_numbered_match.group(3)
            tag = f"heading{level}" if level <= 3 else "heading3"
            # Insert the number as part of the heading
            text_widget.insert(END, number + ' ', tag)
            process_inline_formatting(text_widget, content, (tag,))
            text_widget.insert(END, '\n')
            return
            
        bullet_match = bullet_pattern.match(line)
        if bullet_match:
            content = bullet_match.group(2)
            indent = re.match(r'^\s*', bullet_match.group(1)).group(0)
            insert_with_base_tag(indent + u'\u2022 ', "bullet")
            process_inline_formatting(text_widget, content, ())
            text_widget.insert(END, '\n')
            return
        numbered_match = numbered_pattern.match(line)
        if numbered_match:
            number, content = numbered_match.groups()
            indent = re.match(r'^\s*', numbered_match.group(1)).group(0)
            insert_with_base_tag(indent + number + ' ', "numbered")
            process_inline_formatting(text_widget, content, ())
            text_widget.insert(END, '\n')
            return
            
        # Handle alphabetic subitems (a., b., c., etc.)
        alpha_subitem_match = alpha_subitem_pattern.match(line)
        if alpha_subitem_match:
            indent, letter, content = alpha_subitem_match.groups()
            # Use subitem tag for proper indentation
            insert_with_base_tag(indent + letter + ' ', "subitem")
            process_inline_formatting(text_widget, content, ())
            text_widget.insert(END, '\n')
            return
            
        # Updated blockquote handling using named groups:
        blockquote_match = blockquote_pattern.match(line)
        if blockquote_match:
            markers = blockquote_match.group("markers")
            quote_level = markers.count('>')
            content = blockquote_match.group("content")
            heading_inside = heading_pattern.match(content)
            if heading_inside:
                level = len(heading_inside.group(1))
                heading_text = heading_inside.group(2)
                tag = f"heading{level}" if level <= 3 else "heading3"
                insert_with_base_tag(heading_text + '\n', tag, f"blockquote_{quote_level}")
            else:
                process_inline_formatting(text_widget, content, (f"blockquote_{quote_level}",))
                text_widget.insert(END, '\n')
            return
        process_inline_formatting(text_widget, line, ())
        text_widget.insert(END, '\n')
    
    def process_lines(lines):
        i = 0
        while i < len(lines):
            if i + 1 < len(lines) and re.match(r'^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$', lines[i+1]):
                table_lines = []
                while i < len(lines) and '|' in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                process_table_block(table_lines)
                continue
            if i + 1 < len(lines):
                if re.match(r'^\s*=+\s*$', lines[i+1]):
                    insert_with_base_tag(lines[i].strip() + "\n", "heading1")
                    i += 2
                    continue
                elif re.match(r'^\s*-+\s*$', lines[i+1]):
                    insert_with_base_tag(lines[i].strip() + "\n", "heading2")
                    i += 2
                    continue
            process_line(lines[i])
            i += 1
    
    def split_text(text):
        segments = []
        pos = 0
        for match in code_block_pattern.finditer(text):
            start, end = match.span()
            if start > pos:
                segments.append(('text', text[pos:start]))
            segments.append(('code', match.group()))
            pos = end
        if pos < len(text):
            segments.append(('text', text[pos:]))
        return segments
    
    segments = split_text(text)
    
    for segment_type, segment_text in segments:
        if segment_type == 'text':
            pos = 0
            while pos < len(segment_text):
                think_match = think_block_pattern.search(segment_text, pos)
                if think_match:
                    pre_think_text = segment_text[pos:think_match.start()]
                    if pre_think_text:
                        process_lines(pre_think_text.split('\n'))
                    think_content = think_match.group(1).strip()
                    think_frame = create_think_block_toggle(text_widget, think_content)
                    text_widget.window_create(END, window=think_frame)
                    text_widget.insert(END, '\n')
                    pos = think_match.end()
                else:
                    remaining_text = segment_text[pos:]
                    process_lines(remaining_text.split('\n'))
                    break
        elif segment_type == 'code':
            code_match = code_block_pattern.match(segment_text)
            if code_match:
                language = code_match.group(1)
                code_content = code_match.group(2)
                def copy_code():
                    text_widget.clipboard_clear()
                    text_widget.clipboard_append(code_content)
                    text_widget.update()
                    copy_button.config(text="Copied!", state=tk.DISABLED)
                    text_widget.after(1500, lambda: copy_button.config(text="Copy Code", state=tk.NORMAL))
                copy_button = tk.Button(text_widget, text="Copy Code", command=copy_code)
                text_widget.window_create(END, window=copy_button)
                insert_with_base_tag("\n")
                
                # Special handling for Mermaid diagrams
                if language and language.lower() == 'mermaid':
                    # Try to render the Mermaid diagram
                    if process_mermaid_diagram(code_content):
                        # If successful, we're done
                        insert_with_base_tag("\n")
                        return
                
                # Regular code block handling (fallback for Mermaid if rendering fails)
                if language and language.lower() == 'plaintext':
                    language = 'text'
                try:
                    lexer = get_lexer_by_name(language, stripall=True) if language else TextLexer()
                except ClassNotFound:
                    lexer = TextLexer()
                tokens = lex(code_content, lexer)
                start_index = text_widget.index(END)
                text_widget.insert(END, code_content, ("code_block",))
                end_index = text_widget.index(END)
                current_pos = start_index
                for ttype, value in tokens:
                    if ttype in Token.Keyword:
                        tag = "keyword"
                    elif ttype in Token.String:
                        tag = "string"
                    elif ttype in Token.Comment:
                        tag = "comment"
                    elif ttype in Token.Operator:
                        tag = "operator"
                    else:
                        tag = "code_block_text"
                    end_pos = f"{current_pos}+{len(value)}c"
                    text_widget.tag_add(tag, current_pos, end_pos)
                    current_pos = end_pos
                insert_with_base_tag("\n")

def scroll_to_footnote(text_widget, footnote_id):
    """Scroll to the footnote definition when a footnote reference is clicked."""
    search_pattern = f"[^{footnote_id}]:"
    start_pos = "1.0"
    while True:
        pos = text_widget.search(search_pattern, start_pos, stopindex=END)
        if not pos:
            break
        text_widget.see(pos)
        text_widget.mark_set("insert", pos)
        # Highlight the footnote temporarily
        text_widget.tag_add("footnote_highlight", pos, f"{pos}+{len(search_pattern)}c")
        text_widget.tag_configure("footnote_highlight", background="yellow")
        # Remove highlight after a delay
        text_widget.after(1500, lambda: text_widget.tag_remove("footnote_highlight", "1.0", END))
        break

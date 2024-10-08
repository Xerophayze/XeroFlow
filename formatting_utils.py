# formatting_utils.py

import tkinter as tk
from tkinter import END, messagebox
import re
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

def apply_formatting(text_widget, text, base_tag=None):
    """
    Parses markdown-like syntax in the text and applies formatting tags to the Text widget.
    Supported formats:
    - Headings: # Heading 1, ## Heading 2, etc.
    - Bold: **bold text**
    - Italic: *italic text*
    - Bullet points: - item, * item, + item
    - Code blocks: ```language\ncode\n```

    If 'base_tag' is provided, it is applied to all inserted text.
    """
    # Ensure the text widget is in NORMAL state
    text_widget.config(state=tk.NORMAL)

    # Define tags for formatting
    text_widget.tag_configure("heading1", font=("Helvetica", 16, "bold"))
    text_widget.tag_configure("heading2", font=("Helvetica", 14, "bold"))
    text_widget.tag_configure("heading3", font=("Helvetica", 12, "bold"))
    text_widget.tag_configure("bold", font=("Helvetica", 12, "bold"))
    text_widget.tag_configure("italic", font=("Helvetica", 12, "italic"))
    text_widget.tag_configure("code", font=("Courier", 12), background="#f0f0f0")
    text_widget.tag_configure("bullet", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("numbered", lmargin1=25, lmargin2=25)
    text_widget.tag_configure("blockquote", lmargin1=25, lmargin2=25, foreground="#555555")

    # Additional tags for syntax highlighting in code blocks
    text_widget.tag_configure("keyword", foreground="#0000FF")
    text_widget.tag_configure("string", foreground="#008000")
    text_widget.tag_configure("comment", foreground="#808080")
    text_widget.tag_configure("operator", foreground="#FF00FF")

    # Regular expressions
    code_block_pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    heading_pattern = re.compile(r'^(#{1,6})\s*(.*)$', re.MULTILINE)
    bold_pattern = re.compile(r'\*\*(.*?)\*\*')
    italic_pattern = re.compile(r'\*(?!\*)(.*?)\*')

    bullet_pattern = re.compile(r'^(\s*[-*+])\s+(.*)$', re.MULTILINE)
    numbered_pattern = re.compile(r'^(\s*\d+\.)\s+(.*)$', re.MULTILINE)
    blockquote_pattern = re.compile(r'^>\s+(.*)$', re.MULTILINE)

    # Helper function to insert text with base tag
    def insert_with_base_tag(content, *tags):
        tags_to_apply = list(tags)
        if base_tag:
            tags_to_apply.append(base_tag)
        text_widget.insert(END, content, tuple(tags_to_apply))

    # Split the text into code blocks and other text
    def split_text(text):
        # This function splits the text into segments, separating code blocks
        segments = []
        pos = 0
        for match in code_block_pattern.finditer(text):
            start, end = match.span()
            # Text before the code block
            if start > pos:
                segments.append(('text', text[pos:start]))
            # The code block
            segments.append(('code', match.group()))
            pos = end
        # Any remaining text after the last code block
        if pos < len(text):
            segments.append(('text', text[pos:]))
        return segments

    # Process inline formatting
    def process_inline_formatting(text_widget, text_line):
        """
        Processes a line of text for inline formatting like bold and italic.
        """
        pos = 0
        while pos < len(text_line):
            bold_match = bold_pattern.search(text_line, pos)
            italic_match = italic_pattern.search(text_line, pos)
            next_match = None
            if bold_match and italic_match:
                if bold_match.start() <= italic_match.start():
                    next_match = ('bold', bold_match)
                else:
                    next_match = ('italic', italic_match)
            elif bold_match:
                next_match = ('bold', bold_match)
            elif italic_match:
                next_match = ('italic', italic_match)

            if next_match:
                tag_type, match = next_match
                # Text before the match
                if match.start() > pos:
                    insert_with_base_tag(text_line[pos:match.start()])
                # Matched text
                insert_with_base_tag(match.group(1), tag_type)
                pos = match.end()
            else:
                # No more formatting
                insert_with_base_tag(text_line[pos:])
                break

    # Create copy button for code blocks
    def create_copy_button(code_text):
        def copy_code():
            text_widget.clipboard_clear()
            text_widget.clipboard_append(code_text)
            messagebox.showinfo("Copied", "Code block copied to clipboard.")
        return tk.Button(text_widget, text="Copy Code", command=copy_code)

    segments = split_text(text)

    for segment_type, segment_text in segments:
        if segment_type == 'text':
            # Process the text for headings, bold, italic, etc.
            lines = segment_text.split('\n')
            for line in lines:
                # Check for heading
                heading_match = heading_pattern.match(line)
                if heading_match:
                    level = len(heading_match.group(1))
                    content = heading_match.group(2)
                    tag = f"heading{level}" if level <=3 else "heading3"
                    insert_with_base_tag(content + '\n', tag)
                    continue
                # Check for bullet points
                bullet_match = bullet_pattern.match(line)
                if bullet_match:
                    content = bullet_match.group(2)
                    insert_with_base_tag(u'\u2022 ' + content + '\n', "bullet")
                    continue
                # Check for numbered list
                numbered_match = numbered_pattern.match(line)
                if numbered_match:
                    content = numbered_match.group(2)
                    insert_with_base_tag(numbered_match.group(1) + ' ' + content + '\n', "numbered")
                    continue
                # Check for blockquote
                blockquote_match = blockquote_pattern.match(line)
                if blockquote_match:
                    content = blockquote_match.group(1)
                    insert_with_base_tag(content + '\n', "blockquote")
                    continue
                # Process inline formatting for the line
                process_inline_formatting(text_widget, line)
                insert_with_base_tag('\n')
        elif segment_type == 'code':
            code_match = code_block_pattern.match(segment_text)
            if code_match:
                language = code_match.group(1)
                code_content = code_match.group(2)
                # Insert the "Copy Code" button
                copy_button = create_copy_button(code_content)
                text_widget.window_create(END, window=copy_button)
                insert_with_base_tag("\n")
                # Insert the code block with syntax highlighting
                lexer = get_lexer_by_name(language, stripall=True) if language else TextLexer()
                tokens = lex(code_content, lexer)
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
                        tag = "code"
                    insert_with_base_tag(value, tag)
                insert_with_base_tag("\n")

def append_formatted_text(text_widget, text):
    """
    Appends text to the text_widget with basic formatting applied.
    """
    text_widget.config(state=tk.NORMAL)
    text_widget.insert(tk.END, text)
    text_widget.config(state=tk.DISABLED)

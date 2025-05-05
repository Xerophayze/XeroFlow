# ExportWord.py

import sys
import subprocess
import pkg_resources
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

import re
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT, WD_COLOR_INDEX, WD_BREAK
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.opc.constants import RELATIONSHIP_TYPE as RT
import requests
from io import BytesIO
from tkinter import filedialog, Tk, messagebox
import os
import tempfile

# Import for Mermaid diagram support
try:
    import mermaid as md
    from mermaid.graph import Graph
    MERMAID_AVAILABLE = True
except ImportError:
    logging.warning("mermaid-py package not available. Mermaid diagrams will be rendered as code blocks.")
    MERMAID_AVAILABLE = False

### INLINE FORMATTING FUNCTIONS

def parse_inline_formatting(paragraph, text):
    """
    Parses inline GitHub-Flavored Markdown (GFM) formatting in the text and adds runs with appropriate styles.
    Supported formats include:
      - Combined formatting with strikethrough:
          • Bold with strikethrough: **~~text~~** or ~~**text**~~
          • Italic with strikethrough: *~~text~~* or ~~*text*~~
          • Bold, italic, and strikethrough: ***~~text~~*** or ~~***text***~~
      - Standard formatting:
          • Bold italic: ***text*** or ___text___, etc.
          • Bold: **text** or __text__
          • Italic: *text* or _text_
          • Underline via <u>text</u> (and combined with emphasis if wrapped accordingly)
          • Highlight via ==text== (and combined with other formatting)
          • Inline code, images, and links (with optional emphasis when wrapped)
    Note:
      • Plain ~~text~~ is processed as strikethrough only.
      • To have links styled as bold/italic, wrap the link markdown (e.g. **[link](url)**).
    """
    pattern = re.compile(
        # Combined formatting with strikethrough:
        r'(\*\*\*~~(.+?)~~\*\*\*)|'      # ***~~text~~***  => bold, italic, strikethrough
        r'(~~\*\*\*(.+?)\*\*\*~~)|'      # ~~***text***~~  => bold, italic, strikethrough
        r'(\*\*~~(.+?)~~\*\*)|'          # **~~text~~**      => bold, strikethrough
        r'(~~\*\*(.+?)\*\*~~)|'          # ~~**text**~~      => bold, strikethrough
        r'(\*~~(.+?)~~\*)|'              # *~~text~~*        => italic, strikethrough
        r'(~~\*(.+?)\*~~)|'              # ~~*text*~~        => italic, strikethrough
        
        # Underline combinations with emphasis:
        r'(<u>\*\*(.+?)\*\*</u>)|'       # <u>**text**</u>   => underline, bold
        r'(\*\*<u>(.+?)</u>\*\*)|'       # **<u>text</u>**   => underline, bold
        r'(<u>\*(.+?)\*</u>)|'           # <u>*text*</u>     => underline, italic
        r'(\*<u>(.+?)</u>\*)|'           # *<u>text</u>*     => underline, italic
        r'(<u>\*\*\*(.+?)\*\*\*</u>)|'   # <u>***text***</u> => underline, bold & italic
        r'(\*\*\*<u>(.+?)</u>\*\*\*)|'   # ***<u>text</u>*** => underline, bold & italic
        
        # Links with emphasis:
        r'(\*\*\[[^\]]+\]\([^\)]+\)\*\*)|'   # **[text](url)**   => bold link
        r'(\*\[[^\]]+\]\([^\)]+\)\*)|'       # *[text](url)*       => italic link
        r'(\*\*\*\[[^\]]+\]\([^\)]+\)\*\*\*)|'   # ***[text](url)*** => bold, italic link
        
        # Images with emphasis:
        r'(\*\*!\[[^\]]*\]\([^\)]+\)\*\*)|'     # **![alt](url)**   => bold image
        r'(\*!\[[^\]]*\]\([^\)]+\)\*)|'         # *![alt](url)*       => italic image
        r'(\*\*\*!!\[[^\]]*\]\([^\)]+\)\*\*\*)|' # ***!![alt](url)*** => bold, italic image
        
        # Original formatting patterns:
        r'(\*\*\*(.+?)\*\*\*)|'      # ***bold italic***
        r'(___(.+?)___)|'            # ___bold italic___
        r'(\*\*_(.+?)_\*\*)|'        # **_bold italic_**
        r'(__\*(.+?)\*__)|'          # __*bold italic*__
        r'(\*\*`(.+?)`\*\*)|'        # **`bold code`**
        r'(__`(.+?)`__)|'            # __`bold code`__
        r'(_`(.+?)`_)|'              # _`italic code`_
        r'(\*`(.+?)`\*)|'            # *`italic code`*
        r'(\*\*(.+?)\*\*)|'          # **bold**
        r'(__(.+?)__)|'              # __bold__
        r'(<u>(.+?)</u>)|'           # <u>underline</u>
        r'(==(.+?)==)|'              # ==highlight== (new pattern for highlighted text)
        r'(\*(.+?)\*)|'              # *italic*
        r'(_(.+?)_)|'                # _italic_
        r'(~~(.+?)~~)|'              # ~~strikethrough~~ (plain tilde: strike only)
        r'(`(.+?)`)|'                # `inline code`
        r'(!\[[^\]]*\]\([^\)]+\))|'  # image
        r'(\[[^\]]+\]\([^\)]+\))'    # link
    )
    last_index = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_index:
            paragraph.add_run(text[last_index:start])
        matched_text = match.group()

        # Combined formatting with strikethrough cases:
        if matched_text.startswith('***~~') or matched_text.startswith('~~***'):
            clean_text = matched_text[5:-5]
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.italic = True
            run.font.strike = True

        elif matched_text.startswith('**~~') or matched_text.startswith('~~**'):
            clean_text = matched_text[4:-4]
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.font.strike = True

        elif matched_text.startswith('*~~') or matched_text.startswith('~~*'):
            clean_text = matched_text[3:-3]
            run = paragraph.add_run(clean_text)
            run.italic = True
            run.font.strike = True

        # Underline combined with emphasis cases:
        elif matched_text.startswith('<u>***') or matched_text.startswith('***<u>'):
            if matched_text.startswith('<u>***'):
                clean_text = matched_text[6:-7]
            else:
                clean_text = re.sub(r'</?u>', '', matched_text[3:-3])
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.italic = True
            run.underline = True

        elif matched_text.startswith('<u>**') or matched_text.startswith('**<u>'):
            if matched_text.startswith('<u>**'):
                clean_text = matched_text[5:-6]
            else:
                clean_text = re.sub(r'</?u>', '', matched_text[2:-2])
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.underline = True

        elif matched_text.startswith('<u>*') or matched_text.startswith('*<u>'):
            if matched_text.startswith('<u>*'):
                clean_text = matched_text[4:-5]
            else:
                clean_text = re.sub(r'</?u>', '', matched_text[1:-1])
            run = paragraph.add_run(clean_text)
            run.italic = True
            run.underline = True

        # Links with emphasis (when wrapped with asterisks):
        elif matched_text.startswith('***['):
            link_content = matched_text[3:-3]
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', link_content)
            if m:
                link_text, url = m.groups()
                add_hyperlink(paragraph, link_text, url, bold=True, italic=True)
            else:
                paragraph.add_run(matched_text)

        elif matched_text.startswith('**['):
            link_content = matched_text[2:-2]
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', link_content)
            if m:
                link_text, url = m.groups()
                add_hyperlink(paragraph, link_text, url, bold=True)
            else:
                paragraph.add_run(matched_text)

        elif matched_text.startswith('*['):
            link_content = matched_text[1:-1]
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', link_content)
            if m:
                link_text, url = m.groups()
                add_hyperlink(paragraph, link_text, url, italic=True)
            else:
                paragraph.add_run(matched_text)

        # Images with emphasis cases (similar logic as links)...
        elif matched_text.startswith('***!!['):
            image_content = matched_text[5:-3]
            m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', image_content)
            if m:
                alt_text, url = m.groups()
                try:
                    response = requests.get(url)
                    if response.status_code == 200:
                        image_stream = BytesIO(response.content)
                        run = paragraph.add_run()
                        run.add_picture(image_stream, width=Inches(2))
                        run.bold = True
                        run.italic = True
                    else:
                        run = paragraph.add_run(f"[Image not available: {alt_text}]")
                        run.italic = True
                except Exception as e:
                    run = paragraph.add_run(f"[Image not available: {alt_text}]")
                    run.italic = True
            else:
                paragraph.add_run(matched_text)

        elif matched_text.startswith('**!['):
            image_content = matched_text[2:-2]
            m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', image_content)
            if m:
                alt_text, url = m.groups()
                try:
                    response = requests.get(url)
                    if response.status_code == 200:
                        image_stream = BytesIO(response.content)
                        run = paragraph.add_run()
                        run.add_picture(image_stream, width=Inches(2))
                        run.bold = True
                    else:
                        run = paragraph.add_run(f"[Image not available: {alt_text}]")
                        run.bold = True
                except Exception as e:
                    run = paragraph.add_run(f"[Image not available: {alt_text}]")
                    run.bold = True
            else:
                paragraph.add_run(matched_text)

        elif matched_text.startswith('*!['):
            image_content = matched_text[1:-1]
            m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', image_content)
            if m:
                alt_text, url = m.groups()
                try:
                    response = requests.get(url)
                    if response.status_code == 200:
                        image_stream = BytesIO(response.content)
                        run = paragraph.add_run()
                        run.add_picture(image_stream, width=Inches(2))
                        run.italic = True
                    else:
                        run = paragraph.add_run(f"[Image not available: {alt_text}]")
                        run.italic = True
                except Exception as e:
                    run = paragraph.add_run(f"[Image not available: {alt_text}]")
                    run.italic = True
            else:
                paragraph.add_run(matched_text)

        # Existing combined formatting cases:
        elif matched_text.startswith('**_`') or matched_text.startswith('__*`'):
            clean_text = matched_text[4:-4]
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.italic = True
            run.font.name = 'Consolas'
            rPr = run._r.get_or_add_rPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear')
            shd.set(qn('w:fill'), 'D3D3D3')
            rPr.append(shd)

        elif matched_text.startswith('***') or matched_text.startswith('___') or \
             matched_text.startswith('**_') or matched_text.startswith('__*'):
            clean_text = re.sub(r'[*_]', '', matched_text)
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.italic = True

        elif matched_text.startswith('**`') or matched_text.startswith('__`'):
            clean_text = matched_text[3:-3]
            run = paragraph.add_run(clean_text)
            run.bold = True
            run.font.name = 'Consolas'
            run.font.size = Pt(10)
            shading_elm = OxmlElement('w:shd')
            shading_elm.set(qn('w:fill'), 'E0E0E0')
            paragraph._p.get_or_add_pPr().append(shading_elm)
            pPr = paragraph._p.get_or_add_pPr()
            pBdr = OxmlElement('w:pBdr')
            for border_type in ['top', 'bottom', 'left', 'right']:
                border = OxmlElement(f'w:{border_type}')
                border.set(qn('w:val'), 'single')
                border.set(qn('w:sz'), '6')
                border.set(qn('w:space'), '1')
                border.set(qn('w:color'), 'auto')
                pBdr.append(border)
            pPr.append(pBdr)
            paragraph.paragraph_format.left_indent = Inches(0.25)
            paragraph.paragraph_format.right_indent = Inches(0.25)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)

        elif matched_text.startswith('_`') or matched_text.startswith('*`'):
            clean_text = matched_text[2:-2]
            run = paragraph.add_run(clean_text)
            run.italic = True
            run.font.name = 'Consolas'
            run.font.size = Pt(10)
            shading_elm = OxmlElement('w:shd')
            shading_elm.set(qn('w:fill'), 'E0E0E0')
            paragraph._p.get_or_add_pPr().append(shading_elm)
            pPr = paragraph._p.get_or_add_pPr()
            pBdr = OxmlElement('w:pBdr')
            for border_type in ['top', 'bottom', 'left', 'right']:
                border = OxmlElement(f'w:{border_type}')
                border.set(qn('w:val'), 'single')
                border.set(qn('w:sz'), '6')
                border.set(qn('w:space'), '1')
                border.set(qn('w:color'), 'auto')
                pBdr.append(border)
            pPr.append(pBdr)
            paragraph.paragraph_format.left_indent = Inches(0.25)
            paragraph.paragraph_format.right_indent = Inches(0.25)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)

        elif matched_text.startswith('**') or matched_text.startswith('__'):
            clean_text = matched_text[2:-2]
            run = paragraph.add_run(clean_text)
            run.bold = True

        elif matched_text.startswith('<u>'):
            clean_text = re.sub(r'</?u>', '', matched_text)
            run = paragraph.add_run(clean_text)
            run.underline = True

        elif matched_text.startswith('==') and matched_text.endswith('=='):
            clean_text = matched_text[2:-2]
            run = paragraph.add_run(clean_text)
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW  # Set highlight color to yellow

        elif matched_text.startswith('*') or matched_text.startswith('_'):
            clean_text = matched_text[1:-1]
            run = paragraph.add_run(clean_text)
            run.italic = True

        # Plain tilde: only strikethrough.
        elif matched_text.startswith('~~'):
            clean_text = matched_text[2:-2]
            run = paragraph.add_run(clean_text)
            run.font.strike = True

        elif matched_text.startswith('`'):
            clean_text = matched_text[1:-1]
            run = paragraph.add_run(clean_text)
            run.font.name = 'Consolas'
            run.font.size = Pt(10)
            shading_elm = OxmlElement('w:shd')
            shading_elm.set(qn('w:fill'), 'E0E0E0')
            paragraph._p.get_or_add_pPr().append(shading_elm)

        # Image (plain)
        elif matched_text.startswith('!['):
            alt_text, url = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', matched_text).groups()
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    image_stream = BytesIO(response.content)
                    run = paragraph.add_run()
                    run.add_picture(image_stream, width=Inches(2))
            except Exception as e:
                run = paragraph.add_run(f"[Image not available: {alt_text}]")
                run.italic = True

        # Link (plain)
        elif matched_text.startswith('['):
            link_text, url = re.match(r'\[([^\]]+)\]\(([^)]+)\)', matched_text).groups()
            add_hyperlink(paragraph, link_text, url)

        else:
            paragraph.add_run(matched_text)
        last_index = end
    if last_index < len(text):
        paragraph.add_run(text[last_index:])

def add_hyperlink(paragraph, text, url, bold=False, italic=False):
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)
    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    rStyle = OxmlElement('w:rStyle')
    rStyle.set(qn('w:val'), 'Hyperlink')
    rPr.append(rStyle)
    color = OxmlElement('w:color')
    color.set(qn('w:val'), '0000FF')
    rPr.append(color)
    underline = OxmlElement('w:u')
    underline.set(qn('w:val'), 'single')
    rPr.append(underline)
    if bold:
        b_elem = OxmlElement('w:b')
        b_elem.set(qn('w:val'), 'true')
        rPr.append(b_elem)
    if italic:
        i_elem = OxmlElement('w:i')
        i_elem.set(qn('w:val'), 'true')
        rPr.append(i_elem)
    new_run.append(rPr)
    w_t = OxmlElement('w:t')
    w_t.text = text
    new_run.append(w_t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)

def set_heading_style(paragraph, level):
    sizes = {1: 20, 2: 18, 3: 16, 4: 14, 5: 12, 6: 11}
    font_size = sizes.get(level, 10)
    colors = {
        1: RGBColor(0, 0, 139),
        2: RGBColor(0, 0, 139),
        3: RGBColor(47, 47, 47),
        4: RGBColor(47, 47, 47),
        5: RGBColor(47, 47, 47),
        6: RGBColor(47, 47, 47)
    }
    paragraph.style = f'Heading {level}'
    for run in paragraph.runs:
        run.font.size = Pt(font_size)
        run.font.color.rgb = colors.get(level, RGBColor(0, 0, 0))
        run.font.name = 'Calibri'
        run.bold = True
    if level <= 2:
        pPr = paragraph._p.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single')
        bottom.set(qn('w:sz'), '8' if level == 1 else '4')
        bottom.set(qn('w:space'), '1')
        bottom.set(qn('w:color'), '000000')
        pBdr.append(bottom)
        pPr.append(pBdr)
    paragraph.paragraph_format.space_before = Pt(12)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.keep_with_next = True

def add_code_block(document, code_text, language):
    paragraph = document.add_paragraph()
    run = paragraph.add_run(code_text)
    run.font.name = 'Consolas'
    run.font.size = Pt(10)
    shading_elm = OxmlElement('w:shd')
    shading_elm.set(qn('w:fill'), 'E0E0E0')
    paragraph._p.get_or_add_pPr().append(shading_elm)
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    for border_type in ['top', 'bottom', 'left', 'right']:
        border = OxmlElement(f'w:{border_type}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '6')
        border.set(qn('w:space'), '1')
        border.set(qn('w:color'), 'auto')
        pBdr.append(border)
    pPr.append(pBdr)
    paragraph.paragraph_format.left_indent = Inches(0.25)
    paragraph.paragraph_format.right_indent = Inches(0.25)
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(6)

def add_bookmark(paragraph, bookmark_name, bookmark_id):
    bookmark_start = OxmlElement('w:bookmarkStart')
    bookmark_start.set(qn('w:id'), str(bookmark_id))
    bookmark_start.set(qn('w:name'), bookmark_name)
    bookmark_end = OxmlElement('w:bookmarkEnd')
    bookmark_end.set(qn('w:id'), str(bookmark_id))
    runs = paragraph.runs
    if runs:
        first_run = runs[0]
        first_run._r.insert(0, bookmark_start)
        last_run = runs[-1]
        last_run._r.append(bookmark_end)
    else:
        run = paragraph.add_run()
        run.text = ''
        run._r.insert(0, bookmark_start)
        run._r.append(bookmark_end)

def add_hyperlink(paragraph, text, url, bold=False, italic=False):
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)
    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    rStyle = OxmlElement('w:rStyle')
    rStyle.set(qn('w:val'), 'Hyperlink')
    rPr.append(rStyle)
    color = OxmlElement('w:color')
    color.set(qn('w:val'), '0000FF')
    rPr.append(color)
    underline = OxmlElement('w:u')
    underline.set(qn('w:val'), 'single')
    rPr.append(underline)
    if bold:
        b_elem = OxmlElement('w:b')
        b_elem.set(qn('w:val'), 'true')
        rPr.append(b_elem)
    if italic:
        i_elem = OxmlElement('w:i')
        i_elem.set(qn('w:val'), 'true')
        rPr.append(i_elem)
    new_run.append(rPr)
    w_t = OxmlElement('w:t')
    w_t.text = text
    new_run.append(w_t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)

def parse_table(lines, current_index):
    """
    Parse a markdown table and return the table data and the index after the table.
    """
    if current_index >= len(lines):
        return None, current_index

    # Check if we have a valid table header
    header_line = lines[current_index].strip()
    if not header_line.startswith('|'):
        return None, current_index

    # Extract headers
    headers = [cell.strip() for cell in header_line.strip('|').split('|')]
    current_index += 1

    # Check for separator line, but don't require it
    if current_index < len(lines):
        separator_line = lines[current_index].strip()
        if separator_line.startswith('|') and all('-' in cell for cell in separator_line.strip('|').split('|')):
            current_index += 1

    # Extract data rows
    data = []
    while current_index < len(lines):
        line = lines[current_index].strip()
        if not line.startswith('|'):
            break
        row = [cell.strip() for cell in line.strip('|').split('|')]
        if len(row) == len(headers):
            data.append(row)
        current_index += 1

    if not data:  # No data rows found
        return None, current_index

    return {'headers': headers, 'data': data}, current_index

def insert_table(document, table_data):
    """
    Add a table to the Word document.
    """
    if not table_data or 'headers' not in table_data or 'data' not in table_data:
        return

    # Create table
    table = document.add_table(rows=1, cols=len(table_data['headers']))
    table.style = 'Table Grid'

    # Add headers
    header_cells = table.rows[0].cells
    for i, header in enumerate(table_data['headers']):
        header_cells[i].text = ""
        paragraph = header_cells[i].paragraphs[0]
        parse_inline_formatting(paragraph, header)
        paragraph.runs[0].bold = True

    # Add data rows
    for row_data in table_data['data']:
        row_cells = table.add_row().cells
        for i, cell_data in enumerate(row_data):
            # Split content by <br> tags
            lines = cell_data.split('<br>')
            row_cells[i].text = ""  # Clear default paragraph
            
            # Process each line
            for line_idx, line in enumerate(lines):
                line = line.strip()
                if line_idx > 0:  # Add new paragraph for each line after the first
                    paragraph = row_cells[i].add_paragraph()
                else:
                    paragraph = row_cells[i].paragraphs[0]
                
                # Handle list items with proper indentation
                if line.strip().startswith(('-', '*', '+')):
                    paragraph.paragraph_format.left_indent = Inches(0.25)
                    parse_inline_formatting(paragraph, line)
                elif line.strip().startswith(tuple(f"{n}." for n in range(1, 10))):
                    paragraph.paragraph_format.left_indent = Inches(0.25)
                    parse_inline_formatting(paragraph, line)
                else:
                    parse_inline_formatting(paragraph, line)

    # Add space after table
    document.add_paragraph()

### END TABLE FUNCTIONS

### CHART FUNCTIONS

def process_chart_code(code_text):
    """
    Process chart code and return the image bytes.
    Args:
        code_text (str): The chart configuration code
    Returns:
        bytes: The chart image bytes
    """
    from quickchart import QuickChart
    import json
    import re

    try:
        logging.info("\n[DEBUG Chart] Processing chart code:")
        logging.info(f"Raw code text: {code_text}")
        
        # Pre-process the JSON string to handle escaped characters
        # Replace \$ with $ since $ doesn't need escaping in JSON
        code_text = re.sub(r'\\(\$)', r'\1', code_text)
        logging.info(f"Preprocessed code text: {code_text}")
        
        # Parse the chart configuration
        config = json.loads(code_text)
        logging.info(f"Parsed config: {json.dumps(config, indent=2)}")
        
        # Create QuickChart instance
        qc = QuickChart()
        qc.width = config.get('width', 500)
        qc.height = config.get('height', 300)
        qc.config = config.get('config', {})
        
        logging.info(f"QuickChart config - Width: {qc.width}, Height: {qc.height}")
        logging.info(f"Chart config: {json.dumps(qc.config, indent=2)}")
        
        # Get the chart image bytes
        image_bytes = qc.get_bytes()
        logging.info(f"Successfully generated chart image of size: {len(image_bytes)} bytes")
        return image_bytes
    except json.JSONDecodeError as je:
        logging.error(f"JSON parsing error: {je}")
        logging.error(f"Invalid JSON: {code_text}")
        return None
    except Exception as e:
        logging.error(f"Error processing chart code: {e}")
        logging.error(f"Stack trace:", exc_info=True)
        return None

def process_mermaid_diagram(mermaid_code):
    """
    Process Mermaid diagram code and return the image bytes.
    Args:
        mermaid_code (str): The Mermaid diagram code
    Returns:
        bytes: The diagram image bytes or None if processing fails
    """
    if not MERMAID_AVAILABLE:
        logging.warning("Mermaid package not available. Cannot render diagram.")
        return None
    
    try:
        logging.info("\n[DEBUG Mermaid] Processing Mermaid diagram:")
        logging.info(f"Raw code text: {mermaid_code}")
        
        # Try using the online Mermaid service as a fallback if local rendering fails
        try:
            # Create a Graph object with the Mermaid code
            diagram = Graph('mermaid-diagram', mermaid_code)
            
            # Create a Mermaid renderer
            renderer = md.Mermaid(diagram)
            
            # Get the image bytes - use to_png() with a temporary file
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
                
                if image_bytes and len(image_bytes) > 1000:  # Ensure we have a valid image (not just a few bytes)
                    logging.info(f"Successfully generated Mermaid diagram image of size: {len(image_bytes)} bytes")
                    return image_bytes
                else:
                    logging.warning("Local Mermaid rendering produced a small or empty image, trying online service...")
                    raise Exception("Invalid image size")
            except Exception as e:
                logging.error(f"Error generating Mermaid PNG locally: {e}")
                os.unlink(temp_path)  # Clean up even if there's an error
                raise  # Re-raise to try the online service
        except Exception as local_error:
            logging.warning(f"Local Mermaid rendering failed: {local_error}. Trying online service...")
            
            # Try using the online Mermaid service as a fallback
            try:
                # Encode the Mermaid code for the URL
                import urllib.parse
                encoded_diagram = urllib.parse.quote(mermaid_code)
                
                # Use the Mermaid Live Editor API to generate the image
                url = f"https://mermaid.ink/img/png/{encoded_diagram}"
                
                response = requests.get(url, timeout=10)
                if response.status_code == 200 and len(response.content) > 1000:
                    logging.info(f"Successfully generated Mermaid diagram using online service. Image size: {len(response.content)} bytes")
                    return response.content
                else:
                    logging.error(f"Failed to generate Mermaid diagram using online service. Status code: {response.status_code}")
                    return None
            except Exception as online_error:
                logging.error(f"Error using online Mermaid service: {online_error}")
                return None
    except Exception as e:
        logging.error(f"Error processing Mermaid diagram: {e}")
        logging.error(f"Stack trace:", exc_info=True)
        return None

def insert_chart_image(document, image_bytes):
    """
    Insert a chart image into the Word document.
    Args:
        document: The Word document
        image_bytes: The image bytes to insert
    Returns:
        paragraph: The paragraph containing the image
    """
    try:
        paragraph = document.add_paragraph()
        if image_bytes:
            # Save image bytes to a temporary file to ensure format is recognized
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_file.write(image_bytes)
                temp_path = tmp_file.name
            
            try:
                # Add picture from the temporary file instead of BytesIO
                paragraph.add_run().add_picture(temp_path, width=Inches(6))
                # Clean up the temporary file
                os.unlink(temp_path)
            except Exception as e:
                logging.error(f"Error adding picture from temp file: {e}")
                os.unlink(temp_path)  # Clean up even if there's an error
                raise
        return paragraph
    except Exception as e:
        logging.error(f"Error inserting chart image: {e}")
        return document.add_paragraph("[Error: Failed to insert chart]")

### END CHART FUNCTIONS

### LIST FUNCTIONS

def get_list_level(line):
    """
    Calculate the indentation level of a list item.
    Args:
        line (str): The line containing the list item
    Returns:
        int: The indentation level (0-based)
    """
    indent = 0
    for char in line:
        if char == ' ':
            indent += 1
        elif char == '\t':
            indent += 2
        else:
            break
    return indent // 2

def handle_list_item(document, line, list_level=0, list_counters=None):
    """
    Process a list item line and create a properly formatted paragraph.
    Args:
        document: The Word document
        line: The line containing the list item
        list_level: The indentation level of the list item
        list_counters: Dictionary tracking the current number for each list level
    """
    # Check for numbered list item (1., 2., etc.)
    numbered_match = re.match(r'^(\s*)(\d+\.)\s+(.*)$', line)
    if numbered_match:
        number, content = numbered_match.groups()[1:]
        
        # Create a regular paragraph instead of using List Number style
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Inches(0.25 * list_level)
        
        # If we're manually tracking list numbers, use the tracked number
        # Otherwise, use the number from the markdown
        if list_counters is not None:
            # If this is a new level, initialize the counter
            if list_level not in list_counters:
                list_counters[list_level] = 1
            
            # Add the number as text
            run = paragraph.add_run(f"{list_counters[list_level]}. ")
            
            # Increment the counter for this level
            list_counters[list_level] += 1
            
            # Reset all deeper level counters when we encounter a higher level item
            deeper_levels = [level for level in list_counters.keys() if level > list_level]
            for level in deeper_levels:
                list_counters[level] = 1
        else:
            # Just use the number from the markdown
            run = paragraph.add_run(number + " ")
        
        parse_inline_formatting(paragraph, content)
        return paragraph
    
    # Check for alphabetic subitem (a., b., etc.)
    alpha_match = re.match(r'^(>+)\s*([a-z]\.)\s+(.*)$', line)
    if alpha_match:
        quote_level = len(alpha_match.group(1))
        letter, content = alpha_match.groups()[1:]
        paragraph = document.add_paragraph()
        # Set indentation for subitems
        paragraph.paragraph_format.left_indent = Inches(0.25 * list_level + 0.25)
        # Add the letter as text
        run = paragraph.add_run(f"{letter} ")
        parse_inline_formatting(paragraph, content)
        return paragraph
    
    # Check for bullet list item (-, *, +)
    bullet_match = re.match(r'^(\s*)([-*+])\s+(.*)$', line)
    if bullet_match:
        content = bullet_match.groups()[2]
        paragraph = document.add_paragraph(style='List Bullet')
        paragraph.paragraph_format.left_indent = Inches(0.25 * list_level)
        parse_inline_formatting(paragraph, content)
        return paragraph
    
    # Default case - just a regular paragraph
    paragraph = document.add_paragraph()
    parse_inline_formatting(paragraph, line)
    return paragraph

### CONVERSION FUNCTION

def convert_markdown_to_docx(markdown_text, output_path=None, formatting_enabled=False):
    """
    Converts GitHub-Flavored Markdown (GFM) text to a Word document.
    If output_path is provided, saves to that location.
    Otherwise, opens a file dialog to choose the save location.
    
    Args:
        markdown_text (str): The markdown text to convert
        output_path (str, optional): Path where to save the Word document. If None, shows file dialog.
        formatting_enabled (bool, optional): Whether to apply markdown formatting. If False, saves as plain text.
    """
    logging.info("\n[DEBUG ExportWord] Starting conversion:")
    logging.info("-" * 80)
    logging.info(f"Formatting enabled: {formatting_enabled}")
    logging.info(f"Output path: {output_path}")
    logging.info(f"Content type: {type(markdown_text)}")
    logging.info(f"Content length: {len(markdown_text)}")
    logging.info("First 500 chars of content:")
    logging.info(markdown_text[:500])
    logging.info("-" * 80)

    file_path = output_path
    if file_path is None:
        root = Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Documents", "*.docx")],
            title="Save as"
        )
        if not file_path:
            messagebox.showwarning("No Save Location", "No file was selected. Operation cancelled.")
            return
    try:
        document = Document()
        style = document.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(10)

        in_code_block = False
        code_block_language = ''
        code_block_content = []
        
        # Dictionary to track list numbering for each level
        list_counters = {}

        if not formatting_enabled:
            logging.info("[DEBUG ExportWord] Formatting disabled, adding text as-is")
            paragraph = document.add_paragraph()
            paragraph.add_run(markdown_text)
        else:
            logging.info("[DEBUG ExportWord] Formatting enabled, processing markdown")
            lines = markdown_text.split('\n')
            logging.info(f"[DEBUG ExportWord] Number of lines to process: {len(lines)}")
            bookmark_id = 0
            index = 0
            while index < len(lines):
                line = lines[index]
                stripped_line = line.strip()
                if in_code_block:
                    if stripped_line.startswith('```'):
                        code_text = '\n'.join(code_block_content)
                        logging.info(f"[DEBUG ExportWord] Processing code block with language: '{code_block_language}'")
                        if code_block_language == 'chart':
                            logging.info("[DEBUG ExportWord] Processing chart code block")
                            logging.info(f"Chart code content:\n{code_text}")
                            image_bytes = process_chart_code(code_text)
                            if image_bytes:
                                logging.info("[DEBUG ExportWord] Successfully generated chart image")
                                insert_chart_image(document, image_bytes)
                            else:
                                logging.error("[DEBUG ExportWord] Failed to generate chart image, falling back to code block")
                                add_code_block(document, code_text, code_block_language)
                        elif code_block_language == 'mermaid':
                            logging.info("[DEBUG ExportWord] Processing mermaid code block")
                            logging.info(f"Mermaid code content:\n{code_text}")
                            image_bytes = process_mermaid_diagram(code_text)
                            if image_bytes:
                                logging.info("[DEBUG ExportWord] Successfully generated mermaid diagram image")
                                insert_chart_image(document, image_bytes)
                            else:
                                logging.error("[DEBUG ExportWord] Failed to generate mermaid diagram, falling back to code block")
                                add_code_block(document, code_text, code_block_language)
                        else:
                            add_code_block(document, code_text, code_block_language)
                        in_code_block = False
                        code_block_language = ''
                        code_block_content = []
                    else:
                        code_block_content.append(line)
                    index += 1
                    continue
                if stripped_line.startswith('```'):
                    in_code_block = True
                    code_block_language = stripped_line[3:].strip().lower()
                    logging.info(f"[DEBUG ExportWord] Code block started with language: '{code_block_language}'")
                    index += 1
                    continue
                # Check for page break tag
                if stripped_line == '<pbreak>':
                    logging.info("[DEBUG ExportWord] Adding page break")
                    add_page_break(document)
                    index += 1
                    continue
                if re.match(r'^(\*\*\*|---|___)$', stripped_line):
                    paragraph = document.add_paragraph()
                    run = paragraph.add_run()
                    pPr = paragraph._p.get_or_add_pPr()
                    pBdr = OxmlElement('w:pBdr')
                    bottom = OxmlElement('w:bottom')
                    bottom.set(qn('w:val'), 'single')
                    bottom.set(qn('w:sz'), '6')
                    bottom.set(qn('w:space'), '1')
                    bottom.set(qn('w:color'), 'auto')
                    pBdr.append(bottom)
                    pPr.append(pBdr)
                    index += 1
                    continue
                if stripped_line.startswith('|') and stripped_line.endswith('|'):
                    parsed = parse_table(lines, index)
                    if parsed:
                        table_data, new_index = parsed
                        if table_data:
                            insert_table(document, table_data)
                            index = new_index
                            continue
                if stripped_line.startswith('>'):
                    quote_match = re.match(r'^(>+)\s*(.*)$', stripped_line)
                    if quote_match:
                        quote_level = len(quote_match.group(1))
                        quote_text = quote_match.group(2).strip()
                        paragraph = document.add_paragraph()
                        paragraph.paragraph_format.left_indent = Inches(0.25 * quote_level)
                        paragraph.paragraph_format.space_before = Pt(6)
                        paragraph.paragraph_format.space_after = Pt(6)
                        pPr = paragraph._p.get_or_add_pPr()
                        pBdr = OxmlElement('w:pBdr')
                        for i in range(quote_level):
                            left = OxmlElement('w:left')
                            left.set(qn('w:val'), 'single')
                            left.set(qn('w:sz'), str(6 + (i * 2)))
                            left.set(qn('w:space'), str(20 * i))
                            left.set(qn('w:color'), '666666')
                            pBdr.append(left)
                        pPr.append(pBdr)
                        for run in paragraph.runs:
                            run.italic = True
                            run.font.color.rgb = RGBColor(85, 85, 85)
                        parse_inline_formatting(paragraph, quote_text)
                    index += 1
                    continue
                if not stripped_line:
                    document.add_paragraph()
                    # Reset list counters when we encounter an empty line
                    list_counters = {}
                    index += 1
                    continue
                heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
                if heading_match:
                    level = len(heading_match.group(1))
                    heading_text = heading_match.group(2).strip()
                    paragraph = document.add_paragraph()
                    paragraph.style = f'Heading {level}'
                    set_heading_style(paragraph, level)
                    parse_inline_formatting(paragraph, heading_text)
                    anchor_name = generate_anchor_name(heading_text)
                    bookmark_id += 1
                    add_bookmark(paragraph, anchor_name, bookmark_id)
                    # Reset list counters when we encounter a heading
                    list_counters = {}
                    index += 1
                    continue
                list_match = re.match(r'^(\s*)([-*+]|(\d+\.))\s+(.*)', line)
                if list_match:
                    indent = get_list_level(line)
                    handle_list_item(document, line, indent, list_counters)
                    index += 1
                    continue
                paragraph = document.add_paragraph()
                parse_inline_formatting(paragraph, stripped_line)
                # Reset list counters when we encounter a regular paragraph
                list_counters = {}
                index += 1
        if in_code_block and code_block_content:
            code_text = '\n'.join(code_block_content)
            if code_block_language == 'chart':
                image_bytes = process_chart_code(code_text)
                insert_chart_image(document, image_bytes)
            elif code_block_language == 'mermaid':
                image_bytes = process_mermaid_diagram(code_text)
                insert_chart_image(document, image_bytes)
            else:
                add_code_block(document, code_text, code_block_language)

        document.save(file_path)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        messagebox.showerror("Error", f"An error occurred: {e}")

def generate_anchor_name(heading_text):
    anchor = heading_text.lower()
    anchor = re.sub(r'[^a-z0-9\s\-]', '', anchor)
    anchor = re.sub(r'\s+', '-', anchor)
    return anchor

def add_page_break(document):
    """
    Add a page break to the Word document.
    """
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    run.add_break(WD_BREAK.PAGE)

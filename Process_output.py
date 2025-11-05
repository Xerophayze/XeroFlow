"""
Process_output.py

Extracts Excel code blocks from API markdown output, generates .xlsx files using
ExportExcel.convert_markdown_to_excel, removes those blocks from the markdown,
and returns the filtered markdown plus the list of generated file paths.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from ExportExcel import convert_markdown_to_excel


EXCEL_FENCE_PATTERN = re.compile(
    r"^```[ \t]*excel[^\n]*\n"      # opening fence with language tag 'excel'
    r"(.*?)"                           # block content (non-greedy)
    r"^```[ \t]*$",                    # closing fence on its own line
    flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def process_api_output(
    markdown_text: str,
    output_dir: str,
    base_name: str,
    *,
    insert_placeholders: bool = False,
) -> Tuple[str, List[str]]:
    """Process API markdown output to extract Excel code blocks.

    - Finds fenced blocks that start with ```excel (case-insensitive)
    - Writes each block to an .xlsx using ExportExcel.convert_markdown_to_excel
    - Removes those blocks from the markdown (optionally inserts placeholders)

    Args:
        markdown_text: Full API response markdown text.
        output_dir: Directory where generated .xlsx files should be saved.
        base_name: Base name used for output file naming.
        insert_placeholders: If True, insert a line noting generated Excel file
            where the block was removed.

    Returns:
        (filtered_markdown, created_excel_paths)
    """
    if not markdown_text:
        return markdown_text, []

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    created: List[str] = []
    parts: List[str] = []
    last_end = 0

    for idx, match in enumerate(EXCEL_FENCE_PATTERN.finditer(markdown_text), start=1):
        # Append text before this match
        parts.append(markdown_text[last_end:match.start()])

        block_content = match.group(1).strip("\n\r ")
        # If the block contains any leading non-table lines (e.g., a stray label like
        # "Excel" or a description), remove them so the first table starts at the top.
        # Otherwise, tables would start on row 2 in the workbook and formulas like
        # "=B2*C2" would end up referencing the header/previous row (off-by-one).
        lines = block_content.splitlines()
        while lines and not lines[0].lstrip().startswith('|'):
            lines.pop(0)
        block_content = "\n".join(lines).strip()
        # Build output path
        xlsx_name = f"{base_name}_excel_{idx}.xlsx"
        xlsx_path = out_dir / xlsx_name

        try:
            # Generate the Excel file from the code block content
            convert_markdown_to_excel(block_content, str(xlsx_path), formatting_enabled=True)
            created.append(str(xlsx_path))
            if insert_placeholders:
                parts.append(f"Excel file generated: {xlsx_name}\n")
        except Exception as e:
            # If Excel generation fails, keep the original block in place for visibility
            # and continue processing the rest.
            parts.append(markdown_text[match.start():match.end()])

        last_end = match.end()

    # Append any remaining text after the last match
    parts.append(markdown_text[last_end:])

    filtered_markdown = "".join(parts)
    return filtered_markdown, created

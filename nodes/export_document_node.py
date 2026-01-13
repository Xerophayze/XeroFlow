# nodes/export_document_node.py
"""
Export Document Node
====================

This node exports input text to either a Word (.docx) or Excel (.xlsx) document.
It uses the existing ExportWord and ExportExcel modules for the actual conversion.

Features:
- Export to Word or Excel based on node configuration
- Optional output folder setting (browse or type path)
- If no output folder specified, prompts user with file dialog on execution
- Supports markdown formatting in the input text
"""

import os
from tkinter import filedialog, Tk, messagebox
from .base_node import BaseNode
from node_registry import register_node


@register_node('ExportDocumentNode')
class ExportDocumentNode(BaseNode):
    """Node that exports input text to Word or Excel documents."""
    
    def define_inputs(self):
        return ['input']  # Single input for the text to export
    
    def define_outputs(self):
        return ['output']  # Output the file path or status message
    
    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'Export Document'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Exports input text to Word or Excel document.'
            },
            'export_format': {
                'type': 'dropdown',
                'label': 'Export Format',
                'options': ['Word (.docx)', 'Excel (.xlsx)'],
                'default': 'Word (.docx)'
            },
            'output_folder': {
                'type': 'folder',
                'label': 'Output Folder',
                'default': ''
            },
            'filename': {
                'type': 'text',
                'label': 'Filename (without extension)',
                'default': 'exported_document'
            },
            'formatting_enabled': {
                'type': 'boolean',
                'label': 'Enable Markdown Formatting',
                'default': True
            },
            'auto_open': {
                'type': 'boolean',
                'label': 'Open File After Export',
                'default': False
            },
            'is_start_node': {
                'type': 'boolean',
                'label': 'Start Node',
                'default': False
            },
            'is_end_node': {
                'type': 'boolean',
                'label': 'End Node',
                'default': True  # Typically an end node
            }
        })
        return props
    
    def process(self, inputs):
        """
        Process the input text and export it to the specified document format.
        """
        # Get the input text
        input_text = inputs.get('input', '')
        if isinstance(input_text, list):
            input_text = '\n\n'.join(str(item) for item in input_text)
        input_text = str(input_text).strip()
        
        if not input_text:
            print("[ExportDocumentNode] No input text received.")
            return {'output': "Error: No input text to export."}
        
        print(f"[ExportDocumentNode] Received input text of length: {len(input_text)}")
        
        # Get properties
        export_format = self.properties.get('export_format', {}).get('default', 'Word (.docx)')
        output_folder = self.properties.get('output_folder', {}).get('default', '').strip()
        filename = self.properties.get('filename', {}).get('default', 'exported_document').strip()
        formatting_enabled = self.properties.get('formatting_enabled', {}).get('default', True)
        auto_open = self.properties.get('auto_open', {}).get('default', False)
        
        # Determine file extension
        if 'Word' in export_format:
            extension = '.docx'
            export_type = 'word'
        else:
            extension = '.xlsx'
            export_type = 'excel'
        
        # Sanitize filename
        filename = self._sanitize_filename(filename)
        if not filename:
            filename = 'exported_document'
        
        # Determine output path
        output_path = None
        
        if output_folder and os.path.isdir(output_folder):
            # Use the specified output folder
            output_path = os.path.join(output_folder, f"{filename}{extension}")
            print(f"[ExportDocumentNode] Using configured output path: {output_path}")
        else:
            # No valid output folder - show file dialog
            print("[ExportDocumentNode] No output folder specified, showing file dialog...")
            output_path = self._show_save_dialog(filename, extension, export_type)
            
            if not output_path:
                print("[ExportDocumentNode] User cancelled file save dialog.")
                return {'output': "Export cancelled: No file location selected."}
        
        # Perform the export
        try:
            if export_type == 'word':
                result = self._export_to_word(input_text, output_path, formatting_enabled)
            else:
                result = self._export_to_excel(input_text, output_path, formatting_enabled)
            
            if result['success']:
                print(f"[ExportDocumentNode] Successfully exported to: {output_path}")
                
                # Auto-open if enabled
                if auto_open:
                    self._open_file(output_path)
                
                return {'output': f"Successfully exported to: {output_path}"}
            else:
                print(f"[ExportDocumentNode] Export failed: {result['error']}")
                return {'output': f"Export failed: {result['error']}"}
                
        except Exception as e:
            error_msg = f"Export error: {str(e)}"
            print(f"[ExportDocumentNode] {error_msg}")
            return {'output': error_msg}
    
    def _sanitize_filename(self, filename):
        """Remove invalid characters from filename."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
    
    def _show_save_dialog(self, default_filename, extension, export_type):
        """Show a file save dialog and return the selected path."""
        try:
            root = Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            if export_type == 'word':
                filetypes = [("Word Document", "*.docx"), ("All Files", "*.*")]
                title = "Save Word Document"
            else:
                filetypes = [("Excel Workbook", "*.xlsx"), ("All Files", "*.*")]
                title = "Save Excel Workbook"
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=extension,
                filetypes=filetypes,
                title=title,
                initialfile=f"{default_filename}{extension}"
            )
            
            root.destroy()
            return file_path if file_path else None
            
        except Exception as e:
            print(f"[ExportDocumentNode] Error showing save dialog: {e}")
            return None
    
    def _export_to_word(self, text, output_path, formatting_enabled):
        """Export text to Word document using ExportWord module."""
        try:
            # Import the ExportWord module
            import sys
            import os
            
            # Add parent directory to path if needed
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from ExportWord import convert_markdown_to_docx
            
            # Call the conversion function
            convert_markdown_to_docx(text, output_path=output_path, formatting_enabled=formatting_enabled)
            
            # Check if file was created
            if os.path.exists(output_path):
                return {'success': True, 'path': output_path}
            else:
                return {'success': False, 'error': 'File was not created'}
                
        except ImportError as e:
            return {'success': False, 'error': f'ExportWord module not available: {e}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _export_to_excel(self, text, output_path, formatting_enabled):
        """Export text to Excel document using ExportExcel module."""
        try:
            # Import the ExportExcel module
            import sys
            import os
            
            # Add parent directory to path if needed
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from ExportExcel import convert_markdown_to_excel
            
            # Call the conversion function
            convert_markdown_to_excel(text, output_path=output_path, formatting_enabled=formatting_enabled)
            
            # Check if file was created
            if os.path.exists(output_path):
                return {'success': True, 'path': output_path}
            else:
                return {'success': False, 'error': 'File was not created'}
                
        except ImportError as e:
            return {'success': False, 'error': f'ExportExcel module not available: {e}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _open_file(self, file_path):
        """Open the exported file with the default application."""
        try:
            import subprocess
            import platform
            
            system = platform.system()
            if system == 'Windows':
                os.startfile(file_path)
            elif system == 'Darwin':  # macOS
                subprocess.call(['open', file_path])
            else:  # Linux
                subprocess.call(['xdg-open', file_path])
                
            print(f"[ExportDocumentNode] Opened file: {file_path}")
        except Exception as e:
            print(f"[ExportDocumentNode] Could not open file: {e}")
    
    def requires_api_call(self):
        """This node does not require an API call."""
        return False

# nodes/master_agent_node.py
import json
import os
import re
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import ttk, scrolledtext, END
from threading import Thread
from datetime import datetime, timedelta

from .Assistant_node import AssistantNode
from .team_lead_node import TeamLeadNode
from .agent_comms_channel_node import create_channel, get_channel
from src.workflows.node_registry import register_node, NODE_REGISTRY, get_node_catalog, register_running_instance, unregister_running_instance
from src.export.formatting import apply_formatting
from src.export.word import convert_markdown_to_docx
from src.export.excel import convert_markdown_to_excel
from src.database.db_tools import DatabaseManager


def _safe_db_name(workflow_name: str) -> str:
    if not workflow_name:
        return 'workflow'
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in workflow_name)
    return cleaned.strip('_') or 'workflow'


@register_node('MasterAgentNode')
class MasterAgentNode(AssistantNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chat_history = []
        self.chat_history_box = None
        self.chat_input_entry = None
        self.pending_delegation = None
        self.pending_export_format = None
        self.pending_clarification = None
        self.pending_request = None
        self.channel_id = None
        self.channel_name = 'team'
        self._whatsapp_response_lock = __import__('threading').Lock()
        self._pending_whatsapp_response = None
        # Recent email context for WhatsApp follow-up detection
        from collections import deque
        self._recent_email_context: deque = deque(maxlen=5)
        # Pending email draft awaiting user confirmation before sending
        self._pending_email_draft: dict | None = None
        # Email context hint injected by _check_email_followup for the AI
        self._email_context_hint: str = ""
        # Pending ambiguous intents awaiting user clarification
        self._pending_ambiguous_intents: dict | None = None
        # Personality matrix
        self._personality = self._load_personality()
        # Action Permission Registry — controls what the AI can do without asking
        self._permissions = self._load_permissions()

    def define_inputs(self):
        base = super().define_inputs()
        if 'whatsapp_input' not in base:
            base.append('whatsapp_input')
        return base

    def define_outputs(self):
        return ['output', 'whatsapp_response']

    def define_properties(self):
        props = super().define_properties()
        props['node_name']['default'] = 'MasterAgentNode'
        props['description']['default'] = (
            'Master control agent with split-pane chat. Handles clarification, delegation, '
            'and optional exports. Accepts tool_calls in delegation JSON: '
            '{"type": "NodeType", "input": "...", "properties": {...}}. '
            'Use markdown in responses for rich formatting and include export_format '
            '(word/excel/text) when requested.'
        )
        props.setdefault('channel_name', {
            'type': 'text',
            'label': 'Comms Channel Name',
            'default': 'team'
        })
        return props

    def submit_project(self):
        """Override: route project submission through the MCA chat pipeline."""
        try:
            # Get instructions
            instructions = ''
            if hasattr(self, 'instructions_text') and self.instructions_text:
                instructions = self.instructions_text.get('1.0', tk.END).strip()

            # Get files
            files = list(self.project_files) if hasattr(self, 'project_files') else []

            if not instructions and not files:
                self.update_log("Please enter instructions or add files before submitting.")
                return

            # Get project name
            project_name = ''
            if hasattr(self, 'project_name_var') and self.project_name_var:
                project_name = self.project_name_var.get().strip()

            # Build a chat message from the instructions (or a default)
            chat_message = instructions or "Please process the submitted files."

            # Show the submission in the chat
            self._append_chat_message("User", chat_message)

            # Clear the form
            if hasattr(self, 'instructions_text') and self.instructions_text:
                self.instructions_text.delete('1.0', tk.END)
            if hasattr(self, 'project_name_var') and self.project_name_var:
                self.project_name_var.set('')
            if files:
                self.clear_files()

            if files:
                # Route through project-via-chat (file extraction + MCA processing)
                thread = Thread(
                    target=self._submit_project_via_chat,
                    args=(chat_message, files, '', project_name),
                    daemon=True,
                )
                thread.start()
            else:
                # No files — just send the instructions as a regular chat message
                thread = Thread(target=self._chat_api_call, args=(chat_message,), daemon=True)
                thread.start()

            self.update_log(f"Project submitted via chat. Files: {len(files)}")

        except Exception as e:
            self.update_log(f"Error submitting project: {e}")
            import traceback
            traceback.print_exc()

    def create_monitor_window(self):
        if not hasattr(self, 'monitor_window') or not self.monitor_window:
            self.monitor_window = tk.Toplevel()
            register_running_instance('MasterAgentNode', self)

            window_title = "Master Control Agent"
            if hasattr(self, 'inputs') and isinstance(self.inputs, dict):
                if 'workflow_id' in self.inputs:
                    from src.workflows.workflow_manager import workflow_manager
                    workflow_id = self.inputs.get('workflow_id')
                    workflow = workflow_manager.get_workflow(workflow_id)
                    if workflow and workflow.workflow_name:
                        window_title = f"Master Control Agent - {workflow.workflow_name}"
                elif 'workflow_name' in self.inputs:
                    workflow_name = self.inputs.get('workflow_name')
                    if workflow_name:
                        window_title = f"Master Control Agent - {workflow_name}"

            self.monitor_window.title(window_title)
            self.monitor_window.protocol("WM_DELETE_WINDOW", self.stop_monitoring)
            self.monitor_window.geometry("1100x750")
            self.monitor_window.minsize(800, 650)

            self.monitor_window.grid_rowconfigure(0, weight=1)
            self.monitor_window.grid_columnconfigure(0, weight=1)

            notebook = ttk.Notebook(self.monitor_window)
            notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

            submit_tab = ttk.Frame(notebook)
            output_tab = ttk.Frame(notebook)
            log_tab = ttk.Frame(notebook)

            notebook.add(submit_tab, text="Submit Project")
            notebook.add(output_tab, text="Output Files")
            notebook.add(log_tab, text="Processing Log")

            submit_tab.grid_rowconfigure(0, weight=1)
            submit_tab.grid_columnconfigure(0, weight=1)

            output_tab.grid_rowconfigure(0, weight=0)
            output_tab.grid_rowconfigure(1, weight=1)
            output_tab.grid_columnconfigure(0, weight=1)

            log_tab.grid_rowconfigure(0, weight=1)
            log_tab.grid_columnconfigure(0, weight=1)

            submit_paned = ttk.Panedwindow(submit_tab, orient=tk.HORIZONTAL)
            submit_paned.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

            submit_left = ttk.Frame(submit_paned)
            submit_right = ttk.Frame(submit_paned)
            submit_paned.add(submit_left, weight=3)
            submit_paned.add(submit_right, weight=2)

            submit_left.grid_rowconfigure(0, weight=0)
            submit_left.grid_rowconfigure(1, weight=0)
            submit_left.grid_rowconfigure(2, weight=0)
            submit_left.grid_rowconfigure(3, weight=2)
            submit_left.grid_rowconfigure(4, weight=0)
            submit_left.grid_rowconfigure(5, weight=1)
            submit_left.grid_rowconfigure(6, weight=0)
            submit_left.grid_columnconfigure(0, weight=1)

            project_name_label = ttk.Label(submit_left, text="Project Name (optional):")
            project_name_label.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))

            self.project_name_var = tk.StringVar()
            self.project_name_entry = ttk.Entry(submit_left, textvariable=self.project_name_var, width=80)
            self.project_name_entry.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

            instructions_label = ttk.Label(submit_left, text="Enter your instructions:")
            instructions_label.grid(row=2, column=0, sticky="w", padx=5, pady=(5, 0))

            self.instructions_text = scrolledtext.ScrolledText(submit_left, height=10, width=80, wrap=tk.WORD)
            self.instructions_text.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)

            files_frame = ttk.Frame(submit_left)
            files_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=(10, 0))

            files_label = ttk.Label(files_frame, text="Add files to your project:")
            files_label.pack(side=tk.LEFT, anchor="w")

            self.project_files = []

            files_frame = ttk.Frame(submit_left)
            files_frame.grid(row=5, column=0, sticky="nsew", padx=5, pady=5)

            self.files_listbox = tk.Listbox(files_frame, height=6, width=80)
            self.files_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            files_scrollbar = ttk.Scrollbar(files_frame, command=self.files_listbox.yview)
            files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.files_listbox.config(yscrollcommand=files_scrollbar.set)

            buttons_frame = ttk.Frame(submit_left)
            buttons_frame.grid(row=6, column=0, sticky="ew", padx=5, pady=10)

            add_file_button = ttk.Button(buttons_frame, text="Add Files", command=self.add_files)
            add_file_button.pack(side=tk.LEFT, padx=5)

            remove_file_button = ttk.Button(buttons_frame, text="Remove Selected", command=self.remove_selected_file)
            remove_file_button.pack(side=tk.LEFT, padx=5)

            clear_files_button = ttk.Button(buttons_frame, text="Clear All Files", command=self.clear_files)
            clear_files_button.pack(side=tk.LEFT, padx=5)

            ttk.Separator(buttons_frame, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10, pady=5)

            submit_button = ttk.Button(buttons_frame, text="Submit Project", command=self.submit_project)
            submit_button.pack(side=tk.LEFT, padx=5)

            stop_button = ttk.Button(buttons_frame, text="Stop Assistant", command=self.stop_monitoring)
            stop_button.pack(side=tk.LEFT, padx=5)

            ttk.Separator(buttons_frame, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10, pady=5)

            personality_button = ttk.Button(
                buttons_frame, text="Personality Settings",
                command=self._open_personality_window
            )
            personality_button.pack(side=tk.LEFT, padx=5)

            # Enable drag/drop in the files area and instructions box.
            self.setup_drag_and_drop(self.files_listbox)
            self.setup_drag_and_drop(self.instructions_text)

            submit_right.grid_rowconfigure(1, weight=1)
            submit_right.grid_columnconfigure(0, weight=1)

            chat_label = ttk.Label(submit_right, text="Master Chat")
            chat_label.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))

            self.chat_history_box = scrolledtext.ScrolledText(
                submit_right, height=20, width=40, wrap=tk.WORD, state=tk.DISABLED
            )
            self.chat_history_box.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
            self._configure_chat_tags()

            chat_input_frame = ttk.Frame(submit_right)
            chat_input_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 5))
            chat_input_frame.grid_columnconfigure(0, weight=1)

            self.chat_input_entry = ttk.Entry(chat_input_frame)
            self.chat_input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
            self.chat_input_entry.bind("<Return>", self._on_chat_enter)

            chat_send_button = ttk.Button(chat_input_frame, text="Send", command=self.handle_chat_send)
            chat_send_button.grid(row=0, column=1, sticky="e")

            path_frame = ttk.Frame(output_tab)
            path_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

            path_label = ttk.Label(path_frame, text="Output folder:")
            path_label.pack(side=tk.LEFT, padx=(0, 5))

            self.output_path_var = tk.StringVar()
            self.output_path_var.set(self.properties.get('outbox_folder', {}).get('default', 'Not set'))

            output_path_entry = ttk.Entry(path_frame, textvariable=self.output_path_var, width=50)
            output_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

            browse_button = ttk.Button(path_frame, text="Browse", command=self.browse_output_folder)
            browse_button.pack(side=tk.LEFT, padx=(0, 5))

            refresh_button = ttk.Button(path_frame, text="Refresh", command=self.refresh_file_browser)
            refresh_button.pack(side=tk.LEFT)

            browser_frame = ttk.Frame(output_tab)
            browser_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

            self.file_tree = ttk.Treeview(browser_frame, columns=("size", "modified"), selectmode="browse")
            self.file_tree.heading("#0", text="Name")
            self.file_tree.heading("size", text="Size")
            self.file_tree.heading("modified", text="Modified")

            self.file_tree.column("#0", width=300, minwidth=200)
            self.file_tree.column("size", width=100, minwidth=80, anchor=tk.E)
            self.file_tree.column("modified", width=150, minwidth=120)

            tree_yscroll = ttk.Scrollbar(browser_frame, orient="vertical", command=self.file_tree.yview)
            tree_xscroll = ttk.Scrollbar(browser_frame, orient="horizontal", command=self.file_tree.xview)
            self.file_tree.configure(yscrollcommand=tree_yscroll.set, xscrollcommand=tree_xscroll.set)

            self.file_tree.grid(row=0, column=0, sticky="nsew")
            tree_yscroll.grid(row=0, column=1, sticky="ns")
            tree_xscroll.grid(row=1, column=0, sticky="ew")

            browser_frame.grid_rowconfigure(0, weight=1)
            browser_frame.grid_columnconfigure(0, weight=1)

            self.file_context_menu = tk.Menu(self.file_tree, tearoff=0)
            self.file_context_menu.add_command(label="Open", command=self.open_selected_file)
            self.file_context_menu.add_command(label="Open Folder", command=self.open_containing_folder)
            self.file_context_menu.add_separator()
            self.file_context_menu.add_command(label="Copy Path", command=self.copy_file_path)

            self.file_tree.bind("<Double-1>", self.on_file_double_click)
            self.file_tree.bind("<Button-3>", self.on_file_right_click)

            action_frame = ttk.Frame(output_tab)
            action_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)

            open_button = ttk.Button(action_frame, text="Open Selected", command=self.open_selected_file)
            open_button.pack(side=tk.LEFT, padx=5)

            open_folder_button = ttk.Button(
                action_frame, text="Open Containing Folder", command=self.open_containing_folder
            )
            open_folder_button.pack(side=tk.LEFT, padx=5)

            self.output_text = scrolledtext.ScrolledText(log_tab, height=20, width=80, wrap=tk.WORD)
            self.output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

            log_buttons_frame = ttk.Frame(log_tab)
            log_buttons_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

            clear_log_button = ttk.Button(log_buttons_frame, text="Clear Log", command=self.clear_log)
            clear_log_button.pack(side=tk.LEFT, padx=5)

            self.temp_dir = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_projects"))
            self.temp_dir.mkdir(exist_ok=True)

            # Track recent WhatsApp file attachments so follow-up messages
            # can reference previously-sent documents without re-attaching.
            # Key = sender identifier, Value = list of {"path": str, "name": str, "content": str}
            self._wa_recent_files: dict[str, list[dict]] = {}

            self.update_log("Master Control Agent interface initialized and ready.")
            self.update_log(f"Monitoring inbox folder: {self.properties.get('inbox_folder', {}).get('default', 'Not set')}")
            self.update_log(f"Output folder: {self.properties.get('outbox_folder', {}).get('default', 'Not set')}")
            self.update_log("Use the 'Submit Project' tab to create a new project.")

            self.refresh_file_browser()

    def stop_monitoring(self):
        """Override to unregister from the running instances registry."""
        unregister_running_instance('MasterAgentNode')
        super().stop_monitoring()

    def _on_chat_enter(self, event):
        self.handle_chat_send()
        return "break"

    def handle_chat_send(self):
        if not self.chat_input_entry:
            return
        message = self.chat_input_entry.get().strip()
        if not message:
            return
        self.chat_input_entry.delete(0, tk.END)
        self._append_chat_message("User", message)
        if self.pending_clarification:
            if self._handle_clarification_response(message):
                return
        if self.pending_delegation:
            if self._handle_export_clarification(message):
                return
        # If files are in the file list, treat this as a project submission via chat
        if hasattr(self, 'project_files') and self.project_files:
            # Also grab any instructions text content
            instructions = ''
            if hasattr(self, 'instructions_text') and self.instructions_text:
                instructions = self.instructions_text.get('1.0', tk.END).strip()
            files = list(self.project_files)  # snapshot
            project_name = ''
            if hasattr(self, 'project_name_var') and self.project_name_var:
                project_name = self.project_name_var.get().strip()
            # Clear the form
            if hasattr(self, 'instructions_text') and self.instructions_text:
                self.instructions_text.delete('1.0', tk.END)
            if hasattr(self, 'project_name_var') and self.project_name_var:
                self.project_name_var.set('')
            self.clear_files()
            thread = Thread(
                target=self._submit_project_via_chat,
                args=(message, files, instructions, project_name),
                daemon=True,
            )
            thread.start()
            return
        simple_response = self._handle_simple_local_request(message)
        if simple_response:
            self._append_chat_message("Assistant", simple_response)
            return
        # Check if user is asking to export existing chat data as a document
        if self._handle_export_from_history(message):
            return
        thread = Thread(target=self._chat_api_call, args=(message,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Project-via-chat: extract files, build combined request, send to MCA
    # ------------------------------------------------------------------

    def _submit_project_via_chat(self, chat_message: str, files: list,
                                  instructions: str, project_name: str):
        """Background thread: extract file content, build combined request, process via MCA."""
        import uuid
        try:
            # List the submitted files in the chat window
            file_names = [Path(f).name for f in files]
            file_list_text = "\n".join(f"  - {name}" for name in file_names)
            self._append_chat_message(
                "System",
                f"Processing project with {len(files)} file(s):\n{file_list_text}"
            )
            self.update_log(f"[Project] Starting file extraction for {len(files)} file(s)")
            print(f"[MasterAgentNode] Starting file extraction for {len(files)} file(s)")

            # Create a temp directory for extraction work
            temp_dir = self.temp_dir / f"project_{uuid.uuid4().hex[:8]}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Extract text content from each file
            file_contents = []
            for file_path_str in files:
                file_path = Path(file_path_str)
                if not file_path.exists():
                    self.update_log(f"[Project] File not found, skipping: {file_path.name}")
                    continue
                self.update_log(f"[Project] Extracting content from: {file_path.name}")
                print(f"[MasterAgentNode] Extracting content from: {file_path.name}")
                try:
                    content = self._extract_file_content(file_path, temp_dir)
                    if content and content.strip():
                        file_contents.append(f"=== Content from {file_path.name} ===\n{content}")
                        self.update_log(f"[Project] Extracted {len(content)} chars from {file_path.name}")
                        print(f"[MasterAgentNode] Extracted {len(content)} chars from {file_path.name}")
                except Exception as exc:
                    self.update_log(f"[Project] Error extracting {file_path.name}: {exc}")
                    print(f"[MasterAgentNode] Error extracting {file_path.name}: {exc}")

            # Clean up temp directory
            try:
                import shutil
                shutil.rmtree(str(temp_dir), ignore_errors=True)
            except Exception:
                pass

            # Store extracted file content in the RAG database for future referencing
            if file_contents:
                try:
                    manager, db_name = self._get_db_manager()
                    for i, file_content_block in enumerate(file_contents):
                        file_name = file_names[i] if i < len(file_names) else f"file_{i}"
                        tags = ["project_file", "submitted_document"]
                        if project_name:
                            tags.append(project_name.lower().replace(' ', '_'))
                        manager.add_text_content(
                            db_name, file_content_block,
                            source_label=f"project_file:{file_name}",
                            tags=tags,
                            max_content_length=8000
                        )
                    self.update_log(f"[Project] Stored {len(file_contents)} file(s) in RAG database '{db_name}'")
                    print(f"[MasterAgentNode] Stored {len(file_contents)} file(s) in RAG database '{db_name}'")
                except Exception as rag_exc:
                    self.update_log(f"[Project] Warning: could not store files in RAG: {rag_exc}")
                    print(f"[MasterAgentNode] RAG storage warning: {rag_exc}")

            if not file_contents and not instructions and not chat_message:
                self._append_chat_message("System", "No content could be extracted from the submitted files.")
                return

            # Build the combined request
            parts = []
            if chat_message:
                parts.append(f"User Request: {chat_message}")
            if instructions:
                parts.append(f"Instructions:\n{instructions}")
            if file_contents:
                parts.append("--- SUBMITTED FILE CONTENTS ---")
                parts.extend(file_contents)
                parts.append("--- END OF SUBMITTED FILES ---")

            combined_request = "\n\n".join(parts)

            self._append_chat_message(
                "System",
                f"File extraction complete ({len(file_contents)} file(s) extracted, "
                f"{sum(len(c) for c in file_contents)} chars total). "
                f"Submitting to Master Control Agent for processing..."
            )
            print(f"[MasterAgentNode] File extraction complete: {len(file_contents)} files, "
                  f"{sum(len(c) for c in file_contents)} chars total")

            # Process through the MCA chat pipeline
            self._chat_api_call_with_project(combined_request, project_name, file_names, files,
                                              extracted_file_contents=file_contents)

        except Exception as exc:
            self._append_chat_message("System", f"Project processing error: {exc}")
            self.update_log(f"[Project] Error: {exc}")

    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
                        '.svg', '.tiff', '.tif', '.ico', '.heic', '.heif'}

    def is_image_file(self, file_path) -> bool:
        """Return True if the file is a supported image format."""
        return Path(file_path).suffix.lower() in self.IMAGE_EXTENSIONS

    # Minimum characters of extractable text for a page to be considered
    # "text-based" rather than a scanned image.
    _PDF_TEXT_THRESHOLD = 30

    def _extract_pdf_content(self, file_path: Path, temp_dir: Path) -> str:
        """Extract content from a PDF, handling both text and scanned pages.

        For each page:
          - If meaningful text can be extracted (>= _PDF_TEXT_THRESHOLD chars),
            include it as plain text.
          - Otherwise, render the page to a PNG image and return an
            ``[IMAGE:/path/to/page.png]`` sentinel so the caller can route it
            through the vision API.

        Returns a single string with text blocks and ``[IMAGE:...]`` markers
        interleaved.
        """
        import fitz  # PyMuPDF

        parts: list[str] = []
        doc = fitz.open(str(file_path))
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = (page.get_text("text") or "").strip()

                if len(page_text) >= self._PDF_TEXT_THRESHOLD:
                    # Text-based page — use extracted text
                    parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
                else:
                    # Scanned / image-based page — render to PNG
                    pix = page.get_pixmap(dpi=200)
                    img_path = temp_dir / f"{file_path.stem}_page{page_num + 1}.png"
                    pix.save(str(img_path))
                    parts.append(f"--- Page {page_num + 1} (scanned) ---\n[IMAGE:{img_path}]")
                    self.update_log(
                        f"[PDF] Page {page_num + 1} of {file_path.name} is image-based, "
                        f"rendered to {img_path.name}"
                    )
        finally:
            doc.close()

        return "\n\n".join(parts) if parts else f"[Error: no content in {file_path.name}]"

    def _extract_file_content(self, file_path: Path, temp_dir: Path) -> str:
        """Extract text content from a single file, supporting all file types."""
        suffix = file_path.suffix.lower()

        # Images — do NOT attempt text extraction; return a sentinel so the
        # caller can route these through the vision API instead.
        if self.is_image_file(file_path):
            return f"[IMAGE:{file_path}]"

        # Audio / Video
        if self.is_audio_file(file_path) or self.is_video_file(file_path):
            transcript_path = temp_dir / f"{file_path.stem}_transcript.txt"
            if self.is_video_file(file_path):
                audio_path = temp_dir / f"{file_path.stem}_audio.mp3"
                if self.extract_audio_from_video(file_path, audio_path):
                    self.process_audio_file(str(audio_path), str(transcript_path))
                    try:
                        audio_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                else:
                    return f"[Error: could not extract audio from {file_path.name}]"
            else:
                self.process_audio_file(str(file_path), str(transcript_path))
            if transcript_path.exists():
                return transcript_path.read_text(encoding='utf-8', errors='replace')
            return "[Error: transcription failed]"

        # PDF — detect text vs scanned (image-based) pages
        if self.is_pdf_file(file_path):
            return self._extract_pdf_content(file_path, temp_dir)

        # Excel
        if self.is_excel_file(file_path):
            import pandas as pd
            text = ""
            with pd.ExcelFile(file_path) as xls:
                for sheet in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet)
                    text += f"Sheet: {sheet}\nColumns: {', '.join(str(c) for c in df.columns)}\n"
                    text += df.to_string(index=False) + f"\nTotal Rows: {len(df)}\n\n"
            return text

        # CSV
        if self.is_csv_file(file_path):
            import pandas as pd
            df = pd.read_csv(file_path)
            text = f"Columns: {', '.join(str(c) for c in df.columns)}\n"
            text += df.to_string(index=False) + f"\nTotal Rows: {len(df)}\n"
            return text

        # Word (.docx)
        if self.is_docx_file(file_path):
            from docx import Document as DocxDocument
            doc = DocxDocument(file_path)
            return "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())

        # Plain text / other
        for enc in ('utf-8', 'latin-1', 'cp1252'):
            try:
                return file_path.read_text(encoding=enc)
            except (UnicodeDecodeError, Exception):
                continue
        return f"[Error: could not read {file_path.name}]"

    def _chat_api_call_with_project(self, combined_request: str,
                                     project_name: str, file_names: list,
                                     source_file_paths: list = None,
                                     extracted_file_contents: list = None):
        """Process a project request through the MCA pipeline and save output.

        When delegation occurs the extracted file contents and source file
        paths are injected into the delegation dict so the TeamLead (and its
        workers) can use the actual document text — not just a brief AI
        summary.  The TeamLead is also responsible for creating the project
        folder and copying source files, so we skip the duplicate
        ``_save_project_output`` call when the TeamLead already produced
        output files.
        """
        try:
            api_endpoint = self._get_chat_api_endpoint()
            rag_context = self._query_rag_for_context(combined_request[:2000])

            prompt = self._build_chat_prompt(combined_request, rag_context=rag_context)
            response = self.send_to_api(prompt, api_endpoint)

            # Check for delegation
            delegation = self._extract_delegation(response)
            if delegation:
                self._append_chat_message(
                    "Assistant",
                    delegation.get('message') or "Processing your project with the team..."
                )

                # Inject extracted file content so the TeamLead and workers
                # have the full document text, not just the AI's summary.
                if extracted_file_contents:
                    delegation['file_contents'] = extracted_file_contents
                if source_file_paths:
                    delegation['source_file_paths'] = source_file_paths
                if project_name:
                    delegation['project_name'] = project_name

                results, created_files = self._run_team_lead(delegation)
                formatted = self._format_delegation_results(results)
                self._append_chat_message("Assistant", formatted)
                self._store_to_rag(combined_request[:2000], formatted)

                # If the TeamLead already created a project folder with
                # output files we do NOT create a second one.  Only fall
                # back to _save_project_output when no files were produced.
                if not created_files:
                    self._save_project_output(formatted, project_name, file_names,
                                              source_file_paths, combined_request)
            else:
                self._append_chat_message("Assistant", response)
                if response and len(response.strip()) > 100:
                    self._store_to_rag(combined_request[:2000], response)
                # Save the direct response as the project output
                self._save_project_output(response, project_name, file_names,
                                          source_file_paths, combined_request)

        except Exception as exc:
            self._append_chat_message("System", f"Project processing error: {exc}")

    def _save_project_output(self, content: str, project_name: str,
                              file_names: list, source_file_paths: list = None,
                              combined_request: str = None):
        """Save the AI response to the outbox as a Word document and text file.

        Also copies the original source files and saves the combined source
        text (instructions + extracted file content) so the project folder
        contains everything: source files, combined input, and AI output.
        """
        try:
            import shutil
            import uuid
            outbox_folder = self._get_outbox_folder()
            if not outbox_folder:
                self.update_log("[Project] No outbox folder configured, skipping file output.")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            base_name = project_name or "Project"
            folder_name = f"{base_name}_{timestamp}_{unique_id}"
            project_output_dir = Path(outbox_folder) / folder_name
            project_output_dir.mkdir(parents=True, exist_ok=True)

            # --- 1. Copy original source files ---
            if source_file_paths:
                source_dir = project_output_dir / "source_files"
                source_dir.mkdir(exist_ok=True)
                for src_path_str in source_file_paths:
                    src_path = Path(src_path_str)
                    if src_path.exists() and src_path.is_file():
                        try:
                            shutil.copy2(str(src_path), str(source_dir / src_path.name))
                            self.update_log(f"[Project] Copied source file: {src_path.name}")
                        except Exception as copy_exc:
                            self.update_log(f"[Project] Could not copy {src_path.name}: {copy_exc}")

            # --- 2. Save combined source text (instructions + extracted content) ---
            if combined_request:
                source_text_path = project_output_dir / f"{base_name}_combined_source.txt"
                with open(source_text_path, 'w', encoding='utf-8') as f:
                    f.write(f"Project: {project_name or 'Unnamed'}\n")
                    f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    if file_names:
                        f.write(f"Files: {', '.join(file_names)}\n")
                    f.write(f"\n{'='*60}\n")
                    f.write("COMBINED INPUT SENT TO AI\n")
                    f.write(f"{'='*60}\n\n")
                    f.write(combined_request)

            # --- 3. Save AI response as text ---
            text_path = project_output_dir / f"{base_name}_response.txt"
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(f"Project: {project_name or 'Unnamed'}\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                if file_names:
                    f.write(f"Files: {', '.join(file_names)}\n")
                f.write(f"\n{'='*60}\n")
                f.write("AI RESPONSE\n")
                f.write(f"{'='*60}\n\n")
                f.write(content)

            # --- 4. Save AI response as Word document ---
            docx_path = project_output_dir / f"{base_name}.docx"
            convert_markdown_to_docx(content, str(docx_path), formatting_enabled=True)

            self._append_chat_message(
                "Assistant",
                f"Project output saved to:\n  {project_output_dir}"
            )
            self.update_log(f"[Project] Output saved to: {project_output_dir}")

            # Refresh file browser if available
            try:
                self.refresh_file_browser()
            except Exception:
                pass

        except Exception as exc:
            self._append_chat_message("System", f"Error saving project output: {exc}")
            self.update_log(f"[Project] Error saving output: {exc}")

    def _chat_api_call(self, message: str):
        try:
            api_endpoint = self._get_chat_api_endpoint()

            # --- Complexity triage ---
            complexity = self._assess_complexity(message)
            self.update_log(f"Complexity: {complexity} — \"{message[:60]}\"")

            # SIMPLE: fast LLM, no RAG, no tools
            if complexity == 'simple':
                from datetime import datetime as _dt
                now = _dt.now()
                fast_prompt = (
                    "You are a helpful AI assistant. Answer the user's message "
                    "directly and concisely in 1-2 sentences.\n"
                    f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
                    f"Current time: {now.strftime('%I:%M %p')}\n\n"
                    f"User: {message}\nAssistant:"
                )
                response = self.send_to_api(fast_prompt, api_endpoint)
                if response:
                    self._append_chat_message("Assistant", response)
                    return

            # MEDIUM: Master handles directly with RAG + optional web search
            if complexity == 'medium':
                response = self._handle_medium_complexity(message, api_endpoint)
                if response:
                    return

            # COMPLEX: full pipeline with delegation
            rag_context = self._query_rag_for_context(message)

            prompt = self._build_chat_prompt(message, rag_context=rag_context)
            response = self.send_to_api(prompt, api_endpoint)
            clarification = self._extract_clarification(response)
            if clarification:
                self.pending_clarification = clarification
                self.pending_request = message
                questions = clarification.get('questions') or []
                question_lines = "\n".join(f"{idx + 1}. {q}" for idx, q in enumerate(questions))
                self._append_chat_message(
                    "Assistant",
                    f"I have a few clarifying questions:\n{question_lines}"
                )
                return
            delegation = self._extract_delegation(response)
            if delegation:
                if self._needs_export_clarification(delegation, message):
                    self.pending_delegation = delegation
                    self._append_chat_message(
                        "Assistant",
                        "Do you want the results exported? If so, choose Word (.docx), "
                        "Excel (.xlsx), or Text (.txt). You can also say 'no export'."
                    )
                    return
                self._append_chat_message("Assistant", delegation.get('message') or "Delegation dispatched.")
                results, _created_files = self._run_team_lead(delegation)
                formatted = self._format_delegation_results(results)
                self._append_chat_message("Assistant", formatted)
                self._export_if_requested(formatted)

                # Store delegation results back into RAG for future lookups
                self._store_to_rag(message, formatted)
            else:
                self._append_chat_message("Assistant", response)
                # Store direct answers into RAG if substantive
                if response and len(response.strip()) > 100:
                    self._store_to_rag(message, response)
        except Exception as exc:
            self._append_chat_message("System", f"Chat error: {exc}")

    # -- Complexity triage ------------------------------------------------

    def _assess_complexity(self, message: str) -> str:
        """Classify a message into one of three tiers:
        - 'simple'  : greetings, time/date, very short chat — fast LLM only
        - 'medium'  : general knowledge, recipes, single-topic lookups —
                       Master answers directly (with optional web search)
        - 'complex' : multi-step research, internal business data, reports,
                       multi-source analysis — delegate to team/workers
        """
        msg = message.lower().strip()

        # --- SIMPLE: greetings & small-talk ---
        if msg in ('hi', 'hey', 'hello', 'yo', 'sup', 'thanks', 'thank you',
                   'bye', 'goodbye', 'good morning', 'good afternoon',
                   'good evening', 'good night'):
            return 'simple'

        # --- SIMPLE: time / date ---
        time_date_kw = (
            'what time', 'current time', 'what date', 'current date',
            'today\'s date', 'what day', 'what is the time',
            'what is the date', 'what\'s the time', 'what\'s the date',
            'tell me the time', 'tell me the date',
        )
        if any(kw in msg for kw in time_date_kw):
            return 'simple'

        # --- SIMPLE: self-referential & conversational ---
        # Questions about the AI itself, its personality, opinions, hypotheticals
        self_ref_kw = (
            'tell me about yourself', 'about yourself', 'your personality',
            'your name', 'who are you', 'what are you', 'what is your name',
            'what\'s your name', 'describe yourself', 'your traits',
            'how would you', 'what would you', 'if i asked you',
            'if i was to ask you', 'if someone', 'how do you feel',
            'what do you think', 'your opinion', 'do you like',
            'are you', 'can you tell me about you',
        )
        if any(kw in msg for kw in self_ref_kw):
            return 'simple'

        # --- COMPLEX: signals that need team delegation ---
        complex_signals = (
            'analyze', 'compare', 'investigate', 'report on',
            'create a report', 'multi-step', 'across all',
            'what do we charge', 'our pricing', 'our sla',
            'internal documentation', 'export', 'generate a document',
            'write a report', 'draft a proposal', 'build a',
        )
        if any(kw in msg for kw in complex_signals):
            return 'complex'

        # --- COMPLEX: file creation requests (always need delegation) ---
        file_creation_signals = (
            'word doc', 'word document', '.docx', 'docx',
            'spreadsheet', 'excel', '.xlsx', 'xlsx',
            'save it as', 'save as a', 'create a document',
            'sales sheet', 'marketing sheet', 'sales and marketing',
            'tracking sheet', 'cost tracking', 'profit tracking',
            'create a file', 'generate a file', 'make a document',
            'develop a spreadsheet', 'develop a document',
            'put together a', 'put it in a document',
        )
        if any(kw in msg for kw in file_creation_signals):
            return 'complex'

        # --- COMPLEX: very long or multi-sentence requests ---
        if len(msg) > 500 or msg.count('.') >= 4 or msg.count('\n') >= 3:
            return 'complex'

        # --- Everything else is MEDIUM ---
        return 'medium'

    def _handle_medium_complexity(self, message: str, api_endpoint: str, wa_hint: str = '') -> str:
        """Handle medium-complexity questions using LLM-driven intelligence.

        Instead of hardcoded keyword matching, the LLM decides whether a web
        search is needed, formulates an optimised search query, evaluates the
        results, and retries with a refined query if the first attempt fails.
        """
        from datetime import datetime as _dt
        now = _dt.now()
        time_context = (
            f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
            f"Current time: {now.strftime('%I:%M %p')}\n"
        )

        # 1. Check RAG for existing knowledge
        rag_context = self._query_rag_for_context(message)
        rag_snippet = rag_context[:4000] if rag_context else ""

        # Build recent chat history for conversational context
        recent_lines = []
        for h_msg in self.chat_history[-6:]:
            role = h_msg.get("role", "user").capitalize()
            content = h_msg.get("content", "")[:300]
            recent_lines.append(f"{role}: {content}")
        history_block = "\n".join(recent_lines) if recent_lines else ""

        # 2. Ask the LLM to analyse the request and decide what to do
        analysis = self._llm_analyse_request(message, rag_snippet, api_endpoint, time_context)
        print(f"[MCA-DIAG] LLM analysis: {analysis}")

        can_answer = analysis.get('can_answer_from_knowledge', False)
        needs_search = analysis.get('needs_web_search', True)
        search_query = analysis.get('search_query', '')

        # 3. If the LLM says RAG already has the answer, respond directly
        personality_block = self._build_personality_prompt()
        permissions_block = self._build_permissions_prompt()
        if can_answer and not needs_search and rag_context and len(rag_context.strip()) > 50:
            prompt = (
                "You are a helpful AI assistant.\n\n"
                f"{personality_block}"
                f"{permissions_block}"
                "Use the provided knowledge to "
                "answer the user's question directly and concisely.\n"
                f"{wa_hint}{time_context}\n"
            )
            if history_block:
                prompt += f"RECENT CONVERSATION:\n{history_block}\n\n"
            prompt += (
                f"KNOWLEDGE:\n{rag_context}\n\n"
                f"User: {message}\nAssistant:"
            )
            response = self.send_to_api(prompt, api_endpoint)
            if response:
                self._append_chat_message("Assistant", response)
                if len(response.strip()) > 100:
                    self._store_to_rag(message, response)
                return response

        # 4. Perform web search with the LLM-optimised query
        if not search_query:
            search_query = message  # fallback
        print(f"[MCA-DIAG] Web search query (LLM-optimised): {search_query!r}")
        search_result = self._master_web_search(search_query, api_endpoint)

        # 5. If search returned results, ask LLM to evaluate them
        if search_result:
            evaluation = self._llm_evaluate_search(
                message, search_query, search_result, api_endpoint
            )
            print(f"[MCA-DIAG] Search evaluation: {evaluation}")

            # If the LLM says the results don't answer the question, retry
            if not evaluation.get('answers_question', True):
                retry_query = evaluation.get('better_query', '')
                if retry_query and retry_query.lower() != search_query.lower():
                    print(f"[MCA-DIAG] Retrying with refined query: {retry_query!r}")
                    retry_result = self._master_web_search(retry_query, api_endpoint)
                    if retry_result:
                        search_result = search_result + "\n\n--- REFINED SEARCH ---\n" + retry_result

        # 6. Synthesize final answer from all available data
        search_context = search_result or ""
        prompt = (
            "You are a helpful AI assistant.\n\n"
            f"{personality_block}"
            f"{permissions_block}"
            "Answer the user's question "
            "directly and concisely. Use the search results and any existing "
            "knowledge provided. If the information was found, present it "
            "clearly. If you truly cannot find the answer, say so honestly "
            "and suggest what the user could try.\n"
            f"{wa_hint}{time_context}\n"
        )
        if history_block:
            prompt += f"RECENT CONVERSATION:\n{history_block}\n\n"
        if search_context:
            prompt += f"WEB SEARCH RESULTS:\n{search_context[:6000]}\n\n"
        if rag_context and len(rag_context.strip()) > 50:
            prompt += f"EXISTING KNOWLEDGE:\n{rag_snippet}\n\n"
        prompt += f"User: {message}\nAssistant:"

        response = self.send_to_api(prompt, api_endpoint)
        if response:
            self._append_chat_message("Assistant", response)
            if len(response.strip()) > 100:
                self._store_to_rag(message, response)
        return response or ""

    def _llm_analyse_request(self, message: str, rag_snippet: str,
                              api_endpoint: str, time_context: str) -> dict:
        """Ask the LLM to analyse the user's message and decide the best
        course of action: answer from knowledge, perform a web search, or both.
        Returns a dict with keys: can_answer_from_knowledge, needs_web_search,
        search_query."""
        # Include recent chat history so the LLM can resolve follow-up references
        # like "send that info" or "the GPU alternatives" from prior conversation.
        recent_lines = []
        for h_msg in self.chat_history[-6:]:
            role = h_msg.get("role", "user").capitalize()
            content = h_msg.get("content", "")[:300]
            recent_lines.append(f"{role}: {content}")
        history_block = "\n".join(recent_lines) if recent_lines else ""

        prompt = (
            "You are an intelligent request analyser. Given a user message, "
            "recent conversation history, and optionally some existing knowledge, "
            "decide the best way to answer.\n\n"
            f"{time_context}\n"
            "Respond with ONLY a JSON object (no markdown fences, no commentary):\n"
            "{\n"
            '  "can_answer_from_knowledge": true/false,\n'
            '  "needs_web_search": true/false,\n'
            '  "search_query": "optimised search engine query if web search is needed"\n'
            "}\n\n"
            "IMPORTANT RULES:\n"
            "- If the user is asking about YOU (the AI assistant), your personality, "
            "your name, your opinions, or hypothetical 'how would you respond' "
            "scenarios, set can_answer_from_knowledge=true and needs_web_search=false. "
            "You DO have a personality and can answer these directly.\n"
            "- Conversational, opinion-based, or hypothetical questions do NOT need "
            "web search. Only factual lookups about external topics need search.\n"
            "- CRITICAL: If the user is referring to something from the recent "
            "conversation (e.g. 'send that info', 'the GPU alternatives', "
            "'that summary'), and the EXISTING KNOWLEDGE already contains the "
            "relevant information from a prior analysis or delegation, set "
            "can_answer_from_knowledge=true and needs_web_search=false. "
            "Do NOT do a generic web search when the user is asking for information "
            "that was already produced in the conversation.\n\n"
            "RULES for search_query:\n"
            "- Extract the core information need from the conversational message\n"
            "- Remove filler words like 'can you', 'please', 'I need you to'\n"
            "- Add relevant context (location, company type) if mentioned\n"
            "- Make it a query a human would type into Google\n"
            "- Example: User says 'Can you do a quick search and tell me what the "
            "phone number is for Rocky mountain valves' → search_query: "
            '"Rocky Mountain Valves phone number"\n\n'
        )
        if history_block:
            prompt += f"RECENT CONVERSATION:\n{history_block}\n\n"
        if rag_snippet:
            prompt += f"EXISTING KNOWLEDGE (may or may not be relevant):\n{rag_snippet[:1500]}\n\n"
        prompt += f"USER MESSAGE: {message}\n\nJSON:"

        response = self._low_temp_api_call(prompt, api_endpoint)
        if response:
            try:
                text = response.strip()
                if text.startswith('```'):
                    lines = text.split('\n')
                    text = '\n'.join(lines[1:])
                    if text.rstrip().endswith('```'):
                        text = text.rstrip()[:-3].rstrip()
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, Exception) as exc:
                print(f"[MCA-DIAG] _llm_analyse_request parse error: {exc}")
        return {'can_answer_from_knowledge': False, 'needs_web_search': True,
                'search_query': message}

    def _llm_evaluate_search(self, original_message: str, search_query: str,
                              search_result: str, api_endpoint: str) -> dict:
        """Ask the LLM to evaluate whether the search results actually answer
        the user's question. If not, suggest a better query to retry.
        Returns a dict with keys: answers_question, better_query."""
        prompt = (
            "You are evaluating web search results to determine if they answer "
            "the user's original question.\n\n"
            f"ORIGINAL USER QUESTION: {original_message}\n"
            f"SEARCH QUERY USED: {search_query}\n"
            f"SEARCH RESULTS (first 2000 chars):\n{search_result[:2000]}\n\n"
            "Respond with ONLY a JSON object (no markdown fences, no commentary):\n"
            "{\n"
            '  "answers_question": true/false,\n'
            '  "better_query": "a refined search query if the results do not answer the question, or empty string if they do"\n'
            "}\n\n"
            "RULES:\n"
            "- answers_question = true ONLY if the results contain the specific "
            "information the user asked for\n"
            "- If the results are about the wrong company, wrong topic, or "
            "generic/irrelevant, set answers_question = false\n"
            "- For better_query, try different search terms, add location, "
            "company type, or use quotes for exact names\n"
            '- Example: if searching "Rocky Mountain Valves phone" returned '
            'results about Rocky Mountain Power, try: '
            '"Rocky Mountain Valves" Utah contact phone number\n\n'
            "JSON:"
        )
        response = self._low_temp_api_call(prompt, api_endpoint)
        if response:
            try:
                text = response.strip()
                if text.startswith('```'):
                    lines = text.split('\n')
                    text = '\n'.join(lines[1:])
                    if text.rstrip().endswith('```'):
                        text = text.rstrip()[:-3].rstrip()
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, Exception) as exc:
                print(f"[MCA-DIAG] _llm_evaluate_search parse error: {exc}")
        return {'answers_question': True, 'better_query': ''}

    def _low_temp_api_call(self, prompt: str, api_endpoint: str) -> str:
        """Send a prompt to the LLM with low temperature (0.1) for
        deterministic structured output (JSON analysis, evaluations).
        Uses send_api_request directly to bypass the default temperature."""
        try:
            api_config = self.config.get('interfaces', {}).get(api_endpoint, {})
            model = api_config.get('selected_model')
            max_tokens = api_config.get('max_tokens', 1000)
            response = self.send_api_request(
                content=prompt,
                api_name=api_endpoint,
                model=model,
                max_tokens=max_tokens,
                temperature=0.1
            )
            if response.success:
                return response.content
            else:
                print(f"[MCA-DIAG] _low_temp_api_call error: {response.error}")
                return ""
        except Exception as exc:
            print(f"[MCA-DIAG] _low_temp_api_call exception: {exc}")
            return ""

    def _master_web_search(self, query: str, api_endpoint: str) -> str:
        """Run a single web search using the same tool infrastructure as
        the worker agents. Returns the summarized text or empty string."""
        try:
            search_url = (
                self.properties.get('search_api_url', {}).get('value')
                or self.properties.get('search_api_url', {}).get('default')
                or ''
            )
            print(f"[MCA-DIAG] _master_web_search: search_url={search_url!r}, query={query[:80]!r}")
            tool_call = {
                'type': 'SearchScrapeSummarizeNode',
                'input': query,
                'properties': {
                    'search_query': query,
                    'num_search_results': '5',
                },
            }
            if search_url:
                tool_call['properties']['searxng_api_url'] = search_url

            self._append_chat_message("System", f"Searching: {query[:80]}...")
            results = self._execute_tool_calls([tool_call])

            for r in results:
                print(f"[MCA-DIAG] _master_web_search result: status={r.get('status')}, has_output={bool(r.get('output'))}")
                if r.get('status') == 'ok' and r.get('output'):
                    output = r['output']
                    if isinstance(output, dict):
                        text = output.get('output') or output.get('summary') or str(output)
                    else:
                        text = str(output)[:6000]
                    print(f"[MCA-DIAG] _master_web_search returning {len(text)} chars")
                    return text
            print(f"[MCA-DIAG] _master_web_search: no valid results from tool calls")
        except Exception as exc:
            print(f"[MCA-DIAG] _master_web_search ERROR: {exc}")
            self.update_log(f"Master web search error: {exc}")
        return ""

    # -- WhatsApp attachment helpers ----------------------------------------

    def _store_wa_attachments(self, sender: str, files: list, extracted: list):
        """Remember recently-attached files so follow-up messages can
        reference them without re-attaching."""
        if not hasattr(self, '_wa_recent_files'):
            self._wa_recent_files = {}
        records = []
        for fpath, content_block in zip(files, extracted):
            records.append({
                "path": str(fpath),
                "name": Path(fpath).name,
                "content": content_block,
            })
        # Keep only the most recent set per sender (overwrite)
        self._wa_recent_files[sender] = records
        self.update_log(f"[WA] Stored {len(records)} attachment(s) for sender '{sender}'")

    def _get_wa_recent_files(self, sender: str) -> list[dict]:
        """Return the most recently-attached files for *sender*."""
        if not hasattr(self, '_wa_recent_files'):
            self._wa_recent_files = {}
        return self._wa_recent_files.get(sender, [])

    def _is_file_modification_request(self, message: str) -> bool:
        """Return True if the message asks to modify / rewrite / reformat
        a previously-sent file, OR to create / generate a new document from
        attached content (e.g. an image)."""
        msg = message.lower()
        modify_signals = (
            'modify', 'update', 'change', 'edit', 'rewrite', 'reformat',
            'revise', 'correct', 'fix', 'adjust', 'amend',
            'redo', 'rework', 'restructure', 'convert',
        )
        create_signals = (
            'create', 'generate', 'make', 'produce', 'build', 'draft',
            'write', 'compose', 'turn this into', 'turn it into',
            'convert this to', 'convert it to', 'convert to',
            'develop', 'save', 'save it as', 'save as',
            'put together', 'prepare', 'design', 'set up',
            'come up with',
        )
        file_refs = (
            'document', 'doc', 'docx', 'word', 'word document',
            'file', 'that document', 'the document',
            'that file', 'the file', 'it',
            'spreadsheet', 'the spreadsheet', 'that spreadsheet',
            'excel', 'the excel', 'that excel',
            'csv', 'the csv', 'that csv',
            'pdf', 'the pdf', 'that pdf',
        )
        output_format_refs = (
            'word document', 'word doc', 'docx', '.docx',
            'excel file', 'spreadsheet', '.xlsx',
            'csv file', '.csv',
            'text file', '.txt',
        )
        has_modify = any(kw in msg for kw in modify_signals)
        has_create = any(kw in msg for kw in create_signals)
        has_file_ref = any(kw in msg for kw in file_refs)
        has_output_fmt = any(kw in msg for kw in output_format_refs)
        send_back = ('send it', 'send me', 'send the')
        has_send = any(kw in msg for kw in send_back)
        # Modification: "modify" + file reference
        if has_modify and (has_file_ref or has_send):
            return True
        # Creation: "create/generate/make" + output format reference
        if has_create and (has_output_fmt or has_file_ref):
            return True
        return False

    def _detect_original_file_type(self, sender: str) -> str:
        """Determine the file type of the most recently-attached file for
        *sender*.  Returns one of: 'docx', 'excel', 'csv', 'pdf', 'text',
        or 'docx' as the default fallback."""
        recent = self._get_wa_recent_files(sender)
        if not recent:
            return 'docx'
        name = recent[0].get("name", "").lower()
        if name.endswith(('.xlsx', '.xls')):
            return 'excel'
        if name.endswith('.csv'):
            return 'csv'
        if name.endswith('.pdf'):
            return 'pdf'
        if name.endswith('.txt'):
            return 'text'
        return 'docx'

    def _detect_desired_output_format(self, message: str) -> str:
        """Parse the user's message to determine the desired output format
        when the source is an image.  Returns 'docx', 'excel', 'csv', or
        'text'.  Defaults to 'docx'."""
        msg = message.lower()
        if any(kw in msg for kw in ('excel', 'spreadsheet', '.xlsx', 'xls')):
            return 'excel'
        if any(kw in msg for kw in ('csv', '.csv', 'comma separated')):
            return 'csv'
        if any(kw in msg for kw in ('text file', '.txt', 'plain text')):
            return 'text'
        # Default: Word document
        return 'docx'

    def _generate_wa_output_file(self, content: str, file_type: str = 'docx',
                                  base_name: str = "modified") -> str:
        """Generate an output file from the LLM response content.

        Supported *file_type* values: 'docx', 'excel', 'csv', 'text'.
        PDFs are exported as .docx since generating PDFs from markdown is
        not directly supported.
        Returns the file path or '' on failure.
        """
        import uuid
        out_dir = self.temp_dir / "wa_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique = uuid.uuid4().hex[:6]

        try:
            if file_type == 'excel':
                out_path = out_dir / f"{base_name}_{timestamp}_{unique}.xlsx"
                convert_markdown_to_excel(content, str(out_path), formatting_enabled=True)
            elif file_type == 'csv':
                out_path = out_dir / f"{base_name}_{timestamp}_{unique}.csv"
                # Extract tabular data from the LLM response — write as-is
                with open(out_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(content)
            elif file_type == 'text':
                out_path = out_dir / f"{base_name}_{timestamp}_{unique}.txt"
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                # docx (also used as fallback for pdf)
                out_path = out_dir / f"{base_name}_{timestamp}_{unique}.docx"
                convert_markdown_to_docx(content, str(out_path), formatting_enabled=True)

            self.update_log(f"[WA] Generated output file: {out_path.name}")
            return str(out_path)
        except Exception as exc:
            self.update_log(f"[WA] Error generating {file_type} output: {exc}")
            return ""

    # -- External message processing ----------------------------------------

    def process_external_message(self, message: str, sender: str = "WhatsApp",
                                 files: list = None) -> dict:
        """Process a message from an external source (e.g. WhatsApp) through
        the full MCA chat pipeline and return the response synchronously.

        Parameters:
            message: The user's text message.
            sender: Source label (e.g. "WhatsApp").
            files: Optional list of local file paths attached to the message.

        Returns a dict:
            {"text": str, "files": list[str]}
        where ``files`` contains paths to any output files the agent produced.
        For backward compatibility, callers that expect a plain string can
        still use ``str(result)`` or ``result["text"]``.
        """
        output_files: list[str] = []
        try:
            # --- Separate images from documents ---
            image_files: list[str] = []
            doc_files: list[str] = []
            if files:
                for fpath in files:
                    fp = Path(fpath)
                    if not fp.exists():
                        continue
                    if self.is_image_file(fp):
                        image_files.append(str(fp))
                    else:
                        doc_files.append(str(fp))

            # --- Handle image files via vision API ---
            # Extract content from images using the vision API, then feed
            # the extracted content into the normal LLM pipeline so the
            # Master Agent can interpret the user's full intent (e.g.
            # "convert this to a Word document").
            has_images = bool(image_files)
            vision_responses: list[str] = []
            if image_files:
                api_endpoint = self._get_chat_api_endpoint()
                api_service = self.get_api_service()
                extraction_prompt = (
                    "Extract and describe ALL content from this image as "
                    "thoroughly as possible. If the image contains a document, "
                    "form, letter, or any text, reproduce that text faithfully "
                    "preserving structure, headings, paragraphs, lists, and "
                    "tables. If it is a photo, diagram, or chart, describe it "
                    "in full detail. Return ONLY the extracted content — no "
                    "commentary or meta-notes."
                )

                for img_path in image_files:
                    self.update_log(f"[WA] Extracting content from image via vision API: {Path(img_path).name}")
                    api_config = self.config.get('interfaces', {}).get(api_endpoint, {})
                    model = api_config.get('selected_model')
                    resp = api_service.send_vision_request(
                        image_path=img_path,
                        prompt=extraction_prompt,
                        api_name=api_endpoint,
                        model=model,
                    )
                    if resp.success and resp.content:
                        vision_responses.append(resp.content)
                        self.update_log(f"[WA] Vision extraction: {len(resp.content)} chars from {Path(img_path).name}")
                    else:
                        err = resp.error or "Unknown vision API error"
                        self.update_log(f"[WA] Vision API error for {Path(img_path).name}: {err}")
                        vision_responses.append(f"[Could not process image: {err}]")

                # Store image-extracted content as "attachments" so the
                # pipeline treats them like any other file content.
                image_names = [Path(p).name for p in image_files]
                image_blocks = [
                    f"=== Content extracted from image: {name} ===\n{content}"
                    for name, content in zip(image_names, vision_responses)
                ]
                self._store_wa_attachments(sender, image_files, image_blocks)

            # --- Extract content from document (non-image) files ---
            file_context = ""
            extracted_blocks: list[str] = []
            if doc_files:
                import re as _re
                import uuid
                temp_dir = self.temp_dir / f"wa_{uuid.uuid4().hex[:8]}"
                temp_dir.mkdir(parents=True, exist_ok=True)
                for fpath in doc_files:
                    fp = Path(fpath)
                    if not fp.exists():
                        continue
                    try:
                        content = self._extract_file_content(fp, temp_dir)
                        if content and content.strip():
                            extracted_blocks.append(f"=== Content from {fp.name} ===\n{content}")
                            self.update_log(f"[WA] Extracted {len(content)} chars from {fp.name}")
                    except Exception as exc:
                        self.update_log(f"[WA] Error extracting {fp.name}: {exc}")

                # --- Process any [IMAGE:path] sentinels from scanned PDF pages ---
                _img_sentinel_re = _re.compile(r'\[IMAGE:(.+?)\]')
                sentinel_found = any(_img_sentinel_re.search(b) for b in extracted_blocks)
                if sentinel_found:
                    api_endpoint = self._get_chat_api_endpoint()
                    api_service = self.get_api_service()
                    api_config = self.config.get('interfaces', {}).get(api_endpoint, {})
                    vision_model = api_config.get('selected_model')
                    ocr_prompt = (
                        "Extract and return ALL text content from this scanned "
                        "document page. Preserve the original structure, headings, "
                        "paragraphs, lists, and tables as closely as possible."
                    )
                    resolved_blocks: list[str] = []
                    for block in extracted_blocks:
                        def _replace_sentinel(m):
                            img_p = m.group(1)
                            if not Path(img_p).exists():
                                return f"[Error: rendered page not found: {img_p}]"
                            self.update_log(f"[WA] OCR via vision API: {Path(img_p).name}")
                            resp = api_service.send_vision_request(
                                image_path=img_p, prompt=ocr_prompt,
                                api_name=api_endpoint, model=vision_model,
                            )
                            if resp.success and resp.content:
                                self.update_log(f"[WA] OCR result: {len(resp.content)} chars")
                                return resp.content
                            err = resp.error or "vision API error"
                            self.update_log(f"[WA] OCR error: {err}")
                            return f"[OCR failed: {err}]"
                        resolved_blocks.append(_img_sentinel_re.sub(_replace_sentinel, block))
                    extracted_blocks = resolved_blocks

                # Store in RAG
                if extracted_blocks:
                    try:
                        manager, db_name = self._get_db_manager()
                        for block in extracted_blocks:
                            manager.add_text_content(
                                db_name, block,
                                source_label="whatsapp_attachment",
                                tags=["whatsapp", "attachment"],
                                max_content_length=8000,
                            )
                    except Exception:
                        pass
                    file_context = "\n\n".join(extracted_blocks)
                # Remember these files for follow-up messages
                self._store_wa_attachments(sender, doc_files, extracted_blocks)
                # Clean up temp dir (after vision processing so rendered PNGs are available)
                try:
                    import shutil
                    shutil.rmtree(str(temp_dir), ignore_errors=True)
                except Exception:
                    pass

            # Merge image-extracted content into file_context so it flows
            # through the normal LLM pipeline alongside any document content.
            if has_images and vision_responses:
                image_names = [Path(p).name for p in image_files]
                vision_block = "\n\n".join(
                    f"=== Content extracted from image: {name} ===\n{content}"
                    for name, content in zip(image_names, vision_responses)
                )
                file_context = f"{vision_block}\n\n{file_context}" if file_context else vision_block

            # --- If no new files but user references a previous file,
            #     pull in the stored content so the LLM has it ---
            if not files and self._is_file_modification_request(message):
                recent = self._get_wa_recent_files(sender)
                if recent:
                    parts = [r["content"] for r in recent if r.get("content")]
                    if parts:
                        file_context = "\n\n".join(parts)
                        self.update_log(
                            f"[WA] Re-injecting {len(recent)} previous attachment(s) "
                            f"for document modification request"
                        )

            # --- Detect YouTube URLs in the message and fetch transcripts ---
            _yt_url_re = re.compile(
                r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|'
                r'youtube\.com/shorts/|youtube\.com/live/|youtube\.com/embed/)[\w-]+[^\s]*'
            )
            yt_urls = _yt_url_re.findall(message)
            if yt_urls:
                from nodes.youtube_transcript_node import YoutubeTranscriptNode
                yt_node = YoutubeTranscriptNode(
                    node_id="youtube_transcript_wa", config=self.config
                )
                yt_blocks = []
                for yt_url in yt_urls:
                    yt_url = yt_url.strip()
                    if not yt_url.startswith(('http://', 'https://')):
                        yt_url = f'https://{yt_url}'
                    self.update_log(f"[WA] Fetching YouTube transcript: {yt_url}")
                    try:
                        yt_result = yt_node.process({'input': yt_url})
                        parts = []
                        title = yt_result.get('title', '')
                        if title and not title.startswith('Error:'):
                            parts.append(f"Title: {title}")
                        desc = yt_result.get('description', '')
                        if desc and not desc.startswith('Error:'):
                            parts.append(f"Description: {desc}")
                        transcript = yt_result.get('transcript', '')
                        if transcript and not transcript.startswith('Error:'):
                            parts.append(f"Transcript: {transcript}")
                        if parts:
                            block = f"=== YouTube Video Content from {yt_url} ===\n" + "\n\n".join(parts)
                            yt_blocks.append(block)
                            self.update_log(f"[WA] YouTube transcript fetched ({len(transcript)} chars): {title}")
                        else:
                            self.update_log(f"[WA] Could not fetch YouTube transcript for {yt_url}")
                    except Exception as exc:
                        self.update_log(f"[WA] Error fetching YouTube transcript: {exc}")

                if yt_blocks:
                    yt_context = "\n\n".join(yt_blocks)
                    file_context = f"{yt_context}\n\n{file_context}" if file_context else yt_context
                    # Store in RAG for follow-up questions
                    try:
                        manager, db_name = self._get_db_manager()
                        for block in yt_blocks:
                            manager.add_text_content(
                                db_name, block,
                                source_label="youtube_transcript",
                                tags=["youtube", "transcript", "video"],
                                max_content_length=16000,
                            )
                    except Exception:
                        pass

            # Build the effective message (text + file content)
            effective_message = message
            if file_context:
                effective_message = (
                    f"{message}\n\n"
                    "--- ATTACHED CONTENT ---\n"
                    f"{file_context}\n"
                    "--- END OF ATTACHED CONTENT ---"
                )

            self._append_chat_message(sender, effective_message)
            api_endpoint = self._get_chat_api_endpoint()

            # Determine if this is a file modification/creation request
            wants_file_output = self._is_file_modification_request(message)
            print(f"[MCA-DIAG] wants_file_output={wants_file_output}, has_images={has_images}, file_context={bool(file_context)}")
            original_file_type = self._detect_original_file_type(sender) if wants_file_output else 'docx'
            # When the source is an image, detect desired output format from
            # the user's message and default to docx.
            if wants_file_output and has_images:
                original_file_type = self._detect_desired_output_format(message)

            # --- Build sender-specific hint for the LLM ---
            wa_hint = ''  # default: no hint (console / internal)
            if sender in ("WhatsApp", "Slack"):
                wa_hint = (
                    f"This message came via {sender}. Keep your response concise and "
                    "conversational — no markdown headers, no long lists. "
                    "A few short paragraphs at most.\n\n"
                )

                # =============================================================
                # CONVERSATIONAL REFERENCE RESOLUTION: expand vague refs
                # like "the same person", "that email" using chat history
                # and email context BEFORE follow-up or intent detection.
                # =============================================================
                resolved_message = self._resolve_conversational_references(
                    message, api_endpoint
                )
                if resolved_message != message:
                    message = resolved_message
                    effective_message = resolved_message

                # =============================================================
                # EMAIL CONTEXT INJECTION: if there's recent email context,
                # inject it as a hint so the AI can reason about it.
                # This does NOT intercept the request — it enriches context.
                # Only pending draft confirmations (yes/no) are intercepted.
                # =============================================================
                self._email_context_hint = ""
                email_followup = self._check_email_followup(
                    message, api_endpoint, output_files
                )
                if email_followup is not None:
                    return email_followup
                # If email context was injected, append it to effective_message
                if self._email_context_hint:
                    effective_message = (
                        f"{effective_message}\n\n{self._email_context_hint}"
                    )

            elif sender == "Email":
                # =============================================================
                # EMAIL SHORT-CIRCUIT: single LLM call to summarise + assess.
                # Never delegates, never triggers intents, never does RAG/search.
                # =============================================================
                email_prompt = (
                    "You are an email triage assistant. Analyse the following forwarded email "
                    "and produce a SHORT summary for the user. Your response MUST follow this "
                    "exact format:\n\n"
                    "IMPORTANCE: <low|medium|high|urgent>\n"
                    "SPAM: <yes|no>\n"
                    "FROM: <sender name and address>\n"
                    "SUBJECT: <subject line>\n"
                    "SUMMARY: <1-3 sentence summary of what the email is about>\n"
                    "ACTION: <any action items, or 'None'>\n\n"
                    "Rules:\n"
                    "- If the email is spam, marketing, automated notifications, or "
                    "newsletters, set SPAM to 'yes' and IMPORTANCE to 'low'.\n"
                    "- Do NOT draft a reply. Do NOT suggest sending emails.\n"
                    "- Do NOT delegate or create files.\n"
                    "- Be concise — this will be sent as a WhatsApp message.\n\n"
                    f"--- FORWARDED EMAIL ---\n{message}\n--- END ---"
                )
                try:
                    summary = self.send_to_api(email_prompt, api_endpoint)
                except Exception as exc:
                    self.update_log(f"[Email] LLM summarisation failed: {exc}")
                    return {"text": f"Error summarising email: {exc}", "files": []}

                if not summary:
                    return {"text": "Could not summarise email.", "files": []}

                # Parse importance and spam flag from the LLM response
                summary_lower = summary.lower()
                is_spam = "spam: yes" in summary_lower
                is_low = "importance: low" in summary_lower

                if is_spam:
                    self.update_log("[Email] Spam/marketing email — skipping notification")
                    self._append_chat_message("Assistant", f"[Spam — not forwarded] {summary}")
                    return {"text": summary, "files": []}

                # Save context for WhatsApp follow-up detection
                self._recent_email_context.append({
                    "raw_email": message,
                    "summary": summary,
                    "timestamp": datetime.now(),
                })

                # Notify user via WhatsApp and Slack
                wa_msg = f"📧 *New Email*\n\n{summary}"
                if not is_spam:
                    wa_msg += "\n\n_Reply here if you'd like me to respond to this email._"
                self._notify_via_whatsapp(wa_msg)
                self._notify_via_slack(wa_msg)
                self._append_chat_message("Assistant", summary)
                self.update_log(f"[Email] Summary sent to WhatsApp/Slack (importance: {'low' if is_low else 'medium+'})")
                return {"text": summary, "files": []}

            elif sender == "TaskTracker":
                wa_hint = (
                    "This message is a SCHEDULED TASK that has come due. Execute or "
                    "research what the task description asks for and provide a clear, "
                    "actionable result. Be thorough but concise.\n\n"
                )
            elif sender == "Calendar":
                wa_hint = (
                    "This message is a CALENDAR ALERT about an upcoming event. "
                    "Summarise the event details concisely for the user.\n\n"
                )

            # If the user wants files created from scratch (no attached files),
            # override the hint to encourage delegation so the team can produce
            # the actual files in the outbox folder.
            if wants_file_output and not file_context:
                wa_hint = (
                    "The user is requesting that documents or spreadsheets be CREATED. "
                    "This is a multi-stage project that MUST be delegated to the team. "
                    "Respond with a delegation JSON: {\"delegate\": true, \"tasks\": [...], "
                    "\"message\": \"brief explanation\"}. Each task should describe "
                    "a specific piece of work (research, document creation, etc.). "
                    "Do NOT try to answer this yourself — the team will handle "
                    "the research and file creation.\n\n"
                )
            # If the user wants a file, override the hint so the LLM
            # produces the full file content instead of a conversational reply.
            if wants_file_output and file_context:
                if has_images:
                    # Image-sourced: the attached content was extracted from
                    # an image via the vision API — instruct the LLM to
                    # produce a proper document from it.
                    if original_file_type == 'excel':
                        wa_hint = (
                            "This message came via WhatsApp. The user sent an image "
                            "and wants a spreadsheet created from its content. The "
                            "extracted image content is provided below. Produce the "
                            "FULL data as a markdown table (with | delimiters) so it "
                            "can be converted to an Excel file. Do NOT add any "
                            "commentary or notes after the content.\n\n"
                        )
                    elif original_file_type == 'csv':
                        wa_hint = (
                            "This message came via WhatsApp. The user sent an image "
                            "and wants CSV data created from its content. The "
                            "extracted image content is provided below. Produce the "
                            "FULL data in CSV format (comma-separated values). "
                            "Do NOT add any commentary or notes after the content.\n\n"
                        )
                    else:
                        wa_hint = (
                            "This message came via WhatsApp. The user sent an image "
                            "and wants a Word document created from its content. The "
                            "extracted image content is provided below. Produce the "
                            "FULL document content in well-formatted markdown so it "
                            "can be converted to a Word document. Reproduce the "
                            "content faithfully — preserve all text, structure, "
                            "headings, lists, and formatting from the original. "
                            "Do NOT add any commentary, summary, or notes — output "
                            "ONLY the document content itself.\n\n"
                        )
                else:
                    # Document-sourced: existing file modification flow
                    if original_file_type == 'excel':
                        wa_hint = (
                            "This message came via WhatsApp. The user wants you to modify "
                            "the attached spreadsheet and send it back. Produce the FULL "
                            "modified data as a markdown table (with | delimiters) so it "
                            "can be converted to an Excel file. Do NOT add any commentary, "
                            "summary of changes, or notes after the content.\n\n"
                        )
                    elif original_file_type == 'csv':
                        wa_hint = (
                            "This message came via WhatsApp. The user wants you to modify "
                            "the attached CSV data and send it back. Produce the FULL "
                            "modified data in CSV format (comma-separated values). "
                            "Do NOT add any commentary, summary of changes, or notes "
                            "after the content.\n\n"
                        )
                    elif original_file_type == 'text':
                        wa_hint = (
                            "This message came via WhatsApp. The user wants you to modify "
                            "the attached text file and send it back. Produce the FULL "
                            "modified text content. Do NOT add any commentary, summary "
                            "of changes, or notes after the content.\n\n"
                        )
                    else:
                        wa_hint = (
                            "This message came via WhatsApp. The user wants you to modify "
                            "the attached document and send it back. Produce the FULL "
                            "modified document content in well-formatted markdown so it "
                            "can be converted to a Word document. Do NOT add any "
                            "commentary, summary of changes, or notes after the document "
                            "content — output ONLY the document itself.\n\n"
                        )

            # =============================================================
            # INTENT GATES: detect task/email/calendar intents before
            # general triage. These are handled by specialised nodes.
            # Only for interactive senders (WhatsApp, console) — NOT for
            # forwarded notifications from Email/TaskTracker/Calendar.
            # =============================================================
            if sender not in ("Email", "TaskTracker", "Calendar"):
                intent_result = self._check_special_intents(
                    message, effective_message, sender, api_endpoint, output_files
                )
                if intent_result is not None:
                    return intent_result

            # =============================================================
            # HARD GATE: file-creation requests bypass ALL triage and go
            # directly to forced delegation.  This is deterministic — no
            # LLM decision, no RAG cache can override it.
            # =============================================================
            if wants_file_output and not file_context:
                print(f"[MCA-DIAG] HARD GATE: file-creation request detected — forcing delegation")
                self.update_log(f"[WA] File-creation request detected — forcing delegation")
                self._append_chat_message("Assistant", "Working on your project — delegating to the team...")
                forced_delegation = {
                    "delegate": True,
                    "tasks": [{"task": message}],
                    "message": "Delegating multi-stage file-creation project to team.",
                }
                results, created_file_paths = self._run_team_lead(forced_delegation)
                formatted = self._format_delegation_results(results)
                self._store_to_rag(effective_message, formatted)
                # Add created files to output so they can be sent back
                output_files.extend(created_file_paths)
                print(f"[MCA-DIAG] HARD GATE: output_files after team lead = {output_files}")

                if sender == "WhatsApp":
                    outbox = self._get_outbox_folder()
                    summary = self._summarize_delegation_for_wa(
                        message, formatted, outbox, api_endpoint
                    )
                    self._append_chat_message("Assistant", summary)
                    return {"text": summary, "files": output_files}

                self._append_chat_message("Assistant", formatted)
                return {"text": formatted, "files": output_files}

            # --- Complexity triage (use original text, not file content) ---
            complexity = self._assess_complexity(message)
            print(f"[MCA-DIAG] complexity={complexity}, wants_file_output={wants_file_output}")
            # Files, file-modification, or injected content (e.g. YouTube
            # transcript) bump complexity to at least medium so the LLM gets
            # RAG context and proper handling.
            if (files or wants_file_output or file_context) and complexity == 'simple':
                complexity = 'medium'
            self.update_log(f"Complexity: {complexity} — \"{message[:60]}\"")

            # SIMPLE: fast LLM, no RAG, no tools
            if complexity == 'simple':
                from datetime import datetime as _dt
                now = _dt.now()
                # Include recent chat history for conversational context
                recent_lines = []
                for h_msg in self.chat_history[-6:]:
                    role = h_msg.get("role", "user").capitalize()
                    content = h_msg.get("content", "")[:300]
                    recent_lines.append(f"{role}: {content}")
                history_block = "\n".join(recent_lines) + "\n" if recent_lines else ""
                personality_block = self._build_personality_prompt()
                permissions_block = self._build_permissions_prompt()
                fast_prompt = (
                    "You are a helpful AI assistant.\n\n"
                    f"{personality_block}"
                    f"{permissions_block}"
                    f"{wa_hint}"
                    f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
                    f"Current time: {now.strftime('%I:%M %p')}\n\n"
                    f"{history_block}"
                    f"User: {effective_message}\nAssistant:"
                )
                response = self.send_to_api(fast_prompt, api_endpoint)
                if response:
                    self._append_chat_message("Assistant", response)
                    self._trigger_reflection(message, response, api_endpoint)
                    return {"text": response, "files": output_files}

            # MEDIUM: Master handles directly with RAG + optional web search
            if complexity == 'medium':
                response = self._handle_medium_complexity(
                    effective_message, api_endpoint, wa_hint=wa_hint
                )
                if response:
                    self.update_log(f"Medium response ready ({len(response)} chars)")
                    # If this was a file modification/creation request, generate the output file
                    if wants_file_output and file_context:
                        base = "created" if has_images else "modified"
                        out_path = self._generate_wa_output_file(response, original_file_type, base)
                        if out_path:
                            output_files.append(out_path)
                    self._trigger_reflection(message, response, api_endpoint)
                    return {"text": response, "files": output_files}

            # COMPLEX: full pipeline with delegation
            print(f"[MCA-DIAG] Entering COMPLEX path — will build delegation prompt")
            rag_context = self._query_rag_for_context(effective_message)
            prompt = self._build_chat_prompt(
                effective_message, rag_context=rag_context, wa_hint=wa_hint
            )
            response = self.send_to_api(prompt, api_endpoint)

            # Handle delegation
            print(f"[MCA-DIAG] LLM response (first 300): {response[:300] if response else 'EMPTY'}")
            delegation = self._extract_delegation(response)
            print(f"[MCA-DIAG] delegation extracted: {delegation is not None}")
            if delegation:
                self._append_chat_message("Assistant", delegation.get('message') or "Delegation dispatched.")
                results, created_file_paths = self._run_team_lead(delegation)
                formatted = self._format_delegation_results(results)
                self._store_to_rag(effective_message, formatted)
                # Add created files to output so they can be sent back
                output_files.extend(created_file_paths)
                print(f"[MCA-DIAG] COMPLEX delegation: output_files after team lead = {output_files}")

                # For WhatsApp: return a concise summary instead of the
                # full delegation output (which may contain raw code/HTML).
                if sender == "WhatsApp":
                    outbox = self._get_outbox_folder()
                    summary = self._summarize_delegation_for_wa(
                        message, formatted, outbox, api_endpoint
                    )
                    self._append_chat_message("Assistant", summary)
                    return {"text": summary, "files": output_files}

                # For non-WhatsApp (UI chat): return full formatted results
                self._append_chat_message("Assistant", formatted)
                if wants_file_output:
                    base = "created" if has_images else "modified"
                    out_path = self._generate_wa_output_file(formatted, original_file_type, base)
                    if out_path:
                        output_files.append(out_path)
                return {"text": formatted, "files": output_files}

            # Handle clarification (return the questions as text)
            clarification = self._extract_clarification(response)
            if clarification:
                questions = clarification.get('questions') or []
                question_lines = "\n".join(f"{idx + 1}. {q}" for idx, q in enumerate(questions))
                reply = f"I have a few clarifying questions:\n{question_lines}"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # Direct answer
            self._append_chat_message("Assistant", response)
            if response and len(response.strip()) > 100:
                self._store_to_rag(effective_message, response)
            self._trigger_reflection(message, response, api_endpoint)
            # Generate output file if this was a file modification/creation request
            if wants_file_output and file_context:
                base = "created" if has_images else "modified"
                out_path = self._generate_wa_output_file(response, original_file_type, base)
                if out_path:
                    output_files.append(out_path)
            return {"text": response, "files": output_files}

        except Exception as exc:
            error_msg = f"Error processing message: {exc}"
            self._append_chat_message("System", error_msg)
            return {"text": error_msg, "files": []}

    def _trigger_reflection(self, user_message: str, assistant_response: str,
                             api_endpoint: str) -> None:
        """Fire personality self-reflection in a background thread."""
        if not assistant_response or len(assistant_response.strip()) < 20:
            return
        Thread(
            target=self._run_personality_reflection,
            args=(user_message, assistant_response, api_endpoint),
            daemon=True,
        ).start()

    # -- Conversational reference resolution ---------------------------------

    def _resolve_conversational_references(self, message: str,
                                            api_endpoint: str) -> str:
        """Expand vague conversational references using recent chat history
        and email context.  Returns the enriched message, or the original
        message unchanged if no references were detected.

        Examples resolved:
          'the same person'  → 'ethorup@gmail.com'
          'that email'       → the subject/recipient from context
          'him/her/them'     → the person from the last email exchange
        """
        # Quick check: does the message contain vague references?
        _ref_patterns = re.compile(
            r'\b(the\s+same\s+(person|guy|email|address|recipient)|'
            r'that\s+(same\s+)?(person|email|thread|address)|'
            r'(send|email)\s+(him|her|them)\b|'
            r'same\s+(email\s+)?(address|person|recipient))',
            re.IGNORECASE,
        )
        if not _ref_patterns.search(message):
            return message

        # Build recent conversation context (last 8 messages)
        recent_chat = []
        for msg in self.chat_history[-8:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Truncate long messages to keep the prompt manageable
            recent_chat.append(f"{role.capitalize()}: {content[:300]}")
        chat_context = "\n".join(recent_chat) if recent_chat else "(no recent conversation)"

        # Build email context
        email_context_lines = []
        cutoff = datetime.now() - timedelta(minutes=30)
        for ctx in self._recent_email_context:
            if ctx["timestamp"] > cutoff:
                addr = ctx.get("from_email", "unknown")
                subj = ctx.get("subject", "unknown")
                direction = "SENT TO" if ctx.get("is_outbound") else "RECEIVED FROM"
                email_context_lines.append(f"- {direction} {addr} | Subject: {subj}")
        email_ctx_str = "\n".join(email_context_lines) if email_context_lines else "(no recent emails)"

        resolve_prompt = (
            "The user's message contains vague references (like 'the same person', "
            "'that email', 'him/her/them'). Using the conversation history and "
            "recent email context below, rewrite the user's message by replacing "
            "ALL vague references with the actual concrete details (email addresses, "
            "names, subjects, etc.).\n\n"
            "IMPORTANT: Keep the user's intent and wording intact — only replace "
            "the vague parts. Output ONLY the rewritten message, nothing else.\n\n"
            f"--- RECENT CONVERSATION ---\n{chat_context}\n--- END ---\n\n"
            f"--- RECENT EMAILS ---\n{email_ctx_str}\n--- END ---\n\n"
            f"User's message: \"{message}\"\n\n"
            "Rewritten message:"
        )
        try:
            resolved = self.send_to_api(resolve_prompt, api_endpoint)
            if resolved and resolved.strip():
                resolved = resolved.strip().strip('"')
                self.update_log(f"[Context Resolution] \"{message[:60]}\" → \"{resolved[:60]}\"")
                return resolved
        except Exception:
            pass
        return message

    # -- Email follow-up detection ------------------------------------------

    def _check_email_followup(self, message: str, api_endpoint: str,
                               output_files: list) -> Optional[dict]:
        """Check if a WhatsApp message relates to a recent email notification.

        NEW APPROACH: Instead of intercepting the request and auto-sending,
        this method now:
        1. Handles pending draft confirmations (user said yes/no to a draft)
        2. Injects recent email context as a hint so the AI can reason about
           it naturally and ask the user what they want to do.
        3. Returns None so the request continues through the normal pipeline.

        The AI will see the email context in the prompt and can:
        - Answer the user's actual question (e.g. check calendar)
        - Offer to send a reply if appropriate
        - Ask the user what they'd like to do
        """

        # --- First, check if user is confirming/rejecting a pending draft ---
        if hasattr(self, '_pending_email_draft') and self._pending_email_draft:
            result = self._handle_pending_email_confirmation(
                message, api_endpoint, output_files
            )
            if result is not None:
                return result

        if not self._recent_email_context:
            return None

        # Only consider emails from the last 15 minutes
        cutoff = datetime.now() - timedelta(minutes=15)
        recent = [ctx for ctx in self._recent_email_context
                  if ctx["timestamp"] > cutoff]
        if not recent:
            return None

        # --- Inject email context as a hint into the message ---
        # This does NOT intercept the request. It just enriches the context
        # so the AI knows about recent emails when processing the message.
        # The AI can then decide what to do (answer a question, offer to
        # reply, etc.) based on the full context + permission registry.
        email_hint_parts = []
        for idx, ctx in enumerate(recent, 1):
            summary = ctx.get("summary", "")[:300]
            from_email = ctx.get("from_email", "unknown")
            subject = ctx.get("subject", "unknown")
            replies = ctx.get("replies", [])
            reply_note = f" ({len(replies)} reply(s) already sent)" if replies else ""
            email_hint_parts.append(
                f"Email #{idx}: From {from_email}, Subject: {subject}{reply_note}\n"
                f"Summary: {summary}"
            )
        email_hint = (
            "\n--- RECENT EMAIL CONTEXT (for reference only) ---\n"
            + "\n\n".join(email_hint_parts)
            + "\n--- END EMAIL CONTEXT ---\n"
            "NOTE: The user may or may not be referring to these emails. "
            "Do NOT assume the user wants to reply to an email unless they "
            "explicitly ask to reply, respond, or send a message to the sender. "
            "If the user's message could involve sending an email, ASK for "
            "confirmation first — do not send automatically.\n"
        )

        # Store the hint so it can be injected into the effective message
        # by the caller (process_external_message)
        self._email_context_hint = email_hint
        self.update_log(f"[Email Context] Injected {len(recent)} recent email(s) as context hint")

        # Do NOT intercept — let normal pipeline handle it
        return None

    def _handle_pending_email_confirmation(self, message: str,
                                            api_endpoint: str,
                                            output_files: list) -> Optional[dict]:
        """Handle user confirmation/rejection of a pending email draft."""
        pending = self._pending_email_draft
        if not pending:
            return None

        # Check if the pending draft has expired (5 minutes)
        if (datetime.now() - pending["timestamp"]).total_seconds() > 300:
            self._pending_email_draft = None
            return None  # Expired — continue normal flow

        msg_lower = message.strip().lower()

        # --- Confirmation patterns ---
        confirm_patterns = (
            'send it', 'send', 'yes', 'yeah', 'yep', 'yup', 'sure',
            'go ahead', 'looks good', 'looks great', 'perfect', 'do it',
            'approved', 'confirm', 'ok', 'okay', 'lgtm', 'ship it',
        )
        is_confirm = any(msg_lower.startswith(p) or msg_lower == p
                         for p in confirm_patterns)

        # --- Rejection patterns ---
        reject_patterns = (
            'no', 'nope', 'cancel', 'don\'t send', 'discard', 'stop',
            'never mind', 'nevermind', 'scratch that', 'abort',
        )
        is_reject = any(msg_lower.startswith(p) or msg_lower == p
                        for p in reject_patterns)

        if is_reject:
            self._pending_email_draft = None
            reply = "Email draft discarded. How can I help you?"
            self._append_chat_message("Assistant", reply)
            self._notify_via_whatsapp(reply)
            return {"text": reply, "files": output_files}

        if is_confirm:
            # Actually send the email now
            email_node = self._find_email_node()
            if not email_node:
                self._pending_email_draft = None
                reply = "Email node is not available — can't send the reply."
                self._append_chat_message("Assistant", reply)
                self._notify_via_whatsapp(reply)
                return {"text": reply, "files": output_files}

            result = email_node.send_email(
                to=pending["to"],
                subject=pending["subject"],
                body=pending["body"],
                reply_to_message_id=pending.get("message_id", ""),
            )

            matched_ctx = pending.get("matched_ctx")
            if result.get("success"):
                reply_history = matched_ctx.get("replies", []) if matched_ctx else []
                label = "Follow-up" if reply_history else "Reply"
                confirm = f"✅ {label} sent to {pending['to']}\n\nSubject: {pending['subject']}\n\n{pending['body'][:500]}"
                # Track this reply in the context for future follow-ups
                if matched_ctx:
                    if "replies" not in matched_ctx:
                        matched_ctx["replies"] = []
                    sent_msg_id = result.get("message_id", "")
                    matched_ctx["replies"].append({
                        "user_intent": pending["user_intent"],
                        "draft": pending["body"],
                        "sent_at": datetime.now().isoformat(),
                        "message_id": sent_msg_id,
                    })
                    if sent_msg_id:
                        matched_ctx["message_id"] = sent_msg_id
                    matched_ctx["timestamp"] = datetime.now()
            else:
                confirm = f"❌ Failed to send email: {result.get('error', 'unknown error')}"

            self._pending_email_draft = None
            self._append_chat_message("Assistant", confirm)
            self._notify_via_whatsapp(confirm)
            return {"text": confirm, "files": output_files}

        # Message is neither confirm nor reject — it might be an edit request
        # or a completely different topic. Clear the pending draft and let
        # normal flow handle it.
        self._pending_email_draft = None
        return None

    # -- Special intent detection & handling --------------------------------

    _TASK_INTENT_PATTERNS = re.compile(
        r'\b(remind\s+me|schedule\s+a\s+task|create\s+a\s+(recurring\s+)?task|'
        r'add\s+a\s+task|set\s+a\s+reminder|what\s+tasks?\s+do\s+i\s+have|'
        r'list\s+(my\s+)?tasks|show\s+(my\s+)?tasks|delete\s+task|'
        r'remove\s+task|pause\s+task|cancel\s+task|update\s+task)\b',
        re.IGNORECASE,
    )
    _EMAIL_INTENT_PATTERNS = re.compile(
        r'\b(send\s+an?\s+(email|message)\s+to|send\s+(an?\s+)?(email|message)|'
        r'write\s+an?\s+email|compose\s+an?\s+email|'
        r'email\s+\S+@\S+|message\s+\S+@\S+|'
        r'reply\s+to\s+(that|the|his|her)\s+(email|message)|'
        r'respond\s+to\s+(that|the)\s+(email|message)|'
        r'draft\s+a\s+(reply|response|email)|check\s+my\s+email|'
        r'what\s+emails?\s+do\s+i\s+have)\b',
        re.IGNORECASE,
    )
    _CALENDAR_INTENT_PATTERNS = re.compile(
        r"\b("
        # Query events / schedule  (allow "my work calendar", "my personal calendar", etc.)
        r"what('?s?|\s+is)\s+on\s+my\s+(\w+\s+)?calendar|my\s+schedule|my\s+(\w+\s+)?calendar|"
        r"what\s+meetings?\s+do\s+i\s+have|do\s+i\s+have\s+(any\s+)?(meetings?|events?)|"
        r"what\s+events?\s+do\s+i\s+have|upcoming\s+(meetings?|events?)|"
        r"what('?s?|\s+is)\s+(happening|coming\s+up)|am\s+i\s+free|"
        r"(what\s+(do\s+)?i\s+have|what('?s?|\s+is))\s+(going\s+on\s+)?(on\s+)?(my\s+)?"
        r"(schedule|calendar)|"
        # Availability / openings / free time queries
        r"calendar\s+openings|any\s+openings\s+on|"
        r"(when\s+am\s+i|am\s+i)\s+(available|free)|"
        r"(check|show|see)\s+(my\s+)?availability|"
        r"(any|some)\s+(free\s+time|open\s+slots?|openings?)\s+(on|for|this|next)|"
        r"do\s+i\s+have\s+(anything|something)\s+(on|for|this|next|the)|"
        r"(what|tell\s+me\s+what)\s+(do\s+)?i\s+have\s+(on|for|this|next|the)|"
        r"(what\s+are|show)\s+(my\s+)?openings|"
        # Create / schedule events
        r"schedule\s+a|add\s+(a\s+|an\s+)?(\w+\s+)?(meeting|event|appointment)|\bcalendar\s+event\b|"
        r"add\s+to\s+(my\s+)?(\w+\s+)?calendar|"
        r"put\s+(it\s+|this\s+)?on\s+(my\s+)?(\w+\s+)?calendar|"
        r"create\s+(a\s+|an\s+)?(\w+\s+)?(meeting|event|appointment|calendar)|"
        r"set\s+up\s+(a\s+)?(\w+\s+)?(meeting|event|call)|book\s+(a\s+)?(\w+\s+)?(meeting|room)|"
        # Cancel / delete / remove events (includes reminder)
        r"cancel\s+(my\s+|the\s+|a\s+)?(meeting|event|appointment|reminder)|"
        r"delete\s+(my\s+|the\s+|a\s+)?(meeting|event|appointment|reminder)|"
        r"remove\s+(my\s+|the\s+|a\s+|that\s+)?(\w+\s+)?"
        r"(meeting|event|appointment|reminder|calendar\s+reminder)|"
        # Reschedule / move events
        r"move\s+(my\s+|the\s+)?(meeting|event|appointment|reminder)|"
        r"reschedule\s+(my\s+|the\s+|a\s+)?(meeting|event|appointment|reminder)|"
        r"change\s+(my\s+|the\s+)?(meeting|event|appointment|reminder)|"
        # Attendees
        r"add\s+.{0,20}\s+to\s+(the\s+|my\s+)?(meeting|event|invite)|"
        r"invite\s+.{0,20}\s+to|add\s+attendee|"
        # Google Meet
        r"add\s+(a\s+)?google\s+meet|add\s+(a\s+)?video\s+(call|link|meeting)|"
        r"add\s+(a\s+)?meet\s+link|"
        # Recurring
        r"(daily|weekly|monthly|every\s+(day|week|month|monday|tuesday|wednesday|"
        r"thursday|friday|saturday|sunday))\s+.{0,30}(meeting|event|reminder)|"
        r"recurring\s+(meeting|event)|repeating\s+(meeting|event)|"
        # Calendar reminder (generic)
        r"calendar\s+reminder|"
        # Tasks
        r"(my\s+)?task\s*list|add\s+(a\s+)?task|"
        r"(what\s+are\s+)?my\s+tasks|show\s+(my\s+)?tasks|"
        r"add\s+to\s+(my\s+)?to.?do|to.?do\s+list|"
        r"mark\s+.{0,20}\s+(as\s+)?(done|complete|finished)|"
        r"complete\s+(the\s+|my\s+)?task|delete\s+(the\s+|my\s+|a\s+)?task"
        r")\b",
        re.IGNORECASE,
    )

    def _check_special_intents(self, message: str, effective_message: str,
                               sender: str, api_endpoint: str,
                               output_files: list) -> Optional[dict]:
        """Check if the message matches a task/email/calendar intent.
        Returns a response dict if handled, or None to continue normal flow."""
        msg_lower = message.lower()

        # --- Pending ambiguous intent resolution ---
        if self._pending_ambiguous_intents:
            pending = self._pending_ambiguous_intents
            # Expire after 5 minutes
            if (datetime.now() - pending["timestamp"]).total_seconds() > 300:
                self._pending_ambiguous_intents = None
            else:
                result = self._handle_ambiguous_response(
                    message, effective_message, sender, api_endpoint,
                    output_files, pending
                )
                if result is not None:
                    return result

        # --- Task management intent ---
        tracker = self._find_task_tracker_node()
        if tracker and self._TASK_INTENT_PATTERNS.search(message):
            return self._handle_task_intent(
                message, effective_message, sender, api_endpoint,
                output_files, tracker
            )

        # --- Storage / memory intent (must run BEFORE email to avoid false positives) ---
        _storage_intent = re.search(
            r'\b(store|save|remember|memorize|record|keep\s+track\s+of|'
            r'put\s+(this\s+|that\s+|it\s+)?in\s+(your|the)\s+(database|memory|storage|records)|'
            r'add\s+(this\s+|that\s+)?to\s+(your|the)\s+(database|memory|knowledge))\b',
            message, re.IGNORECASE,
        )
        if _storage_intent and re.search(
            r'\b(database|memory|storage|records|knowledge|brain)\b',
            message, re.IGNORECASE,
        ):
            return self._handle_storage_intent(
                message, effective_message, sender, api_endpoint, output_files
            )

        # =================================================================
        # MULTI-INTENT DETECTION: Collect all matching actionable intents
        # before committing to one. If multiple match, use the LLM to
        # disambiguate and ask the user which actions to take.
        # =================================================================
        detected_intents = []  # list of (intent_name, handler_args)

        # --- Calendar intent ---
        cal_node = self._find_calendar_node()
        cal_match = False
        if cal_node:
            cal_match = bool(self._CALENDAR_INTENT_PATTERNS.search(message))
            if not cal_match:
                _has_calendar_context = any(
                    kw in msg_lower for kw in [
                        "event", "meeting", "appointment", "calendar",
                        "reminder", "schedule", "task list",
                    ]
                )
                _has_contextual_ref = re.search(
                    r'\b(scratch\s+that|delete\s+(that|it|the)|'
                    r'cancel\s+(that|it|the)|remove\s+(that|it|the)|'
                    r'make\s+(it|that)\s+(recurring|weekly|daily|monthly|repeating)|'
                    r'set\s+(it|that)\s+(as|to)\s+(weekly|daily|monthly|recurring|repeating)|'
                    r'add\s+(a\s+)?(meet|google\s+meet|video)\s+(to\s+(it|that))?|'
                    r'(change|update|modify)\s+(it|that|the))\b',
                    message, re.IGNORECASE,
                )
                _recent_calendar_chat = False
                for msg in self.chat_history[-4:]:
                    content = msg.get("content", "").lower()
                    if any(kw in content for kw in [
                        "event created", "event cancelled", "event rescheduled",
                        "calendar", "task added", "google meet",
                    ]):
                        _recent_calendar_chat = True
                        break
                if (_has_calendar_context and _has_contextual_ref) or \
                   (_recent_calendar_chat and _has_contextual_ref):
                    cal_match = True
            if cal_match:
                detected_intents.append(("calendar", {
                    "cal_node": cal_node,
                }))

        # --- Deletion / forget intent (RAG database) ---
        _deletion_intent = re.search(
            r'\b(delete|remove|forget|erase|purge|wipe|drop)\b.*'
            r'\b(database|memory|storage|records|knowledge|brain)\b|'
            r'\b(database|memory|storage|records|knowledge|brain)\b.*'
            r'\b(delete|remove|forget|erase|purge|wipe|drop)\b|'
            r'\b(forget\s+.{0,20}\s*about|forget\s+(that|them|him|her|it|this|those)|'
            r'delete\s+(that|those|this|them|any|all|every)|'
            r'remove\s+(that|those|this|them|any|all|every)|'
            r'erase\s+(that|those|this|them|any|all|every)|'
            r'you\s+can\s+(delete|remove|forget)|'
            r'(delete|remove|forget|erase).{0,30}\b(regarding|about|concerning|related\s+to)\b|'
            r'forget\s+everything)\b',
            message, re.IGNORECASE,
        )
        if _deletion_intent:
            detected_intents.append(("deletion", {}))

        # --- Email action intent ---
        email_node = self._find_email_node()
        email_match = False
        if email_node:
            email_match = bool(self._EMAIL_INTENT_PATTERNS.search(message))
            # Fallback: message contains an email address + a sending verb
            # NOTE: "email" as a noun (e.g. "whose email is", "email address",
            # "their email is") must NOT count as a sending verb.
            if not email_match:
                has_email_addr = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', message)
                has_send_verb = re.search(
                    r'\b(send|message|write\s+to|notify|contact|reach\s+out)\b',
                    message, re.IGNORECASE
                )
                if not has_send_verb:
                    email_as_verb = re.search(
                        r'\bemail\b', message, re.IGNORECASE
                    )
                    if email_as_verb:
                        email_as_noun = re.search(
                            r'\b(whose|their|his|her|my|your|the|an?)\s+email\s+(is|address|:)|'
                            r'email\s+(is|address\s+is|:)',
                            message, re.IGNORECASE
                        )
                        if email_as_verb and not email_as_noun:
                            has_send_verb = email_as_verb
                if has_email_addr and has_send_verb:
                    email_match = True
            if email_match:
                detected_intents.append(("email", {
                    "email_node": email_node,
                }))

        # =================================================================
        # AMBIGUITY RESOLUTION: If multiple actionable intents detected,
        # ask the LLM to figure out what the user actually wants and
        # present options for confirmation.
        # =================================================================
        if len(detected_intents) > 1:
            result = self._resolve_ambiguous_intents(
                message, effective_message, sender, api_endpoint,
                output_files, detected_intents
            )
            if result is not None:
                return result

        # --- Single intent: dispatch directly ---
        if len(detected_intents) == 1:
            intent_name, intent_args = detected_intents[0]
            if intent_name == "calendar":
                return self._handle_calendar_intent(
                    message, effective_message, sender, api_endpoint,
                    output_files, intent_args["cal_node"]
                )
            elif intent_name == "deletion":
                result = self._handle_deletion_intent(
                    message, effective_message, sender, api_endpoint, output_files
                )
                if result:
                    return result
            elif intent_name == "email":
                return self._handle_email_intent(
                    message, effective_message, sender, api_endpoint,
                    output_files, intent_args["email_node"]
                )

        # --- Personality adjustment intent ---
        # Match personality-related adjectives AND trait names so users can say
        # "turn up your humor" or "be more verbose" and both work.
        _personality_adj = (
            r'casual|formal|funny|serious|concise|verbose|detailed|brief|warm|cold|'
            r'friendly|professional|sarcastic|polite|blunt|creative|analytical|'
            r'enthusiastic|reserved|playful|dry|witty|empathetic|direct|gentle|'
            r'humorous|terse|chatty|succinct|wordy'
        )
        _personality_trait = (
            r'humor|formality|verbosity|empathy|proactivity|confidence'
        )
        _personality_keyword = _personality_adj + r'|' + _personality_trait
        _personality_patterns = re.search(
            r'\b(be\s+more\s+(' + _personality_adj + r')'
            r'|be\s+less\s+(' + _personality_adj + r')'
            r'|tone\s+(it\s+)?down|tone\s+(it\s+)?up'
            r'|more\s+(' + _personality_adj + r')'
            r'|less\s+(' + _personality_adj + r')'
            r'|change\s+your\s+(personality|tone|style)|adjust\s+your\s+(personality|tone|style)'
            r'|act\s+more\s+(' + _personality_adj + r')'
            r'|sound\s+more\s+(' + _personality_adj + r')'
            r'|what\s+is\s+your\s+(personality|name)|what\s+are\s+your\s+traits'
            # "turn up/down your humor", "turn your verbosity up"
            r'|turn\s+(up|down)\s+.{0,20}\b(' + _personality_keyword + r')'
            r'|turn\s+.{0,20}\b(' + _personality_keyword + r')\s+(up|down)'
            # "crank/dial/bump/increase/decrease the humor"
            r'|(crank|dial|bump|increase|decrease|raise|lower)\s+.{0,15}\b(' + _personality_keyword + r')'
            # "set humor to 8", "set your verbosity to 0.7"
            r'|set\s+.{0,20}\b(' + _personality_keyword + r')\s+(to|at)\s+\d'
            # Direct trait name + "characteristic/trait/setting" + adjustment
            r'|(' + _personality_trait + r')\s+(characteristic|trait|setting|level)\s+.{0,10}(up|down|\d))\b',
            message, re.IGNORECASE,
        )
        if _personality_patterns:
            result = self._handle_personality_adjustment(message, api_endpoint, output_files)
            if result is not None:
                return result

        # --- Permission management intent ---
        _permission_patterns = re.search(
            r'\b(you\s+can|you\s+may|you\s+are\s+allowed|go\s+ahead\s+and|'
            r'feel\s+free\s+to|you\s+don.t\s+need\s+to\s+ask|'
            r'don.t\s+ask\s+(me\s+)?(before|about)|stop\s+asking\s+(me\s+)?(before|about)|'
            r'no\s+need\s+to\s+ask|without\s+(my\s+)?(approval|permission|asking)|'
            r'always\s+ask\s+(me\s+)?(before|first)|'
            r'don.t\s+(send|create|delete|schedule|do)|'
            r'never\s+(send|create|delete|schedule)|'
            r'stop\s+(sending|creating|deleting|scheduling)|'
            r'what\s+(are\s+)?your\s+permissions|show\s+(me\s+)?your\s+permissions|'
            r'what\s+can\s+you\s+do\s+without\s+asking|'
            r'permission\s*(settings?|list|registry))\b',
            message, re.IGNORECASE,
        )
        if _permission_patterns:
            result = self._handle_permission_intent(
                message, api_endpoint, output_files
            )
            if result is not None:
                return result

        return None  # No special intent detected

    def _handle_storage_intent(self, message: str, effective_message: str,
                               sender: str, api_endpoint: str,
                               output_files: list) -> dict:
        """Handle explicit 'store/remember this' requests by extracting facts
        and saving them to the RAG database with structured tags."""
        extract_prompt = (
            "The user wants to store personal information in the assistant's "
            "memory/database. Extract ALL discrete facts from the message below "
            "and return them as a JSON array of objects.\n\n"
            "Each object should have:\n"
            '  {"fact": "<the fact>", "category": "<category>"}\n\n'
            "Categories: user_profile, contact_info, company_info, preference, "
            "relationship, general_fact\n\n"
            "Return ONLY the JSON array, no commentary.\n\n"
            f"User message: {message}\n\nJSON:"
        )
        try:
            resp = self.send_to_api(extract_prompt, api_endpoint)
            self.update_log(f"[Storage] LLM response: {resp[:500] if resp else '(empty)'}")
            # Parse JSON — handle both arrays and objects
            facts = None
            if resp:
                cleaned = resp.strip()
                # Strip markdown fences
                if cleaned.startswith("```"):
                    first_nl = cleaned.find("\n")
                    last_fence = cleaned.rfind("```")
                    if first_nl > 0 and last_fence > first_nl:
                        cleaned = cleaned[first_nl + 1:last_fence].strip()
                # Try array first, then object
                arr_start = cleaned.find("[")
                arr_end = cleaned.rfind("]")
                obj_start = cleaned.find("{")
                obj_end = cleaned.rfind("}")
                try:
                    if arr_start != -1 and arr_end > arr_start:
                        facts = json.loads(cleaned[arr_start:arr_end + 1])
                    elif obj_start != -1 and obj_end > obj_start:
                        facts = json.loads(cleaned[obj_start:obj_end + 1])
                except json.JSONDecodeError as je:
                    self.update_log(f"[Storage] JSON parse error: {je}")
            if not isinstance(facts, list):
                facts = [facts] if isinstance(facts, dict) else []
            self.update_log(f"[Storage] Extracted {len(facts)} fact(s)")

            stored_count = 0
            stored_items = []
            for fact_obj in facts:
                if not isinstance(fact_obj, dict):
                    continue
                fact_text = fact_obj.get("fact", "").strip()
                category = fact_obj.get("category", "general_fact").strip()
                if not fact_text:
                    continue
                try:
                    manager, db_name = self._get_db_manager()
                    content = f"User Fact ({category}): {fact_text}"
                    manager.add_text_content(
                        db_name, content,
                        source_label="user_stored_fact",
                        tags=["user_fact", category],
                        max_content_length=2000,
                    )
                    stored_count += 1
                    stored_items.append(f"• {fact_text}")
                except Exception as exc:
                    self.update_log(f"[Storage] Error storing fact: {exc}")

            if stored_count > 0:
                items_str = "\n".join(stored_items)
                reply = (
                    f"✅ Stored {stored_count} fact(s) in my database:\n\n"
                    f"{items_str}\n\n"
                    "I'll remember this information for future conversations."
                )
            else:
                reply = "I understood you want me to store some information, but I couldn't extract any specific facts. Could you rephrase what you'd like me to remember?"

        except Exception as exc:
            self.update_log(f"[Storage] Error: {exc}")
            reply = f"I tried to store that information but ran into an error: {exc}"

        self._append_chat_message("Assistant", reply)
        return {"text": reply, "files": output_files}

    def _handle_permission_intent(self, message: str, api_endpoint: str,
                                   output_files: list) -> Optional[dict]:
        """Handle natural language permission management requests.
        Uses the LLM to parse what the user wants to allow/restrict,
        then updates the permission registry."""
        try:
            # Build current permissions summary for the LLM
            actions = self._permissions.get("actions", {})
            current_perms = []
            for action_id, entry in actions.items():
                current_perms.append(
                    f"  - {action_id}: {entry.get('description', '')} "
                    f"[status: {entry.get('status', 'ask')}]"
                )
            perms_str = "\n".join(current_perms)

            parse_prompt = (
                "You are parsing a user's request to view or change AI action permissions. "
                "The permission registry controls what the AI can do without asking.\n\n"
                "CURRENT PERMISSIONS:\n"
                f"{perms_str}\n\n"
                "Each action can have one of these statuses:\n"
                "- 'allowed': AI can do this without asking\n"
                "- 'ask': AI must ask the user for confirmation first\n"
                "- 'denied': AI must never do this\n\n"
                f"User's message: \"{message}\"\n\n"
                "Respond with ONLY a JSON object:\n"
                "{\n"
                '  "intent": "view" or "update",\n'
                '  "changes": [\n'
                '    {"action": "action_id", "new_status": "allowed|ask|denied", '
                '"reason": "brief reason"}\n'
                "  ]\n"
                "}\n\n"
                "RULES:\n"
                "- If the user just wants to see permissions, return intent='view' "
                "with empty changes.\n"
                "- Map the user's natural language to the closest action_id from "
                "the list above.\n"
                "- 'you can send emails without asking' → send_email: allowed\n"
                "- 'always ask before sending emails' → send_email: ask\n"
                "- 'don't ever delete from my database' → delete_from_database: denied\n"
                "- 'you can schedule meetings without asking' → create_calendar_event: allowed\n"
                "- 'stop sending emails without my permission' → send_email: ask\n"
                "- If the user mentions replying to emails specifically, use "
                "send_email_reply.\n"
                "- If unsure which action, default to the most restrictive "
                "interpretation.\n\n"
                "JSON:"
            )

            response = self.send_to_api(parse_prompt, api_endpoint)
            if not response:
                return None

            # Parse the JSON
            text = response.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:])
                if text.rstrip().endswith('```'):
                    text = text.rstrip()[:-3].rstrip()
            start = text.find('{')
            end = text.rfind('}')
            if start == -1 or end == -1:
                return None
            parsed = json.loads(text[start:end + 1])

            intent = parsed.get("intent", "view")
            changes = parsed.get("changes", [])

            if intent == "view" or not changes:
                # Show current permissions
                lines = ["Here are my current action permissions:\n"]
                for action_id, entry in actions.items():
                    status = entry.get("status", "ask")
                    desc = entry.get("description", "")
                    icon = {"allowed": "✅", "ask": "❓", "denied": "🚫"}.get(status, "❓")
                    label = action_id.replace("_", " ").title()
                    lines.append(f"{icon} **{label}**: {desc} — *{status}*")
                lines.append(
                    "\nYou can change these by telling me things like:\n"
                    "• 'You can send emails without asking me'\n"
                    "• 'Always ask before scheduling meetings'\n"
                    "• 'Never delete from my database'"
                )
                reply = "\n".join(lines)
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # Apply changes
            applied = []
            for change in changes:
                action = change.get("action", "")
                new_status = change.get("new_status", "")
                reason = change.get("reason", "")
                if not action or not new_status:
                    continue
                if self._update_permission(action, new_status, reason):
                    label = action.replace("_", " ").title()
                    icon = {"allowed": "✅", "ask": "❓", "denied": "🚫"}.get(new_status, "❓")
                    applied.append(f"{icon} **{label}** → *{new_status}*")
                    self.update_log(f"[Permissions] {action}: → {new_status} ({reason})")

            if applied:
                changes_str = "\n".join(applied)
                reply = f"Permission settings updated:\n\n{changes_str}"
            else:
                reply = "I understood you want to change permissions, but I couldn't determine what to change. Try something like 'you can send emails without asking me' or 'always ask before scheduling meetings'."

            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        except Exception as exc:
            self.update_log(f"[Permissions] Error handling permission intent: {exc}")
            return None

    def _resolve_ambiguous_intents(self, message: str, effective_message: str,
                                    sender: str, api_endpoint: str,
                                    output_files: list,
                                    detected_intents: list) -> Optional[dict]:
        """When multiple actionable intents are detected (e.g. calendar + email),
        use the LLM to understand what the user actually wants and present
        options for confirmation instead of guessing."""
        try:
            intent_names = [name for name, _ in detected_intents]
            intent_labels = {
                "calendar": "Create/modify a calendar event",
                "email": "Send an email",
                "deletion": "Delete information from the database",
            }
            # Build permission context for each detected intent
            perm_map = {
                "calendar": "create_calendar_event",
                "email": "send_email",
                "deletion": "delete_from_database",
            }
            perm_notes = []
            for name in intent_names:
                perm_action = perm_map.get(name, "")
                if perm_action:
                    status = self._check_permission(perm_action)
                    perm_notes.append(
                        f"  - {intent_labels.get(name, name)}: permission={status}"
                    )

            intents_str = "\n".join(
                f"  - {intent_labels.get(n, n)}" for n in intent_names
            )
            perms_str = "\n".join(perm_notes) if perm_notes else "  (no permission data)"

            disambig_prompt = (
                "You are a helpful AI assistant. The user sent a message that "
                "could involve MULTIPLE actions. Your job is to figure out what "
                "the user actually wants and ask them to confirm.\n\n"
                f"User's message: \"{message}\"\n\n"
                f"Detected possible actions:\n{intents_str}\n\n"
                f"Permission status for each action:\n{perms_str}\n\n"
                "INSTRUCTIONS:\n"
                "- Analyse the user's message carefully.\n"
                "- Determine which action(s) the user ACTUALLY wants.\n"
                "- If the user clearly wants only ONE action, say which one "
                "and ask for confirmation.\n"
                "- If the user might want MULTIPLE actions (e.g. create a "
                "calendar event AND email someone about it), present the "
                "options clearly and ask which combination they'd like.\n"
                "- For any action with permission='ask', you MUST get "
                "confirmation before proceeding.\n"
                "- Be concise and conversational. Present numbered options "
                "if there are multiple possibilities.\n"
                "- IMPORTANT: An email address in the message does NOT mean "
                "the user wants to send an email. It could be an attendee "
                "for a calendar event, a contact reference, etc.\n\n"
                "Respond with a short, clear message to the user asking "
                "what they'd like to do:"
            )

            response = self.send_to_api(disambig_prompt, api_endpoint)
            if not response:
                return None

            self._append_chat_message("Assistant", response)
            self._notify_via_whatsapp(response)

            # Store the detected intents so the next message can be routed
            # to the correct handler based on the user's choice
            self._pending_ambiguous_intents = {
                "intents": detected_intents,
                "original_message": message,
                "effective_message": effective_message,
                "timestamp": datetime.now(),
            }

            return {"text": response, "files": output_files}

        except Exception as exc:
            self.update_log(f"[Ambiguity] Error resolving intents: {exc}")
            return None

    def _handle_ambiguous_response(self, message: str, effective_message: str,
                                    sender: str, api_endpoint: str,
                                    output_files: list,
                                    pending: dict) -> Optional[dict]:
        """Process the user's response to an ambiguity question.
        Determines which action(s) the user chose and dispatches accordingly."""
        try:
            intents = pending["intents"]
            original_message = pending["original_message"]
            original_effective = pending["effective_message"]
            intent_names = [name for name, _ in intents]
            intent_labels = {
                "calendar": "Create/modify a calendar event",
                "email": "Send an email",
                "deletion": "Delete information from the database",
            }

            intents_str = "\n".join(
                f"  {i+1}. {intent_labels.get(n, n)}" for i, n in enumerate(intent_names)
            )

            route_prompt = (
                "The user was asked to clarify which action(s) they want. "
                "Based on their response, determine which action(s) to execute.\n\n"
                f"Original request: \"{original_message}\"\n\n"
                f"Available actions:\n{intents_str}\n\n"
                f"User's clarification: \"{message}\"\n\n"
                "Respond with ONLY a JSON object:\n"
                "{\n"
                '  "actions": ["calendar", "email", "deletion"],\n'
                '  "is_new_topic": false\n'
                "}\n\n"
                "RULES:\n"
                "- 'actions' should list ONLY the action(s) the user chose.\n"
                "- If the user wants BOTH calendar and email, include both.\n"
                "- If the user says 'just the calendar' or 'option 1', include "
                "only that action.\n"
                "- If the user's response is completely unrelated to the "
                "original question (new topic), set is_new_topic=true and "
                "actions=[].\n"
                "- Map numbered responses to the action list above.\n\n"
                "JSON:"
            )

            response = self.send_to_api(route_prompt, api_endpoint)
            self._pending_ambiguous_intents = None  # Clear regardless

            if not response:
                return None

            # Parse JSON
            text = response.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:])
                if text.rstrip().endswith('```'):
                    text = text.rstrip()[:-3].rstrip()
            start = text.find('{')
            end = text.rfind('}')
            if start == -1 or end == -1:
                return None
            parsed = json.loads(text[start:end + 1])

            chosen_actions = parsed.get("actions", [])
            is_new_topic = parsed.get("is_new_topic", False)

            if is_new_topic or not chosen_actions:
                # User changed topic — let normal flow handle it
                return None

            # Build a lookup of intent args
            intent_map = {name: args for name, args in intents}

            # Execute chosen actions sequentially using the ORIGINAL message
            results = []
            for action in chosen_actions:
                if action == "calendar" and "calendar" in intent_map:
                    result = self._handle_calendar_intent(
                        original_message, original_effective, sender,
                        api_endpoint, output_files,
                        intent_map["calendar"]["cal_node"]
                    )
                    if result:
                        results.append(result.get("text", ""))
                elif action == "email" and "email" in intent_map:
                    result = self._handle_email_intent(
                        original_message, original_effective, sender,
                        api_endpoint, output_files,
                        intent_map["email"]["email_node"]
                    )
                    if result:
                        results.append(result.get("text", ""))
                elif action == "deletion" and "deletion" in intent_map:
                    result = self._handle_deletion_intent(
                        original_message, original_effective, sender,
                        api_endpoint, output_files
                    )
                    if result:
                        results.append(result.get("text", ""))

            if results:
                combined = "\n\n".join(results)
                return {"text": combined, "files": output_files}

            return None

        except Exception as exc:
            self.update_log(f"[Ambiguity] Error handling response: {exc}")
            self._pending_ambiguous_intents = None
            return None

    def _handle_deletion_intent(self, message: str, effective_message: str,
                                sender: str, api_endpoint: str,
                                output_files: list) -> Optional[dict]:
        """Handle requests to delete/forget information from the RAG database.
        Searches for matching entries, uses LLM to confirm which to remove,
        then deletes them."""
        try:
            api_endpoint = api_endpoint or self._get_chat_api_endpoint()
            manager, db_name = self._get_db_manager()

            # 1. Search RAG for content related to the deletion request
            search_results = manager.search(db_name, message, top_k=15)
            if not search_results:
                reply = "I searched my database but couldn't find any entries matching what you want me to forget. Could you be more specific about what to remove?"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # 2. Build a summary of found entries for the LLM to evaluate
            entries_summary = []
            for i, result in enumerate(search_results):
                content_preview = result.get("content", "")[:200].replace("\n", " ")
                doc_id = result.get("doc_id", "unknown")
                source = result.get("source", "unknown")
                similarity = result.get("similarity", 0.0)
                entries_summary.append(
                    f"  [{i}] doc_id={doc_id} | source={source} | "
                    f"sim={similarity:.3f} | content: {content_preview}"
                )
            entries_text = "\n".join(entries_summary)

            # 3. Ask LLM which entries match the deletion request
            identify_prompt = (
                "The user wants to delete specific information from the AI's memory database. "
                "Given the user's request and the database entries below, identify which entries "
                "should be deleted.\n\n"
                "Respond with ONLY a JSON object (no markdown fences):\n"
                "{\n"
                '  "indices_to_delete": [0, 2, 5],\n'
                '  "reason": "brief explanation of what is being deleted"\n'
                "}\n\n"
                "RULES:\n"
                "- Only select entries that clearly match what the user wants removed\n"
                "- If no entries match, return an empty array\n"
                "- Be conservative — don't delete entries the user didn't ask about\n\n"
                f"USER REQUEST: {message}\n\n"
                f"DATABASE ENTRIES:\n{entries_text}\n\nJSON:"
            )

            resp = self._low_temp_api_call(identify_prompt, api_endpoint)
            if not resp:
                reply = "I tried to process your deletion request but couldn't determine which entries to remove. Could you try rephrasing?"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # Parse LLM response
            cleaned = resp.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                last_fence = cleaned.rfind("```")
                if first_nl > 0 and last_fence > first_nl:
                    cleaned = cleaned[first_nl + 1:last_fence].strip()
            obj_start = cleaned.find("{")
            obj_end = cleaned.rfind("}")
            parsed = None
            if obj_start != -1 and obj_end > obj_start:
                try:
                    parsed = json.loads(cleaned[obj_start:obj_end + 1])
                except json.JSONDecodeError:
                    pass

            if not parsed or not parsed.get("indices_to_delete"):
                reply = "I looked through my database but couldn't find entries matching what you want me to forget. Could you be more specific?"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            indices = parsed["indices_to_delete"]
            reason = parsed.get("reason", "User requested deletion")

            # 4. Collect unique doc_ids to delete
            doc_ids_to_delete = set()
            deleted_previews = []
            for idx in indices:
                if 0 <= idx < len(search_results):
                    result = search_results[idx]
                    doc_id = result.get("doc_id")
                    if doc_id:
                        doc_ids_to_delete.add(doc_id)
                        preview = result.get("content", "")[:80].replace("\n", " ")
                        deleted_previews.append(f"• {preview}...")

            if not doc_ids_to_delete:
                reply = "I couldn't identify the specific entries to remove. Could you try describing what you'd like me to forget?"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # 5. Delete the documents by doc_id
            deleted_count = 0
            documents = manager._load_documents_index(db_name)
            chunk_metadata = manager._load_chunk_metadata(db_name)

            for doc_id in doc_ids_to_delete:
                # Find the document source name for logging
                doc_record = next(
                    (d for d in documents if d.get("doc_id") == doc_id), None
                )
                source_name = doc_record.get("source", doc_id) if doc_record else doc_id

                # Remove from documents index and chunk metadata
                orig_doc_count = len(documents)
                orig_chunk_count = len(chunk_metadata)
                documents = [d for d in documents if d.get("doc_id") != doc_id]
                chunk_metadata = [c for c in chunk_metadata if c.get("doc_id") != doc_id]

                if len(documents) < orig_doc_count or len(chunk_metadata) < orig_chunk_count:
                    deleted_count += 1
                    self.update_log(f"[Deletion] Removed doc_id={doc_id} ({source_name})")

            if deleted_count > 0:
                # Save updated indexes and rebuild FAISS
                manager._save_documents_index(db_name, documents)
                manager._save_chunk_metadata(db_name, chunk_metadata)
                manager._rebuild_faiss_index(db_name, chunk_metadata)

                previews_str = "\n".join(deleted_previews[:5])
                reply = (
                    f"Done! I've removed {deleted_count} entry/entries from my database:\n\n"
                    f"{previews_str}\n\n"
                    f"Reason: {reason}"
                )
                self.update_log(
                    f"[Deletion] Successfully removed {deleted_count} entries. "
                    f"Reason: {reason}"
                )
            else:
                reply = "I tried to remove those entries but they may have already been deleted. My database is up to date."

        except Exception as exc:
            self.update_log(f"[Deletion] Error: {exc}")
            reply = f"I ran into an error trying to delete from my database: {exc}"

        self._append_chat_message("Assistant", reply)
        return {"text": reply, "files": output_files}

    def _handle_task_intent(self, message: str, effective_message: str,
                            sender: str, api_endpoint: str,
                            output_files: list, tracker) -> dict:
        """Handle task management intents via LLM parsing."""
        msg_lower = message.lower()

        # --- List / show tasks ---
        if any(kw in msg_lower for kw in ['list', 'show', 'what task']):
            summary = tracker.get_task_summary()
            self._append_chat_message("Assistant", summary)
            if sender == "WhatsApp":
                self._notify_via_whatsapp(summary)
            return {"text": summary, "files": output_files}

        # --- Delete / remove / cancel / pause task ---
        if any(kw in msg_lower for kw in ['delete task', 'remove task',
                                           'cancel task', 'pause task']):
            # Use LLM to identify which task
            tasks = tracker.list_tasks(status="active")
            if not tasks:
                reply = "You don't have any active tasks to modify."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            task_list = "\n".join(
                f"- ID: {t['id'][:8]} | Title: {t['title']}"
                for t in tasks
            )
            parse_prompt = (
                "The user wants to modify a task. Match their request to one of "
                "these tasks and respond with ONLY a JSON object:\n"
                '{"action": "delete"|"pause", "task_id": "full-uuid"}\n\n'
                f"Available tasks:\n{task_list}\n\n"
                f"User request: {message}\n\nJSON:"
            )
            resp = self.send_to_api(parse_prompt, api_endpoint)
            parsed = self._extract_json_payload(resp)
            if isinstance(parsed, dict) and parsed.get("task_id"):
                # Find full ID
                short_id = parsed["task_id"]
                full_task = None
                for t in tasks:
                    if t["id"].startswith(short_id) or t["id"] == short_id:
                        full_task = t
                        break
                if full_task:
                    action = parsed.get("action", "delete")
                    if action == "pause":
                        tracker.update_task(full_task["id"], {"status": "paused"})
                        reply = f"Task paused: {full_task['title']}"
                    else:
                        tracker.remove_task(full_task["id"])
                        reply = f"Task removed: {full_task['title']}"
                    self._append_chat_message("Assistant", reply)
                    return {"text": reply, "files": output_files}

            reply = "I couldn't identify which task you mean. Try 'list my tasks' to see them."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # --- Create / add / remind / schedule task ---
        parse_prompt = (
            "Parse the user's request into a task definition. Respond with ONLY "
            "a JSON object (no commentary):\n"
            "{\n"
            '  "title": "short task title",\n'
            '  "description": "detailed instructions for the agent to execute",\n'
            '  "schedule_type": "once|daily|hourly|weekly",\n'
            '  "schedule_value": "time or schedule expression",\n'
            '  "notify_via": "whatsapp|email|log",\n'
            '  "priority": "low|medium|high|critical",\n'
            '  "category": "optional category"\n'
            "}\n\n"
            "Schedule value examples:\n"
            "- once: '2026-02-15 09:00'\n"
            "- daily: '09:00'\n"
            "- hourly: '30' (minutes past) or '*/2' (every 2 hours)\n"
            "- weekly: 'mon,wed,fri 09:00'\n\n"
            f"Current date/time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"User request: {message}\n\nJSON:"
        )
        resp = self.send_to_api(parse_prompt, api_endpoint)
        parsed = self._extract_json_payload(resp)

        if isinstance(parsed, dict) and parsed.get("title"):
            task = tracker.add_task(parsed)
            next_run = task.get("next_run", "unscheduled")
            if next_run:
                try:
                    dt = datetime.fromisoformat(next_run)
                    next_run = dt.strftime("%A, %B %d at %I:%M %p")
                except ValueError:
                    pass
            reply = (
                f"Task created: {task['title']}\n"
                f"Schedule: {task['schedule_type']} {task['schedule_value']}\n"
                f"Next run: {next_run}\n"
                f"Notify via: {task['notify_via']}"
            )
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # Fallback: couldn't parse
        reply = "I had trouble understanding that task request. Could you rephrase it?"
        self._append_chat_message("Assistant", reply)
        return {"text": reply, "files": output_files}

    def _handle_email_intent(self, message: str, effective_message: str,
                             sender: str, api_endpoint: str,
                             output_files: list, email_node) -> dict:
        """Handle email action intents (send, reply, check)."""
        msg_lower = message.lower()

        # --- Check email ---
        if any(kw in msg_lower for kw in ['check my email', 'what email']):
            recent = email_node.get_recent_emails(5)
            if not recent:
                reply = "No recent emails in the buffer. The inbox poller will pick up new messages automatically."
            else:
                lines = []
                for em in recent:
                    lines.append(f"- From: {em['from']}\n  Subject: {em['subject']}")
                reply = f"Recent emails ({len(recent)}):\n" + "\n".join(lines)
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # --- Reply to an email ---
        if any(kw in msg_lower for kw in ['reply to', 'respond to', 'draft a reply',
                                           'draft a response']):
            # Find the email to reply to
            last_email = email_node.get_last_email()
            if not last_email:
                reply = "I don't have any recent emails to reply to."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # Use LLM to draft the reply
            draft_prompt = (
                "Draft a professional email reply based on the user's instructions.\n"
                "Output ONLY the email body text — no subject line, no 'From/To' headers.\n\n"
                f"Original email from: {last_email['from']}\n"
                f"Subject: {last_email['subject']}\n"
                f"Body:\n{last_email['body'][:2000]}\n\n"
                f"User's instructions: {message}\n\n"
                "Draft reply:"
            )
            draft = self.send_to_api(draft_prompt, api_endpoint)
            if draft:
                # Send the email
                to_addr = last_email.get("from_email", "")
                subject = last_email.get("subject", "")
                if not subject.lower().startswith("re:"):
                    subject = f"Re: {subject}"
                message_id = last_email.get("message_id", "")

                result = email_node.send_email(
                    to=to_addr,
                    subject=subject,
                    body=draft,
                    reply_to_message_id=message_id,
                )
                if result.get("success"):
                    reply = f"Email sent to {to_addr}:\nSubject: {subject}\n\n{draft[:500]}"
                else:
                    reply = f"Failed to send email: {result.get('error', 'unknown error')}"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

        # --- Send a new email ---
        # Also catch "send a message to X@Y" and fallback: any email address + send verb
        has_email_addr = bool(re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', message))
        send_keywords = ['send an email', 'send email', 'send a message', 'send message',
                         'write an email', 'compose an email', 'message to', 'email to']
        if any(kw in msg_lower for kw in send_keywords) or has_email_addr:
            parse_prompt = (
                "Parse the user's email request into a JSON object. "
                "Extract the REAL email address the user specified. "
                "If no email address is provided, set 'to' to an empty string.\n"
                "Respond with ONLY JSON (no commentary):\n"
                '{"to": "<actual email address from user>", '
                '"subject": "<subject line>", '
                '"body": "<email body text>"}\n\n'
                "If the user didn't specify a full body, draft a professional "
                "email body based on their intent.\n"
                "NEVER invent or guess an email address. Only use addresses "
                "explicitly stated by the user.\n\n"
                f"User request: {message}\n\nJSON:"
            )
            resp = self.send_to_api(parse_prompt, api_endpoint)
            parsed = self._extract_json_payload(resp)

            to_addr = parsed.get("to", "").strip() if isinstance(parsed, dict) else ""
            # Reject empty, placeholder, or obviously fake addresses
            _bad_addrs = {"recipient@email.com", "user@example.com",
                          "email@example.com", "someone@email.com", ""}
            if isinstance(parsed, dict) and to_addr and to_addr.lower() not in _bad_addrs and "@" in to_addr:
                sent_subject = parsed.get("subject", "(no subject)")
                sent_body = parsed.get("body", "")
                result = email_node.send_email(
                    to=to_addr,
                    subject=sent_subject,
                    body=sent_body,
                )
                if result.get("success"):
                    reply = f"Email sent to {to_addr}: {sent_subject}"
                    # Save to email context so follow-ups can thread
                    sent_msg_id = result.get("message_id", "")
                    self._recent_email_context.append({
                        "raw_email": (
                            f"SENT EMAIL\n"
                            f"To: {to_addr}\n"
                            f"Subject: {sent_subject}\n"
                            f"Message-ID: {sent_msg_id}\n\n"
                            f"Body:\n{sent_body}"
                        ),
                        "summary": (
                            f"SENT by user to {to_addr}\n"
                            f"SUBJECT: {sent_subject}\n"
                            f"SUMMARY: {sent_body[:200]}"
                        ),
                        "timestamp": datetime.now(),
                        "from_email": to_addr,
                        "subject": sent_subject,
                        "message_id": sent_msg_id,
                        "is_outbound": True,
                    })
                else:
                    reply = f"Failed to send email: {result.get('error', 'unknown error')}"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}
            else:
                reply = "I couldn't determine a valid email address from your request. Please include the recipient's email address."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

        return None  # Didn't match a specific email sub-intent

    def _handle_calendar_intent(self, message: str, effective_message: str,
                                sender: str, api_endpoint: str,
                                output_files: list, cal_node) -> dict:
        """Handle calendar/task intents via a single LLM classification call
        that extracts structured JSON, then dispatches to the correct
        CalendarNode method."""

        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        weekday = now.strftime("%A")

        # Fetch upcoming events for context (used by several actions)
        upcoming = cal_node.get_events(
            start=now, end=now + timedelta(days=14), max_results=20
        )
        events_ctx = ""
        if upcoming:
            lines = []
            for e in upcoming:
                parts = [f"ID:{e['id']} | {e['summary']} | {e['start']}"]
                if e.get("calendar_name"):
                    parts.append(f"calendar:{e['calendar_name']}")
                if e.get("attendees"):
                    parts.append(f"attendees:{','.join(e['attendees'][:5])}")
                if e.get("meet_link"):
                    parts.append("has_meet:yes")
                lines.append(" | ".join(parts))
            events_ctx = "UPCOMING EVENTS (next 14 days):\n" + "\n".join(lines)

        # Available calendars
        cal_names = cal_node.get_calendar_names() if hasattr(cal_node, 'get_calendar_names') else []
        calendars_ctx = ""
        if cal_names and len(cal_names) > 1:
            calendars_ctx = (
                f"AVAILABLE CALENDARS: {', '.join(cal_names)}\n"
                f"Default calendar (for new events): {cal_names[0]}\n"
            )

        # Build recent chat history for context (so LLM knows what "that" refers to)
        chat_ctx_lines = []
        for msg in self.chat_history[-6:]:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")[:300]
            chat_ctx_lines.append(f"{role}: {content}")
        chat_ctx = "\n".join(chat_ctx_lines) if chat_ctx_lines else "(no recent history)"

        # Also fetch current tasks for task-related actions
        tasks_ctx = ""
        if hasattr(cal_node, 'list_tasks'):
            try:
                tasks = cal_node.list_tasks()
                if tasks:
                    task_lines = [
                        f"ID:{t['id']} | {t['title']} | due:{t.get('due', 'none')} | status:{t['status']}"
                        for t in tasks[:15]
                    ]
                    tasks_ctx = "CURRENT TASKS:\n" + "\n".join(task_lines)
            except Exception:
                pass

        classify_prompt = (
            "You are a calendar assistant. Classify the user's request and "
            "extract structured data. Respond with ONLY a JSON object.\n\n"
            "IMPORTANT: Use the RECENT CONVERSATION to understand contextual "
            "references like 'that event', 'it', 'scratch that', 'make it weekly'. "
            "Match these to the correct event from the UPCOMING EVENTS list using "
            "the event_id.\n\n"
            "ACTIONS (pick exactly one):\n"
            "  query_events — user wants to see their schedule/events/openings/availability\n"
            "  create_event — user wants to add/schedule a brand new event\n"
            "  modify_event — user wants to change an EXISTING event (add recurrence, "
            "add description, change title, add Google Meet, etc.) WITHOUT changing its time\n"
            "  cancel_event — user wants to delete/cancel an event (including 'scratch that')\n"
            "  reschedule_event — user wants to move/change the TIME of an event\n"
            "  add_attendees — user wants to add people to an existing event\n"
            "  add_meet — user wants to add Google Meet to an existing event\n"
            "  list_tasks — user wants to see their task list\n"
            "  add_task — user wants to add a task/to-do item\n"
            "  complete_task — user wants to mark a task as done\n"
            "  delete_task — user wants to remove a task\n\n"
            "CRITICAL RULES:\n"
            "- For query_events: if the user asks about a SPECIFIC date (e.g. 'the 16th', "
            "'Monday', 'next Tuesday', 'February 20'), you MUST include a 'start' field "
            "with that date as an ISO datetime (midnight). Use 'days' to control the range "
            "(default 1 for a single day). Only omit 'start' if the user means 'from now'.\n"
            "- If the user says 'make it recurring/weekly/daily' about an existing event, "
            "use modify_event (NOT create_event). Find the event_id from context.\n"
            "- If the user says 'scratch that', 'delete that event', 'cancel it', etc., "
            "use cancel_event and find the event_id from the conversation context.\n"
            "- ALWAYS include event_id when modifying, cancelling, or rescheduling.\n"
            "- Only use create_event for genuinely NEW events.\n\n"
            "RESPONSE FORMAT (include only relevant fields):\n"
            "{\n"
            '  "action": "one of the above",\n'
            '  "summary": "event/task title",\n'
            '  "start": "ISO datetime YYYY-MM-DDTHH:MM:SS",\n'
            '  "end": "ISO datetime (default 1hr after start if not specified)",\n'
            '  "description": "optional details",\n'
            '  "location": "optional location",\n'
            '  "attendees": ["email1@example.com", "email2@example.com"],\n'
            '  "google_meet": true/false,\n'
            '  "all_day": true/false,\n'
            '  "recurrence": "RRULE string e.g. RRULE:FREQ=WEEKLY;BYDAY=MO",\n'
            '  "event_id": "ID of existing event (from the list below)",\n'
            '  "calendar": "target calendar name (from AVAILABLE CALENDARS, omit for default)",\n'
            '  "days": number of days to query (default 1),\n'
            '  "task_title": "title for a new task",\n'
            '  "task_notes": "optional notes for a task",\n'
            '  "task_due": "YYYY-MM-DD due date for task",\n'
            '  "task_id": "ID of existing task"\n'
            "}\n\n"
            "RECURRENCE EXAMPLES:\n"
            "  Daily: RRULE:FREQ=DAILY\n"
            "  Weekly on Mon/Wed/Fri: RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR\n"
            "  Monthly on the 15th: RRULE:FREQ=MONTHLY;BYMONTHDAY=15\n"
            "  Every weekday: RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR\n"
            "  Weekly until a date: RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20260401T000000Z\n\n"
            f"CURRENT DATE/TIME: {now_str} ({weekday})\n"
            f"TIMEZONE: America/Denver (Mountain Time)\n\n"
            f"{calendars_ctx}"
            f"RECENT CONVERSATION:\n{chat_ctx}\n\n"
            f"{events_ctx}\n\n"
            f"{tasks_ctx}\n\n"
            f"USER REQUEST: {message}\n\nJSON:"
        )

        resp = self.send_to_api(classify_prompt, api_endpoint)
        parsed = self._extract_json_payload(resp)

        if not isinstance(parsed, dict) or not parsed.get("action"):
            self.update_log(f"[Calendar] LLM parse failed: {resp[:300] if resp else '(empty)'}")
            reply = "I had trouble understanding that calendar request. Could you rephrase it?"
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        action = parsed["action"]
        self.update_log(f"[Calendar] Action: {action} | Parsed: {json.dumps(parsed, default=str)[:500]}")

        # ── query_events ──────────────────────────────────────────────
        if action == "query_events":
            days = parsed.get("days", 1)
            if isinstance(days, str):
                try:
                    days = int(days)
                except ValueError:
                    days = 1
            # If the LLM provided a specific start date, use it
            start_date = None
            if parsed.get("start"):
                try:
                    start_date = datetime.fromisoformat(
                        parsed["start"].replace("Z", "+00:00")
                    )
                    if start_date.tzinfo:
                        start_date = start_date.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    pass

            # Fetch the raw calendar data
            raw_summary = cal_node.get_events_summary(days=days, start_date=start_date)

            # Pass the raw data back through the LLM with the user's
            # original question so we get a natural, conversational answer
            # instead of dumping a messy event list.
            personality_block = self._build_personality_prompt()
            permissions_block = self._build_permissions_prompt()
            date_label = (
                start_date.strftime("%A, %B %d") if start_date
                else "today" if days == 1
                else f"the next {days} days"
            )

            natural_prompt = (
                f"{personality_block}"
                f"{permissions_block}"
                "You are answering a calendar query. The user asked a question "
                "and here is the raw calendar data for the relevant period.\n\n"
                f"USER'S QUESTION: {message}\n\n"
                f"RAW CALENDAR DATA FOR {date_label.upper()}:\n{raw_summary}\n\n"
                "INSTRUCTIONS:\n"
                "- Answer the user's question naturally and conversationally.\n"
                "- If they asked about openings/availability, identify the gaps "
                "between events and highlight when they're free.\n"
                "- If they asked what they have going on, summarize the day in "
                "a readable way — don't just list raw data.\n"
                "- Group overlapping events and mention conflicts if any.\n"
                "- Keep it concise but informative. Use a friendly tone.\n"
                "- If there are no events, say so naturally.\n"
                "- Include relevant details like locations or meet links "
                "only when they add value.\n"
                "- Do NOT just repeat the raw data back. Synthesize it.\n"
            )

            reply = self.send_to_api(natural_prompt, api_endpoint)
            if not reply:
                # Fallback to raw summary if LLM fails
                reply = raw_summary

            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── create_event ──────────────────────────────────────────────
        if action == "create_event":
            event_data = {
                "summary": parsed.get("summary", "Untitled Event"),
                "start": parsed.get("start"),
                "end": parsed.get("end"),
                "description": parsed.get("description", ""),
                "location": parsed.get("location", ""),
                "attendees": parsed.get("attendees", []),
                "google_meet": parsed.get("google_meet", False),
                "all_day": parsed.get("all_day", False),
                "calendar": parsed.get("calendar"),
            }
            if parsed.get("recurrence"):
                rec = parsed["recurrence"]
                if not rec.startswith("RRULE:"):
                    rec = "RRULE:" + rec
                event_data["recurrence"] = rec

            result = cal_node.create_event(event_data)
            if result:
                start_str = result.get("start", "")
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    start_str = dt.strftime("%A, %B %d at %I:%M %p")
                except (ValueError, AttributeError):
                    pass
                reply = f"Event created: {result['summary']} — {start_str}"
                if result.get("location"):
                    reply += f"\nLocation: {result['location']}"
                if result.get("meet_link"):
                    reply += f"\nGoogle Meet: {result['meet_link']}"
                if result.get("attendees"):
                    reply += f"\nAttendees: {', '.join(result['attendees'])}"
                if result.get("recurrence"):
                    reply += f"\nRecurring: {result['recurrence'][0] if result['recurrence'] else 'yes'}"
            else:
                reply = "Failed to create the calendar event."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── modify_event ──────────────────────────────────────────────
        if action == "modify_event":
            event_id = parsed.get("event_id", "")
            if not event_id:
                reply = "I couldn't identify which event to modify. Could you be more specific?"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            target = next((e for e in upcoming if e["id"] == event_id
                           or e["id"].startswith(event_id)), None)
            full_id = target["id"] if target else event_id

            updates = {}
            if parsed.get("summary"):
                updates["summary"] = parsed["summary"]
            if parsed.get("description"):
                updates["description"] = parsed["description"]
            if parsed.get("location"):
                updates["location"] = parsed["location"]
            if parsed.get("recurrence"):
                rec = parsed["recurrence"]
                if not rec.startswith("RRULE:"):
                    rec = "RRULE:" + rec
                updates["recurrence"] = [rec]

            # Determine calendar from event context or parsed field
            target_cal = (target.get("calendar_name") if target else None) or parsed.get("calendar")

            # Handle Google Meet addition via modify
            if parsed.get("google_meet"):
                meet_result = cal_node.add_google_meet(full_id, calendar=target_cal)
                if meet_result and meet_result.get("meet_link"):
                    reply_parts = [f"Google Meet added to {meet_result['summary']}"]
                    reply_parts.append(f"Link: {meet_result['meet_link']}")
                    # If there are other updates too, apply them
                    if updates:
                        cal_node.update_event(full_id, updates, calendar=target_cal)
                        if updates.get("recurrence"):
                            reply_parts.append(f"Recurrence set: {updates['recurrence'][0]}")
                    reply = "\n".join(reply_parts)
                    self._append_chat_message("Assistant", reply)
                    return {"text": reply, "files": output_files}

            if updates:
                result = cal_node.update_event(full_id, updates, calendar=target_cal)
                if result:
                    reply_parts = [f"Event updated: {result['summary']}"]
                    if updates.get("recurrence"):
                        reply_parts.append(f"Recurrence set: {updates['recurrence'][0]}")
                    if updates.get("description"):
                        reply_parts.append(f"Description: {updates['description'][:100]}")
                    if updates.get("location"):
                        reply_parts.append(f"Location: {updates['location']}")
                    reply = "\n".join(reply_parts)
                else:
                    reply = "Failed to update the event."
            else:
                reply = "I couldn't determine what to change. Could you be more specific?"
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── cancel_event ──────────────────────────────────────────────
        if action == "cancel_event":
            event_id = parsed.get("event_id", "")
            if not event_id:
                reply = "I couldn't identify which event to cancel. Could you be more specific?"
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            # Find full event for confirmation message
            target = next((e for e in upcoming if e["id"] == event_id
                           or e["id"].startswith(event_id)), None)
            event_name = target["summary"] if target else event_id

            target_cal = (target.get("calendar_name") if target else None) or parsed.get("calendar")
            if cal_node.delete_event(target["id"] if target else event_id, calendar=target_cal):
                reply = f"Event cancelled: {event_name}"
            else:
                reply = f"Failed to cancel event: {event_name}"
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── reschedule_event ──────────────────────────────────────────
        if action == "reschedule_event":
            event_id = parsed.get("event_id", "")
            if not event_id:
                reply = "I couldn't identify which event to reschedule."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            target = next((e for e in upcoming if e["id"] == event_id
                           or e["id"].startswith(event_id)), None)
            full_id = target["id"] if target else event_id
            target_cal = (target.get("calendar_name") if target else None) or parsed.get("calendar")

            updates = {}
            if parsed.get("start"):
                updates["start"] = parsed["start"]
            if parsed.get("end"):
                updates["end"] = parsed["end"]

            if updates:
                result = cal_node.update_event(full_id, updates, calendar=target_cal)
                if result:
                    new_start = result.get("start", "")
                    try:
                        dt = datetime.fromisoformat(new_start.replace("Z", "+00:00"))
                        new_start = dt.strftime("%A, %B %d at %I:%M %p")
                    except (ValueError, AttributeError):
                        pass
                    reply = f"Event rescheduled: {result['summary']} → {new_start}"
                else:
                    reply = "Failed to reschedule the event."
            else:
                reply = "I couldn't determine the new time. Could you specify when?"
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── add_attendees ─────────────────────────────────────────────
        if action == "add_attendees":
            event_id = parsed.get("event_id", "")
            attendees = parsed.get("attendees", [])
            if not event_id or not attendees:
                reply = "I need both an event and email addresses to add attendees."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            target = next((e for e in upcoming if e["id"] == event_id
                           or e["id"].startswith(event_id)), None)
            full_id = target["id"] if target else event_id

            target_cal = (target.get("calendar_name") if target else None) or parsed.get("calendar")
            result = cal_node.add_attendees(full_id, attendees, calendar=target_cal)
            if result:
                reply = (
                    f"Attendees added to {result['summary']}: "
                    f"{', '.join(attendees)}"
                )
            else:
                reply = "Failed to add attendees."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── add_meet ──────────────────────────────────────────────────
        if action == "add_meet":
            event_id = parsed.get("event_id", "")
            if not event_id:
                reply = "I need to know which event to add Google Meet to."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            target = next((e for e in upcoming if e["id"] == event_id
                           or e["id"].startswith(event_id)), None)
            full_id = target["id"] if target else event_id

            target_cal = (target.get("calendar_name") if target else None) or parsed.get("calendar")
            result = cal_node.add_google_meet(full_id, calendar=target_cal)
            if result and result.get("meet_link"):
                reply = (
                    f"Google Meet added to {result['summary']}\n"
                    f"Link: {result['meet_link']}"
                )
            elif result:
                reply = f"Google Meet requested for {result['summary']} (link may take a moment to generate)."
            else:
                reply = "Failed to add Google Meet."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── list_tasks ────────────────────────────────────────────────
        if action == "list_tasks":
            summary = cal_node.get_tasks_summary()
            self._append_chat_message("Assistant", summary)
            return {"text": summary, "files": output_files}

        # ── add_task ──────────────────────────────────────────────────
        if action == "add_task":
            title = parsed.get("task_title") or parsed.get("summary", "")
            notes = parsed.get("task_notes", "")
            due = parsed.get("task_due", "")
            if not title:
                reply = "I need a title for the task."
                self._append_chat_message("Assistant", reply)
                return {"text": reply, "files": output_files}

            result = cal_node.add_task(title, notes=notes, due=due)
            if result:
                reply = f"Task added: {result['title']}"
                if result.get("due"):
                    try:
                        due_dt = datetime.fromisoformat(result["due"].replace("Z", "+00:00"))
                        reply += f" (due {due_dt.strftime('%b %d')})"
                    except ValueError:
                        reply += f" (due {result['due'][:10]})"
            else:
                reply = "Failed to add the task."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── complete_task ─────────────────────────────────────────────
        if action == "complete_task":
            task_id = parsed.get("task_id", "")
            if not task_id:
                # Try to find task by title
                tasks = cal_node.list_tasks()
                title_hint = parsed.get("task_title") or parsed.get("summary", "")
                if title_hint and tasks:
                    match = next(
                        (t for t in tasks
                         if title_hint.lower() in t["title"].lower()),
                        None
                    )
                    if match:
                        task_id = match["id"]
            if task_id and cal_node.complete_task(task_id):
                reply = "Task marked as completed!"
            else:
                reply = "I couldn't find or complete that task."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── delete_task ───────────────────────────────────────────────
        if action == "delete_task":
            task_id = parsed.get("task_id", "")
            if not task_id:
                tasks = cal_node.list_tasks()
                title_hint = parsed.get("task_title") or parsed.get("summary", "")
                if title_hint and tasks:
                    match = next(
                        (t for t in tasks
                         if title_hint.lower() in t["title"].lower()),
                        None
                    )
                    if match:
                        task_id = match["id"]
            if task_id and cal_node.delete_task(task_id):
                reply = "Task deleted."
            else:
                reply = "I couldn't find or delete that task."
            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        # ── Fallback ──────────────────────────────────────────────────
        reply = "I had trouble understanding that calendar request. Could you rephrase it?"
        self._append_chat_message("Assistant", reply)
        return {"text": reply, "files": output_files}

    def _cross_channel_notify(self, sender: str, response_text: str,
                              output_files: list = None):
        """After processing a message from a non-interactive sender (Email,
        TaskTracker, Calendar), forward the response to the user via WhatsApp
        and Slack so they see it in real time."""
        if sender == "Email":
            self._notify_via_whatsapp(response_text, output_files)
            self._notify_via_slack(response_text, output_files)
        elif sender == "TaskTracker":
            self._notify_via_whatsapp(response_text, output_files)
            self._notify_via_slack(response_text, output_files)
        elif sender == "Calendar":
            self._notify_via_whatsapp(response_text)
            self._notify_via_slack(response_text)

    # -- Cross-channel notification helpers ---------------------------------

    def _notify_via_whatsapp(self, text: str, files: list = None):
        """Send a notification to the user via WhatsApp (if connected).
        Uses the WhatsApp node's self-chat (or first allowed number)."""
        try:
            from src.workflows.node_registry import get_running_instance
            wa_node = get_running_instance("WhatsAppWebNode")
            if not wa_node or not getattr(wa_node, '_connected', False):
                return
            # Send to self-chat using the node's own JID
            my_jid = getattr(wa_node, '_my_jid', None)
            if not my_jid:
                return
            from neonize.utils import build_jid
            chat_jid = build_jid(my_jid)
            wa_node._send_wa_text(chat_jid, text)
            for fpath in (files or []):
                try:
                    wa_node._send_wa_file(chat_jid, fpath)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[MCA] WhatsApp notification failed: {exc}")

    def _notify_via_slack(self, text: str, files: list = None):
        """Send a notification to the user via Slack (if connected)."""
        try:
            from src.workflows.node_registry import get_running_instance
            slack_node = get_running_instance("SlackNode")
            if not slack_node or not getattr(slack_node, '_connected', False):
                return
            slack_node.send_notification(text, files)
        except Exception as exc:
            print(f"[MCA] Slack notification failed: {exc}")

    def _find_email_node(self):
        """Discover a running EmailNode via the shared runtime registry."""
        try:
            from src.workflows.node_registry import get_running_instance
            node = get_running_instance("EmailNode")
            if node and hasattr(node, "send_email"):
                return node
        except Exception:
            pass
        return None

    def _find_task_tracker_node(self):
        """Discover a running TaskTrackerNode via the shared runtime registry."""
        try:
            from src.workflows.node_registry import get_running_instance
            node = get_running_instance("TaskTrackerNode")
            if node and hasattr(node, "add_task"):
                return node
        except Exception:
            pass
        return None

    def _find_calendar_node(self):
        """Discover a running CalendarNode via the shared runtime registry."""
        try:
            from src.workflows.node_registry import get_running_instance
            node = get_running_instance("CalendarNode")
            if node and hasattr(node, "get_events"):
                return node
        except Exception:
            pass
        return None

    def _get_db_name(self) -> str:
        """Get the RAG database name for this workflow."""
        workflow_name = self._get_workflow_name()
        return _safe_db_name(str(workflow_name))

    # -- Personality matrix ---------------------------------------------------

    _PERSONALITY_PATH = Path(__file__).resolve().parent.parent / "data" / "personality.json"
    _DEFAULT_PERSONALITY = {
        "traits": {
            "humor":       {"score": 0.5, "description": "How witty/playful vs. strictly professional"},
            "formality":   {"score": 0.4, "description": "How formal vs. casual the tone is"},
            "verbosity":   {"score": 0.5, "description": "How detailed vs. concise responses are"},
            "empathy":     {"score": 0.6, "description": "How much emotional warmth to show"},
            "proactivity": {"score": 0.6, "description": "How much to volunteer suggestions"},
            "confidence":  {"score": 0.7, "description": "How assertive vs. cautious"},
        },
        "learned_preferences": [],
        "interaction_count": 0,
        "last_reflection": None,
        "reflection_interval": 5,
        "name": "Jack",
        "persona_summary": (
            "A helpful, friendly AI assistant who balances professionalism "
            "with approachability. Moderately humorous, fairly casual, and "
            "proactively helpful."
        ),
    }

    def _load_personality(self) -> dict:
        """Load personality from disk, falling back to defaults."""
        try:
            if self._PERSONALITY_PATH.exists():
                with open(self._PERSONALITY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge with defaults so new traits are always present
                merged = json.loads(json.dumps(self._DEFAULT_PERSONALITY))
                merged.update(data)
                for k, v in self._DEFAULT_PERSONALITY["traits"].items():
                    if k not in merged.get("traits", {}):
                        merged["traits"][k] = v
                return merged
        except Exception as exc:
            print(f"[Personality] Load error: {exc}")
        return json.loads(json.dumps(self._DEFAULT_PERSONALITY))

    def _save_personality(self) -> None:
        """Persist the current personality to disk."""
        try:
            self._PERSONALITY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self._PERSONALITY_PATH, "w", encoding="utf-8") as f:
                json.dump(self._personality, f, indent=4, default=str)
        except Exception as exc:
            print(f"[Personality] Save error: {exc}")

    # -- Action Permission Registry --------------------------------------------

    _PERMISSIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "permissions.json"
    _DEFAULT_PERMISSIONS = {
        "actions": {
            "send_email": {
                "description": "Send or reply to emails on behalf of the user",
                "status": "ask",          # "allowed", "ask", "denied"
                "reason": "Default: always ask before sending emails",
            },
            "send_email_reply": {
                "description": "Reply to a recently received email",
                "status": "ask",
                "reason": "Default: always ask before replying to emails",
            },
            "create_calendar_event": {
                "description": "Create, modify, or delete calendar events",
                "status": "ask",
                "reason": "Default: always ask before modifying calendar",
            },
            "delegate_to_team": {
                "description": "Delegate complex tasks to the team (TeamLead + Workers)",
                "status": "allowed",
                "reason": "Default: delegation is allowed without asking",
            },
            "web_search": {
                "description": "Perform web searches to gather information",
                "status": "allowed",
                "reason": "Default: web searches are allowed without asking",
            },
            "create_file": {
                "description": "Create and send back documents (Word, Excel, etc.)",
                "status": "allowed",
                "reason": "Default: file creation is allowed when requested",
            },
            "store_to_database": {
                "description": "Store information in the RAG knowledge database",
                "status": "allowed",
                "reason": "Default: storing knowledge is allowed without asking",
            },
            "delete_from_database": {
                "description": "Delete information from the RAG knowledge database",
                "status": "ask",
                "reason": "Default: always ask before deleting knowledge",
            },
            "send_notification": {
                "description": "Send notifications via WhatsApp or Slack",
                "status": "allowed",
                "reason": "Default: notifications are allowed",
            },
        },
        "log": [],  # Audit trail of permission changes
    }

    def _load_permissions(self) -> dict:
        """Load permission registry from disk, falling back to defaults."""
        try:
            if self._PERMISSIONS_PATH.exists():
                with open(self._PERMISSIONS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge with defaults so new actions are always present
                merged = json.loads(json.dumps(self._DEFAULT_PERMISSIONS))
                merged.update(data)
                # Ensure all default actions exist
                for k, v in self._DEFAULT_PERMISSIONS["actions"].items():
                    if k not in merged.get("actions", {}):
                        merged["actions"][k] = v
                return merged
        except Exception as exc:
            print(f"[Permissions] Load error: {exc}")
        return json.loads(json.dumps(self._DEFAULT_PERMISSIONS))

    def _save_permissions(self) -> None:
        """Persist the current permissions to disk."""
        try:
            self._PERMISSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self._PERMISSIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._permissions, f, indent=4, default=str)
        except Exception as exc:
            print(f"[Permissions] Save error: {exc}")

    def _check_permission(self, action: str) -> str:
        """Check if an action is allowed, denied, or needs user approval.
        Returns: 'allowed', 'ask', or 'denied'."""
        actions = self._permissions.get("actions", {})
        entry = actions.get(action)
        if not entry:
            # Unknown action — default to asking
            return "ask"
        return entry.get("status", "ask")

    def _update_permission(self, action: str, status: str, reason: str = "") -> bool:
        """Update the permission status for an action.
        status must be 'allowed', 'ask', or 'denied'.
        Returns True if the action was found and updated."""
        if status not in ("allowed", "ask", "denied"):
            return False
        actions = self._permissions.get("actions", {})
        if action not in actions:
            # Create a new entry for unknown actions
            actions[action] = {
                "description": action.replace("_", " ").title(),
                "status": status,
                "reason": reason or f"Set by user",
            }
        else:
            old_status = actions[action].get("status", "ask")
            actions[action]["status"] = status
            actions[action]["reason"] = reason or f"Changed from {old_status} to {status}"
        # Audit log
        log = self._permissions.setdefault("log", [])
        log.append({
            "action": action,
            "old_status": actions.get(action, {}).get("status", "unknown"),
            "new_status": status,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep log manageable
        if len(log) > 100:
            self._permissions["log"] = log[-50:]
        self._save_permissions()
        return True

    def _build_permissions_prompt(self) -> str:
        """Build a permission-awareness block for LLM prompts so the AI
        knows what it can and cannot do without asking."""
        actions = self._permissions.get("actions", {})
        lines_ask = []
        lines_allowed = []
        lines_denied = []
        for action_id, entry in actions.items():
            desc = entry.get("description", action_id)
            status = entry.get("status", "ask")
            label = action_id.replace("_", " ").title()
            if status == "ask":
                lines_ask.append(f"  - {label}: {desc}")
            elif status == "allowed":
                lines_allowed.append(f"  - {label}: {desc}")
            elif status == "denied":
                lines_denied.append(f"  - {label}: {desc}")

        parts = ["## Action Permissions\n"]
        if lines_ask:
            parts.append(
                "Actions that REQUIRE user confirmation before executing "
                "(ask the user before doing these):\n"
                + "\n".join(lines_ask) + "\n"
            )
        if lines_allowed:
            parts.append(
                "Actions you may perform WITHOUT asking:\n"
                + "\n".join(lines_allowed) + "\n"
            )
        if lines_denied:
            parts.append(
                "Actions that are BLOCKED (do not attempt these):\n"
                + "\n".join(lines_denied) + "\n"
            )
        parts.append(
            "\nIMPORTANT: For any action marked 'REQUIRE user confirmation', "
            "you MUST ask the user before proceeding. Present what you plan "
            "to do and wait for approval. Never assume the user wants you to "
            "take an action just because the context is related.\n\n"
        )
        return "\n".join(parts)

    def _build_personality_prompt(self) -> str:
        """Build a personality instruction block for LLM prompts."""
        p = self._personality
        traits = p.get("traits", {})
        name = p.get("name", "Assistant")
        summary = p.get("persona_summary", "")

        # Convert trait scores to descriptive labels
        def _label(score: float) -> str:
            if score <= 0.2:   return "very low"
            if score <= 0.4:   return "low"
            if score <= 0.6:   return "moderate"
            if score <= 0.8:   return "high"
            return "very high"

        trait_lines = []
        for trait_name, trait_data in traits.items():
            score = trait_data.get("score", 0.5)
            trait_lines.append(f"  - {trait_name.capitalize()}: {_label(score)} ({score:.1f})")
        traits_block = "\n".join(trait_lines)

        # Include learned preferences
        prefs = p.get("learned_preferences", [])
        prefs_block = ""
        if prefs:
            recent_prefs = prefs[-10:]  # Last 10 learned preferences
            prefs_lines = [f"  - {pref}" for pref in recent_prefs]
            prefs_block = (
                "\nLearned user preferences (adapt your style accordingly):\n"
                + "\n".join(prefs_lines) + "\n"
            )

        return (
            f"## Your Identity & Personality\n"
            f"Your name is **{name}**. {summary}\n\n"
            f"Personality traits (guide your tone and style):\n"
            f"{traits_block}\n"
            f"{prefs_block}\n"
            f"Apply these traits naturally — don't mention them explicitly. "
            f"Let them shape HOW you communicate, not WHAT you communicate.\n\n"
        )

    def _run_personality_reflection(self, user_message: str, assistant_response: str,
                                     api_endpoint: str) -> None:
        """Lightweight self-reflection after every N interactions.
        Evaluates the interaction and may learn new preferences."""
        p = self._personality
        p["interaction_count"] = p.get("interaction_count", 0) + 1
        interval = p.get("reflection_interval", 5)

        if p["interaction_count"] % interval != 0:
            self._save_personality()
            return

        # Time for reflection
        traits = p.get("traits", {})
        trait_summary = ", ".join(
            f"{k}={v.get('score', 0.5):.1f}" for k, v in traits.items()
        )
        prefs = p.get("learned_preferences", [])
        prefs_str = "; ".join(prefs[-5:]) if prefs else "(none yet)"

        reflection_prompt = (
            "You are an AI personality calibration system. Analyse the recent "
            "interaction below and determine if any personality adjustments are "
            "needed.\n\n"
            f"Current traits: {trait_summary}\n"
            f"Known preferences: {prefs_str}\n\n"
            f"User message: \"{user_message[:500]}\"\n"
            f"Assistant response: \"{assistant_response[:500]}\"\n\n"
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "adjustments": {  // trait_name: new_score (0.0-1.0), only include traits to change\n'
            "  },\n"
            '  "new_preference": "",  // a short learned preference string, or empty if none\n'
            '  "updated_summary": ""  // updated persona_summary, or empty to keep current\n'
            "}\n\n"
            "Only suggest changes if the interaction clearly indicates a mismatch. "
            "Most of the time, return empty adjustments. Be conservative."
        )
        try:
            resp = self.send_to_api(reflection_prompt, api_endpoint)
            if not resp:
                return
            # Parse the reflection
            cleaned = resp.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                last_fence = cleaned.rfind("```")
                if first_nl > 0 and last_fence > first_nl:
                    cleaned = cleaned[first_nl + 1:last_fence].strip()
            obj_start = cleaned.find("{")
            obj_end = cleaned.rfind("}")
            if obj_start == -1 or obj_end <= obj_start:
                return
            reflection = json.loads(cleaned[obj_start:obj_end + 1])

            changed = False
            # Apply trait adjustments
            adjustments = reflection.get("adjustments", {})
            for trait_name, new_score in adjustments.items():
                if trait_name in traits and isinstance(new_score, (int, float)):
                    new_score = max(0.0, min(1.0, float(new_score)))
                    old_score = traits[trait_name].get("score", 0.5)
                    if abs(new_score - old_score) > 0.05:
                        traits[trait_name]["score"] = round(new_score, 2)
                        self.update_log(
                            f"[Personality] {trait_name}: {old_score:.2f} → {new_score:.2f}"
                        )
                        changed = True

            # Learn new preference
            new_pref = reflection.get("new_preference", "").strip()
            if new_pref and len(new_pref) > 5:
                prefs = p.get("learned_preferences", [])
                if new_pref not in prefs:
                    prefs.append(new_pref)
                    # Keep only the last 20 preferences
                    p["learned_preferences"] = prefs[-20:]
                    self.update_log(f"[Personality] Learned: {new_pref}")
                    changed = True

            # Update persona summary
            new_summary = reflection.get("updated_summary", "").strip()
            if new_summary and len(new_summary) > 20:
                p["persona_summary"] = new_summary
                changed = True

            p["last_reflection"] = datetime.now().isoformat()
            if changed:
                self._save_personality()
                self.update_log("[Personality] Reflection complete — traits updated")
            else:
                self._save_personality()

        except Exception as exc:
            print(f"[Personality] Reflection error: {exc}")

    def _open_personality_window(self):
        """Open a dedicated Personality Settings popup window with sliders."""
        # Prevent multiple windows
        if hasattr(self, '_personality_window') and self._personality_window:
            try:
                self._personality_window.lift()
                self._personality_window.focus_force()
                return
            except tk.TclError:
                self._personality_window = None

        p = self._personality
        win = tk.Toplevel()
        win.title("Personality Settings — " + p.get("name", "Jack"))
        win.geometry("520x720")
        win.minsize(480, 600)
        win.resizable(True, True)
        self._personality_window = win

        def on_close():
            self._personality_window = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        # Scrollable canvas for content
        canvas = tk.Canvas(win, highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- Name ---
        name_frame = ttk.LabelFrame(content, text="Assistant Name", padding=10)
        name_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        name_var = tk.StringVar(value=p.get("name", "Jack"))
        name_entry = ttk.Entry(name_frame, textvariable=name_var, width=30)
        name_entry.pack(fill=tk.X)

        # --- Trait Sliders ---
        traits_frame = ttk.LabelFrame(content, text="Personality Traits", padding=10)
        traits_frame.pack(fill=tk.X, padx=10, pady=5)

        trait_vars = {}
        trait_labels = {}
        traits = p.get("traits", {})

        def _label_text(name, val):
            if val <= 0.2:   lvl = "Very Low"
            elif val <= 0.4: lvl = "Low"
            elif val <= 0.6: lvl = "Moderate"
            elif val <= 0.8: lvl = "High"
            else:            lvl = "Very High"
            return f"{name.capitalize()}: {val:.2f} ({lvl})"

        for trait_name, trait_data in traits.items():
            score = trait_data.get("score", 0.5)
            desc = trait_data.get("description", "")

            row_frame = ttk.Frame(traits_frame)
            row_frame.pack(fill=tk.X, pady=3)

            lbl = ttk.Label(row_frame, text=_label_text(trait_name, score), width=35, anchor="w")
            lbl.pack(side=tk.LEFT)
            trait_labels[trait_name] = lbl

            var = tk.DoubleVar(value=score)
            trait_vars[trait_name] = var

            def make_update(tn, v, lb):
                def update_label(event=None):
                    lb.config(text=_label_text(tn, v.get()))
                return update_label

            slider = ttk.Scale(
                row_frame, from_=0.0, to=1.0, orient=tk.HORIZONTAL,
                variable=var, length=200,
                command=lambda val, tn=trait_name, v=var, lb=lbl: lb.config(
                    text=_label_text(tn, float(val))
                )
            )
            slider.pack(side=tk.RIGHT, fill=tk.X, expand=True)

            if desc:
                desc_lbl = ttk.Label(traits_frame, text=f"  {desc}", foreground="gray")
                desc_lbl.pack(fill=tk.X, anchor="w")

        # --- Persona Summary ---
        summary_frame = ttk.LabelFrame(content, text="Persona Summary", padding=10)
        summary_frame.pack(fill=tk.X, padx=10, pady=5)
        summary_text = scrolledtext.ScrolledText(summary_frame, height=4, wrap=tk.WORD)
        summary_text.insert("1.0", p.get("persona_summary", ""))
        summary_text.pack(fill=tk.X)

        # --- Reflection Interval ---
        interval_frame = ttk.LabelFrame(content, text="Self-Reflection", padding=10)
        interval_frame.pack(fill=tk.X, padx=10, pady=5)

        interval_row = ttk.Frame(interval_frame)
        interval_row.pack(fill=tk.X)
        ttk.Label(interval_row, text="Reflect every N interactions:").pack(side=tk.LEFT)
        interval_var = tk.IntVar(value=p.get("reflection_interval", 5))
        interval_spin = ttk.Spinbox(interval_row, from_=1, to=50, textvariable=interval_var, width=5)
        interval_spin.pack(side=tk.LEFT, padx=10)

        interaction_count = p.get("interaction_count", 0)
        last_ref = p.get("last_reflection", None)
        info_text = f"Interactions so far: {interaction_count}"
        if last_ref:
            info_text += f"  |  Last reflection: {last_ref}"
        ttk.Label(interval_frame, text=info_text, foreground="gray").pack(fill=tk.X, pady=(5, 0))

        # --- Learned Preferences ---
        prefs_frame = ttk.LabelFrame(content, text="Learned Preferences", padding=10)
        prefs_frame.pack(fill=tk.X, padx=10, pady=5)

        prefs = p.get("learned_preferences", [])
        prefs_listbox = tk.Listbox(prefs_frame, height=5)
        for pref in prefs:
            prefs_listbox.insert(tk.END, pref)
        prefs_listbox.pack(fill=tk.X, pady=(0, 5))

        prefs_btn_frame = ttk.Frame(prefs_frame)
        prefs_btn_frame.pack(fill=tk.X)

        def remove_pref():
            sel = prefs_listbox.curselection()
            if sel:
                prefs_listbox.delete(sel[0])

        def clear_prefs():
            prefs_listbox.delete(0, tk.END)

        ttk.Button(prefs_btn_frame, text="Remove Selected", command=remove_pref).pack(side=tk.LEFT, padx=5)
        ttk.Button(prefs_btn_frame, text="Clear All", command=clear_prefs).pack(side=tk.LEFT, padx=5)

        # --- Action Buttons ---
        action_frame = ttk.Frame(content)
        action_frame.pack(fill=tk.X, padx=10, pady=15)

        def save_personality():
            # Update personality dict from UI
            self._personality["name"] = name_var.get().strip() or "Jack"
            for tn, tv in trait_vars.items():
                val = max(0.0, min(1.0, tv.get()))
                self._personality["traits"][tn]["score"] = round(val, 2)
            self._personality["persona_summary"] = summary_text.get("1.0", tk.END).strip()
            self._personality["reflection_interval"] = max(1, interval_var.get())
            # Rebuild learned preferences from listbox
            new_prefs = [prefs_listbox.get(i) for i in range(prefs_listbox.size())]
            self._personality["learned_preferences"] = new_prefs
            self._save_personality()
            win.title("Personality Settings — " + self._personality["name"])
            self.update_log(
                f"[Personality] Settings saved: "
                + ", ".join(f"{tn}={tv.get():.2f}" for tn, tv in trait_vars.items())
            )
            # Brief flash to confirm save
            save_btn.config(text="Saved!")
            win.after(1500, lambda: save_btn.config(text="Save"))

        def reset_defaults():
            defaults = self._DEFAULT_PERSONALITY
            name_var.set(defaults["name"])
            for tn, td in defaults["traits"].items():
                if tn in trait_vars:
                    trait_vars[tn].set(td["score"])
                    trait_labels[tn].config(text=_label_text(tn, td["score"]))
            summary_text.delete("1.0", tk.END)
            summary_text.insert("1.0", defaults["persona_summary"])
            interval_var.set(defaults["reflection_interval"])
            prefs_listbox.delete(0, tk.END)

        save_btn = ttk.Button(action_frame, text="Save", command=save_personality)
        save_btn.pack(side=tk.LEFT, padx=5)

        reset_btn = ttk.Button(action_frame, text="Reset to Defaults", command=reset_defaults)
        reset_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(action_frame, text="Close", command=on_close).pack(side=tk.RIGHT, padx=5)

    def _handle_personality_adjustment(self, message: str, api_endpoint: str,
                                       output_files: list) -> Optional[dict]:
        """Handle user commands to adjust personality traits directly.
        E.g. 'be more casual', 'tone down the humor', 'be more concise'."""
        adjust_prompt = (
            "The user wants to adjust the AI assistant's personality traits. "
            "Parse their request and return a JSON object with trait adjustments.\n\n"
            "Available traits and current scores (scale: 0.0 to 1.0):\n"
        )
        traits = self._personality.get("traits", {})
        for name, data in traits.items():
            score = data.get("score", 0.5)
            desc = data.get("description", "")
            adjust_prompt += f"  - {name}: {score:.2f}  ({desc})\n"
        adjust_prompt += (
            "\nSCALE RULES:\n"
            "- All scores are on a 0.0 to 1.0 scale.\n"
            "- If the user says a number 1-10 (e.g. 'eight', '8', 'to 8'), "
            "convert it: divide by 10 → 0.8.\n"
            "- 'a little bit' / 'slightly' = adjust by ±0.10 to ±0.15 from current.\n"
            "- 'a lot' / 'way more' / 'much more' = adjust by ±0.25 to ±0.30 from current.\n"
            "- 'turn up' / 'increase' / 'more' without qualifier = adjust by ±0.15 to ±0.20.\n"
            "- Map adjectives to traits: funny/humorous→humor, casual/formal→formality, "
            "verbose/detailed/wordy→verbosity, warm/empathetic→empathy, "
            "proactive→proactivity, confident/assertive→confidence.\n"
            "- 'turn up' means INCREASE the score. 'turn down' means DECREASE.\n"
            "- For formality: 'more casual' = LOWER formality, 'more formal' = HIGHER.\n\n"
            "Return ONLY JSON:\n"
            "{\n"
            '  "adjustments": {"trait_name": new_score, ...},\n'
            '  "acknowledgment": "brief friendly confirmation mentioning old→new values"\n'
            "}\n\n"
            "IMPORTANT: Only include traits that the user actually wants to change. "
            "The acknowledgment should mention the specific change made.\n\n"
            f"User request: \"{message}\"\n\nJSON:"
        )
        try:
            resp = self.send_to_api(adjust_prompt, api_endpoint)
            if not resp:
                return None
            cleaned = resp.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                last_fence = cleaned.rfind("```")
                if first_nl > 0 and last_fence > first_nl:
                    cleaned = cleaned[first_nl + 1:last_fence].strip()
            obj_start = cleaned.find("{")
            obj_end = cleaned.rfind("}")
            if obj_start == -1 or obj_end <= obj_start:
                return None
            result = json.loads(cleaned[obj_start:obj_end + 1])

            adjustments = result.get("adjustments", {})
            changes = []
            for trait_name, new_score in adjustments.items():
                if trait_name in traits and isinstance(new_score, (int, float)):
                    new_score = max(0.0, min(1.0, float(new_score)))
                    old_score = traits[trait_name].get("score", 0.5)
                    traits[trait_name]["score"] = round(new_score, 2)
                    changes.append(f"• {trait_name.capitalize()}: {old_score:.1f} → {new_score:.1f}")

            if changes:
                self._save_personality()
                ack = result.get("acknowledgment", "Got it! I've adjusted my personality.")
                changes_str = "\n".join(changes)
                reply = f"{ack}\n\nAdjustments made:\n{changes_str}"
            else:
                reply = "I understood you want me to adjust my personality, but I wasn't sure what to change. Try something like 'be more casual' or 'less verbose'."

            self._append_chat_message("Assistant", reply)
            return {"text": reply, "files": output_files}

        except Exception as exc:
            self.update_log(f"[Personality] Adjustment error: {exc}")
            return None

    def _get_db_manager(self):
        """Get or create a DatabaseManager instance and ensure the DB exists."""
        manager = DatabaseManager()
        db_name = self._get_db_name()
        manager.ensure_database(db_name)
        return manager, db_name

    def _query_rag_for_context(self, message: str) -> str:
        """Query the RAG database for relevant existing knowledge."""
        try:
            manager, db_name = self._get_db_manager()
            results = manager.search(db_name, message, top_k=5)
            if not results:
                # Also search all available databases for cross-workflow knowledge
                all_dbs = manager.list_databases()
                for other_db in all_dbs:
                    if other_db == db_name:
                        continue
                    other_results = manager.search(other_db, message, top_k=3)
                    if other_results:
                        results.extend(other_results)
                    if len(results) >= 5:
                        break

            if not results:
                return ''

            context_parts = []
            for r in results[:5]:
                content = r.get('content', '')
                source = r.get('source', 'unknown')
                score = r.get('similarity', 0)
                if content and score > 0.3:
                    context_parts.append(f"[Source: {source}, Relevance: {score:.2f}]\n{content}")

            if not context_parts:
                return ''

            return "\n\n".join(context_parts)
        except Exception as exc:
            print(f"[MasterAgentNode] RAG query error: {exc}")
            return ''

    def _store_to_rag(self, query: str, response: str) -> None:
        """Store a query-response pair into the RAG database for future lookups."""
        try:
            manager, db_name = self._get_db_manager()
            content = f"User Query: {query}\n\nAssistant Response:\n{response}"
            manager.add_text_content(
                db_name, content,
                source_label="master_agent_response",
                tags=["master_agent", "chat_response"],
                max_content_length=4000
            )
        except Exception as exc:
            print(f"[MasterAgentNode] RAG store error: {exc}")

    def _get_chat_api_endpoint(self) -> str:
        api_prop = self.properties.get('text_api_endpoint', {})
        value = api_prop.get('value')
        default = api_prop.get('default', '')
        raw = value or default
        resolved = self._normalize_endpoint_name(raw)
        print(f"[MasterAgentNode] _get_chat_api_endpoint: value={value!r}, default={default!r}, raw={raw!r}, resolved={resolved!r}")
        return resolved

    def _normalize_endpoint_name(self, endpoint: str) -> str:
        if not endpoint:
            return ''
        interfaces = self.config.get('interfaces') or {}
        if endpoint in interfaces:
            return endpoint
        lower = endpoint.strip().lower()
        for name in interfaces:
            if name.lower() == lower:
                return name
        tokens = [token for token in re.split(r"\s+", lower) if token]
        best_match = ''
        best_score = 0
        for name in interfaces:
            name_lower = name.lower()
            score = sum(1 for token in tokens if token in name_lower)
            if score > best_score:
                best_score = score
                best_match = name
        return best_match or endpoint

    def _build_chat_prompt(self, latest_message: str, rag_context: str = '', wa_hint: str = '') -> str:
        history_lines = []
        for message in self.chat_history[-10:]:
            role = message.get("role", "user")
            content = message.get("content", "")
            history_lines.append(f"{role.capitalize()}: {content}")
        history_lines.append(f"User: {latest_message}")
        history = "\n".join(history_lines)
        catalog_lines = self._get_tool_catalog_text()

        # Build dynamic capabilities section based on running nodes
        capabilities = []
        if self._find_email_node():
            capabilities.append(
                "- **Email**: You can send emails, check recent emails, and draft replies. "
                "The user can say things like 'send an email to...', 'reply to that email', "
                "'check my email'."
            )
        if self._find_task_tracker_node():
            capabilities.append(
                "- **Task Tracker**: You can create, list, pause, and delete scheduled tasks. "
                "The user can say 'remind me every Monday at 9am to...', 'list my tasks', "
                "'delete the backup check task'."
            )
        if self._find_calendar_node():
            capabilities.append(
                "- **Calendar & Tasks**: Full Google Calendar and Tasks integration. You can:\n"
                "  - Query events: 'what's on my calendar today', 'am I free tomorrow at 3?'\n"
                "  - Create events: 'schedule a meeting tomorrow at 2pm', 'add a weekly standup every Monday at 9am'\n"
                "  - Create with Google Meet: 'schedule a video call with john@example.com'\n"
                "  - Add attendees: 'add sarah@example.com to the standup meeting'\n"
                "  - Add Google Meet to existing events: 'add a meet link to my 3pm meeting'\n"
                "  - Recurring events: 'create a daily standup at 9am', 'weekly team sync every Friday'\n"
                "  - Reschedule: 'move my 3pm meeting to 4pm'\n"
                "  - Cancel: 'cancel my meeting tomorrow'\n"
                "  - Tasks: 'add a task to call the dentist', 'show my tasks', 'mark groceries as done'\n"
                "IMPORTANT: Calendar and task actions are handled by the specialised intent handler. "
                "Do NOT fabricate calendar confirmations."
            )
        capabilities.append(
            "- **Memory / Database**: You can store facts the user tells you and "
            "delete/forget specific entries on request. The user can say "
            "'remember that my email is...', 'store this in your database', "
            "'delete those from your memory', 'forget about Bob'. "
            "IMPORTANT: Do NOT claim you have deleted or stored something unless "
            "the specialised intent handler has actually done it. If the user asks "
            "you to delete something, the deletion handler will take care of it — "
            "do not fabricate a confirmation."
        )
        capabilities_section = ""
        if capabilities:
            capabilities_section = (
                "\n## Available Digital Assistant Capabilities:\n"
                + "\n".join(capabilities) + "\n\n"
                "Note: Task management, email, calendar, and memory requests are "
                "handled automatically by specialised intent detection. You do NOT "
                "need to delegate these — just respond naturally.\n\n"
            )

        # Build the knowledge context section
        knowledge_section = ""
        if rag_context:
            knowledge_section = (
                "\n\n--- EXISTING KNOWLEDGE (from RAG database) ---\n"
                "The following information was found in the knowledge database and may be relevant to the user's request. "
                "Use this data to answer directly if it contains what the user needs.\n\n"
                f"{rag_context}\n"
                "--- END EXISTING KNOWLEDGE ---\n"
            )

        # Inject current date/time so the LLM can answer instantly
        from datetime import datetime as _dt
        now = _dt.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d, %Y")

        personality_section = self._build_personality_prompt()
        permissions_section = self._build_permissions_prompt()

        return (
            "You are the Master Control Agent — an intelligent orchestrator that manages a team of agents. "
            "Your primary goal is to provide the best possible answer to the user's request.\n\n"
            f"{personality_section}"
            f"{permissions_section}"
            f"**Current Date & Time:** {date_str}, {time_str}\n\n"
            f"{wa_hint}"
            "## Decision Process (follow this order):\n\n"
            "1. **Check Existing Knowledge First**: Review the EXISTING KNOWLEDGE section below (if present). "
            "If the knowledge database already contains the information the user is asking about, "
            "use it to answer directly. Do NOT delegate when you already have the answer.\n\n"
            "2. **Answer Simple Requests Directly**: For conversational messages, simple factual questions, "
            "opinions, date/time queries, or quick lookups you can answer from your training or existing knowledge, "
            "respond directly with a helpful answer. No delegation needed.\n\n"
            "3. **Ask for Clarification if Ambiguous**: If the request is unclear or could be interpreted "
            "multiple ways, respond ONLY with JSON: {\"clarify\": true, \"questions\": [...]}\n\n"
            "4. **ALWAYS Delegate Multi-Stage Projects**: You MUST delegate when the request involves ANY of:\n"
            "   - Research/comparison AND creating documents (Word docs, spreadsheets, reports)\n"
            "   - Multiple deliverables (e.g. a sales sheet AND a cost tracking spreadsheet)\n"
            "   - Creating professional documents like sales sheets, marketing materials, proposals\n"
            "   - Building spreadsheets for tracking, analysis, or financial planning\n"
            "   - Live web research or data that may have changed recently\n"
            "   - Multi-step research across multiple sources\n"
            "   - Tool execution (web scraping, file processing, etc.)\n"
            "   - Tasks that need worker coordination\n"
            "   Even if you COULD answer the research part from training data, if the user also wants "
            "   files created (Word doc, spreadsheet, etc.), you MUST delegate so the team can produce "
            "   the actual files. Do NOT try to handle file-creation projects yourself.\n"
            "   Respond with: {\"delegate\": true, \"tasks\": [...], \"message\": \"brief explanation\"}\n"
            "   Each task should be a dict with \"task\" and optionally \"query\" fields.\n"
            "   You may include tool_calls: [{\"type\": \"NodeType\", \"input\": \"...\", \"properties\": {...}}]\n\n"
            "5. **Simple Export from Existing Data**: If the user asks you to export or reformat data "
            "that is ALREADY fully present in the conversation or knowledge base (no new research needed, "
            "no new content to create), respond directly with well-formatted markdown content. "
            "The system will handle the file export automatically.\n\n"
            "## Key Principles:\n"
            "- If the user asks for files to be CREATED (Word doc, spreadsheet, report) → DELEGATE\n"
            "- If the request has multiple parts (research + documents) → DELEGATE\n"
            "- Simple Q&A with no file output → answer directly\n"
            "- Reformatting existing conversation data → answer directly\n"
            "- When in doubt about whether to delegate, DELEGATE\n"
            "- Use markdown formatting in your responses\n\n"
            f"{capabilities_section}"
            f"Available tools (nodes):\n{catalog_lines}\n"
            f"{knowledge_section}\n"
            f"Conversation so far:\n{history}\n\nAssistant, respond helpfully."
        )

    def _append_chat_message(self, role: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {role}: {message}"
        self.chat_history.append({"role": role.lower(), "content": message})
        if hasattr(self, 'update_log'):
            try:
                self.update_log(f"[CHAT] {role}: {message}")
            except Exception:
                pass
        if self.chat_history_box and self.monitor_window:
            self.monitor_window.after(0, self._append_latest_chat_message)

    def _extract_delegation(self, response: str) -> dict | None:
        if not response:
            return None
        payload = self._extract_json_payload(response)
        if isinstance(payload, dict) and payload.get("delegate"):
            return payload
        return None

    def _extract_clarification(self, response: str) -> dict | None:
        if not response:
            return None
        payload = self._extract_json_payload(response)
        if isinstance(payload, dict) and payload.get("clarify"):
            return payload
        if isinstance(payload, dict) and payload.get("questions"):
            return {"questions": payload.get("questions")}
        return None

    def _extract_json_payload(self, response: str) -> dict | None:
        text = response.strip()
        if not text:
            return None
        if text.startswith("```"):
            fence_end = text.rfind("```")
            if fence_end > 0:
                text = text.strip('`').strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None

    def _handle_clarification_response(self, message: str) -> bool:
        questions = self.pending_clarification.get('questions') if self.pending_clarification else None
        if not questions:
            self.pending_clarification = None
            return False
        combined = [f"Original request: {self.pending_request}"]
        combined.append("Clarifications:")
        combined.append(message)
        self.pending_clarification = None
        self.pending_request = None
        thread = Thread(target=self._chat_api_call, args=("\n".join(combined),), daemon=True)
        thread.start()
        return True

    def _handle_simple_local_request(self, message: str) -> str | None:
        normalized = message.lower().strip()
        if any(phrase in normalized for phrase in ("what date", "today's date", "current date")):
            return f"Today's date is {datetime.now().strftime('%A, %B %d, %Y')}."
        if any(phrase in normalized for phrase in ("what time", "current time", "time is it")):
            return f"The current time is {datetime.now().strftime('%I:%M %p')}."
        return None

    def _handle_export_from_history(self, message: str) -> bool:
        """Detect if user wants to export existing chat data as a document.

        If the conversation already contains substantive content and the user
        is asking for it in a document format, handle the export directly
        instead of delegating to agents.
        """
        normalized = message.lower()
        # Must mention an export format
        export_keywords = ("word", "docx", "excel", "xlsx", "spreadsheet", "text file", ".txt", "document", "report")
        has_export_keyword = any(kw in normalized for kw in export_keywords)
        if not has_export_keyword:
            return False
        # Must reference existing data ("that", "this", "the information", etc.)
        reference_keywords = ("that info", "that data", "this info", "this data",
                              "the information", "the data", "the results",
                              "take that", "take this", "take the",
                              "convert that", "convert this", "convert the",
                              "export that", "export this", "export the",
                              "provide me with", "give me a", "create a",
                              "make a", "generate a", "put that", "put this",
                              "format that", "format this", "format the")
        has_reference = any(ref in normalized for ref in reference_keywords)
        if not has_reference:
            return False
        # Get the last substantive assistant response from chat history
        content = self._get_last_substantive_response()
        if not content:
            return False
        # Determine export format
        if 'excel' in normalized or 'xlsx' in normalized or 'spreadsheet' in normalized:
            export_fmt = 'excel'
        elif 'text' in normalized or '.txt' in normalized:
            export_fmt = 'text'
        else:
            export_fmt = 'word'
        # Run the export in a background thread to avoid freezing the UI
        thread = Thread(
            target=self._do_export_from_history,
            args=(content, export_fmt, message, normalized),
            daemon=True
        )
        thread.start()
        return True

    def _do_export_from_history(self, content: str, export_fmt: str, message: str, normalized: str):
        """Background thread: optionally reformat content then export."""
        try:
            # Use the LLM to reformat the content for the document if the user
            # asked for "detailed" or "well formatted" output
            needs_formatting = any(w in normalized for w in ("detailed", "well formatted", "well-formatted",
                                                              "professional", "formatted", "polished"))
            if needs_formatting:
                fmt_label = 'Word' if export_fmt == 'word' else export_fmt.title()
                self._append_chat_message("Assistant",
                                          f"Preparing your {fmt_label} document from the existing data...")
                content = self._reformat_for_export(content, export_fmt, message)

            self.pending_export_format = export_fmt
            self._export_if_requested(content)
            self.pending_export_format = None
        except Exception as exc:
            self._append_chat_message("System", f"Export error: {exc}")

    def _get_last_substantive_response(self) -> str | None:
        """Find the last substantive assistant response in chat history."""
        for msg in reversed(self.chat_history):
            if msg.get('role', '').lower() != 'assistant':
                continue
            content = msg.get('content', '')
            # Skip short responses, export confirmations, and clarification prompts
            if len(content) < 200:
                continue
            if content.startswith("Exported results to:"):
                continue
            if "clarifying questions" in content.lower():
                continue
            return content
        return None

    def _reformat_for_export(self, content: str, export_fmt: str, user_request: str) -> str:
        """Use the LLM to reformat content into a well-structured document."""
        try:
            api_endpoint = self._get_chat_api_endpoint()
            if not api_endpoint:
                return content
            fmt_name = {'word': 'Word document', 'excel': 'Excel spreadsheet', 'text': 'text document'}
            prompt = (
                f"The user wants the following information exported as a {fmt_name.get(export_fmt, 'document')}. "
                f"User request: \"{user_request}\"\n\n"
                "Reformat the content below into a well-structured, professional document with clear headings, "
                "sections, and tables where appropriate. Use markdown formatting. "
                "Do NOT add new information — only reorganize and format what is provided.\n\n"
                f"Content to format:\n{content}"
            )
            response = self.send_to_api(prompt, api_endpoint)
            if response and len(response.strip()) > 100:
                return response
        except Exception as exc:
            print(f"[MasterAgentNode] Reformat error: {exc}")
        return content

    def _needs_export_clarification(self, delegation: dict, latest_message: str) -> bool:
        if self.pending_export_format:
            return False
        export_format = delegation.get('export_format') or delegation.get('output_format')
        if export_format:
            self.pending_export_format = export_format
            return False
        return self._message_requests_export(latest_message)

    def _handle_export_clarification(self, message: str) -> bool:
        selected = self._parse_export_format(message)
        if selected is None:
            self._append_chat_message(
                "Assistant",
                "Please choose Word (.docx), Excel (.xlsx), Text (.txt), or say 'no export'."
            )
            return True
        if selected == 'none':
            self.pending_export_format = None
            delegation = self.pending_delegation
            self.pending_delegation = None
            if delegation:
                self._append_chat_message("Assistant", "Delegation dispatched.")
                results, _created_files = self._run_team_lead(delegation)
                formatted = self._format_delegation_results(results)
                self._append_chat_message("Assistant", formatted)
            return True
        self.pending_export_format = selected
        delegation = self.pending_delegation
        self.pending_delegation = None
        if delegation:
            self._append_chat_message("Assistant", "Delegation dispatched.")
            results, _created_files = self._run_team_lead(delegation)
            formatted = self._format_delegation_results(results)
            self._append_chat_message("Assistant", formatted)
            self._export_if_requested(formatted)
        return True

    def _parse_export_format(self, message: str) -> str | None:
        normalized = message.lower().strip()
        words = normalized.replace(',', ' ').replace('.', ' ').split()
        if 'no export' in normalized or normalized.startswith('no '):
            return 'none'
        if 'no' in words and any(term in normalized for term in ("show", "here", "thanks")):
            return 'none'
        if 'just show' in normalized or 'show here' in normalized or 'show them here' in normalized:
            return 'none'
        if 'word' in normalized or '.docx' in normalized:
            return 'word'
        if 'excel' in normalized or 'spreadsheet' in normalized or '.xlsx' in normalized:
            return 'excel'
        if 'text' in normalized or '.txt' in normalized or 'plain' in normalized:
            return 'text'
        return None

    def _message_requests_export(self, message: str) -> bool:
        if not message:
            return False
        normalized = message.lower()
        export_terms = ("export", "download", "save", "docx", "word", "xlsx", "excel", "spreadsheet", "text file", ".txt")
        return any(term in normalized for term in export_terms)

    def _format_delegation_results(self, raw: str) -> str:
        comms_summary = None
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, str):
            main_text = raw
            if "## Agent Comms Summary" in raw:
                main_text, comms_summary = raw.split("## Agent Comms Summary", 1)
                comms_summary = comms_summary.strip()
            data = self._extract_json_payload(main_text)
            if data is None:
                try:
                    data = json.loads(main_text)
                except Exception:
                    return raw
        else:
            return str(raw)
        if not isinstance(data, dict):
            return str(raw)

        lines = ["## Delegation Results"]
        tasks = data.get('tasks') or []
        if tasks:
            lines.append("### Tasks")
            for task in tasks:
                if isinstance(task, dict):
                    lines.append(f"- {task.get('task') or task.get('query') or json.dumps(task)}")
                else:
                    lines.append(f"- {task}")

        completion = data.get('completion_summary')
        if isinstance(completion, dict):
            lines.append("### Completion Summary")
            lines.append(f"- Total: {completion.get('total', 0)}")
            lines.append(f"- Completed: {completion.get('completed', 0)}")
            lines.append(f"- Errors: {completion.get('errors', 0)}")

        llm_response = data.get('llm_response')
        if llm_response:
            lines.append("### Team Lead Synthesis")
            lines.append(str(llm_response))

        tool_results = data.get('tool_results') or []
        if tool_results:
            lines.append("### Tool Results")
            for tool in tool_results:
                if not isinstance(tool, dict):
                    lines.append(f"- {tool}")
                    continue
                tool_name = tool.get('type', 'Tool')
                status = tool.get('status', 'unknown')
                lines.append(f"#### {tool_name} ({status})")
                output = tool.get('output')
                if isinstance(output, dict):
                    if 'summary' in output:
                        lines.append(str(output.get('summary')))
                    elif 'prompt' in output:
                        lines.append(str(output.get('prompt')))
                    elif 'results' in output and isinstance(output.get('results'), list):
                        for item in output.get('results'):
                            if isinstance(item, dict):
                                title = item.get('title') or item.get('name') or json.dumps(item)
                                url = item.get('url') or item.get('link')
                                lines.append(f"- {title}{f' ({url})' if url else ''}")
                            else:
                                lines.append(f"- {item}")
                    else:
                        lines.append("```")
                        lines.append(json.dumps(output, indent=2))
                        lines.append("```")
                elif output is not None:
                    lines.append(str(output))

        worker_results = data.get('worker_results') or []
        if worker_results:
            lines.append("### Worker Results")
            for result in worker_results:
                if isinstance(result, dict):
                    worker_id = result.get('worker_id') or result.get('workerid') or result.get('agent_id')
                    status = result.get('status') or 'unknown'
                    summary = result.get('summary') or result.get('prompt') or result.get('llm_response')
                    line = f"- {worker_id or 'worker'}: {status}"
                    if summary:
                        line = f"{line} — {summary}"
                    lines.append(line)
                else:
                    lines.append(f"- {result}")

        created_files = data.get('created_files') or []
        if created_files:
            lines.append("### Created Files")
            for cf in created_files:
                if isinstance(cf, dict):
                    path = cf.get('path', '')
                    fmt = cf.get('format', '')
                    lines.append(f"- {fmt}: {path}")
                else:
                    lines.append(f"- {cf}")

        if comms_summary:
            lines.append("### Agent Comms Summary")
            lines.append(comms_summary)
        return "\n".join(lines)

    def _summarize_delegation_for_wa(self, original_request: str,
                                      formatted_results: str,
                                      outbox_folder: str,
                                      api_endpoint: str) -> str:
        """Produce a concise WhatsApp-friendly summary of delegation results.

        Instead of returning the full worker output (which may contain raw
        HTML, code, etc.), ask the LLM to summarise what was accomplished
        and tell the user where to find the output files.
        """
        folder_note = (
            f"The output files were saved to: {outbox_folder}"
            if outbox_folder else "The output files were saved to the project folder."
        )

        # Extract created file paths from the formatted results
        file_lines = []
        if "### Created Files" in formatted_results:
            in_files = False
            for line in formatted_results.split('\n'):
                if line.strip() == "### Created Files":
                    in_files = True
                    continue
                if in_files:
                    if line.startswith('###') or line.startswith('## '):
                        break
                    if line.strip().startswith('- '):
                        file_lines.append(line.strip()[2:])
        files_note = ""
        if file_lines:
            files_note = "Files created:\n" + "\n".join(f"  - {f}" for f in file_lines)

        # Extract the Team Lead Synthesis (the high-quality analysis) if present,
        # since the raw formatted_results starts with task metadata that isn't useful.
        synthesis = ""
        if "### Team Lead Synthesis" in formatted_results:
            parts = formatted_results.split("### Team Lead Synthesis", 1)
            tail = parts[1]
            # Find the next section header to isolate just the synthesis
            next_header = -1
            for marker in ("### Tool Results", "### Worker Results",
                           "### Created Files", "### Agent Comms Summary"):
                idx = tail.find(marker)
                if idx != -1 and (next_header == -1 or idx < next_header):
                    next_header = idx
            synthesis = tail[:next_header].strip() if next_header != -1 else tail.strip()

        # Also grab worker result summaries if synthesis is short
        worker_block = ""
        if "### Worker Results" in formatted_results:
            wp = formatted_results.split("### Worker Results", 1)[1]
            nh = -1
            for marker in ("### Created Files", "### Agent Comms Summary", "### Tool Results"):
                idx = wp.find(marker)
                if idx != -1 and (nh == -1 or idx < nh):
                    nh = idx
            worker_block = wp[:nh].strip() if nh != -1 else wp.strip()

        # Build the best context: synthesis first, then workers, then raw
        max_ctx = 8000
        if synthesis:
            context_for_llm = synthesis[:max_ctx]
            remaining = max_ctx - len(context_for_llm)
            if worker_block and remaining > 500:
                context_for_llm += "\n\n--- Worker Details ---\n" + worker_block[:remaining]
        else:
            context_for_llm = formatted_results[:max_ctx]
        if len(context_for_llm) >= max_ctx:
            context_for_llm += "\n... (truncated)"

        summary_prompt = (
            "You are a helpful assistant replying via WhatsApp. "
            "A team of AI agents just completed a delegated task. "
            "Provide a meaningful summary of the KEY FINDINGS and RESULTS. "
            "Include the most important specific details, numbers, names, "
            "and conclusions from the analysis — not just 'we analyzed it'. "
            "Keep it conversational and WhatsApp-friendly (no markdown headers, "
            "no code blocks). Use short paragraphs or a simple numbered list "
            "if there are multiple key points. Aim for 4-8 sentences.\n\n"
            f"Original request: {original_request}\n\n"
            f"Team analysis results:\n{context_for_llm}\n\n"
        )
        if files_note:
            summary_prompt += f"{files_note}\n\n"
        summary_prompt += f"{folder_note}\n\nYour concise WhatsApp reply:"

        try:
            summary = self.send_to_api(summary_prompt, api_endpoint)
            if summary and summary.strip():
                return summary.strip()
        except Exception as exc:
            self.update_log(f"[WA] Error summarising delegation: {exc}")

        # Fallback if LLM call fails
        if file_lines:
            file_list = ", ".join(file_lines)
            return (
                f"Your request has been completed! The following files were created: "
                f"{file_list}. {folder_note}"
            )
        return (
            f"Your request has been completed. The team processed your task "
            f"and the output files are ready. {folder_note}"
        )

    def _run_team_lead(self, delegation: dict) -> str:
        workflow_name = self._get_workflow_name()
        inbox_folder = self._get_inbox_folder()
        outbox_folder = self._get_outbox_folder()
        channel_id = self._ensure_channel_id(workflow_name)
        team_lead = TeamLeadNode(node_id="team_lead_runtime", config=self.config)

        # Propagate the Master's configured LLM endpoint to the TeamLead
        # so it (and its Workers) use the workflow-configured endpoint
        # instead of defaulting to the first interface in config.yaml.
        llm_endpoint = self._get_chat_api_endpoint()
        if llm_endpoint:
            team_lead.properties.setdefault('llm_api_endpoint', {'type': 'dropdown', 'default': llm_endpoint})
            team_lead.properties['llm_api_endpoint']['value'] = llm_endpoint
            print(f"[MasterAgentNode] Propagating llm_api_endpoint={llm_endpoint!r} to runtime TeamLead")

        # Propagate search API URL
        search_url = (
            self.properties.get('search_api_url', {}).get('value')
            or self.properties.get('search_api_url', {}).get('default')
            or ''
        )
        if search_url:
            team_lead.properties.setdefault('search_api_url', {'type': 'text', 'default': search_url})
            team_lead.properties['search_api_url']['value'] = search_url

        # Propagate LLM model override if set
        llm_model = (
            self.properties.get('llm_model', {}).get('value')
            or self.properties.get('llm_model', {}).get('default')
        )
        if llm_model:
            team_lead.properties.setdefault('llm_model', {'type': 'text', 'default': llm_model})
            team_lead.properties['llm_model']['value'] = llm_model

        # Propagate LLM temperature if set
        llm_temperature = (
            self.properties.get('llm_temperature', {}).get('value')
            or self.properties.get('llm_temperature', {}).get('default')
        )
        if llm_temperature is not None:
            team_lead.properties.setdefault('llm_temperature', {'type': 'number', 'default': llm_temperature})
            team_lead.properties['llm_temperature']['value'] = llm_temperature

        inputs = {
            "input": delegation,
            "workflow_name": workflow_name,
            "inbox_folder": inbox_folder,
            "outbox_folder": outbox_folder,
            "channel_id": channel_id,
        }
        print(f"[MCA-DIAG] _run_team_lead: outbox_folder={outbox_folder!r}, delegation_keys={list(delegation.keys())}")
        result = team_lead.process(inputs)
        output = result.get("output") if isinstance(result, dict) else result
        # Extract created_files from the team lead output
        created_files = []
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
            if isinstance(parsed, dict):
                created_files = parsed.get('created_files', [])
                print(f"[MCA-DIAG] _run_team_lead result: created_files={created_files}, output_len={len(output) if output else 0}")
        except Exception:
            print(f"[MCA-DIAG] _run_team_lead result: output_len={len(output) if output else 0} (not JSON)")
        comms_summary = self._summarize_channel_messages(channel_id)
        base_output = output if isinstance(output, str) else json.dumps(output, indent=2)
        if comms_summary:
            base_output = f"{base_output}\n\n## Agent Comms Summary\n{comms_summary}"
        # Return tuple: (output_text, list_of_created_file_paths)
        file_paths = []
        for cf in created_files:
            if isinstance(cf, dict) and cf.get('path'):
                file_paths.append(cf['path'])
            elif isinstance(cf, str):
                file_paths.append(cf)
        print(f"[MCA-DIAG] _run_team_lead returning {len(file_paths)} file paths: {file_paths}")
        return base_output, file_paths

    def _ensure_channel_id(self, workflow_name: str) -> str | None:
        if self.channel_id:
            return self.channel_id
        channel_name = self.properties.get('channel_name', {}).get('value') or self.properties.get('channel_name', {}).get('default')
        if channel_name:
            self.channel_name = channel_name
        channel = create_channel(str(workflow_name or 'workflow'), str(self.channel_name or 'team'))
        self.channel_id = channel.channel_id
        return self.channel_id

    def _summarize_channel_messages(self, channel_id: str | None) -> str | None:
        if not channel_id:
            return None
        channel = get_channel(channel_id)
        if not channel:
            return None
        messages = channel.snapshot()
        if not messages:
            return None
        lines = []
        for message in messages[-10:]:
            sender = message.get('from', 'agent')
            msg = message.get('message', '')
            status = message.get('status') or message.get('type')
            prefix = f"[{status}] " if status else ""
            lines.append(f"- {sender}: {prefix}{msg}")
        return "\n".join(lines)

    def _export_if_requested(self, content: str):
        export_format = self.pending_export_format
        if not export_format or export_format == 'none':
            return
        output_folder = self._get_outbox_folder()
        if not output_folder:
            self._append_chat_message("System", "Export skipped: output folder is not set.")
            return
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        filename_base = self.project_name_var.get().strip() if hasattr(self, 'project_name_var') else ''
        if not filename_base:
            filename_base = 'master_agent_export'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if export_format == 'word':
            output_path = os.path.join(output_folder, f"{filename_base}_{timestamp}.docx")
            convert_markdown_to_docx(content, output_path=output_path, formatting_enabled=True)
        elif export_format == 'excel':
            output_path = os.path.join(output_folder, f"{filename_base}_{timestamp}.xlsx")
            convert_markdown_to_excel(content, output_path=output_path, formatting_enabled=True)
        else:
            output_path = os.path.join(output_folder, f"{filename_base}_{timestamp}.txt")
            with open(output_path, 'w', encoding='utf-8') as handle:
                handle.write(content)
        self._append_chat_message("Assistant", f"Exported results to: {output_path}")

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        results = []
        if not tool_calls:
            return results
        llm_endpoint = self._get_chat_api_endpoint()
        print(f"[MasterAgentNode] _execute_tool_calls: llm_endpoint={llm_endpoint!r}, num_calls={len(tool_calls)}")
        valid_endpoints = set((self.config.get('interfaces') or {}).keys())
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            node_type = call.get('type') or call.get('node_type')
            if not node_type:
                continue
            node_cls = NODE_REGISTRY.get(node_type)
            if not node_cls:
                results.append({'type': node_type, 'status': 'error', 'error': 'Unknown node type'})
                continue
            try:
                node = node_cls(node_id=f"tool_{node_type}", config=self.config)
                properties = call.get('properties') or {}
                if node_type == 'SearchScrapeSummarizeNode':
                    if llm_endpoint and llm_endpoint in valid_endpoints:
                        properties['api_endpoint'] = llm_endpoint
                    elif properties.get('api_endpoint') and properties['api_endpoint'] not in valid_endpoints:
                        properties.pop('api_endpoint', None)
                    print(f"[MasterAgentNode] SearchScrapeSummarize: api_endpoint={properties.get('api_endpoint')!r}")
                # Propagate outbox_folder and export_format to ExportDocumentNode
                if node_type == 'ExportDocumentNode':
                    outbox = self._get_outbox_folder()
                    if outbox:
                        properties.setdefault('output_folder', outbox)
                    # Ensure export_format is set correctly from pending or properties
                    if self.pending_export_format and 'export_format' not in properties:
                        fmt_map = {'word': 'Word (.docx)', 'excel': 'Excel (.xlsx)', 'text': 'Text (.txt)'}
                        properties['export_format'] = fmt_map.get(self.pending_export_format, 'Word (.docx)')
                for key, value in properties.items():
                    if key in node.properties and isinstance(node.properties[key], dict):
                        node.properties[key]['value'] = value
                    else:
                        node.properties[key] = {'type': 'text', 'default': value, 'value': value}
                tool_input = call.get('input') or call.get('payload') or ''
                if isinstance(tool_input, dict):
                    payload = dict(tool_input)
                else:
                    payload = {'input': tool_input}
                output = node.process(payload)
                results.append({'type': node_type, 'status': 'ok', 'output': output})
            except Exception as exc:
                results.append({'type': node_type, 'status': 'error', 'error': str(exc)})
        return results

    def _get_tool_catalog_text(self) -> str:
        catalog = get_node_catalog()
        lines = []
        for entry in catalog:
            inputs = ", ".join(entry.get('inputs') or [])
            outputs = ", ".join(entry.get('outputs') or [])
            lines.append(
                f"- {entry.get('type')}: {entry.get('description')} (inputs: {inputs or 'none'}; outputs: {outputs or 'none'})"
            )
        return "\n".join(lines)

    def _get_outbox_folder(self) -> str:
        prop = self.properties.get('outbox_folder', {})
        if isinstance(prop, dict):
            return prop.get('value') or prop.get('default', '')
        return prop or ''

    def _get_inbox_folder(self) -> str:
        prop = self.properties.get('inbox_folder', {})
        if isinstance(prop, dict):
            return prop.get('value') or prop.get('default', '')
        return prop or ''

    def _get_workflow_name(self) -> str:
        if hasattr(self, 'inputs') and isinstance(self.inputs, dict):
            return self.inputs.get('workflow_name') or self.inputs.get('workflow_id') or "workflow"
        return "workflow"

    def _configure_chat_tags(self):
        if not self.chat_history_box:
            return
        self.chat_history_box.tag_configure('role', font=('Helvetica', 10, 'bold'))
        self.chat_history_box.tag_configure('user_content', foreground='black')
        self.chat_history_box.tag_configure('assistant_content', foreground='dark blue')
        self.chat_history_box.tag_configure('system_content', foreground='dark green')

    def _append_latest_chat_message(self):
        """Append only the most recent chat message to the widget.

        This avoids the O(n²) cost of re-rendering the entire history on
        every message, which was causing severe UI lag with large conversations.
        """
        if not self.chat_history_box or not self.chat_history:
            return
        try:
            msg = self.chat_history[-1]
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            self.chat_history_box.config(state=tk.NORMAL)
            self.chat_history_box.insert(END, f"{role.capitalize()}:\n", 'role')
            base_tag = f"{role}_content"
            apply_formatting(self.chat_history_box, content, base_tag=base_tag)
            self.chat_history_box.insert(END, "\n\n")
            self.chat_history_box.config(state=tk.DISABLED)
            self.chat_history_box.see(END)
        except Exception:
            pass

    def _render_chat_history(self):
        """Full re-render of chat history. Used only on initial load."""
        if not self.chat_history_box:
            return
        try:
            self.chat_history_box.config(state=tk.NORMAL)
            self.chat_history_box.delete('1.0', END)
            for message in self.chat_history:
                role = message.get('role', 'user')
                content = message.get('content', '')
                self.chat_history_box.insert(END, f"{role.capitalize()}:\n", 'role')
                base_tag = f"{role}_content"
                apply_formatting(self.chat_history_box, content, base_tag=base_tag)
                self.chat_history_box.insert(END, "\n\n")
            self.chat_history_box.config(state=tk.DISABLED)
            self.chat_history_box.see(END)
        except Exception:
            pass

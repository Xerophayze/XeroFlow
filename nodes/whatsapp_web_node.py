# nodes/whatsapp_web_node.py
"""WhatsApp Web Node — connects to a personal WhatsApp account via QR code
scan using the neonize library (built on Whatsmeow). No API keys or business
account required. Just scan the QR code with your phone and start chatting
with the Master Agent through WhatsApp."""

from __future__ import annotations

import io
import logging
import mimetypes
import os
import re
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .base_node import BaseNode
from src.workflows.node_registry import register_node

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WA_MAX_TEXT_LENGTH = 4096  # WhatsApp text message limit
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_sessions")


# ---------------------------------------------------------------------------
# The Node
# ---------------------------------------------------------------------------
@register_node("WhatsAppWebNode")
class WhatsAppWebNode(BaseNode):
    """Personal WhatsApp integration via QR code scan. Uses the neonize
    library (Whatsmeow) to connect directly to WhatsApp Web — no API keys
    or business account needed. Add this node to a workflow and connect it
    to the MasterAgentNode to chat with the AI through WhatsApp."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None
        self._client_thread: Optional[threading.Thread] = None
        self._connected = False
        self._stop_event = threading.Event()
        self._message_queue: List[Dict] = []
        self._queue_lock = threading.Lock()
        self._processed_ids: set = set()
        self._log_messages: List[str] = []
        self._log_lock = threading.Lock()
        self._monitor_window = None
        self._qr_label = None
        self._status_var = None
        self._log_text = None
        self._media_dir = Path(tempfile.gettempdir()) / "xeroflow_wa_web_media"
        self._media_dir.mkdir(parents=True, exist_ok=True)
        self._message_callback = None
        self._my_jid = None          # str: primary JID user
        self._my_jids = set()          # set of all known self-identifiers

    # -- Node interface -----------------------------------------------------

    def define_inputs(self):
        return ["response"]

    def define_outputs(self):
        return ["message", "files"]

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            "node_name": {
                "type": "text",
                "label": "Custom Node Name",
                "default": "WhatsAppWebNode",
            },
            "description": {
                "type": "text",
                "label": "Description",
                "default": (
                    "Connects to your personal WhatsApp via QR code scan. "
                    "No API keys needed. Scan the QR code displayed in the "
                    "monitor window with your phone to link. Supports text "
                    "and file messages."
                ),
            },
            "session_name": {
                "type": "text",
                "label": "Session Name",
                "default": "xeroflow_wa",
                "description": "Name for the session database file. Changing this creates a new session.",
            },
            "allowed_numbers": {
                "type": "textarea",
                "label": "Allowed Phone Numbers",
                "default": "",
                "description": (
                    "Comma-separated phone numbers or JIDs allowed to interact "
                    "(e.g. 11234567890). Use 'self' to allow only your own "
                    "self-chat. Empty = allow all."
                ),
            },
            "trigger_keyword": {
                "type": "text",
                "label": "Bot Trigger Name",
                "default": "",
                "description": (
                    "A name or keyword that external (non-self) messages must "
                    "contain for the bot to respond (e.g. 'Jarvis'). "
                    "Case-insensitive. Self-chat messages are always processed "
                    "regardless. Leave empty to respond to all allowed messages."
                ),
            },
            "auto_reply": {
                "type": "boolean",
                "label": "Auto-Reply Mode",
                "default": True,
                "description": "Automatically forward messages to the AI and send the response back.",
            },
            "reply_to_groups": {
                "type": "boolean",
                "label": "Reply to Group Messages",
                "default": False,
                "description": "If enabled, the bot will also respond to messages in group chats.",
            },
            "is_start_node": {
                "type": "boolean",
                "label": "Start Node",
                "default": False,
            },
            "is_end_node": {
                "type": "boolean",
                "label": "End Node",
                "default": False,
            },
            "is_persistent": {
                "type": "boolean",
                "label": "Persistent Node",
                "default": True,
                "description": "Keeps the WhatsApp connection alive to receive messages continuously.",
            },
        })
        return props

    def process(self, inputs):
        """Called by the workflow engine.

        Creates the monitor window, starts the neonize client, then enters
        a blocking loop (like AssistantNode) so the node stays alive for
        the duration of the workflow.
        """
        self.inputs = inputs
        self._stop_event.clear()

        # Get the workflow's stop_event if available
        workflow_stop_event = inputs.get("stop_event") if isinstance(inputs, dict) else None

        # 1. Create the monitor window first so QR code has somewhere to display
        try:
            self._create_monitor_window()
        except Exception as exc:
            self._log(f"Monitor window error: {exc}")

        # 2. Start the neonize client (background thread)
        self._initialize()

        # 3. Block — keep the node alive so the graph processor doesn't
        #    treat it as "done". This mirrors how AssistantNode works.
        self._log("WhatsApp Web node running. Waiting for messages...")
        while not self._stop_event.is_set():
            if workflow_stop_event and workflow_stop_event.is_set():
                self._log("Workflow stop event detected.")
                self._stop_event.set()
                break
            try:
                time.sleep(1)
            except Exception:
                break

        # Cleanup
        self._stop_node()
        return {"message": "", "files": ""}

    # -- Initialization -----------------------------------------------------

    def _initialize(self):
        """Set up the neonize client and start it in a background thread."""
        try:
            from neonize.client import NewClient
            from neonize.events import ConnectedEv, MessageEv, PairStatusEv, event as neonize_event
        except ImportError:
            self._log("ERROR: neonize is not installed. Run: pip install neonize")
            self._log("Then restart the workflow.")
            return

        # Register this node so MasterAgentNode can find us (and vice versa)
        try:
            from src.workflows.node_registry import register_running_instance
            register_running_instance("WhatsAppWebNode", self)
        except Exception:
            pass

        # Ensure session directory exists
        os.makedirs(SESSION_DIR, exist_ok=True)
        session_name = self._get_prop("session_name") or "xeroflow_wa"
        db_path = os.path.join(SESSION_DIR, f"{session_name}.sqlite3")

        self._log(f"Session database: {db_path}")
        self._log("Initializing WhatsApp Web client...")

        client = NewClient(db_path)
        self._client = client
        self._neonize_event = neonize_event

        # --- QR code callback: display in monitor window + terminal ---
        @client.event.qr
        def on_qr(_client, qr_data: bytes):
            """Called by neonize when a QR code needs to be displayed."""
            qr_string = qr_data.decode("utf-8") if isinstance(qr_data, bytes) else str(qr_data)
            self._log("QR code received! Scan it with WhatsApp > Linked Devices > Link a Device")

            # Print to terminal as fallback (using segno like neonize's default)
            try:
                import segno
                segno.make_qr(qr_string).terminal(compact=True)
            except Exception:
                print(f"[WhatsAppWeb] QR data: {qr_string}")

            # Display in the monitor window
            if self._monitor_window:
                try:
                    self._monitor_window.after(0, lambda qs=qr_string: self._display_qr_in_window(qs))
                except Exception:
                    pass

            # Update status
            if self._status_var and self._monitor_window:
                try:
                    self._monitor_window.after(0, lambda: self._status_var.set("Scan QR Code"))
                except Exception:
                    pass

        # --- Connected event ---
        @client.event(ConnectedEv)
        def on_connected(_client, _ev):
            self._connected = True
            self._log("Connected to WhatsApp!")
            # Retrieve own JID from the client (essential for self-chat detection).
            # On reconnect from a saved session, PairStatusEv does NOT fire,
            # so this is the only place to capture it.
            if not self._my_jids:
                self._extract_my_jids(_client)
            if self._my_jids:
                self._log(f"My identifiers: {self._my_jids}")
            if self._status_var and self._monitor_window:
                try:
                    label = self._my_jid or next(iter(self._my_jids), "")
                    status_text = f"Connected ({label})" if label else "Connected"
                    self._monitor_window.after(0, lambda: self._status_var.set(status_text))
                except Exception:
                    pass
            # Hide QR code label if visible
            if self._qr_label and self._monitor_window:
                try:
                    self._monitor_window.after(0, self._hide_qr)
                except Exception:
                    pass

        # --- Pair status event ---
        @client.event(PairStatusEv)
        def on_pair_status(_client, ev):
            if hasattr(ev, "ID") and hasattr(ev.ID, "User"):
                uid = str(ev.ID.User)
                self._my_jid = uid
                self._my_jids.add(uid)
            self._log(f"Logged in as: {self._my_jid}")
            # Also grab full identity set
            self._extract_my_jids(_client)
            if self._status_var and self._monitor_window:
                try:
                    self._monitor_window.after(
                        0, lambda: self._status_var.set(f"Paired: {self._my_jid}")
                    )
                except Exception:
                    pass

        # --- Message event ---
        @client.event(MessageEv)
        def on_message(_client, message):
            self._handle_incoming_message(_client, message)

        # Start the client in a background thread
        def run_client():
            self._log("Starting WhatsApp Web connection...")
            self._log("Open WhatsApp on your phone > Settings > Linked Devices > Link a Device")
            self._log("Scan the QR code when it appears.")
            try:
                client.connect()
                # connect() blocks; after it returns, wait for stop
                neonize_event.wait()
            except Exception as exc:
                self._log(f"Client error: {exc}")
                traceback.print_exc()
            finally:
                self._connected = False
                self._log("WhatsApp Web client stopped.")
                if self._status_var and self._monitor_window:
                    try:
                        self._monitor_window.after(0, lambda: self._status_var.set("Disconnected"))
                    except Exception:
                        pass

        self._client_thread = threading.Thread(target=run_client, daemon=True)
        self._client_thread.start()

    # -- Incoming message handling ------------------------------------------

    def _handle_incoming_message(self, client, message):
        """Process an incoming WhatsApp message from neonize."""
        try:
            info = message.Info
            msg = message.Message
            msg_id = str(info.ID) if hasattr(info, "ID") else ""

            # Deduplicate
            if msg_id in self._processed_ids:
                return
            self._processed_ids.add(msg_id)
            if len(self._processed_ids) > 5000:
                self._processed_ids = set(list(self._processed_ids)[-2500:])

            # Get sender info
            source = info.MessageSource
            chat_jid = source.Chat
            sender_jid = source.Sender
            is_group = source.IsGroup if hasattr(source, "IsGroup") else False

            # Skip group messages if not enabled
            reply_to_groups = self._get_prop("reply_to_groups")
            if is_group and not (reply_to_groups and str(reply_to_groups).lower() not in ("false", "0", "")):
                return

            # Get sender number (WhatsApp JID User field)
            sender_number = str(sender_jid.User) if hasattr(sender_jid, "User") else str(sender_jid)
            chat_number = str(chat_jid.User) if hasattr(chat_jid, "User") else str(chat_jid)
            self._log(f"Message from sender={sender_number}, chat={chat_number}")

            # Determine if this is a true self-chat message.
            # Self-chat = sender is me AND the chat/conversation is also me
            # (i.e. messaging yourself). Messages you send to OTHER people
            # have sender=you but chat=them — those are NOT self-chat.
            sender_is_me = (sender_number in self._my_jids) if self._my_jids else False
            chat_is_me = (chat_number in self._my_jids) if self._my_jids else False
            is_self_chat = sender_is_me and chat_is_me

            # Check allowed numbers (empty = allow all)
            allowed = self._get_allowed_numbers()
            allow_self = self._allows_self_chat(allowed)

            if is_self_chat:
                if not allow_self:
                    self._log(f"Self-chat blocked (allowed={allowed}, allow_self={allow_self})")
                    return
                self._log("Self-chat allowed — processing")
            else:
                # Not a self-message — check allowed list
                if allowed and not self._number_matches(sender_number, allowed):
                    self._log(f"Blocked message from: {sender_number} (not in allowed list: {allowed})")
                    self._log(f"  Tip: Add '{sender_number}' to allowed_numbers, or leave blank to allow all.")
                    return

            # Extract text content (pre-read for trigger keyword check)
            text_content = ""
            file_paths = []

            # Pre-extract text so we can check trigger keyword before downloading media
            if msg.conversation:
                text_content = msg.conversation
            elif hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage and msg.extendedTextMessage.text:
                text_content = msg.extendedTextMessage.text

            # For non-self-chat messages, require the trigger keyword
            if not is_self_chat:
                trigger = (self._get_prop("trigger_keyword") or "").strip()
                if trigger:
                    if trigger.lower() not in text_content.lower():
                        self._log(f"No trigger '{trigger}' in message from {sender_number} — ignoring")
                        return
                    self._log(f"Trigger '{trigger}' matched — processing message")
                    # Strip the trigger keyword from the message
                    import re
                    text_content = re.sub(
                        re.escape(trigger), "", text_content, count=1, flags=re.IGNORECASE
                    ).strip()

            # Image message
            if hasattr(msg, "HasField") and msg.HasField("imageMessage"):
                img_msg = msg.imageMessage
                caption = img_msg.caption if hasattr(img_msg, "caption") else ""
                if caption:
                    text_content = caption
                elif not text_content:
                    text_content = "[Sent an image]"
                # Download the image
                local_path = self._download_media(client, msg, "image")
                if local_path:
                    file_paths.append(local_path)

            # Document message
            if hasattr(msg, "HasField") and msg.HasField("documentMessage"):
                doc_msg = msg.documentMessage
                caption = doc_msg.caption if hasattr(doc_msg, "caption") else ""
                filename = doc_msg.fileName if hasattr(doc_msg, "fileName") else ""
                if caption:
                    text_content = caption
                elif not text_content:
                    text_content = f"[Sent document: {filename}]"
                local_path = self._download_media(client, msg, "document")
                if local_path:
                    file_paths.append(local_path)

            # Audio message
            if hasattr(msg, "HasField") and msg.HasField("audioMessage"):
                if not text_content:
                    text_content = "[Sent audio]"
                local_path = self._download_media(client, msg, "audio")
                if local_path:
                    file_paths.append(local_path)

            # Video message
            if hasattr(msg, "HasField") and msg.HasField("videoMessage"):
                vid_msg = msg.videoMessage
                caption = vid_msg.caption if hasattr(vid_msg, "caption") else ""
                if caption:
                    text_content = caption
                elif not text_content:
                    text_content = "[Sent video]"
                local_path = self._download_media(client, msg, "video")
                if local_path:
                    file_paths.append(local_path)

            if not text_content and not file_paths:
                return

            display_name = sender_number
            self._log(
                f"Message from {display_name}: "
                f"{text_content[:100]}{'...' if len(text_content) > 100 else ''}"
            )

            msg_data = {
                "id": msg_id,
                "from": sender_number,
                "chat_jid": chat_jid,
                "sender_jid": sender_jid,
                "is_group": is_group,
                "text": text_content,
                "files": file_paths,
                "raw_message": message,
                "received_at": datetime.now().isoformat(),
            }

            with self._queue_lock:
                self._message_queue.append(msg_data)

            # Auto-reply (run in a separate thread to avoid blocking the
            # neonize event loop — otherwise concurrent messages queue up
            # and responses can get lost)
            auto_reply = self._get_prop("auto_reply")
            if auto_reply and str(auto_reply).lower() not in ("false", "0", ""):
                t = threading.Thread(
                    target=self._handle_auto_reply,
                    args=(msg_data,),
                    daemon=True,
                    name=f"wa-reply-{msg_data['id'][:8]}",
                )
                t.start()

        except Exception as exc:
            self._log(f"Error handling message: {exc}")
            traceback.print_exc()

    def _download_media(self, client, msg, media_type: str) -> Optional[str]:
        """Download media from a WhatsApp message using neonize's download method."""
        try:
            data = client.download_any(msg)
            if not data:
                return None

            # Determine extension
            ext_map = {
                "image": ".jpg",
                "document": ".bin",
                "audio": ".ogg",
                "video": ".mp4",
            }
            # Try to get actual extension from the message
            ext = ext_map.get(media_type, ".bin")
            if media_type == "document" and hasattr(msg, "documentMessage") and msg.documentMessage:
                fname = msg.documentMessage.fileName if hasattr(msg.documentMessage, "fileName") else ""
                if fname and "." in fname:
                    ext = "." + fname.rsplit(".", 1)[-1]
            elif media_type == "image" and hasattr(msg, "imageMessage") and msg.imageMessage:
                mime = msg.imageMessage.mimetype if hasattr(msg.imageMessage, "mimetype") else ""
                if mime:
                    guessed = mimetypes.guess_extension(mime)
                    if guessed:
                        ext = guessed
            elif media_type == "audio" and hasattr(msg, "audioMessage") and msg.audioMessage:
                mime = msg.audioMessage.mimetype if hasattr(msg.audioMessage, "mimetype") else ""
                if mime:
                    guessed = mimetypes.guess_extension(mime)
                    if guessed:
                        ext = guessed

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"wa_{media_type}_{timestamp}{ext}"
            save_path = str(self._media_dir / filename)

            with open(save_path, "wb") as f:
                f.write(data)

            self._log(f"Downloaded {media_type}: {filename} ({len(data)} bytes)")
            return save_path

        except Exception as exc:
            self._log(f"Media download error ({media_type}): {exc}")
            return None

    def _find_master_agent(self):
        """Discover a running MasterAgentNode via the shared runtime registry.

        When MasterAgentNode starts its monitor window it registers itself
        in ``RUNNING_INSTANCES``.  We look it up here each time (no caching)
        so that we pick up the instance even if it started after us.
        """
        try:
            from src.workflows.node_registry import get_running_instance
            master = get_running_instance('MasterAgentNode')
            if master and hasattr(master, 'process_external_message'):
                return master
        except Exception:
            pass
        return None

    def _handle_auto_reply(self, msg_data: dict):
        """Forward the message to the AI and send the response back.

        Priority order:
        1. Connected MasterAgentNode (via process_external_message)
        2. Registered callback function
        3. Direct API call as fallback
        """
        text = msg_data["text"]
        files = msg_data.get("files", [])
        chat_jid = msg_data["chat_jid"]

        # 1. Try the connected MasterAgentNode
        master = self._find_master_agent()
        if master:
            try:
                self._log(f"Routing to Master Agent... (chat={getattr(chat_jid, 'User', chat_jid)})")
                result = master.process_external_message(
                    text, sender="WhatsApp", files=files if files else None
                )
                # Handle both dict (new) and str (legacy) returns
                if isinstance(result, dict):
                    response_text = result.get("text", "")
                    response_files = result.get("files", [])
                else:
                    response_text = result
                    response_files = []

                if response_text:
                    self._log(f"Got response ({len(response_text)} chars), sending to chat...")
                    self._send_wa_text(chat_jid, response_text)
                # Send any output files back through WhatsApp
                for fpath in response_files:
                    try:
                        self._log(f"Sending file: {Path(fpath).name}")
                        self._send_wa_file(chat_jid, fpath)
                    except Exception as fexc:
                        self._log(f"Error sending file {fpath}: {fexc}")
                if response_text or response_files:
                    return
                self._log("Master Agent returned empty response")
            except Exception as exc:
                self._log(f"Master Agent error: {exc}")
                traceback.print_exc()

        prompt = text
        if files:
            file_names = [Path(f).name for f in files]
            prompt = f"{text}\n\n[Attached files: {', '.join(file_names)}]"

        # 2. Try registered callback
        if self._message_callback:
            try:
                response = self._message_callback(text, files)
                if response:
                    self._send_wa_text(chat_jid, response)
                    return
            except Exception as exc:
                self._log(f"Callback error: {exc}")

        # 3. Fallback: use the node's own API service
        try:
            api_endpoints = self.get_api_endpoints()
            if not api_endpoints:
                self._send_wa_text(
                    chat_jid,
                    "I'm currently unable to process your request. No AI endpoint is configured.",
                )
                return

            api_name = api_endpoints[0]
            api_config = self.config.get("interfaces", {}).get(api_name, {})

            response = self.send_api_request(
                content=prompt,
                api_name=api_name,
                model=api_config.get("selected_model"),
                max_tokens=api_config.get("max_tokens"),
                temperature=api_config.get("temperature", 0.7),
            )

            if response.success:
                self._send_wa_text(chat_jid, response.content)
            else:
                self._send_wa_text(
                    chat_jid,
                    f"Sorry, I encountered an error: {response.error}",
                )

        except Exception as exc:
            self._log(f"Auto-reply error: {exc}")
            traceback.print_exc()
            self._send_wa_text(chat_jid, "Sorry, an unexpected error occurred.")

    # -- Sending messages ---------------------------------------------------

    def _send_response_to_pending(self, response_text: str):
        """Send a response to the most recent pending message sender."""
        with self._queue_lock:
            if not self._message_queue:
                return
            last_msg = self._message_queue[-1]

        chat_jid = last_msg.get("chat_jid")
        if chat_jid:
            self._send_wa_text(chat_jid, response_text)

    def _send_wa_text(self, chat_jid, text: str):
        """Send a text message via neonize, splitting if needed."""
        if not self._client or not self._connected:
            self._log("Cannot send — not connected")
            return

        clean_text = self._strip_markdown_for_whatsapp(text)
        chunks = self._split_text(clean_text)

        for chunk in chunks:
            try:
                self._client.send_message(chat_jid, chunk)
            except Exception as exc:
                self._log(f"Send error: {exc}")
                return

        display = clean_text[:80] + ("..." if len(clean_text) > 80 else "")
        self._log(f"Sent reply: {display}")

    def _send_wa_file(self, chat_jid, file_path: str, caption: str = ""):
        """Send a file via neonize."""
        if not self._client or not self._connected:
            self._log("Cannot send file — not connected")
            return

        if not os.path.exists(file_path):
            self._log(f"File not found: {file_path}")
            return

        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        filename = Path(file_path).name

        try:
            if mime_type.startswith("image/"):
                self._client.send_image(chat_jid, file_path, caption=caption)
            elif mime_type.startswith("video/"):
                self._client.send_video(chat_jid, file_path, caption=caption)
            elif mime_type.startswith("audio/"):
                self._client.send_audio(chat_jid, file_path)
            else:
                self._client.send_document(
                    chat_jid, file_path, caption=caption, filename=filename
                )
            self._log(f"Sent file: {filename}")
        except Exception as exc:
            self._log(f"File send error ({filename}): {exc}")

    # -- Monitor window (tkinter) ------------------------------------------

    def _create_monitor_window(self):
        """Create a tkinter monitor window with QR display area, status,
        message log, and manual send."""
        try:
            import tkinter as tk
            from tkinter import ttk, scrolledtext
        except ImportError:
            return

        if self._monitor_window:
            return

        self._monitor_window = tk.Toplevel()
        self._monitor_window.title("WhatsApp Web — Personal")
        self._monitor_window.geometry("750x600")
        self._monitor_window.minsize(550, 450)
        self._monitor_window.protocol("WM_DELETE_WINDOW", self._stop_node)

        self._monitor_window.grid_rowconfigure(1, weight=1)
        self._monitor_window.grid_columnconfigure(0, weight=1)

        # -- Status frame --
        status_frame = ttk.LabelFrame(self._monitor_window, text="Connection")
        status_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="Connecting...")
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, textvariable=self._status_var, font=("Helvetica", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=5, pady=2
        )

        session_name = self._get_prop("session_name") or "xeroflow_wa"
        ttk.Label(status_frame, text="Session:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, text=session_name).grid(row=0, column=3, sticky="w", padx=5, pady=2)

        # QR code info label
        self._qr_info_var = tk.StringVar(
            value="Scan the QR code in the terminal with WhatsApp > Linked Devices > Link a Device"
        )
        qr_info_label = ttk.Label(status_frame, textvariable=self._qr_info_var, wraplength=500)
        qr_info_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=2)

        # QR code image area (hidden until QR is available)
        self._qr_label = ttk.Label(status_frame)
        self._qr_label.grid(row=2, column=0, columnspan=4, pady=5)
        self._qr_label.grid_remove()  # Hidden by default

        # -- Notebook for log + send --
        notebook = ttk.Notebook(self._monitor_window)
        notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Log tab
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Message Log")
        log_tab.grid_rowconfigure(0, weight=1)
        log_tab.grid_columnconfigure(0, weight=1)

        self._log_text = scrolledtext.ScrolledText(
            log_tab, height=15, width=80, wrap=tk.WORD, state=tk.DISABLED
        )
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Send tab
        send_tab = ttk.Frame(notebook)
        notebook.add(send_tab, text="Send Message")
        send_tab.grid_columnconfigure(1, weight=1)

        ttk.Label(send_tab, text="To (phone number):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self._send_to_var = tk.StringVar()
        ttk.Entry(send_tab, textvariable=self._send_to_var, width=25).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(send_tab, text="Message:").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self._send_msg_text = scrolledtext.ScrolledText(send_tab, height=5, width=50, wrap=tk.WORD)
        self._send_msg_text.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        btn_frame = ttk.Frame(send_tab)
        btn_frame.grid(row=2, column=1, sticky="e", padx=5, pady=5)

        ttk.Button(btn_frame, text="Send", command=self._manual_send).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Stop", command=self._stop_node).pack(side=tk.RIGHT, padx=5)

        # Bottom buttons
        bottom_frame = ttk.Frame(self._monitor_window)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)

        ttk.Button(bottom_frame, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Disconnect", command=self._stop_node).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="New QR Code", command=self._request_new_qr).pack(side=tk.RIGHT, padx=5)

        # Flush buffered log messages
        self._flush_log_to_widget()

    def _hide_qr(self):
        """Hide the QR code label after successful connection."""
        if self._qr_label:
            self._qr_label.grid_remove()
        if self._qr_info_var:
            self._qr_info_var.set("Connected! You can now send and receive messages.")

    def _display_qr_in_window(self, qr_string: str):
        """Generate a QR code image from the string and display it in the
        monitor window."""
        try:
            import qrcode
            from PIL import Image, ImageTk

            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(qr_string)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to PhotoImage for tkinter
            if not isinstance(img, Image.Image):
                img = img.get_image()

            tk_image = ImageTk.PhotoImage(img)

            if self._qr_label and self._monitor_window:
                self._qr_label.configure(image=tk_image)
                self._qr_label._tk_image = tk_image  # Keep reference
                self._qr_label.grid()  # Show it
                if self._qr_info_var:
                    self._qr_info_var.set(
                        "Scan this QR code with WhatsApp > Linked Devices > Link a Device"
                    )
        except ImportError:
            self._log("Install 'qrcode' and 'Pillow' to display QR in window: pip install qrcode Pillow")
        except Exception as exc:
            self._log(f"QR display error: {exc}")

    def _request_new_qr(self):
        """Request a new QR code by resetting the session."""
        self._log("To get a new QR code, delete the session file and restart the workflow.")
        session_name = self._get_prop("session_name") or "xeroflow_wa"
        db_path = os.path.join(SESSION_DIR, f"{session_name}.sqlite3")
        self._log(f"Session file: {db_path}")

    def _flush_log_to_widget(self):
        """Write buffered log messages to the tkinter text widget."""
        if not self._log_text:
            return
        with self._log_lock:
            messages = list(self._log_messages)
        try:
            import tkinter as tk
            self._log_text.config(state=tk.NORMAL)
            for msg in messages:
                self._log_text.insert(tk.END, msg + "\n")
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    def _clear_log(self):
        """Clear the log widget."""
        if not self._log_text:
            return
        try:
            import tkinter as tk
            self._log_text.config(state=tk.NORMAL)
            self._log_text.delete("1.0", tk.END)
            self._log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    def _manual_send(self):
        """Send a message manually from the monitor window."""
        import tkinter as tk
        to = self._send_to_var.get().strip()
        msg = self._send_msg_text.get("1.0", tk.END).strip()
        if not to or not msg:
            self._log("Please enter both a phone number and message.")
            return
        if not self._client or not self._connected:
            self._log("Not connected to WhatsApp.")
            return
        try:
            from neonize.utils import build_jid
            jid = build_jid(to)
            self._send_wa_text(jid, msg)
            self._send_msg_text.delete("1.0", tk.END)
        except Exception as exc:
            self._log(f"Manual send error: {exc}")

    def _stop_node(self):
        """Disconnect and close the monitor window."""
        self._stop_event.set()
        self._connected = False
        self._log("Stopping WhatsApp Web node...")

        # Unregister from the running instances registry
        try:
            from src.workflows.node_registry import unregister_running_instance
            unregister_running_instance("WhatsAppWebNode")
        except Exception:
            pass

        # Signal neonize event loop to stop
        if hasattr(self, "_neonize_event") and self._neonize_event:
            try:
                self._neonize_event.set()
            except Exception:
                pass

        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass

        if self._monitor_window:
            try:
                self._monitor_window.destroy()
            except Exception:
                pass
            self._monitor_window = None

    # -- Helpers ------------------------------------------------------------

    def _get_prop(self, name: str):
        """Get a property value, checking 'value' first then 'default'."""
        prop = self.properties.get(name, {})
        if isinstance(prop, dict):
            val = prop.get("value")
            if val is not None and val != "":
                return val
            return prop.get("default", "")
        return prop or ""

    def _get_allowed_numbers(self) -> set:
        raw = self._get_prop("allowed_numbers") or ""
        if not raw.strip():
            return set()
        return {n.strip().lstrip("+") for n in raw.split(",") if n.strip()}

    def _extract_my_jids(self, client):
        """Extract all self-identifiers (JID User + LID User) from the neonize
        client.  The get_me() return value is a protobuf with nested JID and
        LID sub-messages, each having a User field."""
        try:
            me = client.get_me()
        except Exception:
            me = getattr(client, 'me', None) or getattr(client, 'jid', None)
        if me is None:
            return
        # Direct .User (simple JID)
        if hasattr(me, 'User') and me.User:
            uid = str(me.User)
            self._my_jids.add(uid)
            if not self._my_jid:
                self._my_jid = uid
        # Nested JID sub-message
        if hasattr(me, 'JID') and hasattr(me.JID, 'User') and me.JID.User:
            self._my_jids.add(str(me.JID.User))
            if not self._my_jid:
                self._my_jid = str(me.JID.User)
        # Nested LID sub-message (internal WhatsApp ID)
        if hasattr(me, 'LID') and hasattr(me.LID, 'User') and me.LID.User:
            self._my_jids.add(str(me.LID.User))
        # Fallback: parse the string representation for User fields
        if not self._my_jids:
            import re
            me_str = str(me)
            for match in re.findall(r'User:\s*"(\d+)"', me_str):
                self._my_jids.add(match)
                if not self._my_jid:
                    self._my_jid = match

    def _allows_self_chat(self, allowed: set) -> bool:
        """Return True if self-chat messages should be processed.

        Self-chat is allowed when:
        - 'self' is in the allowed numbers list (case-insensitive), OR
        - The user's own JID is in the allowed numbers list, OR
        - allowed is empty (allow all)
        """
        if not allowed:
            return True
        # Case-insensitive check for 'self'
        if any(n.lower() == 'self' for n in allowed):
            return True
        for jid in self._my_jids:
            if self._number_matches(jid, allowed):
                return True
        return False

    @staticmethod
    def _number_matches(sender: str, allowed: set) -> bool:
        """Check if a sender number matches any allowed number.

        WhatsApp JID User fields can differ from the phone number the user
        enters (e.g. ``207348169728082`` vs ``+12073481697``).  We compare:
        1. Exact match after stripping non-digits.
        2. Suffix match — if the last 10 digits of either number match.
        """
        import re
        sender_digits = re.sub(r'\D', '', sender)
        for num in allowed:
            num_digits = re.sub(r'\D', '', num)
            if not num_digits:
                continue
            if sender_digits == num_digits:
                return True
            # Suffix match (last 10 digits covers most national numbers)
            if len(sender_digits) >= 10 and len(num_digits) >= 10:
                if sender_digits[-10:] == num_digits[-10:]:
                    return True
            # Check if one contains the other
            if sender_digits in num_digits or num_digits in sender_digits:
                return True
        return False

    def _log(self, message: str):
        """Thread-safe logging to console and monitor widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        logger.info(message)
        print(f"[WhatsAppWeb] {entry}")

        with self._log_lock:
            self._log_messages.append(entry)

        if self._log_text and self._monitor_window:
            try:
                self._monitor_window.after(0, lambda e=entry: self._append_log_line(e))
            except Exception:
                pass

    def _append_log_line(self, line: str):
        """Append a line to the log widget (main thread only)."""
        try:
            import tkinter as tk
            self._log_text.config(state=tk.NORMAL)
            self._log_text.insert(tk.END, line + "\n")
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    @staticmethod
    def _strip_markdown_for_whatsapp(text: str) -> str:
        """Convert markdown to WhatsApp-compatible formatting."""
        # Bold+italic ***text*** -> *_text_*
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"*_\1_*", text)
        # Bold **text** -> *text*
        text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
        # Headers -> bold
        text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
        # Strikethrough ~~text~~ -> ~text~
        text = re.sub(r"~~(.+?)~~", r"~\1~", text)
        # Code block language markers
        text = re.sub(r"```\w*\n", "```\n", text)
        # Image syntax
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[\1]", text)
        # Links [text](url) -> text (url)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        return text

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Split text into chunks within WhatsApp's limit."""
        if len(text) <= WA_MAX_TEXT_LENGTH:
            return [text]
        chunks = []
        while text:
            if len(text) <= WA_MAX_TEXT_LENGTH:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, WA_MAX_TEXT_LENGTH)
            if split_at < WA_MAX_TEXT_LENGTH // 2:
                split_at = text.rfind(" ", 0, WA_MAX_TEXT_LENGTH)
            if split_at < WA_MAX_TEXT_LENGTH // 2:
                split_at = WA_MAX_TEXT_LENGTH
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks

    def requires_api_call(self):
        return True

    def set_message_callback(self, callback):
        """Register a callback for incoming messages. The callback receives
        (text, file_paths) and should return a response string."""
        self._message_callback = callback

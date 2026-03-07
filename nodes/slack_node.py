# nodes/slack_node.py
"""Slack Integration Node — connects to a Slack workspace via Bot Token
and Socket Mode so users can chat with the Master Agent through Slack DMs
or a designated channel. No public URL or webhook server required.

Requirements:
    pip install slack-bolt slack-sdk
"""

from __future__ import annotations

import logging
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
SLACK_MAX_TEXT_LENGTH = 4000  # Slack message limit (approx)


# ---------------------------------------------------------------------------
# The Node
# ---------------------------------------------------------------------------
@register_node("SlackNode")
class SlackNode(BaseNode):
    """Slack integration via Bot Token + Socket Mode. Add this node to a
    workflow and connect it to the MasterAgentNode to chat with the AI
    through Slack. Supports text messages and file uploads/downloads.

    Setup:
        1. Create a Slack App at https://api.slack.com/apps
        2. Enable Socket Mode (Settings > Socket Mode > Enable)
        3. Add an App-Level Token with ``connections:write`` scope
        4. Under OAuth & Permissions, add Bot Token Scopes:
           - chat:write, files:read, files:write, im:history,
             im:read, im:write, channels:history, channels:read,
             app_mentions:read
        5. Install the app to your workspace
        6. Copy the Bot Token (xoxb-...) and App Token (xapp-...) into
           the node properties
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._app = None
        self._handler = None
        self._client_thread: Optional[threading.Thread] = None
        self._connected = False
        self._stop_event = threading.Event()
        self._processed_ids: set = set()
        self._log_messages: List[str] = []
        self._log_lock = threading.Lock()
        self._monitor_window = None
        self._status_var = None
        self._log_text = None
        self._media_dir = Path(tempfile.gettempdir()) / "xeroflow_slack_media"
        self._media_dir.mkdir(parents=True, exist_ok=True)
        self._bot_user_id: Optional[str] = None
        self._message_callback = None

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
                "default": "SlackNode",
            },
            "description": {
                "type": "text",
                "label": "Description",
                "default": (
                    "Connects to Slack via Bot Token + Socket Mode. "
                    "No public URL needed. Messages in DMs or a designated "
                    "channel are forwarded to the Master Agent."
                ),
            },
            "bot_token": {
                "type": "text",
                "label": "Bot Token (xoxb-...)",
                "default": "",
                "description": (
                    "The Bot User OAuth Token from your Slack App. "
                    "Found under OAuth & Permissions."
                ),
            },
            "app_token": {
                "type": "text",
                "label": "App-Level Token (xapp-...)",
                "default": "",
                "description": (
                    "The App-Level Token with connections:write scope. "
                    "Found under Basic Information > App-Level Tokens."
                ),
            },
            "channel_id": {
                "type": "text",
                "label": "Channel ID (optional)",
                "default": "",
                "description": (
                    "If set, the bot only listens in this channel. "
                    "Leave empty to respond to all DMs. "
                    "Right-click a channel > View channel details > copy the ID."
                ),
            },
            "allowed_users": {
                "type": "textarea",
                "label": "Allowed User IDs",
                "default": "",
                "description": (
                    "Comma-separated Slack user IDs allowed to interact. "
                    "Empty = allow all. Find your ID in your Slack profile."
                ),
            },
            "auto_reply": {
                "type": "boolean",
                "label": "Auto-Reply Mode",
                "default": True,
                "description": "Automatically forward messages to the AI and send the response back.",
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
                "description": "Keeps the Slack connection alive to receive messages continuously.",
            },
        })
        return props

    def process(self, inputs):
        """Called by the workflow engine. Creates the monitor window, starts
        the Slack Socket Mode client, then enters a blocking loop."""
        self.inputs = inputs
        self._stop_event.clear()

        workflow_stop_event = inputs.get("stop_event") if isinstance(inputs, dict) else None

        # 1. Create the monitor window
        try:
            self._create_monitor_window()
        except Exception as exc:
            self._log(f"Monitor window error: {exc}")

        # 2. Start the Slack client
        self._initialize()

        # 3. Block — keep the node alive
        self._log("Slack node running. Waiting for messages...")
        while not self._stop_event.is_set():
            if workflow_stop_event and workflow_stop_event.is_set():
                self._log("Workflow stop event detected.")
                self._stop_event.set()
                break
            try:
                time.sleep(1)
            except Exception:
                break

        self._stop_node()
        return {"message": "", "files": ""}

    # -- Initialization -----------------------------------------------------

    def _initialize(self):
        """Set up the Slack Bolt app with Socket Mode."""
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
        except ImportError:
            self._log("ERROR: slack-bolt is not installed. Run: pip install slack-bolt slack-sdk")
            self._log("Then restart the workflow.")
            return

        # Register this node so MasterAgentNode can find us
        try:
            from src.workflows.node_registry import register_running_instance
            register_running_instance("SlackNode", self)
        except Exception:
            pass

        bot_token = self._get_prop("bot_token")
        app_token = self._get_prop("app_token")

        if not bot_token or not bot_token.startswith("xoxb-"):
            self._log("ERROR: Bot Token is missing or invalid. It should start with 'xoxb-'.")
            return
        if not app_token or not app_token.startswith("xapp-"):
            self._log("ERROR: App-Level Token is missing or invalid. It should start with 'xapp-'.")
            return

        self._log("Initializing Slack connection...")

        app = App(token=bot_token)
        self._app = app

        # Get our own bot user ID so we can ignore our own messages
        try:
            auth = app.client.auth_test()
            self._bot_user_id = auth.get("user_id")
            self._log(f"Authenticated as bot user: {self._bot_user_id}")
        except Exception as exc:
            self._log(f"Auth test failed: {exc}")
            return

        # --- Event handlers ---
        channel_filter = (self._get_prop("channel_id") or "").strip()

        @app.event("message")
        def handle_message(event, say):
            self._handle_incoming_message(event, say)

        @app.event("app_mention")
        def handle_mention(event, say):
            self._handle_incoming_message(event, say)

        # Start Socket Mode in a background thread
        def run_client():
            try:
                handler = SocketModeHandler(app, app_token)
                self._handler = handler
                self._connected = True
                self._log("Connected to Slack via Socket Mode!")
                if self._status_var and self._monitor_window:
                    try:
                        self._monitor_window.after(
                            0, lambda: self._status_var.set(
                                f"Connected (bot: {self._bot_user_id})"
                            )
                        )
                    except Exception:
                        pass
                handler.start()  # Blocks
            except Exception as exc:
                self._log(f"Slack client error: {exc}")
                traceback.print_exc()
            finally:
                self._connected = False
                self._log("Slack client stopped.")
                if self._status_var and self._monitor_window:
                    try:
                        self._monitor_window.after(
                            0, lambda: self._status_var.set("Disconnected")
                        )
                    except Exception:
                        pass

        self._client_thread = threading.Thread(target=run_client, daemon=True)
        self._client_thread.start()

    # -- Incoming message handling ------------------------------------------

    def _handle_incoming_message(self, event: dict, say):
        """Process an incoming Slack message event."""
        try:
            # Skip bot's own messages
            user_id = event.get("user", "")
            if user_id == self._bot_user_id:
                return

            # Skip message subtypes (edits, joins, etc.) except regular messages
            subtype = event.get("subtype")
            if subtype and subtype not in ("file_share",):
                return

            msg_ts = event.get("ts", "")
            channel = event.get("channel", "")

            # Deduplicate
            if msg_ts in self._processed_ids:
                return
            self._processed_ids.add(msg_ts)
            if len(self._processed_ids) > 5000:
                self._processed_ids = set(list(self._processed_ids)[-2500:])

            # Channel filter
            channel_filter = (self._get_prop("channel_id") or "").strip()
            if channel_filter and channel != channel_filter:
                return

            # User filter
            allowed = self._get_allowed_users()
            if allowed and user_id not in allowed:
                self._log(f"Blocked message from user {user_id} (not in allowed list)")
                return

            # Extract text
            text_content = event.get("text", "")
            # Strip bot mention from text (e.g. "<@U12345> hello" -> "hello")
            if self._bot_user_id:
                text_content = re.sub(
                    rf"<@{re.escape(self._bot_user_id)}>\s*", "", text_content
                ).strip()

            # Download any attached files
            file_paths = []
            for file_info in event.get("files", []):
                local_path = self._download_file(file_info)
                if local_path:
                    file_paths.append(local_path)

            if not text_content and not file_paths:
                return

            display = text_content[:100] + ("..." if len(text_content) > 100 else "")
            self._log(f"Message from {user_id} in {channel}: {display}")

            msg_data = {
                "id": msg_ts,
                "from": user_id,
                "channel": channel,
                "text": text_content,
                "files": file_paths,
                "received_at": datetime.now().isoformat(),
                "say": say,
            }

            # Auto-reply
            auto_reply = self._get_prop("auto_reply")
            if auto_reply and str(auto_reply).lower() not in ("false", "0", ""):
                t = threading.Thread(
                    target=self._handle_auto_reply,
                    args=(msg_data,),
                    daemon=True,
                    name=f"slack-reply-{msg_ts[:8]}",
                )
                t.start()

        except Exception as exc:
            self._log(f"Error handling message: {exc}")
            traceback.print_exc()

    def _download_file(self, file_info: dict) -> Optional[str]:
        """Download a file from Slack."""
        try:
            url = file_info.get("url_private_download") or file_info.get("url_private")
            if not url:
                return None

            filename = file_info.get("name", "slack_file")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(self._media_dir / f"slack_{timestamp}_{filename}")

            bot_token = self._get_prop("bot_token")
            import requests
            resp = requests.get(
                url, headers={"Authorization": f"Bearer {bot_token}"}, timeout=30
            )
            resp.raise_for_status()

            with open(save_path, "wb") as f:
                f.write(resp.content)

            self._log(f"Downloaded file: {filename} ({len(resp.content)} bytes)")
            return save_path

        except Exception as exc:
            self._log(f"File download error: {exc}")
            return None

    def _find_master_agent(self):
        """Discover a running MasterAgentNode via the shared runtime registry."""
        try:
            from src.workflows.node_registry import get_running_instance
            master = get_running_instance("MasterAgentNode")
            if master and hasattr(master, "process_external_message"):
                return master
        except Exception:
            pass
        return None

    def _handle_auto_reply(self, msg_data: dict):
        """Forward the message to the AI and send the response back."""
        text = msg_data["text"]
        files = msg_data.get("files", [])
        channel = msg_data["channel"]

        # 1. Try the connected MasterAgentNode
        master = self._find_master_agent()
        if master:
            try:
                self._log(f"Routing to Master Agent... (channel={channel})")
                result = master.process_external_message(
                    text, sender="Slack", files=files if files else None
                )
                if isinstance(result, dict):
                    response_text = result.get("text", "")
                    response_files = result.get("files", [])
                else:
                    response_text = result
                    response_files = []

                if response_text:
                    self._log(f"Got response ({len(response_text)} chars), sending to channel...")
                    self.send_message(channel, response_text)
                for fpath in response_files:
                    try:
                        self._log(f"Sending file: {Path(fpath).name}")
                        self.send_file(channel, fpath)
                    except Exception as fexc:
                        self._log(f"Error sending file {fpath}: {fexc}")
                if response_text or response_files:
                    return
                self._log("Master Agent returned empty response")
            except Exception as exc:
                self._log(f"Master Agent error: {exc}")
                traceback.print_exc()

        # 2. Try registered callback
        if self._message_callback:
            try:
                response = self._message_callback(text, files)
                if response:
                    self.send_message(channel, response)
                    return
            except Exception as exc:
                self._log(f"Callback error: {exc}")

        # 3. Fallback: use the node's own API service
        try:
            api_endpoints = self.get_api_endpoints()
            if not api_endpoints:
                self.send_message(
                    channel,
                    "I'm currently unable to process your request. No AI endpoint is configured.",
                )
                return

            api_name = api_endpoints[0]
            api_config = self.config.get("interfaces", {}).get(api_name, {})

            response = self.send_api_request(
                content=text,
                api_name=api_name,
                model=api_config.get("selected_model"),
                max_tokens=api_config.get("max_tokens"),
                temperature=api_config.get("temperature", 0.7),
            )

            if response.success:
                self.send_message(channel, response.content)
            else:
                self.send_message(
                    channel, f"Sorry, I encountered an error: {response.error}"
                )

        except Exception as exc:
            self._log(f"Auto-reply error: {exc}")
            traceback.print_exc()
            self.send_message(channel, "Sorry, an unexpected error occurred.")

    # -- Sending messages ---------------------------------------------------

    def send_message(self, channel: str, text: str):
        """Send a text message to a Slack channel, splitting if needed."""
        if not self._app or not self._connected:
            self._log("Cannot send — not connected to Slack")
            return

        clean_text = self._format_for_slack(text)
        chunks = self._split_text(clean_text)

        for chunk in chunks:
            try:
                self._app.client.chat_postMessage(channel=channel, text=chunk)
            except Exception as exc:
                self._log(f"Send error: {exc}")
                return

        display = clean_text[:80] + ("..." if len(clean_text) > 80 else "")
        self._log(f"Sent reply: {display}")

    def send_file(self, channel: str, file_path: str, title: str = ""):
        """Upload and send a file to a Slack channel."""
        if not self._app or not self._connected:
            self._log("Cannot send file — not connected to Slack")
            return

        if not os.path.exists(file_path):
            self._log(f"File not found: {file_path}")
            return

        filename = Path(file_path).name
        try:
            self._app.client.files_upload_v2(
                channel=channel,
                file=file_path,
                filename=filename,
                title=title or filename,
            )
            self._log(f"Sent file: {filename}")
        except Exception as exc:
            self._log(f"File send error ({filename}): {exc}")

    def send_notification(self, text: str, files: list = None):
        """Send a proactive notification to the configured channel or the
        bot's DM channel. Called by CalendarNode, TaskTrackerNode, etc."""
        if not self._app or not self._connected:
            return

        channel = (self._get_prop("channel_id") or "").strip()
        if not channel:
            # Try to find a DM channel with the first allowed user
            allowed = self._get_allowed_users()
            if allowed:
                first_user = next(iter(allowed))
                try:
                    resp = self._app.client.conversations_open(users=[first_user])
                    channel = resp["channel"]["id"]
                except Exception as exc:
                    self._log(f"Could not open DM for notification: {exc}")
                    return
            else:
                self._log("No channel configured for notifications")
                return

        self.send_message(channel, text)
        for fpath in (files or []):
            try:
                self.send_file(channel, fpath)
            except Exception:
                pass

    # -- Monitor window (tkinter) ------------------------------------------

    def _create_monitor_window(self):
        """Create a tkinter monitor window with status, message log, and
        manual send."""
        try:
            import tkinter as tk
            from tkinter import ttk, scrolledtext
        except ImportError:
            return

        if self._monitor_window:
            return

        self._monitor_window = tk.Toplevel()
        self._monitor_window.title("Slack Integration")
        self._monitor_window.geometry("700x500")
        self._monitor_window.minsize(500, 400)
        self._monitor_window.protocol("WM_DELETE_WINDOW", self._stop_node)

        self._monitor_window.grid_rowconfigure(1, weight=1)
        self._monitor_window.grid_columnconfigure(0, weight=1)

        # -- Status frame --
        status_frame = ttk.LabelFrame(self._monitor_window, text="Connection")
        status_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="Connecting...")
        ttk.Label(status_frame, text="Status:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Label(
            status_frame, textvariable=self._status_var,
            font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        channel_id = self._get_prop("channel_id") or "(DMs)"
        ttk.Label(status_frame, text="Channel:").grid(
            row=0, column=2, sticky="w", padx=5, pady=2
        )
        ttk.Label(status_frame, text=channel_id).grid(
            row=0, column=3, sticky="w", padx=5, pady=2
        )

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

        ttk.Label(send_tab, text="Channel ID:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        self._send_channel_var = tk.StringVar(
            value=self._get_prop("channel_id") or ""
        )
        ttk.Entry(send_tab, textvariable=self._send_channel_var, width=25).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(send_tab, text="Message:").grid(
            row=1, column=0, sticky="nw", padx=5, pady=5
        )
        self._send_msg_text = scrolledtext.ScrolledText(
            send_tab, height=5, width=50, wrap=tk.WORD
        )
        self._send_msg_text.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        btn_frame = ttk.Frame(send_tab)
        btn_frame.grid(row=2, column=1, sticky="e", padx=5, pady=5)

        ttk.Button(btn_frame, text="Send", command=self._manual_send).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(btn_frame, text="Stop", command=self._stop_node).pack(
            side=tk.RIGHT, padx=5
        )

        # Bottom buttons
        bottom_frame = ttk.Frame(self._monitor_window)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)

        ttk.Button(bottom_frame, text="Clear Log", command=self._clear_log).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(bottom_frame, text="Disconnect", command=self._stop_node).pack(
            side=tk.RIGHT, padx=5
        )

        # Flush buffered log messages
        self._flush_log_to_widget()

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
        channel = self._send_channel_var.get().strip()
        msg = self._send_msg_text.get("1.0", tk.END).strip()
        if not channel or not msg:
            self._log("Please enter both a channel ID and message.")
            return
        if not self._app or not self._connected:
            self._log("Not connected to Slack.")
            return
        try:
            self.send_message(channel, msg)
            self._send_msg_text.delete("1.0", tk.END)
        except Exception as exc:
            self._log(f"Manual send error: {exc}")

    def _stop_node(self):
        """Disconnect and close the monitor window."""
        self._stop_event.set()
        self._connected = False
        self._log("Stopping Slack node...")

        # Unregister from the running instances registry
        try:
            from src.workflows.node_registry import unregister_running_instance
            unregister_running_instance("SlackNode")
        except Exception:
            pass

        # Stop the Socket Mode handler
        if self._handler:
            try:
                self._handler.close()
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

    def _get_allowed_users(self) -> set:
        raw = self._get_prop("allowed_users") or ""
        if not raw.strip():
            return set()
        return {u.strip() for u in raw.split(",") if u.strip()}

    def _log(self, message: str):
        """Thread-safe logging to console and monitor widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        logger.info(message)
        print(f"[Slack] {entry}")

        with self._log_lock:
            self._log_messages.append(entry)

        if self._log_text and self._monitor_window:
            try:
                self._monitor_window.after(
                    0, lambda e=entry: self._append_log_line(e)
                )
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
    def _format_for_slack(text: str) -> str:
        """Convert markdown to Slack-compatible mrkdwn formatting."""
        # Bold+italic ***text*** -> *_text_*
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"*_\1_*", text)
        # Bold **text** -> *text*
        text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
        # Headers -> bold
        text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
        # Inline code stays the same (backticks)
        # Code block language markers — Slack doesn't support language hints
        text = re.sub(r"```\w*\n", "```\n", text)
        # Image syntax -> link
        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"<\2|\1>", text)
        # Links [text](url) -> <url|text>
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
        return text

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Split text into chunks within Slack's limit."""
        if len(text) <= SLACK_MAX_TEXT_LENGTH:
            return [text]
        chunks = []
        while text:
            if len(text) <= SLACK_MAX_TEXT_LENGTH:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, SLACK_MAX_TEXT_LENGTH)
            if split_at < SLACK_MAX_TEXT_LENGTH // 2:
                split_at = text.rfind(" ", 0, SLACK_MAX_TEXT_LENGTH)
            if split_at < SLACK_MAX_TEXT_LENGTH // 2:
                split_at = SLACK_MAX_TEXT_LENGTH
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks

    def requires_api_call(self):
        return True

    def set_message_callback(self, callback):
        """Register a callback for incoming messages. The callback receives
        (text, file_paths) and should return a response string."""
        self._message_callback = callback

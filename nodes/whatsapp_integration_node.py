# nodes/whatsapp_integration_node.py
"""WhatsApp Integration Node — connects WhatsApp Business Cloud API to the
XeroFlow workflow engine so users can chat with the Master Agent via WhatsApp,
including sending and receiving files."""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .base_node import BaseNode
from src.workflows.node_registry import register_node

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Maximum WhatsApp text message length
WA_MAX_TEXT_LENGTH = 4096

# Supported media MIME types for WhatsApp
WA_SUPPORTED_IMAGES = {"image/jpeg", "image/png", "image/webp"}
WA_SUPPORTED_DOCUMENTS = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/msword",
    "text/plain",
    "application/zip",
}
WA_SUPPORTED_AUDIO = {"audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"}
WA_SUPPORTED_VIDEO = {"video/mp4", "video/3gp"}


# ---------------------------------------------------------------------------
# WhatsApp Cloud API helper class
# ---------------------------------------------------------------------------
class WhatsAppCloudAPI:
    """Thin wrapper around the Meta WhatsApp Cloud API."""

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })

    # -- Sending messages ---------------------------------------------------

    def send_text(self, to: str, text: str) -> dict:
        """Send a plain text message. Splits long messages automatically."""
        results = []
        chunks = self._split_text(text)
        for chunk in chunks:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": chunk},
            }
            results.append(self._post_message(payload))
        return results[-1] if results else {}

    def send_image(self, to: str, image_path: str, caption: str = "") -> dict:
        media_id = self._upload_media(image_path)
        if not media_id:
            return {"error": "Failed to upload image"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {"id": media_id},
        }
        if caption:
            payload["image"]["caption"] = caption[:1024]
        return self._post_message(payload)

    def send_document(self, to: str, doc_path: str, caption: str = "",
                      filename: str = "") -> dict:
        media_id = self._upload_media(doc_path)
        if not media_id:
            return {"error": "Failed to upload document"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": filename or Path(doc_path).name,
            },
        }
        if caption:
            payload["document"]["caption"] = caption[:1024]
        return self._post_message(payload)

    def send_audio(self, to: str, audio_path: str) -> dict:
        media_id = self._upload_media(audio_path)
        if not media_id:
            return {"error": "Failed to upload audio"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id},
        }
        return self._post_message(payload)

    def send_video(self, to: str, video_path: str, caption: str = "") -> dict:
        media_id = self._upload_media(video_path)
        if not media_id:
            return {"error": "Failed to upload video"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "video",
            "video": {"id": media_id},
        }
        if caption:
            payload["video"]["caption"] = caption[:1024]
        return self._post_message(payload)

    # -- Receiving media ----------------------------------------------------

    def download_media(self, media_id: str, save_dir: str) -> Optional[str]:
        """Download a media file by its WhatsApp media ID.

        Returns the local file path or None on failure.
        """
        try:
            # Step 1: Get the media URL
            url = f"{GRAPH_API_BASE}/{media_id}"
            resp = self._session.get(url)
            resp.raise_for_status()
            media_url = resp.json().get("url")
            mime_type = resp.json().get("mime_type", "application/octet-stream")
            if not media_url:
                logger.error("No URL returned for media %s", media_id)
                return None

            # Step 2: Download the actual file
            file_resp = self._session.get(media_url)
            file_resp.raise_for_status()

            # Determine extension from MIME type
            ext = mimetypes.guess_extension(mime_type) or ""
            filename = f"wa_media_{media_id[:12]}{ext}"
            save_path = os.path.join(save_dir, filename)

            with open(save_path, "wb") as f:
                f.write(file_resp.content)

            logger.info("Downloaded media %s -> %s (%d bytes)",
                        media_id, save_path, len(file_resp.content))
            return save_path

        except Exception as exc:
            logger.error("Failed to download media %s: %s", media_id, exc)
            return None

    # -- Internal helpers ---------------------------------------------------

    def _post_message(self, payload: dict) -> dict:
        url = f"{GRAPH_API_BASE}/{self.phone_number_id}/messages"
        try:
            resp = self._session.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("WhatsApp send error: %s", exc)
            error_body = ""
            if hasattr(exc, "response") and exc.response is not None:
                error_body = exc.response.text
            return {"error": str(exc), "detail": error_body}

    def _upload_media(self, file_path: str) -> Optional[str]:
        """Upload a file to WhatsApp media and return the media ID."""
        url = f"{GRAPH_API_BASE}/{self.phone_number_id}/media"
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    files={"file": (Path(file_path).name, f, mime_type)},
                    data={"messaging_product": "whatsapp"},
                )
            resp.raise_for_status()
            media_id = resp.json().get("id")
            logger.info("Uploaded media %s -> id=%s", file_path, media_id)
            return media_id
        except Exception as exc:
            logger.error("Media upload failed for %s: %s", file_path, exc)
            return None

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Split text into chunks that fit within WhatsApp's limit."""
        if len(text) <= WA_MAX_TEXT_LENGTH:
            return [text]
        chunks = []
        while text:
            if len(text) <= WA_MAX_TEXT_LENGTH:
                chunks.append(text)
                break
            # Try to split at a newline near the limit
            split_at = text.rfind("\n", 0, WA_MAX_TEXT_LENGTH)
            if split_at < WA_MAX_TEXT_LENGTH // 2:
                # No good newline — split at space
                split_at = text.rfind(" ", 0, WA_MAX_TEXT_LENGTH)
            if split_at < WA_MAX_TEXT_LENGTH // 2:
                split_at = WA_MAX_TEXT_LENGTH
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks

    def mark_as_read(self, message_id: str) -> None:
        """Mark a message as read."""
        url = f"{GRAPH_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            self._session.post(url, json=payload)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Webhook server (Flask)
# ---------------------------------------------------------------------------
def _create_webhook_app(node_ref):
    """Create a minimal Flask app that handles WhatsApp webhook verification
    and incoming message notifications.

    ``node_ref`` is a weak-ish reference (just the node instance) so the
    Flask routes can call back into the node to enqueue messages.
    """
    try:
        from flask import Flask, request as flask_request, jsonify
    except ImportError:
        logger.error("Flask is required for WhatsApp webhook. Install with: pip install flask")
        return None

    app = Flask(__name__)
    # Suppress Flask's default request logging in production
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)

    @app.route("/webhook", methods=["GET"])
    def verify_webhook():
        """Handle the Meta webhook verification challenge."""
        mode = flask_request.args.get("hub.mode")
        token = flask_request.args.get("hub.verify_token")
        challenge = flask_request.args.get("hub.challenge")

        verify_token = node_ref._get_verify_token()
        if mode == "subscribe" and token == verify_token:
            logger.info("Webhook verified successfully")
            node_ref._log("Webhook verified successfully")
            return challenge, 200
        logger.warning("Webhook verification failed (token mismatch)")
        node_ref._log("Webhook verification FAILED — token mismatch")
        return jsonify({"status": "error", "message": "Verification failed"}), 403

    @app.route("/webhook", methods=["POST"])
    def receive_message():
        """Handle incoming WhatsApp messages."""
        body = flask_request.get_json(silent=True)
        if not body:
            return jsonify({"status": "error"}), 400

        try:
            if body.get("object"):
                entries = body.get("entry", [])
                for entry in entries:
                    changes = entry.get("changes", [])
                    for change in changes:
                        value = change.get("value", {})
                        messages = value.get("messages", [])
                        contacts = value.get("contacts", [])
                        for msg in messages:
                            sender_name = ""
                            sender_phone = msg.get("from", "")
                            # Try to get the sender's name from contacts
                            for contact in contacts:
                                if contact.get("wa_id") == sender_phone:
                                    sender_name = contact.get("profile", {}).get("name", "")
                                    break
                            node_ref._enqueue_incoming(msg, sender_phone, sender_name)
        except Exception as exc:
            logger.error("Error processing webhook payload: %s", exc)
            traceback.print_exc()

        # Always return 200 to acknowledge receipt
        return jsonify({"status": "ok"}), 200

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "running", "node": "WhatsAppIntegrationNode"}), 200

    return app


# ---------------------------------------------------------------------------
# The Node
# ---------------------------------------------------------------------------
@register_node("WhatsAppIntegrationNode")
class WhatsAppIntegrationNode(BaseNode):
    """WhatsApp integration node that bridges WhatsApp Business Cloud API
    with the XeroFlow workflow engine. Receives messages via webhook,
    forwards them to connected nodes (e.g. MasterAgentNode), and sends
    responses back through WhatsApp — including file attachments."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._wa_client: Optional[WhatsAppCloudAPI] = None
        self._webhook_thread: Optional[threading.Thread] = None
        self._webhook_running = False
        self._message_queue: List[Dict] = []
        self._queue_lock = threading.Lock()
        self._processed_ids: set = set()  # Deduplicate webhook retries
        self._log_messages: List[str] = []
        self._log_lock = threading.Lock()
        self._monitor_window = None
        self._stop_event = threading.Event()
        self._media_dir = Path(tempfile.gettempdir()) / "xeroflow_wa_media"
        self._media_dir.mkdir(parents=True, exist_ok=True)
        # Callback for forwarding messages to the Master Agent
        self._message_callback = None

    # -- Node interface -----------------------------------------------------

    def define_inputs(self):
        return ["response"]  # Receives AI response to send back via WhatsApp

    def define_outputs(self):
        return ["message", "files"]  # Outgoing: user message text + any attached files

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            "node_name": {
                "type": "text",
                "label": "Custom Node Name",
                "default": "WhatsAppIntegrationNode",
            },
            "description": {
                "type": "text",
                "label": "Description",
                "default": (
                    "Connects to WhatsApp Business Cloud API. Receives messages "
                    "via webhook and sends responses back. Supports text and file "
                    "attachments. Connect output to MasterAgentNode input."
                ),
            },
            "phone_number_id": {
                "type": "text",
                "label": "WhatsApp Phone Number ID",
                "default": "",
                "description": "From Meta Developer Dashboard > WhatsApp > API Setup",
            },
            "access_token": {
                "type": "text",
                "label": "Access Token",
                "default": "",
                "description": "Permanent or temporary token from Meta Developer Dashboard",
            },
            "verify_token": {
                "type": "text",
                "label": "Webhook Verify Token",
                "default": "xeroflow_whatsapp_verify",
                "description": "Custom string you set when configuring the webhook in Meta Dashboard",
            },
            "webhook_port": {
                "type": "text",
                "label": "Webhook Port",
                "default": "5555",
                "description": "Local port for the webhook server (use ngrok to expose publicly)",
            },
            "allowed_numbers": {
                "type": "textarea",
                "label": "Allowed Phone Numbers",
                "default": "",
                "description": "Comma-separated phone numbers allowed to interact (empty = allow all)",
            },
            "auto_reply": {
                "type": "boolean",
                "label": "Auto-Reply Mode",
                "default": True,
                "description": "When enabled, automatically forwards messages to the connected AI and replies",
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
                "description": "Keeps the webhook server running to receive messages continuously",
            },
        })
        return props

    def process(self, inputs):
        """Process method called by the workflow engine.

        On first call: starts the webhook server and monitor window.
        On subsequent calls (with 'response' input): sends the response
        back to the WhatsApp user.
        """
        response_text = inputs.get("response", "")

        # If we receive a response from the AI, send it back via WhatsApp
        if response_text and self._wa_client:
            self._send_response_to_pending(response_text)
            return {"message": "", "files": ""}

        # First-time initialization
        if not self._webhook_running:
            self._initialize()

        return {"message": "", "files": ""}

    # -- Initialization -----------------------------------------------------

    def _initialize(self):
        """Set up the WhatsApp client, start the webhook server, and open
        the monitor window."""
        phone_id = self._get_prop("phone_number_id")
        token = self._get_prop("access_token")

        if not phone_id or not token:
            self._log("ERROR: Phone Number ID and Access Token are required.")
            self._log("Configure them in the node properties, then restart the workflow.")
            return

        self._wa_client = WhatsAppCloudAPI(phone_id, token)
        self._log(f"WhatsApp client initialized (Phone ID: {phone_id[:6]}...)")

        # Start webhook server
        self._start_webhook_server()

        # Open monitor window (must be on main thread for tkinter)
        try:
            self._create_monitor_window()
        except Exception as exc:
            self._log(f"Monitor window error (non-fatal): {exc}")

    def _start_webhook_server(self):
        """Start the Flask webhook server in a background daemon thread."""
        app = _create_webhook_app(self)
        if app is None:
            self._log("ERROR: Flask is not installed. Run: pip install flask")
            return

        port = int(self._get_prop("webhook_port") or 5555)

        def run_server():
            self._webhook_running = True
            self._log(f"Webhook server starting on port {port}...")
            self._log(f"Webhook URL: http://localhost:{port}/webhook")
            self._log("Use ngrok or a reverse proxy to expose this publicly.")
            self._log(f"  Example: ngrok http {port}")
            try:
                app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
            except Exception as exc:
                self._log(f"Webhook server error: {exc}")
            finally:
                self._webhook_running = False
                self._log("Webhook server stopped.")

        self._webhook_thread = threading.Thread(target=run_server, daemon=True)
        self._webhook_thread.start()

    # -- Incoming message handling ------------------------------------------

    def _enqueue_incoming(self, message: dict, sender_phone: str,
                          sender_name: str):
        """Called by the Flask webhook route when a new message arrives."""
        msg_id = message.get("id", "")

        # Deduplicate (Meta sometimes retries)
        if msg_id in self._processed_ids:
            return
        self._processed_ids.add(msg_id)
        # Keep the set from growing unbounded
        if len(self._processed_ids) > 5000:
            self._processed_ids = set(list(self._processed_ids)[-2500:])

        msg_type = message.get("type", "")
        timestamp = message.get("timestamp", "")
        display_name = sender_name or sender_phone

        # Check allowed numbers
        allowed = self._get_allowed_numbers()
        if allowed and sender_phone not in allowed:
            self._log(f"Blocked message from unauthorized number: {sender_phone}")
            return

        # Mark as read
        if self._wa_client and msg_id:
            self._wa_client.mark_as_read(msg_id)

        # Extract content based on message type
        text_content = ""
        file_paths = []

        if msg_type == "text":
            text_content = message.get("text", {}).get("body", "")
        elif msg_type in ("image", "document", "audio", "video"):
            media_info = message.get(msg_type, {})
            media_id = media_info.get("id", "")
            caption = media_info.get("caption", "")
            text_content = caption or f"[Sent {msg_type}]"

            if media_id and self._wa_client:
                local_path = self._wa_client.download_media(
                    media_id, str(self._media_dir)
                )
                if local_path:
                    file_paths.append(local_path)
                    self._log(f"Downloaded {msg_type} from {display_name}: {local_path}")
        elif msg_type == "location":
            loc = message.get("location", {})
            lat = loc.get("latitude", "")
            lon = loc.get("longitude", "")
            name = loc.get("name", "")
            text_content = f"[Location: {name} ({lat}, {lon})]" if name else f"[Location: ({lat}, {lon})]"
        elif msg_type == "contacts":
            text_content = "[Shared contact(s)]"
        else:
            text_content = f"[Unsupported message type: {msg_type}]"

        self._log(f"Message from {display_name}: {text_content[:100]}{'...' if len(text_content) > 100 else ''}")

        # Store in queue
        msg_data = {
            "id": msg_id,
            "from": sender_phone,
            "from_name": sender_name,
            "type": msg_type,
            "text": text_content,
            "files": file_paths,
            "timestamp": timestamp,
            "received_at": datetime.now().isoformat(),
        }

        with self._queue_lock:
            self._message_queue.append(msg_data)

        # Auto-reply mode: forward to the connected AI
        auto_reply = self._get_prop("auto_reply")
        if auto_reply and auto_reply is not False and str(auto_reply).lower() != "false":
            self._handle_auto_reply(msg_data)

    def _handle_auto_reply(self, msg_data: dict):
        """Forward the incoming message to the Master Agent for processing
        and send the response back via WhatsApp."""
        sender = msg_data["from"]
        text = msg_data["text"]
        files = msg_data.get("files", [])

        # If a message callback is registered (by the workflow engine),
        # use it to forward the message
        if self._message_callback:
            try:
                response = self._message_callback(text, files)
                if response:
                    self._send_wa_response(sender, response, [])
                    return
            except Exception as exc:
                self._log(f"Callback error: {exc}")

        # Fallback: use the node's own API service to get a response
        try:
            api_endpoints = self.get_api_endpoints()
            if not api_endpoints:
                self._send_wa_response(
                    sender,
                    "I'm currently unable to process your request. No AI endpoint is configured.",
                    [],
                )
                return

            # Build a simple prompt with the user's message
            prompt = text
            if files:
                file_names = [Path(f).name for f in files]
                prompt = f"{text}\n\n[Attached files: {', '.join(file_names)}]"

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
                self._send_wa_response(sender, response.content, [])
            else:
                self._send_wa_response(
                    sender,
                    f"Sorry, I encountered an error processing your request: {response.error}",
                    [],
                )

        except Exception as exc:
            self._log(f"Auto-reply error: {exc}")
            traceback.print_exc()
            self._send_wa_response(
                sender,
                "Sorry, an unexpected error occurred. Please try again.",
                [],
            )

    # -- Sending responses --------------------------------------------------

    def _send_response_to_pending(self, response_text: str):
        """Send a response to the most recent pending message sender."""
        with self._queue_lock:
            if not self._message_queue:
                return
            last_msg = self._message_queue[-1]

        sender = last_msg.get("from", "")
        if sender:
            self._send_wa_response(sender, response_text, [])

    def _send_wa_response(self, to: str, text: str, file_paths: List[str]):
        """Send a text response (and optional files) back via WhatsApp."""
        if not self._wa_client:
            self._log("Cannot send — WhatsApp client not initialized")
            return

        # Strip markdown formatting that doesn't render in WhatsApp
        clean_text = self._strip_markdown_for_whatsapp(text)

        # Send text
        result = self._wa_client.send_text(to, clean_text)
        if "error" in result:
            self._log(f"Send error: {result['error']}")
        else:
            self._log(f"Sent reply to {to}: {clean_text[:80]}{'...' if len(clean_text) > 80 else ''}")

        # Send any file attachments
        for fpath in file_paths:
            self._send_file(to, fpath)

    def _send_file(self, to: str, file_path: str):
        """Send a file via WhatsApp, choosing the right media type."""
        if not self._wa_client or not os.path.exists(file_path):
            return

        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        filename = Path(file_path).name

        if mime_type in WA_SUPPORTED_IMAGES:
            result = self._wa_client.send_image(to, file_path)
        elif mime_type in WA_SUPPORTED_AUDIO:
            result = self._wa_client.send_audio(to, file_path)
        elif mime_type in WA_SUPPORTED_VIDEO:
            result = self._wa_client.send_video(to, file_path)
        else:
            result = self._wa_client.send_document(to, file_path, filename=filename)

        if "error" in result:
            self._log(f"File send error ({filename}): {result['error']}")
        else:
            self._log(f"Sent file to {to}: {filename}")

    # -- Monitor window (tkinter) ------------------------------------------

    def _create_monitor_window(self):
        """Create a tkinter monitor window showing connection status and
        message log."""
        try:
            import tkinter as tk
            from tkinter import ttk, scrolledtext, END
        except ImportError:
            return

        if hasattr(self, "_monitor_window") and self._monitor_window:
            return

        self._monitor_window = tk.Toplevel()
        self._monitor_window.title("WhatsApp Integration")
        self._monitor_window.geometry("700x500")
        self._monitor_window.minsize(500, 400)
        self._monitor_window.protocol("WM_DELETE_WINDOW", self._stop_node)

        self._monitor_window.grid_rowconfigure(0, weight=0)
        self._monitor_window.grid_rowconfigure(1, weight=1)
        self._monitor_window.grid_rowconfigure(2, weight=0)
        self._monitor_window.grid_columnconfigure(0, weight=1)

        # -- Status frame --
        status_frame = ttk.LabelFrame(self._monitor_window, text="Connection Status")
        status_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        phone_id = self._get_prop("phone_number_id") or "Not set"
        port = self._get_prop("webhook_port") or "5555"

        self._status_var = tk.StringVar(value="Running" if self._webhook_running else "Stopped")
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, textvariable=self._status_var).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(status_frame, text="Phone ID:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, text=f"{phone_id[:10]}..." if len(phone_id) > 10 else phone_id).grid(
            row=0, column=3, sticky="w", padx=5, pady=2
        )

        ttk.Label(status_frame, text="Webhook Port:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, text=port).grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(status_frame, text="Webhook URL:").grid(row=1, column=2, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, text=f"http://localhost:{port}/webhook").grid(
            row=1, column=3, sticky="w", padx=5, pady=2
        )

        # -- Log frame --
        log_frame = ttk.LabelFrame(self._monitor_window, text="Message Log")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log_text = scrolledtext.ScrolledText(
            log_frame, height=15, width=80, wrap=tk.WORD, state=tk.DISABLED
        )
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # -- Manual send frame --
        send_frame = ttk.LabelFrame(self._monitor_window, text="Send Message")
        send_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        send_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(send_frame, text="To:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self._send_to_var = tk.StringVar()
        ttk.Entry(send_frame, textvariable=self._send_to_var, width=20).grid(
            row=0, column=1, sticky="w", padx=5, pady=2
        )

        ttk.Label(send_frame, text="Message:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self._send_msg_var = tk.StringVar()
        msg_entry = ttk.Entry(send_frame, textvariable=self._send_msg_var, width=50)
        msg_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        send_btn = ttk.Button(send_frame, text="Send", command=self._manual_send)
        send_btn.grid(row=1, column=2, padx=5, pady=2)

        stop_btn = ttk.Button(send_frame, text="Stop", command=self._stop_node)
        stop_btn.grid(row=0, column=2, padx=5, pady=2)

        # Flush any buffered log messages
        self._flush_log_to_widget()

    def _flush_log_to_widget(self):
        """Write any buffered log messages to the tkinter text widget."""
        if not hasattr(self, "_log_text") or not self._log_text:
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

    def _manual_send(self):
        """Send a message manually from the monitor window."""
        to = self._send_to_var.get().strip()
        msg = self._send_msg_var.get().strip()
        if not to or not msg:
            self._log("Please enter both a phone number and message.")
            return
        if self._wa_client:
            self._send_wa_response(to, msg, [])
            self._send_msg_var.set("")
        else:
            self._log("WhatsApp client not initialized.")

    def _stop_node(self):
        """Stop the webhook server and close the monitor window."""
        self._stop_event.set()
        self._webhook_running = False
        self._log("Stopping WhatsApp integration node...")
        if hasattr(self, "_monitor_window") and self._monitor_window:
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

    def _get_verify_token(self) -> str:
        return self._get_prop("verify_token") or "xeroflow_whatsapp_verify"

    def _get_allowed_numbers(self) -> set:
        raw = self._get_prop("allowed_numbers") or ""
        if not raw.strip():
            return set()
        return {n.strip().lstrip("+") for n in raw.split(",") if n.strip()}

    def _log(self, message: str):
        """Thread-safe logging to both console and the monitor widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        logger.info(message)
        print(f"[WhatsAppNode] {entry}")

        with self._log_lock:
            self._log_messages.append(entry)

        # Update the tkinter widget if available
        if hasattr(self, "_log_text") and self._log_text and hasattr(self, "_monitor_window") and self._monitor_window:
            try:
                import tkinter as tk
                self._monitor_window.after(0, lambda e=entry: self._append_log_line(e))
            except Exception:
                pass

    def _append_log_line(self, line: str):
        """Append a line to the log widget (must run on main thread)."""
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
        """Convert markdown to WhatsApp-compatible formatting.

        WhatsApp supports: *bold*, _italic_, ~strikethrough~, ```monospace```
        """
        import re
        # Convert markdown bold **text** to WhatsApp bold *text*
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"*_\1_*", text)  # bold+italic
        text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)  # bold
        # Convert markdown headers to bold
        text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
        # Convert markdown strikethrough ~~text~~ to WhatsApp ~text~
        text = re.sub(r"~~(.+?)~~", r"~\1~", text)
        # Convert markdown code blocks
        text = re.sub(r"```\w*\n", "```\n", text)
        # Remove markdown image syntax
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[\1]", text)
        # Convert markdown links [text](url) to text (url)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        return text

    def requires_api_call(self):
        return True

    def set_message_callback(self, callback):
        """Register a callback function that will be called when a new
        WhatsApp message arrives. The callback receives (text, file_paths)
        and should return a response string."""
        self._message_callback = callback

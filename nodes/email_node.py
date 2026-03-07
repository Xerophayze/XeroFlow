# nodes/email_node.py
"""EmailNode — Gmail integration via app passwords.

Provides SMTP send and IMAP inbox polling. Incoming emails are forwarded
to the MasterAgentNode for summarisation and interactive reply. Other
nodes (TaskTrackerNode, CalendarNode) can discover this node via
RUNNING_INSTANCES and call send_email() directly.

No external dependencies — uses Python stdlib smtplib, imaplib, email.
"""

from __future__ import annotations

import email as email_lib
import email.header
import email.utils
import imaplib
import logging
import mimetypes
import os
import smtplib
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_node import BaseNode
from src.workflows.node_registry import register_node

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
MAX_RECENT_EMAILS = 20  # in-memory context buffer size


# ---------------------------------------------------------------------------
# The Node
# ---------------------------------------------------------------------------
@register_node("EmailNode")
class EmailNode(BaseNode):
    """Gmail integration via app passwords. Add this node to a workflow to
    give the agent the ability to send and receive email. Configure your
    Gmail address and app password in the node properties."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._connected = False
        self._log_messages: List[str] = []
        self._log_lock = threading.Lock()
        self._monitor_window = None
        self._status_var = None
        self._log_text = None
        # Recent email buffer for context lookups ("reply to that email")
        self._recent_emails: deque = deque(maxlen=MAX_RECENT_EMAILS)
        self._recent_lock = threading.Lock()
        # Track IMAP UIDs we have already processed
        self._seen_uids: set = set()
        # First-run flag — bulk-skip only happens on the very first poll
        self._initial_scan_done: bool = False
        # Timestamp when the node started — only process emails after this
        self._start_time: datetime = datetime.now()

    # -- Node interface -----------------------------------------------------

    def define_inputs(self):
        return ["response"]

    def define_outputs(self):
        return ["message"]

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            "node_name": {
                "type": "text",
                "label": "Custom Node Name",
                "default": "EmailNode",
            },
            "description": {
                "type": "text",
                "label": "Description",
                "default": (
                    "Gmail integration via app password. Sends and receives "
                    "email. Incoming messages are forwarded to the Master "
                    "Agent for summarisation and interactive reply."
                ),
            },
            "gmail_address": {
                "type": "text",
                "label": "Gmail Address",
                "default": "",
                "description": "Your full Gmail address (e.g. you@gmail.com).",
            },
            "gmail_app_password": {
                "type": "text",
                "label": "Gmail App Password",
                "default": "",
                "sensitive": True,
                "description": (
                    "A Google App Password for your account. Generate one at "
                    "https://myaccount.google.com/apppasswords"
                ),
            },
            "poll_interval_seconds": {
                "type": "text",
                "label": "Inbox Poll Interval (seconds)",
                "default": "300",
                "description": "How often to check for new emails. Default 300 (5 min).",
            },
            "auto_forward_to_master": {
                "type": "boolean",
                "label": "Auto-Forward to Master Agent",
                "default": True,
                "description": "Automatically forward new incoming emails to the Master Agent.",
            },
            "allowed_senders": {
                "type": "textarea",
                "label": "Allowed Senders",
                "default": "",
                "description": (
                    "Comma-separated email addresses to monitor. "
                    "Leave empty to forward ALL incoming emails."
                ),
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
                "description": "Keeps the email connection alive to poll for new messages.",
            },
        })
        return props

    # -- process (main entry point) -----------------------------------------

    def process(self, inputs):
        """Called by the workflow engine. Opens monitor window, starts IMAP
        poller, then blocks to keep the node alive."""
        self.inputs = inputs
        self._stop_event.clear()

        workflow_stop_event = inputs.get("stop_event") if isinstance(inputs, dict) else None

        # Register so other nodes can discover us
        try:
            from src.workflows.node_registry import register_running_instance
            register_running_instance("EmailNode", self)
        except Exception:
            pass

        # Create monitor window
        try:
            self._create_monitor_window()
        except Exception as exc:
            self._log(f"Monitor window error: {exc}")

        # Validate credentials
        address = self._get_prop("gmail_address")
        app_pw = self._get_prop("gmail_app_password")
        if not address or not app_pw:
            self._log("ERROR: Gmail address and app password are required. "
                      "Configure them in the node properties.")
            self._update_status("Missing credentials")
        else:
            # Test SMTP connection
            if self._test_smtp_connection(address, app_pw):
                self._log("SMTP connection verified.")
                self._update_status(f"Connected ({address})")
                self._connected = True
            else:
                self._update_status("SMTP connection failed")

            # Start IMAP poller
            auto_fwd = self._get_prop("auto_forward_to_master")
            if auto_fwd and str(auto_fwd).lower() not in ("false", "0", ""):
                self._poll_thread = threading.Thread(
                    target=self._poll_inbox_loop,
                    daemon=True,
                    name="email-imap-poller",
                )
                self._poll_thread.start()
                self._log("IMAP inbox poller started.")

        # Block — keep node alive
        self._log("Email node running. Waiting for activity...")
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
        return {"message": ""}

    # -- SMTP: send email ---------------------------------------------------

    def send_email(self, to: str, subject: str, body: str,
                   attachments: Optional[List[str]] = None,
                   reply_to_message_id: Optional[str] = None) -> dict:
        """Send an email via Gmail SMTP.

        Parameters:
            to: Recipient email address (comma-separated for multiple).
            subject: Email subject line.
            body: Plain-text email body.
            attachments: Optional list of file paths to attach.
            reply_to_message_id: Optional Message-ID for threading replies.

        Returns:
            {"success": bool, "error": str or None}
        """
        address = self._get_prop("gmail_address")
        app_pw = self._get_prop("gmail_app_password")
        if not address or not app_pw:
            return {"success": False, "error": "Gmail credentials not configured"}

        try:
            msg = MIMEMultipart()
            msg["From"] = address
            msg["To"] = to
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            sent_message_id = email.utils.make_msgid(domain=address.split("@")[-1])
            msg["Message-ID"] = sent_message_id
            if reply_to_message_id:
                msg["In-Reply-To"] = reply_to_message_id
                msg["References"] = reply_to_message_id

            msg.attach(MIMEText(body, "plain", "utf-8"))

            # Attach files
            for fpath in (attachments or []):
                if not os.path.exists(fpath):
                    self._log(f"Attachment not found: {fpath}")
                    continue
                mime_type = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
                with open(fpath, "rb") as f:
                    part = MIMEApplication(f.read(), Name=Path(fpath).name)
                part["Content-Disposition"] = f'attachment; filename="{Path(fpath).name}"'
                msg.attach(part)

            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(address, app_pw)
                server.sendmail(address, [a.strip() for a in to.split(",")], msg.as_string())

            self._log(f"Email sent to {to}: {subject}")
            return {"success": True, "error": None, "message_id": sent_message_id}

        except Exception as exc:
            err = f"SMTP send error: {exc}"
            self._log(err)
            traceback.print_exc()
            return {"success": False, "error": err}

    # -- IMAP: poll inbox ---------------------------------------------------

    def _poll_inbox_loop(self):
        """Background thread: periodically check for new emails."""
        address = self._get_prop("gmail_address")
        app_pw = self._get_prop("gmail_app_password")
        interval = self._parse_int(self._get_prop("poll_interval_seconds"), 300)

        self._log(f"Polling inbox every {interval}s for {address}")

        while not self._stop_event.is_set():
            try:
                self._check_inbox(address, app_pw)
            except Exception as exc:
                self._log(f"IMAP poll error: {exc}")
                traceback.print_exc()

            # Sleep in small increments so we can stop quickly
            for _ in range(interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _check_inbox(self, address: str, app_pw: str):
        """Connect to IMAP, fetch emails arriving SINCE the node started."""
        allowed = self._get_allowed_senders()

        with imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT) as imap:
            imap.login(address, app_pw)
            imap.select("INBOX")

            # Only fetch emails from today or later (IMAP SINCE is date-only)
            since_date = self._start_time.strftime("%d-%b-%Y")
            status, data = imap.search(None, "UNSEEN", f'(SINCE "{since_date}")')
            if status != "OK" or not data[0]:
                return

            msg_nums = data[0].split()

            # --- First-run protection: bulk-skip all pre-existing unread ---
            if not self._initial_scan_done:
                self._initial_scan_done = True
                if msg_nums:
                    self._log(f"Skipping {len(msg_nums)} pre-existing unread emails — only monitoring new arrivals")
                    for num in msg_nums:
                        if self._stop_event.is_set():
                            return
                        try:
                            uid_status, uid_data = imap.fetch(num, "(UID)")
                            uid = self._extract_uid(uid_data)
                            if uid:
                                self._seen_uids.add(uid)
                        except Exception:
                            pass
                    self._log(f"Marked {len(self._seen_uids)} existing emails as seen")
                return  # always return on first scan — nothing to process yet

            # --- Subsequent polls: only process emails with unknown UIDs ---
            new_nums = []
            for num in msg_nums:
                if self._stop_event.is_set():
                    return
                try:
                    uid_status, uid_data = imap.fetch(num, "(UID)")
                    uid = self._extract_uid(uid_data)
                    if uid and uid in self._seen_uids:
                        continue
                    new_nums.append((num, uid))
                except Exception:
                    pass

            if not new_nums:
                return

            self._log(f"Found {len(new_nums)} new email(s)")

            for num, uid in new_nums:
                if self._stop_event.is_set():
                    return
                if uid:
                    self._seen_uids.add(uid)
                try:
                    # Fetch full message
                    status2, msg_data = imap.fetch(num, "(RFC822)")
                    if status2 != "OK":
                        continue

                    raw_email = msg_data[0][1]
                    parsed = email_lib.message_from_bytes(raw_email)

                    from_addr = self._decode_header(parsed.get("From", ""))
                    subject = self._decode_header(parsed.get("Subject", "(no subject)"))
                    date_str = parsed.get("Date", "")
                    message_id = parsed.get("Message-ID", "")
                    body = self._extract_body(parsed)

                    # Filter by allowed senders
                    if allowed:
                        sender_email = email.utils.parseaddr(from_addr)[1].lower()
                        if not any(a in sender_email for a in allowed):
                            continue

                    email_data = {
                        "from": from_addr,
                        "from_email": email.utils.parseaddr(from_addr)[1],
                        "subject": subject,
                        "body": body,
                        "date": date_str,
                        "message_id": message_id,
                        "uid": uid,
                    }

                    # Skip emails that arrived before the node started
                    email_date = email.utils.parsedate_to_datetime(
                        date_str
                    ) if date_str else None
                    if email_date and email_date.replace(tzinfo=None) < self._start_time:
                        continue

                    self._log(f"New email from {from_addr}: {subject}")

                    # Store in recent buffer
                    with self._recent_lock:
                        self._recent_emails.append(email_data)

                    # Forward to Master Agent
                    self._handle_incoming_email(email_data)

                except Exception as exc:
                    self._log(f"Error processing email #{num}: {exc}")
                    traceback.print_exc()

    def _handle_incoming_email(self, email_data: dict):
        """Forward an incoming email to the MasterAgentNode."""
        auto_fwd = self._get_prop("auto_forward_to_master")
        if not auto_fwd or str(auto_fwd).lower() in ("false", "0", ""):
            return

        master = self._find_master_agent()
        if not master:
            self._log("No MasterAgentNode found — cannot forward email")
            return

        # Build a structured message for the Master Agent
        summary = (
            f"NEW EMAIL RECEIVED\n"
            f"From: {email_data['from']}\n"
            f"Subject: {email_data['subject']}\n"
            f"Date: {email_data['date']}\n"
            f"Message-ID: {email_data['message_id']}\n\n"
            f"Body:\n{email_data['body'][:4000]}"
        )

        try:
            self._log(f"Forwarding to Master Agent: {email_data['subject']}")
            result = master.process_external_message(
                summary, sender="Email"
            )
            response_text = result.get("text", "") if isinstance(result, dict) else str(result)
            if response_text:
                self._log(f"Master Agent processed email ({len(response_text)} chars)")
                # WhatsApp notification is handled by the MasterAgent's Email
                # short-circuit — no need to send again from here.
        except Exception as exc:
            self._log(f"Error forwarding to Master Agent: {exc}")
            traceback.print_exc()

    # -- Recent email context buffer ----------------------------------------

    def get_recent_emails(self, count: int = 5) -> List[dict]:
        """Return the N most recent emails for context lookups."""
        with self._recent_lock:
            return list(self._recent_emails)[-count:]

    def find_email_by_sender(self, sender_query: str) -> Optional[dict]:
        """Find the most recent email matching a sender name or address."""
        query = sender_query.lower()
        with self._recent_lock:
            for em in reversed(self._recent_emails):
                if query in em.get("from", "").lower() or query in em.get("from_email", "").lower():
                    return em
        return None

    def find_email_by_subject(self, subject_query: str) -> Optional[dict]:
        """Find the most recent email matching a subject fragment."""
        query = subject_query.lower()
        with self._recent_lock:
            for em in reversed(self._recent_emails):
                if query in em.get("subject", "").lower():
                    return em
        return None

    def get_last_email(self) -> Optional[dict]:
        """Return the most recently received email."""
        with self._recent_lock:
            return self._recent_emails[-1] if self._recent_emails else None

    # -- Connection test ----------------------------------------------------

    def _test_smtp_connection(self, address: str, app_pw: str) -> bool:
        """Test SMTP credentials. Returns True on success."""
        try:
            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(address, app_pw)
            return True
        except Exception as exc:
            self._log(f"SMTP test failed: {exc}")
            return False

    # -- Master Agent discovery ---------------------------------------------

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

    # -- WhatsApp notification -----------------------------------------------

    def _notify_user_via_whatsapp(self, text: str):
        """Forward a message to the user via WhatsApp (if connected)."""
        try:
            from src.workflows.node_registry import get_running_instance
            wa_node = get_running_instance("WhatsAppWebNode")
            if not wa_node or not getattr(wa_node, '_connected', False):
                self._log("WhatsApp not connected — notification skipped")
                return
            my_jid = getattr(wa_node, '_my_jid', None)
            if not my_jid:
                return
            from neonize.utils import build_jid
            chat_jid = build_jid(my_jid)
            wa_node._send_wa_text(chat_jid, text)
            self._log("Email notification sent to WhatsApp")
        except ImportError:
            self._log("neonize not available — WhatsApp notification skipped")
        except Exception as exc:
            self._log(f"WhatsApp notification failed: {exc}")

    # -- Stop ---------------------------------------------------------------

    def _stop_node(self):
        """Clean up and close."""
        self._stop_event.set()
        self._connected = False
        self._log("Stopping Email node...")

        try:
            from src.workflows.node_registry import unregister_running_instance
            unregister_running_instance("EmailNode")
        except Exception:
            pass

        if self._monitor_window:
            try:
                self._monitor_window.destroy()
            except Exception:
                pass
            self._monitor_window = None

    # -- Monitor window (tkinter) ------------------------------------------

    def _create_monitor_window(self):
        """Create a tkinter monitor window with status and log."""
        try:
            import tkinter as tk
            from tkinter import ttk, scrolledtext
        except ImportError:
            return

        if self._monitor_window:
            return

        self._monitor_window = tk.Toplevel()
        self._monitor_window.title("Email Node — Gmail")
        self._monitor_window.geometry("650x450")
        self._monitor_window.minsize(450, 300)
        self._monitor_window.protocol("WM_DELETE_WINDOW", self._stop_node)

        self._monitor_window.grid_rowconfigure(1, weight=1)
        self._monitor_window.grid_columnconfigure(0, weight=1)

        # -- Status frame --
        status_frame = ttk.LabelFrame(self._monitor_window, text="Connection")
        status_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="Initializing...")
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(
            status_frame, textvariable=self._status_var,
            font=("Helvetica", 10, "bold")
        ).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        address = self._get_prop("gmail_address") or "(not configured)"
        ttk.Label(status_frame, text="Account:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, text=address).grid(row=1, column=1, sticky="w", padx=5, pady=2)

        # -- Log frame --
        log_frame = ttk.LabelFrame(self._monitor_window, text="Activity Log")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="#d4d4d4"
        )
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        # -- Manual send frame --
        send_frame = ttk.LabelFrame(self._monitor_window, text="Quick Send")
        send_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        send_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(send_frame, text="To:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self._send_to_var = tk.StringVar()
        ttk.Entry(send_frame, textvariable=self._send_to_var).grid(
            row=0, column=1, sticky="ew", padx=5, pady=2
        )

        ttk.Label(send_frame, text="Subject:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self._send_subject_var = tk.StringVar()
        ttk.Entry(send_frame, textvariable=self._send_subject_var).grid(
            row=1, column=1, sticky="ew", padx=5, pady=2
        )

        ttk.Label(send_frame, text="Body:").grid(row=2, column=0, sticky="nw", padx=5, pady=2)
        self._send_body_text = tk.Text(send_frame, height=3, wrap=tk.WORD)
        self._send_body_text.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ttk.Button(send_frame, text="Send", command=self._on_manual_send).grid(
            row=3, column=1, sticky="e", padx=5, pady=5
        )

    def _on_manual_send(self):
        """Handle the Quick Send button click."""
        to = self._send_to_var.get().strip()
        subject = self._send_subject_var.get().strip()
        body = self._send_body_text.get("1.0", "end").strip()
        if not to:
            self._log("Quick Send: 'To' address is required")
            return
        if not subject:
            subject = "(no subject)"

        result = self.send_email(to, subject, body)
        if result["success"]:
            self._send_to_var.set("")
            self._send_subject_var.set("")
            self._send_body_text.delete("1.0", "end")
        else:
            self._log(f"Quick Send failed: {result['error']}")

    def _update_status(self, text: str):
        """Update the status label in the monitor window."""
        if self._status_var and self._monitor_window:
            try:
                self._monitor_window.after(0, lambda: self._status_var.set(text))
            except Exception:
                pass

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

    def _get_allowed_senders(self) -> set:
        """Parse the allowed_senders property into a set of lowercase emails."""
        raw = self._get_prop("allowed_senders") or ""
        if not raw.strip():
            return set()
        return {s.strip().lower() for s in raw.split(",") if s.strip()}

    @staticmethod
    def _parse_int(value, default: int) -> int:
        """Safely parse an integer from a property value."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _extract_uid(uid_data) -> Optional[str]:
        """Extract UID from IMAP fetch response."""
        if not uid_data or not uid_data[0]:
            return None
        try:
            import re
            match = re.search(rb"UID\s+(\d+)", uid_data[0])
            if match:
                return match.group(1).decode()
        except Exception:
            pass
        return None

    @staticmethod
    def _decode_header(header_value: str) -> str:
        """Decode an email header that may contain encoded words."""
        if not header_value:
            return ""
        parts = email.header.decode_header(header_value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    @staticmethod
    def _extract_body(msg) -> str:
        """Extract the plain-text body from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""

    def _log(self, message: str):
        """Thread-safe logging to console and monitor widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        logger.info(message)
        print(f"[EmailNode] {entry}")

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

    def requires_api_call(self):
        return False

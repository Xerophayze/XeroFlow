# nodes/task_tracker_node.py
"""TaskTrackerNode — Scheduled task and duty tracker.

Maintains a SQLite database of recurring and one-off tasks. A background
scheduler checks for due tasks and triggers the MasterAgentNode to
execute them. Results are routed to the user via WhatsApp, email, or
logged to the monitor window.

Other nodes (especially MasterAgentNode) can discover this node via
RUNNING_INSTANCES and call add_task / update_task / remove_task / list_tasks
to manage the task database through natural language.

No external dependencies — uses Python stdlib sqlite3 + threading.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base_node import BaseNode
from src.workflows.node_registry import register_node

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_DIR = "data"
DB_FILENAME = "task_tracker.db"
DEFAULT_CHECK_INTERVAL = 60  # seconds


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _parse_time(time_str: str) -> tuple:
    """Parse a time string like '09:00' or '14:30' into (hour, minute)."""
    m = re.match(r'(\d{1,2}):(\d{2})', time_str.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def calculate_next_run(schedule_type: str, schedule_value: str,
                       from_time: datetime = None) -> Optional[datetime]:
    """Calculate the next run time based on schedule type and value.

    schedule_type: 'once', 'hourly', 'daily', 'weekly', 'cron'
    schedule_value: depends on type:
        once   → ISO datetime or 'YYYY-MM-DD HH:MM'
        hourly → minutes past the hour, e.g. '15' or '*/2' (every 2 hours)
        daily  → time, e.g. '09:00'
        weekly → 'mon,wed,fri 09:00' or 'monday 14:30'
        cron   → simplified cron (not full POSIX, basic support)
    """
    now = from_time or datetime.now()

    if schedule_type == 'once':
        try:
            target = datetime.fromisoformat(schedule_value.strip())
            return target if target > now else None
        except ValueError:
            return None

    if schedule_type == 'hourly':
        val = schedule_value.strip()
        if val.startswith('*/'):
            # Every N hours
            try:
                interval_hours = int(val[2:])
            except ValueError:
                interval_hours = 1
            next_run = now + timedelta(hours=interval_hours)
            return next_run.replace(minute=0, second=0, microsecond=0)
        else:
            # Minutes past the hour
            try:
                minute = int(val)
            except ValueError:
                minute = 0
            candidate = now.replace(minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(hours=1)
            return candidate

    if schedule_type == 'daily':
        hour, minute = _parse_time(schedule_value)
        if hour is None:
            return now + timedelta(days=1)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if schedule_type == 'weekly':
        # Format: 'mon,wed,fri 09:00' or 'monday 14:30'
        parts = schedule_value.strip().split()
        if len(parts) < 2:
            return now + timedelta(weeks=1)
        day_names = parts[0].lower().split(',')
        hour, minute = _parse_time(parts[1])
        if hour is None:
            hour, minute = 9, 0

        day_map = {
            'mon': 0, 'monday': 0, 'tue': 1, 'tuesday': 1,
            'wed': 2, 'wednesday': 2, 'thu': 3, 'thursday': 3,
            'fri': 4, 'friday': 4, 'sat': 5, 'saturday': 5,
            'sun': 6, 'sunday': 6,
        }
        target_days = sorted(set(day_map.get(d.strip(), 0) for d in day_names))
        if not target_days:
            target_days = [0]

        # Find the next matching day
        for offset in range(1, 8):
            candidate = now + timedelta(days=offset)
            candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate.weekday() in target_days and candidate > now:
                return candidate
        # Also check today if time hasn't passed
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today > now and now.weekday() in target_days:
            return today

        return now + timedelta(weeks=1)

    # Fallback
    return now + timedelta(days=1)


# ---------------------------------------------------------------------------
# The Node
# ---------------------------------------------------------------------------
@register_node("TaskTrackerNode")
class TaskTrackerNode(BaseNode):
    """Scheduled task and duty tracker. Maintains a database of tasks that
    fire on schedule and trigger the Master Agent to execute them. Add this
    node to a workflow to give the agent proactive, time-driven capabilities."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._db_path: Optional[str] = None
        self._db_lock = threading.Lock()
        self._log_messages: List[str] = []
        self._log_lock = threading.Lock()
        self._monitor_window = None
        self._status_var = None
        self._log_text = None
        self._task_tree = None  # tkinter Treeview for task list

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
                "default": "TaskTrackerNode",
            },
            "description": {
                "type": "text",
                "label": "Description",
                "default": (
                    "Scheduled task and duty tracker. Maintains a database of "
                    "recurring tasks that trigger the Master Agent on schedule. "
                    "Create tasks via natural language through WhatsApp or chat."
                ),
            },
            "check_interval_seconds": {
                "type": "text",
                "label": "Scheduler Check Interval (seconds)",
                "default": "60",
                "description": "How often the scheduler checks for due tasks.",
            },
            "default_notify_via": {
                "type": "text",
                "label": "Default Notification Channel",
                "default": "whatsapp",
                "description": "Default channel for task notifications: whatsapp, email, log",
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
                "description": "Keeps the scheduler running to check for due tasks.",
            },
        })
        return props

    # -- process (main entry point) -----------------------------------------

    def process(self, inputs):
        """Called by the workflow engine. Initialises the database, starts
        the scheduler, opens the monitor window, then blocks."""
        self.inputs = inputs
        self._stop_event.clear()

        workflow_stop_event = inputs.get("stop_event") if isinstance(inputs, dict) else None

        # Register so other nodes can discover us
        try:
            from src.workflows.node_registry import register_running_instance
            register_running_instance("TaskTrackerNode", self)
        except Exception:
            pass

        # Initialise database
        self._init_database()

        # Create monitor window
        try:
            self._create_monitor_window()
        except Exception as exc:
            self._log(f"Monitor window error: {exc}")

        # Start scheduler
        interval = self._parse_int(self._get_prop("check_interval_seconds"),
                                   DEFAULT_CHECK_INTERVAL)
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(interval,),
            daemon=True,
            name="task-scheduler",
        )
        self._scheduler_thread.start()

        task_count = len(self.list_tasks(status="active"))
        self._log(f"Task Tracker running. {task_count} active task(s). "
                  f"Checking every {interval}s.")
        self._update_status(f"Running — {task_count} active tasks")

        # Block — keep node alive
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

    # -- Database -----------------------------------------------------------

    def _init_database(self):
        """Create the SQLite database and tasks table if they don't exist."""
        os.makedirs(DATA_DIR, exist_ok=True)
        self._db_path = os.path.join(DATA_DIR, DB_FILENAME)

        with self._db_lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    schedule_type TEXT DEFAULT 'once',
                    schedule_value TEXT DEFAULT '',
                    next_run TEXT,
                    last_run TEXT,
                    notify_via TEXT DEFAULT 'whatsapp',
                    notify_target TEXT DEFAULT '',
                    status TEXT DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    priority TEXT DEFAULT 'medium',
                    category TEXT DEFAULT '',
                    max_retries INTEGER DEFAULT 3,
                    retry_count INTEGER DEFAULT 0,
                    last_result TEXT DEFAULT ''
                )
            """)
            conn.commit()
            conn.close()
        self._log(f"Database initialised: {self._db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection (thread-safe with lock)."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- CRUD API -----------------------------------------------------------

    def add_task(self, task_dict: dict) -> dict:
        """Add a new task to the database.

        Required keys: title
        Optional: description, schedule_type, schedule_value, notify_via,
                  notify_target, priority, category, max_retries

        Returns the created task as a dict.
        """
        task_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()

        title = task_dict.get("title", "Untitled Task")
        schedule_type = task_dict.get("schedule_type", "once")
        schedule_value = task_dict.get("schedule_value", "")
        notify_via = task_dict.get("notify_via",
                                   self._get_prop("default_notify_via") or "whatsapp")

        next_run = calculate_next_run(schedule_type, schedule_value)
        next_run_str = next_run.isoformat() if next_run else None

        task = {
            "id": task_id,
            "title": title,
            "description": task_dict.get("description", ""),
            "schedule_type": schedule_type,
            "schedule_value": schedule_value,
            "next_run": next_run_str,
            "last_run": None,
            "notify_via": notify_via,
            "notify_target": task_dict.get("notify_target", ""),
            "status": "active",
            "created_at": now_str,
            "priority": task_dict.get("priority", "medium"),
            "category": task_dict.get("category", ""),
            "max_retries": task_dict.get("max_retries", 3),
            "retry_count": 0,
            "last_result": "",
        }

        with self._db_lock:
            conn = self._get_conn()
            conn.execute("""
                INSERT INTO tasks (id, title, description, schedule_type,
                    schedule_value, next_run, last_run, notify_via, notify_target,
                    status, created_at, priority, category, max_retries,
                    retry_count, last_result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task["id"], task["title"], task["description"],
                task["schedule_type"], task["schedule_value"],
                task["next_run"], task["last_run"],
                task["notify_via"], task["notify_target"],
                task["status"], task["created_at"],
                task["priority"], task["category"],
                task["max_retries"], task["retry_count"],
                task["last_result"],
            ))
            conn.commit()
            conn.close()

        self._log(f"Task created: {title} [{schedule_type} {schedule_value}]")
        self._refresh_task_list()
        return task

    def update_task(self, task_id: str, updates: dict) -> Optional[dict]:
        """Update fields of an existing task. Returns the updated task or None."""
        allowed_fields = {
            "title", "description", "schedule_type", "schedule_value",
            "notify_via", "notify_target", "status", "priority", "category",
            "max_retries",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return None

        # Recalculate next_run if schedule changed
        if "schedule_type" in filtered or "schedule_value" in filtered:
            existing = self._get_task_by_id(task_id)
            if existing:
                stype = filtered.get("schedule_type", existing["schedule_type"])
                sval = filtered.get("schedule_value", existing["schedule_value"])
                next_run = calculate_next_run(stype, sval)
                filtered["next_run"] = next_run.isoformat() if next_run else None

        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [task_id]

        with self._db_lock:
            conn = self._get_conn()
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
            conn.commit()
            conn.close()

        self._log(f"Task updated: {task_id[:8]}... — {list(filtered.keys())}")
        self._refresh_task_list()
        return self._get_task_by_id(task_id)

    def remove_task(self, task_id: str) -> bool:
        """Remove a task from the database. Returns True if deleted."""
        with self._db_lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            conn.close()

        if deleted:
            self._log(f"Task removed: {task_id[:8]}...")
            self._refresh_task_list()
        return deleted

    def list_tasks(self, status: str = None, category: str = None,
                   limit: int = 50) -> List[dict]:
        """Query tasks with optional filters. Returns list of dicts."""
        query = "SELECT * FROM tasks"
        params = []
        conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY next_run ASC LIMIT ?"
        params.append(limit)

        with self._db_lock:
            conn = self._get_conn()
            rows = conn.execute(query, params).fetchall()
            conn.close()

        return [dict(row) for row in rows]

    def get_task_summary(self) -> str:
        """Return a human-readable summary of all active tasks."""
        tasks = self.list_tasks(status="active")
        if not tasks:
            return "No active tasks."
        lines = []
        for t in tasks:
            next_run = t.get("next_run", "unscheduled")
            if next_run:
                try:
                    dt = datetime.fromisoformat(next_run)
                    next_run = dt.strftime("%a %b %d %I:%M %p")
                except ValueError:
                    pass
            lines.append(
                f"- {t['title']} [{t['schedule_type']} {t['schedule_value']}] "
                f"next: {next_run} | notify: {t['notify_via']} | "
                f"priority: {t['priority']}"
            )
        return f"Active tasks ({len(tasks)}):\n" + "\n".join(lines)

    def _get_task_by_id(self, task_id: str) -> Optional[dict]:
        """Fetch a single task by ID."""
        with self._db_lock:
            conn = self._get_conn()
            row = conn.execute("SELECT * FROM tasks WHERE id = ?",
                               (task_id,)).fetchone()
            conn.close()
        return dict(row) if row else None

    # -- Scheduler ----------------------------------------------------------

    def _scheduler_loop(self, interval: int):
        """Background thread: check for due tasks every N seconds."""
        self._log(f"Scheduler started (interval={interval}s)")
        while not self._stop_event.is_set():
            try:
                self._check_due_tasks()
            except Exception as exc:
                self._log(f"Scheduler error: {exc}")
                traceback.print_exc()

            for _ in range(interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _check_due_tasks(self):
        """Find tasks where next_run <= now and execute them."""
        now = datetime.now()
        now_str = now.isoformat()

        with self._db_lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'active' AND next_run <= ?",
                (now_str,)
            ).fetchall()
            conn.close()

        if not rows:
            return

        for row in rows:
            task = dict(row)
            self._log(f"Task due: {task['title']}")
            threading.Thread(
                target=self._execute_task,
                args=(task,),
                daemon=True,
                name=f"task-exec-{task['id'][:8]}",
            ).start()

    def _execute_task(self, task: dict):
        """Execute a due task by sending it to the MasterAgentNode."""
        master = self._find_master_agent()
        if not master:
            self._log(f"No MasterAgentNode found — cannot execute task: {task['title']}")
            self._mark_task_result(task, "ERROR: No MasterAgentNode available")
            return

        task_message = (
            f"SCHEDULED TASK: {task['title']}\n"
            f"Priority: {task['priority']}\n"
            f"Category: {task.get('category', 'general')}\n\n"
            f"{task['description']}"
        )

        try:
            self._log(f"Executing task: {task['title']}")
            result = master.process_external_message(
                task_message, sender="TaskTracker"
            )
            response_text = result.get("text", "") if isinstance(result, dict) else str(result)
            response_files = result.get("files", []) if isinstance(result, dict) else []

            self._log(f"Task result ({len(response_text)} chars): {task['title']}")

            # Route notification
            self._route_notification(task, response_text, response_files)

            # Update task record
            self._mark_task_result(task, response_text[:2000])

        except Exception as exc:
            error_msg = f"Task execution error: {exc}"
            self._log(error_msg)
            traceback.print_exc()
            self._mark_task_result(task, error_msg)

    def _mark_task_result(self, task: dict, result_text: str):
        """Update a task after execution: set last_run, calculate next_run,
        update retry count and status."""
        now = datetime.now()
        now_str = now.isoformat()

        # Calculate next run
        if task["schedule_type"] == "once":
            next_run = None
            new_status = "completed"
        else:
            next_run = calculate_next_run(
                task["schedule_type"], task["schedule_value"], from_time=now
            )
            new_status = "active"

        next_run_str = next_run.isoformat() if next_run else None

        # Handle failures
        is_error = result_text.startswith("ERROR:") or result_text.startswith("Task execution error:")
        retry_count = task.get("retry_count", 0)
        if is_error:
            retry_count += 1
            if retry_count >= task.get("max_retries", 3):
                new_status = "failed"
                self._log(f"Task failed after {retry_count} retries: {task['title']}")
        else:
            retry_count = 0  # Reset on success

        with self._db_lock:
            conn = self._get_conn()
            conn.execute("""
                UPDATE tasks SET last_run = ?, next_run = ?, status = ?,
                    retry_count = ?, last_result = ?
                WHERE id = ?
            """, (now_str, next_run_str, new_status, retry_count,
                  result_text[:2000], task["id"]))
            conn.commit()
            conn.close()

        self._refresh_task_list()

    # -- Notification routing -----------------------------------------------

    def _route_notification(self, task: dict, response_text: str,
                            response_files: list = None):
        """Send the task result to the configured notification channel(s)."""
        channels = [c.strip().lower()
                    for c in task.get("notify_via", "log").split(",")]

        notification = (
            f"Task completed: {task['title']}\n"
            f"Schedule: {task['schedule_type']} {task['schedule_value']}\n\n"
            f"{response_text}"
        )

        for channel in channels:
            if channel == "whatsapp":
                self._notify_via_whatsapp(notification, response_files)
            elif channel == "slack":
                self._notify_via_slack(notification, response_files)
            elif channel == "email":
                self._notify_via_email(task, notification, response_files)
            elif channel == "log":
                self._log(f"[RESULT] {task['title']}: {response_text[:200]}")
            else:
                self._log(f"Unknown notification channel: {channel}")

    def _notify_via_whatsapp(self, text: str, files: list = None):
        """Send notification to user via WhatsApp."""
        try:
            from src.workflows.node_registry import get_running_instance
            wa_node = get_running_instance("WhatsAppWebNode")
            if not wa_node or not getattr(wa_node, '_connected', False):
                self._log("WhatsApp not connected — notification logged only")
                return
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
            self._log("Task notification sent to WhatsApp")
        except ImportError:
            self._log("neonize not available — WhatsApp notification skipped")
        except Exception as exc:
            self._log(f"WhatsApp notification failed: {exc}")

    def _notify_via_slack(self, text: str, files: list = None):
        """Send notification to user via Slack."""
        try:
            from src.workflows.node_registry import get_running_instance
            slack_node = get_running_instance("SlackNode")
            if not slack_node or not getattr(slack_node, '_connected', False):
                self._log("Slack not connected — notification logged only")
                return
            slack_node.send_notification(text, files)
            self._log("Task notification sent to Slack")
        except Exception as exc:
            self._log(f"Slack notification failed: {exc}")

    def _notify_via_email(self, task: dict, text: str, files: list = None):
        """Send notification via EmailNode."""
        try:
            from src.workflows.node_registry import get_running_instance
            email_node = get_running_instance("EmailNode")
            if not email_node or not hasattr(email_node, 'send_email'):
                self._log("EmailNode not available — email notification skipped")
                return
            target = task.get("notify_target", "")
            if not target:
                # Send to self (the configured Gmail address)
                target = email_node._get_prop("gmail_address")
            if not target:
                self._log("No email target configured")
                return
            email_node.send_email(
                to=target,
                subject=f"Task: {task['title']}",
                body=text,
                attachments=files,
            )
            self._log(f"Task notification emailed to {target}")
        except Exception as exc:
            self._log(f"Email notification failed: {exc}")

    # -- Discovery ----------------------------------------------------------

    def _find_master_agent(self):
        """Discover a running MasterAgentNode."""
        try:
            from src.workflows.node_registry import get_running_instance
            master = get_running_instance("MasterAgentNode")
            if master and hasattr(master, "process_external_message"):
                return master
        except Exception:
            pass
        return None

    # -- Stop ---------------------------------------------------------------

    def _stop_node(self):
        """Clean up and close."""
        self._stop_event.set()
        self._log("Stopping Task Tracker...")

        try:
            from src.workflows.node_registry import unregister_running_instance
            unregister_running_instance("TaskTrackerNode")
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
        """Create a tkinter monitor window with task list and log."""
        try:
            import tkinter as tk
            from tkinter import ttk, scrolledtext
        except ImportError:
            return

        if self._monitor_window:
            return

        self._monitor_window = tk.Toplevel()
        self._monitor_window.title("Task Tracker")
        self._monitor_window.geometry("800x550")
        self._monitor_window.minsize(600, 400)
        self._monitor_window.protocol("WM_DELETE_WINDOW", self._stop_node)

        self._monitor_window.grid_rowconfigure(1, weight=1)
        self._monitor_window.grid_columnconfigure(0, weight=1)

        # -- Status frame --
        status_frame = ttk.LabelFrame(self._monitor_window, text="Status")
        status_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="Initializing...")
        ttk.Label(status_frame, text="Status:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(
            status_frame, textvariable=self._status_var,
            font=("Helvetica", 10, "bold")
        ).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # -- PanedWindow: task list (top) + log (bottom) --
        paned = ttk.PanedWindow(self._monitor_window, orient=tk.VERTICAL)
        paned.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Task list frame
        task_frame = ttk.LabelFrame(paned, text="Active Tasks")
        paned.add(task_frame, weight=1)
        task_frame.grid_rowconfigure(0, weight=1)
        task_frame.grid_columnconfigure(0, weight=1)

        columns = ("title", "schedule", "next_run", "notify", "priority", "status")
        self._task_tree = ttk.Treeview(
            task_frame, columns=columns, show="headings", height=8
        )
        self._task_tree.heading("title", text="Title")
        self._task_tree.heading("schedule", text="Schedule")
        self._task_tree.heading("next_run", text="Next Run")
        self._task_tree.heading("notify", text="Notify Via")
        self._task_tree.heading("priority", text="Priority")
        self._task_tree.heading("status", text="Status")

        self._task_tree.column("title", width=200)
        self._task_tree.column("schedule", width=120)
        self._task_tree.column("next_run", width=140)
        self._task_tree.column("notify", width=80)
        self._task_tree.column("priority", width=70)
        self._task_tree.column("status", width=70)

        tree_scroll = ttk.Scrollbar(task_frame, orient=tk.VERTICAL,
                                    command=self._task_tree.yview)
        self._task_tree.configure(yscrollcommand=tree_scroll.set)
        self._task_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

        # Log frame
        log_frame = ttk.LabelFrame(paned, text="Activity Log")
        paned.add(log_frame, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="#d4d4d4"
        )
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        # Populate task list
        self._refresh_task_list()

    def _refresh_task_list(self):
        """Refresh the task Treeview with current database contents."""
        if not self._task_tree or not self._monitor_window:
            return
        try:
            self._monitor_window.after(0, self._do_refresh_task_list)
        except Exception:
            pass

    def _do_refresh_task_list(self):
        """Actually refresh the Treeview (must run on main thread)."""
        if not self._task_tree:
            return
        try:
            for item in self._task_tree.get_children():
                self._task_tree.delete(item)

            tasks = self.list_tasks()
            for t in tasks:
                schedule = f"{t['schedule_type']} {t['schedule_value']}"
                next_run = t.get("next_run", "")
                if next_run:
                    try:
                        dt = datetime.fromisoformat(next_run)
                        next_run = dt.strftime("%m/%d %I:%M %p")
                    except ValueError:
                        pass
                self._task_tree.insert("", "end", iid=t["id"], values=(
                    t["title"], schedule, next_run,
                    t["notify_via"], t["priority"], t["status"]
                ))

            # Update status
            active = sum(1 for t in tasks if t["status"] == "active")
            self._update_status(f"Running — {active} active tasks")
        except Exception:
            pass

    def _update_status(self, text: str):
        """Update the status label."""
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

    @staticmethod
    def _parse_int(value, default: int) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _log(self, message: str):
        """Thread-safe logging to console and monitor widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        logger.info(message)
        print(f"[TaskTracker] {entry}")

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

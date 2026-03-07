# nodes/calendar_node.py
"""CalendarNode — Google Calendar integration via OAuth2.

Provides read/create/update/delete access to Google Calendar events.
A background thread checks for upcoming events and sends proactive
alerts to the user via WhatsApp or other channels.

Requires: google-api-python-client, google-auth-oauthlib, google-auth-httplib2
Install:  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

One-time setup:
1. Create a Google Cloud project at https://console.cloud.google.com
2. Enable the Google Calendar API
3. Create OAuth2 credentials (Desktop app) and download credentials.json
4. Place credentials.json in the data/ folder
5. First run will open a browser for consent — token is saved locally
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base_node import BaseNode
from src.workflows.node_registry import register_node

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_DIR = "data"
DEFAULT_CREDENTIALS_PATH = os.path.join(DATA_DIR, "client_secret_google.json")
DEFAULT_TOKEN_PATH = os.path.join(DATA_DIR, "calendar_token.json")
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
DEFAULT_ALERT_MINUTES = 15
DEFAULT_ALERT_CHECK_INTERVAL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# The Node
# ---------------------------------------------------------------------------
@register_node("CalendarNode")
class CalendarNode(BaseNode):
    """Google Calendar integration via OAuth2. Add this node to a workflow
    to give the agent the ability to read, create, update, and delete
    calendar events. Proactive alerts notify you of upcoming events."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self._alert_thread: Optional[threading.Thread] = None
        self._service = None  # Google Calendar API service
        self._tasks_service = None  # Google Tasks API service
        self._connected = False
        self._log_messages: List[str] = []
        self._log_lock = threading.Lock()
        self._monitor_window = None
        self._status_var = None
        self._log_text = None
        # Track events we've already alerted about (to avoid duplicates)
        self._alerted_event_ids: set = set()

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
                "default": "CalendarNode",
            },
            "description": {
                "type": "text",
                "label": "Description",
                "default": (
                    "Google Calendar integration via OAuth2. Reads, creates, "
                    "updates, and deletes calendar events. Sends proactive "
                    "alerts for upcoming events."
                ),
            },
            "credentials_path": {
                "type": "text",
                "label": "OAuth2 Credentials Path",
                "default": DEFAULT_CREDENTIALS_PATH,
                "description": (
                    "Path to the Google OAuth2 credentials.json file. "
                    "Download from Google Cloud Console."
                ),
            },
            "calendar_id": {
                "type": "text",
                "label": "Calendar ID(s)",
                "default": "primary",
                "description": (
                    "Comma-separated list of calendars to use. Can be display names "
                    "or full IDs. Example: 'AIAssistant, primary, Work'. "
                    "The first calendar is the default for creating events."
                ),
            },
            "alert_minutes_before": {
                "type": "text",
                "label": "Alert Lead Time (minutes)",
                "default": "15",
                "description": "How many minutes before an event to send an alert.",
            },
            "alert_check_interval": {
                "type": "text",
                "label": "Alert Check Interval (seconds)",
                "default": "300",
                "description": "How often to check for upcoming events.",
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
                "description": "Keeps the calendar connection alive for proactive alerts.",
            },
        })
        return props

    # -- process (main entry point) -----------------------------------------

    def process(self, inputs):
        """Called by the workflow engine. Authenticates with Google Calendar,
        starts the alert thread, opens monitor window, then blocks."""
        self.inputs = inputs
        self._stop_event.clear()

        workflow_stop_event = inputs.get("stop_event") if isinstance(inputs, dict) else None

        # Register so other nodes can discover us
        try:
            from src.workflows.node_registry import register_running_instance
            register_running_instance("CalendarNode", self)
        except Exception:
            pass

        # Create monitor window
        try:
            self._create_monitor_window()
        except Exception as exc:
            self._log(f"Monitor window error: {exc}")

        # Authenticate
        if self._authenticate():
            self._connected = True
            self._update_status("Connected to Google Calendar")

            # Start alert thread
            interval = self._parse_int(
                self._get_prop("alert_check_interval"),
                DEFAULT_ALERT_CHECK_INTERVAL
            )
            self._alert_thread = threading.Thread(
                target=self._alert_loop,
                args=(interval,),
                daemon=True,
                name="calendar-alerts",
            )
            self._alert_thread.start()
            self._log(f"Calendar alert thread started (interval={interval}s)")
        else:
            self._update_status("Not connected — check credentials")

        # Block — keep node alive
        self._log("Calendar node running.")
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

    # -- Authentication -----------------------------------------------------

    def _authenticate(self) -> bool:
        """Authenticate with Google Calendar API using OAuth2."""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError:
            self._log(
                "ERROR: Google API packages not installed. Run:\n"
                "  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
            )
            return False

        creds_path = self._get_prop("credentials_path") or DEFAULT_CREDENTIALS_PATH
        token_path = DEFAULT_TOKEN_PATH

        # Auto-discover credentials file if configured path doesn't exist
        if not os.path.exists(creds_path):
            candidates = [
                DEFAULT_CREDENTIALS_PATH,
                os.path.join(DATA_DIR, "credentials.json"),
                os.path.join(DATA_DIR, "client_secret_google.json"),
            ]
            # Also check for any client_secret*.json in data/
            if os.path.isdir(DATA_DIR):
                for f in os.listdir(DATA_DIR):
                    if f.startswith("client_secret") and f.endswith(".json"):
                        candidates.append(os.path.join(DATA_DIR, f))
            found = None
            for candidate in candidates:
                if os.path.exists(candidate):
                    found = candidate
                    break
            if found:
                self._log(f"Credentials auto-discovered at {found}")
                creds_path = found
            else:
                self._log(
                    f"ERROR: Google OAuth credentials not found.\n"
                    f"Checked: {creds_path}\n"
                    "Download from Google Cloud Console > APIs & Services > Credentials\n"
                    "and place in the data/ folder."
                )
                return False

        creds = None

        # Load existing token
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                self._log("Loaded existing calendar token")
            except Exception as exc:
                self._log(f"Token load error: {exc}")

        # Refresh or get new token
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._log("Calendar token refreshed")
                except Exception as exc:
                    self._log(f"Token refresh failed: {exc}")
                    creds = None

            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        creds_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    self._log("Calendar OAuth2 consent completed")
                except Exception as exc:
                    self._log(f"OAuth2 flow error: {exc}")
                    return False

            # Save token for next time
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                self._log(f"Token saved to {token_path}")
            except Exception as exc:
                self._log(f"Token save error: {exc}")

        # Build the services
        try:
            self._service = build("calendar", "v3", credentials=creds)
            self._log("Google Calendar API service created")
        except Exception as exc:
            self._log(f"Calendar service build error: {exc}")
            return False

        try:
            self._tasks_service = build("tasks", "v1", credentials=creds)
            self._log("Google Tasks API service created")
        except Exception as exc:
            self._log(f"Tasks service build warning: {exc} (tasks will be unavailable)")

        # Resolve calendar_id(s) — supports comma-separated list of names/IDs
        cal_id_raw = self._get_prop("calendar_id") or "primary"
        self._log(f"Calendar ID property value: '{cal_id_raw}'")
        cal_names = [c.strip() for c in cal_id_raw.split(",") if c.strip()]
        self._log(f"Parsed calendar names: {cal_names}")
        if not cal_names:
            cal_names = ["primary"]

        # Fetch the full calendar list once for resolution
        cal_list_items = []
        try:
            cal_list = self._service.calendarList().list().execute()
            cal_list_items = cal_list.get("items", [])
            self._log(
                f"Available Google calendars ({len(cal_list_items)}): "
                + " | ".join(
                    f"'{e.get('summary', '?')}' (id={e.get('id', '?')[:40]}...)"
                    for e in cal_list_items
                )
            )
        except Exception as exc:
            self._log(f"Calendar list lookup error: {exc}")

        # Build resolved calendars dict: display_name -> real_id
        self._resolved_calendars = {}  # ordered dict (insertion order)
        for name in cal_names:
            if name == "primary" or "@" in name:
                # Already a real ID or 'primary'
                display = name
                if name != "primary":
                    # Try to find display name for this ID
                    for entry in cal_list_items:
                        if entry.get("id", "").lower() == name.lower():
                            display = entry.get("summary", name)
                            break
                self._resolved_calendars[display] = name
                self._log(f"Calendar added: {display} ({name})")
            else:
                # Looks like a display name — resolve it
                found = False
                for entry in cal_list_items:
                    if (entry.get("summary", "").lower() == name.lower()
                            or entry.get("id", "").lower() == name.lower()):
                        resolved_id = entry["id"]
                        display = entry.get("summary", name)
                        self._resolved_calendars[display] = resolved_id
                        self._log(f"Resolved calendar '{name}' -> {resolved_id}")
                        found = True
                        break
                if not found:
                    self._log(
                        f"WARNING: Calendar '{name}' not found. "
                        f"Available: {', '.join(e.get('summary', '?') for e in cal_list_items)}"
                    )

        # Fallback if nothing resolved
        if not self._resolved_calendars:
            self._resolved_calendars["primary"] = "primary"
            self._log("No calendars resolved — falling back to primary.")

        # Keep backward-compatible single ID (first calendar = default)
        first_name = next(iter(self._resolved_calendars))
        self._resolved_calendar_id = self._resolved_calendars[first_name]
        self._log(
            f"Active calendars ({len(self._resolved_calendars)}): "
            + ", ".join(self._resolved_calendars.keys())
        )

        return True

    # -- Multi-calendar helpers -----------------------------------------------

    def _get_calendar_id(self, calendar_name: str = None) -> str:
        """Resolve a calendar display name to its real ID.

        If calendar_name is None or empty, returns the default (first) calendar.
        Accepts display names, real IDs, or 'primary'.
        """
        calendars = getattr(self, '_resolved_calendars', {})
        if not calendar_name:
            return getattr(self, '_resolved_calendar_id', None) or "primary"

        # Exact match by display name
        for name, cid in calendars.items():
            if name.lower() == calendar_name.lower():
                return cid
        # Exact match by ID
        for name, cid in calendars.items():
            if cid.lower() == calendar_name.lower():
                return cid
        # Partial match by display name
        for name, cid in calendars.items():
            if calendar_name.lower() in name.lower():
                return cid

        # Not found in resolved list — return as-is (might be a raw ID)
        self._log(f"Calendar '{calendar_name}' not in resolved list, using as-is")
        return calendar_name

    def get_calendar_names(self) -> List[str]:
        """Return the list of active calendar display names."""
        return list(getattr(self, '_resolved_calendars', {}).keys())

    # -- Calendar API methods (public) --------------------------------------

    def get_events(self, start: datetime = None, end: datetime = None,
                   max_results: int = 20, calendar: str = None) -> List[dict]:
        """Get events from one or all calendars within a date range.

        Parameters:
            start: Start of range (default: now)
            end: End of range (default: 7 days from now)
            max_results: Maximum events to return
            calendar: Specific calendar name to query (None = all calendars)

        Returns list of event dicts with keys:
            id, summary, start, end, location, description, attendees, calendar_name
        """
        if not self._service:
            self._log("Calendar not connected")
            return []

        if not start:
            start = datetime.now()
        if not end:
            end = start + timedelta(days=7)

        # Convert naive local datetimes to timezone-aware so the API
        # interprets them correctly (previously "Z" was appended which
        # told Google the local time was UTC, causing wrong results).
        if start.tzinfo is None:
            start = start.astimezone()  # attach local timezone
        if end.tzinfo is None:
            end = end.astimezone()
        time_min = start.isoformat()
        time_max = end.isoformat()

        # Determine which calendars to query
        calendars = getattr(self, '_resolved_calendars', {})
        if calendar:
            # Query a specific calendar
            cal_id = self._get_calendar_id(calendar)
            targets = {calendar: cal_id}
        elif len(calendars) > 1:
            # Query all calendars
            targets = calendars
        else:
            # Single calendar (backward compatible)
            cal_id = getattr(self, '_resolved_calendar_id', None) or "primary"
            targets = {next(iter(calendars), "primary"): cal_id}

        all_events = []
        for cal_name, cal_id in targets.items():
            try:
                events_result = self._service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                for e in events_result.get("items", []):
                    parsed = self._parse_event(e)
                    parsed["calendar_name"] = cal_name
                    parsed["calendar_id"] = cal_id
                    all_events.append(parsed)

            except Exception as exc:
                self._log(f"Error fetching events from '{cal_name}': {exc}")

        # Sort merged events by start time
        all_events.sort(key=lambda e: e.get("start_dt") or datetime.max)

        # Trim to max_results
        return all_events[:max_results]

    def create_event(self, event_dict: dict) -> Optional[dict]:
        """Create a new calendar event.

        Required keys: summary, start, end
        Optional: description, location, attendees, recurrence,
                  google_meet (bool), all_day (bool), calendar (str)

        start/end can be datetime objects or ISO strings.
        recurrence: RRULE string (e.g. "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR")
                    or list of RRULE strings.
        calendar: Display name of target calendar (default = first configured).
        Returns the created event dict or None on failure.
        """
        if not self._service:
            self._log("Calendar not connected")
            return None

        calendar_id = self._get_calendar_id(event_dict.get("calendar"))

        body = {
            "summary": event_dict.get("summary", "Untitled Event"),
        }

        # Handle start/end times
        start = event_dict.get("start")
        end = event_dict.get("end")
        all_day = event_dict.get("all_day", False)

        if all_day:
            # All-day events use date (not dateTime)
            if isinstance(start, datetime):
                body["start"] = {"date": start.strftime("%Y-%m-%d")}
            elif isinstance(start, str):
                body["start"] = {"date": start[:10]}  # Take YYYY-MM-DD
            if isinstance(end, datetime):
                body["end"] = {"date": end.strftime("%Y-%m-%d")}
            elif isinstance(end, str):
                body["end"] = {"date": end[:10]}
        else:
            if isinstance(start, datetime):
                body["start"] = {"dateTime": start.isoformat(), "timeZone": "America/Denver"}
            elif isinstance(start, str):
                body["start"] = {"dateTime": start, "timeZone": "America/Denver"}

            if isinstance(end, datetime):
                body["end"] = {"dateTime": end.isoformat(), "timeZone": "America/Denver"}
            elif isinstance(end, str):
                body["end"] = {"dateTime": end, "timeZone": "America/Denver"}

        if event_dict.get("description"):
            body["description"] = event_dict["description"]
        if event_dict.get("location"):
            body["location"] = event_dict["location"]
        if event_dict.get("attendees"):
            body["attendees"] = [
                {"email": a} if isinstance(a, str) else a
                for a in event_dict["attendees"]
            ]

        # Recurrence (RRULE)
        recurrence = event_dict.get("recurrence")
        if recurrence:
            if isinstance(recurrence, str):
                recurrence = [recurrence]
            body["recurrence"] = recurrence

        # Google Meet
        if event_dict.get("google_meet"):
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

        try:
            # conferenceDataVersion=1 is required when creating Google Meet
            conf_version = 1 if event_dict.get("google_meet") else 0
            event = self._service.events().insert(
                calendarId=calendar_id, body=body,
                conferenceDataVersion=conf_version,
            ).execute()
            self._log(f"Event created: {body['summary']}")
            return self._parse_event(event)
        except Exception as exc:
            self._log(f"Error creating event: {exc}")
            traceback.print_exc()
            return None

    def add_attendees(self, event_id: str, attendee_emails: List[str],
                      calendar: str = None) -> Optional[dict]:
        """Add attendees to an existing event without removing existing ones."""
        if not self._service:
            return None

        calendar_id = self._get_calendar_id(calendar)

        try:
            event = self._service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            existing = event.get("attendees", [])
            existing_emails = {a.get("email", "").lower() for a in existing}

            for email in attendee_emails:
                if email.lower() not in existing_emails:
                    existing.append({"email": email})

            event["attendees"] = existing

            updated = self._service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event,
                sendUpdates="all",
            ).execute()
            self._log(f"Attendees added to: {updated.get('summary', event_id)}")
            return self._parse_event(updated)
        except Exception as exc:
            self._log(f"Error adding attendees: {exc}")
            return None

    def add_google_meet(self, event_id: str, calendar: str = None) -> Optional[dict]:
        """Add a Google Meet link to an existing event."""
        if not self._service:
            return None

        calendar_id = self._get_calendar_id(calendar)

        try:
            event = self._service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            event["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet-{event_id[:8]}-{datetime.now().strftime('%H%M%S')}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

            updated = self._service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event,
                conferenceDataVersion=1,
            ).execute()
            meet_link = updated.get("hangoutLink", "")
            self._log(f"Google Meet added to: {updated.get('summary', event_id)} — {meet_link}")
            return self._parse_event(updated)
        except Exception as exc:
            self._log(f"Error adding Google Meet: {exc}")
            return None

    def search_events(self, query: str, days_ahead: int = 30,
                      max_results: int = 10, calendar: str = None) -> List[dict]:
        """Search for events by text query within a date range across all calendars."""
        if not self._service:
            return []

        now = datetime.now()
        end = now + timedelta(days=days_ahead)
        time_min = now.isoformat() + "Z" if now.tzinfo is None else now.isoformat()
        time_max = end.isoformat() + "Z" if end.tzinfo is None else end.isoformat()

        calendars = getattr(self, '_resolved_calendars', {})
        if calendar:
            targets = {calendar: self._get_calendar_id(calendar)}
        else:
            targets = calendars if calendars else {"primary": "primary"}

        all_results = []
        for cal_name, cal_id in targets.items():
            try:
                result = self._service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    q=query,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                for e in result.get("items", []):
                    parsed = self._parse_event(e)
                    parsed["calendar_name"] = cal_name
                    parsed["calendar_id"] = cal_id
                    all_results.append(parsed)
            except Exception as exc:
                self._log(f"Error searching events in '{cal_name}': {exc}")

        all_results.sort(key=lambda e: e.get("start_dt") or datetime.max)
        return all_results[:max_results]

    def update_event(self, event_id: str, updates: dict,
                     calendar: str = None) -> Optional[dict]:
        """Update an existing calendar event.

        updates can include: summary, start, end, description, location,
                             recurrence (list of RRULE strings),
                             attendees (list of email strings)
        calendar: Display name of target calendar (auto-detected from event if None).
        Returns the updated event dict or None on failure.
        """
        if not self._service:
            return None

        calendar_id = self._get_calendar_id(calendar)

        try:
            # Fetch existing event
            event = self._service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            if "summary" in updates:
                event["summary"] = updates["summary"]
            if "description" in updates:
                event["description"] = updates["description"]
            if "location" in updates:
                event["location"] = updates["location"]
            if "start" in updates:
                start = updates["start"]
                if isinstance(start, datetime):
                    event["start"] = {"dateTime": start.isoformat(), "timeZone": "America/Denver"}
                elif isinstance(start, str):
                    event["start"] = {"dateTime": start, "timeZone": "America/Denver"}
            if "end" in updates:
                end = updates["end"]
                if isinstance(end, datetime):
                    event["end"] = {"dateTime": end.isoformat(), "timeZone": "America/Denver"}
                elif isinstance(end, str):
                    event["end"] = {"dateTime": end, "timeZone": "America/Denver"}
            if "recurrence" in updates:
                event["recurrence"] = updates["recurrence"]
            if "attendees" in updates:
                existing = event.get("attendees", [])
                existing_emails = {a.get("email", "").lower() for a in existing}
                for email in updates["attendees"]:
                    if isinstance(email, str) and email.lower() not in existing_emails:
                        existing.append({"email": email})
                event["attendees"] = existing

            updated = self._service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event
            ).execute()
            self._log(f"Event updated: {updated.get('summary', event_id)}")
            return self._parse_event(updated)

        except Exception as exc:
            self._log(f"Error updating event: {exc}")
            traceback.print_exc()
            return None

    def delete_event(self, event_id: str, calendar: str = None) -> bool:
        """Delete a calendar event. Returns True on success."""
        if not self._service:
            return False

        calendar_id = self._get_calendar_id(calendar)

        try:
            self._service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            self._log(f"Event deleted: {event_id}")
            return True
        except Exception as exc:
            self._log(f"Error deleting event: {exc}")
            return False

    def get_events_summary(self, days: int = 1, start_date: datetime = None) -> str:
        """Return a human-readable summary of events for N days.

        Parameters:
            days: Number of days to cover (default 1).
            start_date: Specific start date. If None, defaults to now.
                        When a specific date is given, the range covers
                        midnight-to-midnight for `days` days.
        """
        if start_date:
            # Query from start of that day to end of the range
            start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=days)
        else:
            start = datetime.now()
            end = start + timedelta(days=days)
        events = self.get_events(start=start, end=end)

        if not events:
            if start_date:
                period = start_date.strftime("%A, %B %d")
                if days > 1:
                    end_display = (start_date + timedelta(days=days - 1)).strftime("%A, %B %d")
                    period = f"{period} through {end_display}"
            else:
                period = "today" if days == 1 else f"the next {days} days"
            return f"No events on your calendar for {period}."

        multi_cal = len(getattr(self, '_resolved_calendars', {})) > 1
        lines = []
        current_date = None
        for ev in events:
            ev_start = ev.get("start_dt")
            if ev_start:
                ev_date = ev_start.strftime("%A, %B %d")
                if ev_date != current_date:
                    current_date = ev_date
                    lines.append(f"\n{ev_date}:")
                time_str = ev_start.strftime("%I:%M %p")
                end_dt = ev.get("end_dt")
                end_str = end_dt.strftime("%I:%M %p") if end_dt else ""
                cal_tag = f" [{ev.get('calendar_name', '')}]" if multi_cal and ev.get("calendar_name") else ""
                lines.append(
                    f"  {time_str}–{end_str}  {ev['summary']}{cal_tag}"
                    + (f" ({ev['location']})" if ev.get("location") else "")
                )
            else:
                cal_tag = f" [{ev.get('calendar_name', '')}]" if multi_cal and ev.get("calendar_name") else ""
                lines.append(f"  {ev['summary']}{cal_tag} (all day)")

        return f"Calendar ({len(events)} events):" + "\n".join(lines)

    # -- Proactive alerts ---------------------------------------------------

    def _alert_loop(self, interval: int):
        """Background thread: check for upcoming events and send alerts."""
        self._log("Alert loop started")
        while not self._stop_event.is_set():
            try:
                self._check_upcoming_events()
            except Exception as exc:
                self._log(f"Alert check error: {exc}")
                traceback.print_exc()

            for _ in range(interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _check_upcoming_events(self):
        """Check for events starting within the alert window."""
        alert_minutes = self._parse_int(
            self._get_prop("alert_minutes_before"), DEFAULT_ALERT_MINUTES
        )
        now = datetime.now()
        window_end = now + timedelta(minutes=alert_minutes)

        events = self.get_events(start=now, end=window_end)

        for ev in events:
            event_id = ev.get("id")
            if not event_id or event_id in self._alerted_event_ids:
                continue

            self._alerted_event_ids.add(event_id)

            # Build alert message
            start_dt = ev.get("start_dt")
            if start_dt:
                minutes_until = int((start_dt - now).total_seconds() / 60)
                # Skip events that have already started
                if minutes_until < 0:
                    continue
                time_str = start_dt.strftime("%I:%M %p")
                if minutes_until <= 1:
                    time_label = f"Starting now at {time_str}"
                else:
                    time_label = f"Starting in {minutes_until} minutes at {time_str}"
                alert = (
                    f"Calendar Reminder: {ev['summary']}\n"
                    f"{time_label}"
                )
                if ev.get("location"):
                    alert += f"\nLocation: {ev['location']}"
                if ev.get("description"):
                    alert += f"\n{ev['description'][:200]}"
            else:
                alert = f"Calendar Reminder: {ev['summary']} (starting soon)"

            self._log(f"Alert: {ev['summary']}")

            # Notify via WhatsApp
            self._notify_user(alert)

            # Also notify MasterAgent
            master = self._find_master_agent()
            if master:
                try:
                    master.process_external_message(alert, sender="Calendar")
                except Exception:
                    pass

    def _notify_user(self, text: str):
        """Send alert to user via WhatsApp and Slack."""
        # WhatsApp
        try:
            from src.workflows.node_registry import get_running_instance
            wa_node = get_running_instance("WhatsAppWebNode")
            if wa_node and getattr(wa_node, '_connected', False):
                my_jid = getattr(wa_node, '_my_jid', None)
                if my_jid:
                    from neonize.utils import build_jid
                    chat_jid = build_jid(my_jid)
                    wa_node._send_wa_text(chat_jid, text)
        except ImportError:
            pass
        except Exception as exc:
            self._log(f"WhatsApp alert failed: {exc}")
        # Slack
        try:
            from src.workflows.node_registry import get_running_instance
            slack_node = get_running_instance("SlackNode")
            if slack_node and getattr(slack_node, '_connected', False):
                slack_node.send_notification(text)
        except Exception as exc:
            self._log(f"Slack alert failed: {exc}")

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _parse_event(event: dict) -> dict:
        """Parse a Google Calendar API event into a simplified dict."""
        start_raw = event.get("start", {})
        end_raw = event.get("end", {})

        start_str = start_raw.get("dateTime") or start_raw.get("date", "")
        end_str = end_raw.get("dateTime") or end_raw.get("date", "")

        start_dt = None
        end_dt = None
        try:
            if "T" in start_str:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_dt.tzinfo is not None:
                    start_dt = start_dt.astimezone().replace(tzinfo=None)
            else:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d") if start_str else None
        except ValueError:
            pass
        try:
            if "T" in end_str:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if end_dt.tzinfo is not None:
                    end_dt = end_dt.astimezone().replace(tzinfo=None)
            else:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d") if end_str else None
        except ValueError:
            pass

        attendees = event.get("attendees", [])
        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]

        # Google Meet link
        meet_link = event.get("hangoutLink", "")
        if not meet_link:
            conf_data = event.get("conferenceData", {})
            for ep in conf_data.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break

        return {
            "id": event.get("id", ""),
            "summary": event.get("summary", "(no title)"),
            "start": start_str,
            "end": end_str,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "attendees": attendee_emails,
            "html_link": event.get("htmlLink", ""),
            "meet_link": meet_link,
            "recurrence": event.get("recurrence", []),
        }

    # -- Google Tasks API methods ---------------------------------------------

    def _get_default_task_list_id(self) -> Optional[str]:
        """Get the ID of the default (first) task list."""
        if not self._tasks_service:
            return None
        try:
            result = self._tasks_service.tasklists().list(maxResults=1).execute()
            items = result.get("items", [])
            return items[0]["id"] if items else None
        except Exception as exc:
            self._log(f"Error getting task lists: {exc}")
            return None

    def list_tasks(self, show_completed: bool = False,
                   max_results: int = 50) -> List[dict]:
        """List tasks from the default task list."""
        if not self._tasks_service:
            self._log("Tasks service not available")
            return []

        tl_id = self._get_default_task_list_id()
        if not tl_id:
            return []

        try:
            result = self._tasks_service.tasks().list(
                tasklist=tl_id,
                maxResults=max_results,
                showCompleted=show_completed,
                showHidden=show_completed,
            ).execute()
            tasks = result.get("items", [])
            return [
                {
                    "id": t.get("id", ""),
                    "title": t.get("title", "(no title)"),
                    "notes": t.get("notes", ""),
                    "due": t.get("due", ""),
                    "status": t.get("status", "needsAction"),
                    "completed": t.get("completed", ""),
                }
                for t in tasks if t.get("title", "").strip()
            ]
        except Exception as exc:
            self._log(f"Error listing tasks: {exc}")
            return []

    def add_task(self, title: str, notes: str = "", due: str = "") -> Optional[dict]:
        """Add a new task to the default task list.

        Parameters:
            title: Task title
            notes: Optional notes/description
            due: Optional due date as ISO string (YYYY-MM-DD or full ISO)
        """
        if not self._tasks_service:
            self._log("Tasks service not available")
            return None

        tl_id = self._get_default_task_list_id()
        if not tl_id:
            return None

        body = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            # Google Tasks API expects RFC 3339 date
            if len(due) == 10:  # YYYY-MM-DD
                due += "T00:00:00.000Z"
            body["due"] = due

        try:
            task = self._tasks_service.tasks().insert(
                tasklist=tl_id, body=body
            ).execute()
            self._log(f"Task added: {title}")
            return {
                "id": task.get("id", ""),
                "title": task.get("title", ""),
                "notes": task.get("notes", ""),
                "due": task.get("due", ""),
                "status": task.get("status", "needsAction"),
            }
        except Exception as exc:
            self._log(f"Error adding task: {exc}")
            return None

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed."""
        if not self._tasks_service:
            return False

        tl_id = self._get_default_task_list_id()
        if not tl_id:
            return False

        try:
            task = self._tasks_service.tasks().get(
                tasklist=tl_id, task=task_id
            ).execute()
            task["status"] = "completed"
            self._tasks_service.tasks().update(
                tasklist=tl_id, task=task_id, body=task
            ).execute()
            self._log(f"Task completed: {task.get('title', task_id)}")
            return True
        except Exception as exc:
            self._log(f"Error completing task: {exc}")
            return False

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        if not self._tasks_service:
            return False

        tl_id = self._get_default_task_list_id()
        if not tl_id:
            return False

        try:
            self._tasks_service.tasks().delete(
                tasklist=tl_id, task=task_id
            ).execute()
            self._log(f"Task deleted: {task_id}")
            return True
        except Exception as exc:
            self._log(f"Error deleting task: {exc}")
            return False

    def get_tasks_summary(self) -> str:
        """Return a human-readable summary of current tasks."""
        tasks = self.list_tasks(show_completed=False)
        if not tasks:
            return "No tasks on your task list."

        lines = [f"Tasks ({len(tasks)} items):"]
        for t in tasks:
            status = "✅" if t["status"] == "completed" else "⬜"
            due_str = ""
            if t.get("due"):
                try:
                    due_dt = datetime.fromisoformat(t["due"].replace("Z", "+00:00"))
                    due_str = f" (due {due_dt.strftime('%b %d')})"
                except ValueError:
                    due_str = f" (due {t['due'][:10]})"
            lines.append(f"  {status} {t['title']}{due_str}")
            if t.get("notes"):
                lines.append(f"      {t['notes'][:100]}")
        return "\n".join(lines)

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
        self._log("Stopping Calendar node...")

        try:
            from src.workflows.node_registry import unregister_running_instance
            unregister_running_instance("CalendarNode")
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
        self._monitor_window.title("Calendar Node — Google Calendar")
        self._monitor_window.geometry("650x400")
        self._monitor_window.minsize(450, 300)
        self._monitor_window.protocol("WM_DELETE_WINDOW", self._stop_node)

        self._monitor_window.grid_rowconfigure(1, weight=1)
        self._monitor_window.grid_columnconfigure(0, weight=1)

        # -- Status frame --
        status_frame = ttk.LabelFrame(self._monitor_window, text="Connection")
        status_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="Initializing...")
        ttk.Label(status_frame, text="Status:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(
            status_frame, textvariable=self._status_var,
            font=("Helvetica", 10, "bold")
        ).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        cal_display = ", ".join(getattr(self, '_resolved_calendars', {}).keys()) or self._get_prop("calendar_id") or "primary"
        ttk.Label(status_frame, text="Calendar(s):").grid(
            row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(status_frame, text=cal_display).grid(
            row=1, column=1, sticky="w", padx=5, pady=2)

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

    def _update_status(self, text: str):
        """Update the status label."""
        if self._status_var and self._monitor_window:
            try:
                self._monitor_window.after(0, lambda: self._status_var.set(text))
            except Exception:
                pass

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
        print(f"[CalendarNode] {entry}")

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

# WhatsApp Web Node — Setup Guide (Personal Account)

Connect your **personal WhatsApp account** to XeroFlow by scanning a QR code — no API keys, no business account, no Meta Developer setup needed.

---

## How It Works

The **WhatsAppWebNode** uses [neonize](https://github.com/krypton-byte/neonize), an open-source Python library built on [Whatsmeow](https://github.com/tulir/whatsmeow) (Go). It connects to WhatsApp Web the same way your browser does — by scanning a QR code with your phone.

Once connected, anyone who messages your WhatsApp number gets a response from the AI.

---

## Quick Start

### 1. Install Dependencies

```bash
pip install neonize qrcode Pillow
```

These are already in `requirements.txt` if you run the standard setup.

### 2. Add the Node to Your Workflow and Wire It

In the XeroFlow workflow editor:

1. Add a **WhatsAppWebNode** to the graph
2. Add a **MasterAgentNode** to the graph (if not already present)
3. **Wire them together** — draw a connection from WhatsAppWeb's `message` output to MasterAgent's `whatsapp_input` input

That's the only wire you need. Here's what the graph looks like:

```
┌──────────────────┐          ┌──────────────────────┐
│  WhatsAppWeb     │          │  MasterAgent         │
│                  │          │                      │
│  [response] ◄────┼──────────┼── [whatsapp_response]│
│                  │          │                      │
│    [message] ────┼──────────┼─► [whatsapp_input]   │
│                  │          │                      │
│      [files] ○   │          │   [output] ──► TeamLead
└──────────────────┘          └──────────────────────┘
```

**How the routing works:**
- The `message` → `whatsapp_input` wire tells the system these nodes are connected
- At runtime, WhatsApp automatically discovers the running MasterAgentNode and sends messages to it directly
- The Master Agent processes the message through its full chat pipeline (RAG lookup, AI call, delegation if needed)
- The response is sent back to WhatsApp automatically
- The Master Agent's `output` → TeamLead connection still works as before for delegation tasks

**You do NOT need to wire `whatsapp_response` back to `response`** — the WhatsApp node handles the return path internally. The connectors exist for visual clarity in the graph.

**Standalone mode:** If no MasterAgentNode is running, the WhatsApp node falls back to using its own configured API endpoint to generate responses directly.

### 3. Start the Workflow

When the workflow starts, the node will:
1. Open a **monitor window** showing connection status and message log
2. Print a **QR code in the terminal**
3. Wait for you to scan it

### 4. Scan the QR Code

On your phone:
1. Open **WhatsApp**
2. Go to **Settings** > **Linked Devices** > **Link a Device**
3. Scan the QR code shown in the terminal

That's it! You're connected.

### 5. Start Chatting

Send a message to your own WhatsApp number from another phone (or have someone message you). The AI will respond automatically.

---

## Node Properties

| Property | Default | Description |
|---|---|---|
| **Session Name** | `xeroflow_wa` | Name for the session database. Changing this creates a new session requiring a new QR scan. |
| **Allowed Numbers** | *(empty)* | Comma-separated phone numbers that can interact (e.g., `11234567890,447911123456`). Use `self` to only respond to your own self-chat. Empty = allow all. |
| **Bot Trigger Name** | *(empty)* | A name/keyword that external (non-self) messages must contain for the bot to respond (e.g., `Jarvis`). Case-insensitive. Self-chat always works regardless. Empty = respond to all allowed messages. |
| **Auto-Reply Mode** | `True` | Automatically forward messages to the AI and reply. |
| **Reply to Groups** | `False` | Whether to respond to messages in group chats. |

---

## Session Persistence

After the first QR scan, your session is saved to a SQLite database at:
```
nodes/whatsapp_sessions/{session_name}.sqlite3
```

On subsequent starts, the node **reconnects automatically** — no QR scan needed. The session stays valid as long as the linked device isn't removed from your phone.

To force a new QR scan, delete the session file and restart.

---

## Supported Message Types

### Receiving (from WhatsApp contacts)
- **Text messages** — forwarded to the AI as-is
- **Images** — downloaded locally, path available for processing
- **Documents** (PDF, Word, Excel, etc.) — downloaded locally
- **Audio/Voice notes** — downloaded locally
- **Video** — downloaded locally

### Sending (AI responses back to WhatsApp)
- **Text** — markdown converted to WhatsApp formatting (`*bold*`, `_italic_`, `~strikethrough~`, `` ```code``` ``)
- **Images, documents, audio, video** — can be sent via the `_send_wa_file()` method
- Long messages automatically split at WhatsApp's 4096-character limit

---

## Monitor Window

The monitor window shows:
- **Connection status** — Connecting / Connected / Disconnected
- **Session name** — which session database is in use
- **Message log** — real-time log of all incoming/outgoing messages
- **Send tab** — manually send a message to any phone number

---

## Comparison: WhatsApp Web Node vs WhatsApp Business Node

| Feature | WhatsApp Web Node | WhatsApp Business Node |
|---|---|---|
| **Account type** | Personal WhatsApp | Meta Business Account |
| **Setup** | Scan QR code | API keys + webhook + ngrok |
| **Cost** | Free | Free tier (limited) |
| **API keys needed** | No | Yes |
| **Library** | neonize (Whatsmeow) | Meta Cloud API (requests) |
| **File** | `whatsapp_web_node.py` | `whatsapp_integration_node.py` |
| **Best for** | Personal use, testing, small teams | Production, business bots |

---

## Troubleshooting

| Issue | Solution |
|---|---|
| No QR code appears | Make sure neonize is installed: `pip install neonize` |
| QR code expired | Restart the workflow to get a new QR code |
| "neonize is not installed" | Run `pip install neonize` in your venv |
| Session won't reconnect | Delete the session file in `nodes/whatsapp_sessions/` and re-scan |
| Messages not arriving | Check the "Allowed Numbers" property isn't blocking the sender |
| Group messages ignored | Enable "Reply to Group Messages" in node properties |
| Bot replies to itself | The node automatically skips messages from your own number |

---

## Security Notes

- The session database contains your WhatsApp encryption keys — **keep it secure**
- Use the `allowed_numbers` property to restrict who can interact with the bot
- The node skips messages from your own number to prevent reply loops
- Group replies are disabled by default to avoid spam

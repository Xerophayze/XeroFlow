# WhatsApp Integration Node — Setup Guide

This guide walks you through connecting the **WhatsAppIntegrationNode** to the Meta WhatsApp Business Cloud API so you can chat with your Master Agent via WhatsApp, including sending and receiving files.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Meta Developer Account** | Free at [developers.facebook.com](https://developers.facebook.com/) |
| **Meta Business Account** | Created during app setup (or use an existing one) |
| **Python packages** | `flask>=3.0.0` (added to `requirements.txt`) |
| **Public URL for webhook** | Use [ngrok](https://ngrok.com/) for testing, or a real domain in production |

---

## Step 1: Create a Meta (Facebook) App

1. Go to [Meta for Developers > My Apps](https://developers.facebook.com/apps/)
2. Click **Create App**
3. Select **Business** as the app type → **Next**
4. Fill in the app name (e.g., "XeroFlow WhatsApp") and email → **Create App**
5. In **Add products to your app**, find **WhatsApp** and click **Set Up**
6. Select (or create) a Meta Business Account → **Submit**

## Step 2: Get Your Credentials

1. In the left sidebar, expand **WhatsApp** → click **API Setup**
2. Copy these two values:
   - **Phone Number ID** — a numeric ID like `123456789012345`
   - **Temporary Access Token** — valid for 24 hours (see below for permanent token)

### Creating a Permanent Access Token

The temporary token expires after 24 hours. For production use:

1. Go to [Business Settings > System Users](https://business.facebook.com/settings/system-users)
2. Create a system user (Admin role)
3. Click **Generate New Token**
4. Select your WhatsApp app
5. Add these permissions:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
6. Generate and copy the token — **this is your permanent access token**

## Step 3: Configure the Node in XeroFlow

Add a **WhatsAppIntegrationNode** to your workflow and set these properties:

| Property | Value |
|---|---|
| **Phone Number ID** | Your WhatsApp Phone Number ID from Step 2 |
| **Access Token** | Your temporary or permanent access token |
| **Webhook Verify Token** | Any custom string (e.g., `xeroflow_whatsapp_verify`) — you'll use this same string in Meta's webhook config |
| **Webhook Port** | Default `5555` — the local port for the Flask webhook server |
| **Allowed Numbers** | Comma-separated phone numbers that can interact (leave empty to allow all) |
| **Auto-Reply Mode** | `True` — automatically forwards messages to the AI and replies |

## Step 4: Expose Your Webhook with ngrok

The WhatsApp Cloud API needs to reach your webhook server over HTTPS. For local development, use ngrok:

1. Install ngrok: [ngrok.com/download](https://ngrok.com/download)
2. Start the XeroFlow workflow (this starts the webhook server on port 5555)
3. In a separate terminal, run:
   ```
   ngrok http 5555
   ```
4. Copy the **HTTPS** forwarding URL (e.g., `https://abc123.ngrok-free.app`)

## Step 5: Configure the Webhook in Meta Dashboard

1. In Meta Developer Dashboard, go to **WhatsApp** → **Configuration**
2. Under **Webhook**, click **Edit**
3. Set:
   - **Callback URL**: `https://abc123.ngrok-free.app/webhook` (your ngrok URL + `/webhook`)
   - **Verify Token**: The same string you set in the node properties (e.g., `xeroflow_whatsapp_verify`)
4. Click **Verify and Save**
5. Under **Webhook fields**, subscribe to:
   - `messages` (required)
   - `message_deliveries` (optional — for delivery receipts)
   - `message_reads` (optional — for read receipts)

## Step 6: Add a Test Phone Number

If you're using Meta's test number (not a real business number):

1. Go to **WhatsApp** → **API Setup**
2. Under **To**, add the phone number you want to send test messages from
3. The recipient must first send a message to your WhatsApp number to open a 24-hour conversation window

## Step 7: Connect to the Master Agent

In your XeroFlow workflow:

```
[WhatsAppIntegrationNode] --message--> [MasterAgentNode]
                          <--response--
```

The WhatsApp node's `message` output connects to the Master Agent's input. When the Master Agent produces a response, it flows back to the WhatsApp node's `response` input and is sent back to the WhatsApp user.

**For standalone use** (without connecting to MasterAgentNode), the node will use its own API endpoint to generate responses directly.

---

## Workflow Example

```yaml
nodes:
  - id: whatsapp
    type: WhatsAppIntegrationNode
    properties:
      phone_number_id: "YOUR_PHONE_NUMBER_ID"
      access_token: "YOUR_ACCESS_TOKEN"
      verify_token: "xeroflow_whatsapp_verify"
      webhook_port: "5555"
      auto_reply: true
      is_persistent: true
```

---

## Supported Message Types

### Receiving (from WhatsApp users)
- **Text messages** — forwarded as-is to the AI
- **Images** — downloaded and saved locally, path passed to the AI
- **Documents** (PDF, Word, Excel, etc.) — downloaded and saved locally
- **Audio** — downloaded and saved locally
- **Video** — downloaded and saved locally
- **Location** — converted to text coordinates
- **Contacts** — noted as shared contacts

### Sending (back to WhatsApp users)
- **Text** — markdown is converted to WhatsApp formatting (`*bold*`, `_italic_`, `~strikethrough~`, `` ```code``` ``)
- **Images** — uploaded and sent as image messages
- **Documents** — uploaded and sent with filename
- **Audio** — uploaded and sent as audio messages
- **Video** — uploaded and sent as video messages
- Long messages are automatically split into chunks within WhatsApp's 4096-character limit

---

## Monitor Window

When the node starts, a monitor window opens showing:
- **Connection status** — webhook server status, phone ID, port
- **Message log** — real-time log of incoming/outgoing messages
- **Manual send** — send a message to any WhatsApp number directly from the UI

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Webhook verification fails | Ensure the verify token in Meta Dashboard matches the node property exactly |
| Messages not arriving | Check ngrok is running and the URL is correct in Meta Dashboard. Check the `messages` webhook field is subscribed |
| "Flask is not installed" | Run `pip install flask` in your venv |
| Token expired | Generate a permanent token via System Users (see Step 2) |
| Can't send to a number | The recipient must message your WhatsApp number first (24-hour window policy) |
| Media download fails | Verify your access token has the correct permissions |

---

## Security Notes

- **Never commit your access token** to version control
- Use environment variables or a `.env` file for sensitive credentials
- The `allowed_numbers` property restricts who can interact with your bot
- In production, use a proper reverse proxy (nginx) with SSL instead of ngrok

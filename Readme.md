# Nokia / Airtel GPON Home Router API & Web Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Control, automate, and manage your **Nokia G-2425G-A GPON Home Gateway** (commonly deployed by **Airtel Xstream Fiber** and other ISPs) via **Web Dashboard**, **MCP (Model Context Protocol)**, **REST API**, and **CLI** — with persistent **Device Nicknames (SQLite)** and zero browser automation!

---

## 💡 Why This Project?

### The Problem
Most home fiber routers (such as Airtel's Nokia GPON ONT) do not provide an official API or integration for smart home ecosystems. Whenever you want to:
- Check which devices are currently connected to your Wi-Fi,
- Assign friendly nicknames (e.g. *"Akanksha Phone"*, *"Guestroom TV"*),
- Block internet access for a specific device (e.g., managing children's screen time),
- Or automate network rules based on time or smart home states...

...you are forced to manually open a browser, navigate a sluggish web portal, type credentials, and click through multiple nested settings menus. 

Worse, because the router's web portal uses a complex client-side **hybrid encryption scheme** (RSA-1024 + AES-128-CBC via custom SJCL JavaScript), simple `curl` scripts or standard HTTP requests fail. Most developers resort to heavy, brittle browser automation (like Selenium or Puppeteer).

### The Solution
This project **fully reverse-engineers the router's RSA + AES cryptographic handshake in pure Python**. 

It communicates directly with the router's internal endpoints with sub-second response times and zero browser overhead. It combines a local **SQLite database** to store persistent device metadata (nicknames, custom notes, first/last seen) and wraps that core engine into four ready-to-use interfaces:
1. **🌐 Web Dashboard** — Sleek dark glassmorphism web app with live search, nickname editing, and 1-click block/unblock toggles.
2. **🤖 MCP Server** — Allows **AI Agents** (like Antigravity, Claude, Cursor) to control your Wi-Fi and block/unblock by friendly nicknames.
3. **⚡ REST API (FastAPI)** — Perfect for **Home Assistant**, webhooks, and custom automation.
4. **🖥️ CLI** — Instant terminal commands and bash scripting.

---

## 🎯 Real-World Use Cases

### 1. 🤖 AI Agent Voice & Chat Control (via MCP)
Connect this project to any MCP-compatible AI assistant (e.g., Claude Desktop, Antigravity IDE, Cursor). You can simply say:
> *"Set a nickname 'Akanksha Phone' for device f6:cf:28:1c:bd:e5."*  
> *"Block Guestroom TV from internet access."*  
> *"Is the Living Room TV connected to the Wi-Fi right now?"*  
> *"Unblock Akanksha Phone."*

The AI agent will inspect your connected devices, resolve the target by nickname/hostname/IP/MAC, and execute the action on your router automatically.

### 2. 🌐 Visual Web Dashboard
Open `http://localhost:8000/` to monitor all connected devices in a responsive web UI:
- **Live Stats Bar:** Total Devices, Active Online, Blocked count, and Custom Nicknames count.
- **Instant Search & Filter:** Filter by All, Online, Blocked, or Custom Nickname.
- **Inline Nickname Editor:** Assign friendly nicknames and location notes to any device.
- **1-Click Block/Unblock:** Toggle access with immediate in-flight loading spinners and toast notifications.

### 3. 🏠 Home Assistant Integration
Integrate your router into **Home Assistant** using the REST API:
- **Bedtime Automations:** Automatically block children's tablets and gaming consoles at 10:00 PM on school nights.
- **Presence Detection:** Trigger automations when specific phones join or leave the network.
- **Dashboard Toggles:** Create dedicated "Block / Unblock Internet" switch buttons on your Home Assistant Lovelace dashboard.

---

## ✨ Features

- 🏷️ **Persistent Device Nicknames** — Stored in SQLite (`data/router.db`) so you can reference devices by human-friendly names like *"Guestroom TV"*.
- 🎯 **Smart Multi-Target Resolution** — Block/unblock/query by **Nickname**, **Hostname**, **IP address**, or **MAC address** (supports partial/case-insensitive matching).
- 🔍 **List Connected Devices** — Hostname, IP address, MAC address, active online status, and connection interface (Ethernet, 2.4GHz 802.11, 5GHz 802.11ac).
- 🚫 **Block Devices** — Block internet access 24/7 for any device via Parental Control rules.
- ✅ **Unblock Devices** — Remove blocking rules instantly.
- 📋 **List Blocked Policies** — View all active access restriction policies and schedules.
- 🔄 **Auto-Sync & Self-Healing Sessions** — Automatic re-login and session recovery if router sessions expire.
- 🔐 **Zero Browser Overhead** — Pure cryptographic authentication via `pycryptodome` and `requests`.

---

## 🏗️ Architecture: Four Ways to Interact

| Interface | Best For | Entry Point |
|---|---|---|
| **Web Dashboard** | Visual management, editing nicknames, live device list | `python -m api.server` -> `http://localhost:8000` |
| **MCP Server** | AI agents (Claude, Antigravity, Cursor) | `python -m mcp_server.server` |
| **REST API** | Home Assistant, Node-RED, custom automation | `python -m api.server` -> `http://localhost:8000/docs` |
| **CLI** | Fast terminal access, cron jobs, shell scripts | `python -m cli.main` |

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/surajnai567/airtel-router-api.git
cd airtel-router-api

# Install dependencies
pip install -r requirements.txt
```

**Dependencies:** `requests`, `pycryptodome`, `python-dotenv`, `fastapi`, `uvicorn`, `mcp`

---

## ⚙️ Configuration

Create a `.env` file in the root directory (or copy from `.env.example`):

```env
ROUTER_IP=192.168.1.1
ROUTER_USERNAME=admin
ROUTER_PASSWORD=your_router_password

# Optional: REST API & Dashboard settings
API_HOST=0.0.0.0
API_PORT=8000
```

> 🔒 **Security Note:** The `.env` and `data/*.db` files are included in `.gitignore` so your router credentials and local database are never committed.

---

## 🌐 1. Web Dashboard & REST API

Start the server:

```bash
python -m api.server
```

- Open **`http://localhost:8000/`** in your browser to view the **Web Dashboard**.
- Open **`http://localhost:8000/docs`** for interactive Swagger API documentation.

### REST Endpoints

| Method | Path | Description | Payload |
|---|---|---|---|
| `GET` | `/api/devices` | List all connected devices with nicknames & blocked status | — |
| `GET` | `/api/blocked` | List all blocked devices with nicknames | — |
| `POST` | `/api/devices/nickname` | Set or clear friendly nickname | `{"target": "f6:cf:28:1c:bd:e5", "nickname": "Akanksha Phone", "notes": "Optional"}` |
| `POST` | `/api/block` | Block device by Nickname, Hostname, IP, or MAC | `{"target": "Akanksha Phone", "policy_name": "Optional"}` |
| `POST` | `/api/unblock` | Unblock device by Nickname, Hostname, IP, or MAC | `{"target": "Akanksha Phone"}` |
| `GET` | `/api/health` | Health check & router connection status | — |

---

## 🤖 2. MCP Server Usage (For AI Agents)

Expose router tools directly to AI agents using the Model Context Protocol (MCP).

### Available MCP Tools

- `list_devices()` — Returns formatted table with `Nickname`, `Hostname`, `IP`, `MAC`, `Active`, `Blocked`, and `Interface`.
- `set_device_nickname(target, nickname, notes=None)` — Sets or updates a device's friendly nickname.
- `block_device(target, policy_name=None)` — Blocks device by Nickname (e.g. `"Guestroom TV"`), Hostname, IP, or MAC.
- `unblock_device(target)` — Unblocks device by Nickname, Hostname, IP, or MAC.
- `list_blocked_devices()` — Returns active blocked devices with their nicknames and policies.

### MCP Configuration

Add this server to your MCP client config (e.g. `claude_desktop_config.json` or `mcp_config.json`):

```json
{
  "mcpServers": {
    "home_router": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "d:/project/routerapi"
    }
  }
}
```

---

## 🖥️ 3. CLI Usage

```bash
# List all connected/known devices (with nicknames)
python -m cli.main list

# List all currently blocked devices
python -m cli.main blocked

# Block a device by MAC address or Nickname
python -m cli.main block AA:BB:CC:DD:EE:FF

# Block a device with a custom policy name
python -m cli.main block AA:BB:CC:DD:EE:FF --name "Kid_Tablet_Block"

# Unblock a device by MAC address
python -m cli.main unblock AA:BB:CC:DD:EE:FF
```

---

## 🐍 4. Python Library Usage

```python
from core import RouterAPI

# Initialize and authenticate
router = RouterAPI(ip_address="192.168.1.1", username="admin", password="admin_password")
if router.login():
    # 1. Set a friendly nickname
    router.set_nickname("f6:cf:28:1c:bd:e5", "Akanksha Phone")

    # 2. Get all devices (auto-synced with SQLite)
    devices = router.list_devices()
    for d in devices:
        print(f"[{'ONLINE' if d['active'] else 'OFFLINE'}] {d['nickname'] or d['hostname']} ({d['ip']}) - {d['mac']}")

    # 3. Block directly by nickname!
    router.block_device("Akanksha Phone")

    # 4. Unblock by nickname!
    router.unblock_device("Akanksha Phone")

    # Clean up session
    router.logout()
```

---

## 📁 Project Structure

```
routerapi/
├── core/                      # Core business logic (the engine)
│   ├── __init__.py            # Re-exports RouterAPI, DB helpers, and crypto
│   ├── client.py              # RouterAPI client class with smart target resolution
│   ├── crypto.py              # AES-CBC + RSA encryption implementation
│   └── db.py                  # SQLite database layer for persistent nicknames
│
├── api/                       # REST API & Web Dashboard
│   ├── __init__.py
│   ├── server.py              # FastAPI server with CORS, static routes, & models
│   └── static/                # Web Dashboard assets
│       ├── index.html         # Dashboard HTML template
│       ├── style.css          # Dark glassmorphism stylesheet
│       └── app.js             # Frontend state management & async API calls
│
├── mcp_server/                # Model Context Protocol interface
│   ├── __init__.py
│   └── server.py              # MCP server exposing router tools to AI
│
├── cli/                       # Terminal interface
│   ├── __init__.py
│   └── main.py                # Argparse CLI entry point
│
├── data/                      # Local SQLite storage (git-ignored)
│   └── router.db              # Persistent device metadata & nicknames
│
├── .env                       # Credentials (git-ignored)
├── .env.example               # Template environment configuration
├── .gitignore
├── requirements.txt           # Project dependencies
└── Readme.md                  # Project documentation
```

---

## ⚠️ Notes & Disclaimer

- **Session Expiry & Self-Healing:** Router sessions naturally time out after inactivity. The API and MCP servers automatically manage re-authentication on subsequent calls.
- **Parental Control Compatibility:** Supports both **NEW** firmware (`NPCProfileList` group-based access control) and **OLD** firmware (`pc_config` access policies).
- **Tested Hardware:** Tested on **Nokia G-2425G-A GPON Home Gateway** (Airtel Xstream Fiber).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](file:///d:/project/routerapi/LICENSE) file for details.

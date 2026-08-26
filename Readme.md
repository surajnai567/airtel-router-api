# Nokia / Airtel GPON Home Router API

> Control and automate your **Nokia G-2425G-A GPON Home Gateway** (commonly deployed by **Airtel Xstream Fiber** and other ISPs) via **CLI**, **REST API**, and **MCP (Model Context Protocol)** — without any browser automation!

---

## 💡 Why This Project?

### The Problem
Most home fiber routers (such as Airtel's Nokia GPON ONT) do not provide an official API or integration for smart home ecosystems. Whenever you want to:
- Check which devices are currently connected to your Wi-Fi,
- Block internet access for a specific device (e.g., managing children's screen time),
- Or automate network rules based on time or smart home states...

...you are forced to manually open a browser, navigate a sluggish web portal, type credentials, and click through multiple nested settings menus. 

Worse, because the router's web portal uses a complex client-side **hybrid encryption scheme** (RSA-1024 + AES-128-CBC via custom SJCL JavaScript), simple `curl` scripts or standard HTTP requests fail. Most developers resort to heavy, brittle browser automation (like Selenium or Puppeteer).

### The Solution
This project **fully reverse-engineers the router's RSA + AES cryptographic handshake in pure Python**. 

It communicates directly with the router's internal endpoints with sub-second response times and zero browser overhead. It then wraps that core engine into three ready-to-use interfaces:
1. **CLI** — Instant terminal commands and bash scripting.
2. **REST API (FastAPI)** — Perfect for **Home Assistant**, web apps, and webhooks.
3. **MCP Server** — Allows **AI Agents** (like Antigravity, Claude, Cursor) to control your Wi-Fi through natural language.

---

## 🎯 Real-World Use Cases

### 1. 🤖 AI Agent Voice & Chat Control (via MCP)
Connect this project to any MCP-compatible AI assistant (e.g., Claude Desktop, Antigravity IDE, Cursor). You can simply say:
> *"My child is using too much internet on their phone. Find their device and block it."*  
> *"Is the living room TV connected to the Wi-Fi right now?"*  
> *"Unblock the iPad."*

The AI agent will inspect your connected devices, match the hostname/MAC, and execute the action on your router automatically.

### 2. 🏠 Home Assistant Integration
Integrate your router into **Home Assistant** using the REST API:
- **Bedtime Automations:** Automatically block children's tablets and gaming consoles at 10:00 PM on school nights.
- **Presence Detection:** Trigger automations when specific phones join or leave the network.
- **Dashboard Toggles:** Create dedicated "Block / Unblock Internet" switch buttons on your Home Assistant Lovelace dashboard.

### 3. ⚡ Quick Terminal & Scripting Access (CLI)
Query connected devices or toggle access directly from your terminal or scheduled cron jobs without logging into web portals.

---

## ✨ Features

- 🔍 **List Connected Devices** — Hostname, IP address, MAC address, active online status, and connection interface (Ethernet, 2.4GHz 802.11, 5GHz 802.11ac).
- 🚫 **Block Devices** — Block internet access 24/7 for any device by MAC address via Parental Control rules.
- ✅ **Unblock Devices** — Remove blocking rules instantly.
- 📋 **List Blocked Policies** — View all active access restriction policies and schedules.
- 🔐 **Zero Browser Overhead** — Pure cryptographic authentication via `pycryptodome` and `requests`.

---

## 🏗️ Architecture: Three Ways to Interact

| Interface | Best For | Entry Point |
|---|---|---|
| **CLI** | Fast terminal access, cron jobs, shell scripts | `python -m cli.main` |
| **REST API** | Home Assistant, Node-RED, custom web dashboards | `python -m api.server` |
| **MCP Server** | AI agents (Claude, Antigravity, Cursor) | `python -m mcp_server.server` |

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/your-username/routerapi.git
cd routerapi

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

# Optional: REST API Server settings
API_HOST=0.0.0.0
API_PORT=8000
```

> 🔒 **Security Note:** The `.env` file is included in `.gitignore` so your router credentials will never be committed to source control.

---

## 🖥️ 1. CLI Usage

Run commands via the command line interface:

```bash
# List all connected/known devices on the network
python -m cli.main list

# List all currently blocked devices
python -m cli.main blocked

# Block a device by MAC address
python -m cli.main block AA:BB:CC:DD:EE:FF

# Block a device with a custom policy name
python -m cli.main block AA:BB:CC:DD:EE:FF --name "Kid_Tablet_Block"

# Unblock a device by MAC address
python -m cli.main unblock AA:BB:CC:DD:EE:FF
```

---

## 🌐 2. REST API Usage (FastAPI)

Start the REST API server:

```bash
python -m api.server
```

The server runs on `http://localhost:8000` (or your configured `API_HOST`/`API_PORT`).  
Interactive Swagger documentation is available at **`http://localhost:8000/docs`**.

### Endpoints

| Method | Path | Description | Payload |
|---|---|---|---|
| `GET` | `/devices` | List all connected devices | — |
| `GET` | `/blocked` | List all blocked devices & policies | — |
| `POST` | `/block` | Block a device by MAC | `{"mac": "AA:BB:CC:DD:EE:FF", "policy_name": "Optional"}` |
| `POST` | `/unblock` | Unblock a device by MAC | `{"mac": "AA:BB:CC:DD:EE:FF"}` |
| `GET` | `/health` | Health check & authentication status | — |

### Home Assistant Integration Example

Add the following to your `configuration.yaml` in Home Assistant to create block/unblock actions:

```yaml
rest_command:
  router_block_device:
    url: "http://<ROUTER_API_SERVER_IP>:8000/block"
    method: POST
    headers:
      content-type: "application/json"
    payload: '{"mac": "{{ mac }}", "policy_name": "{{ name }}"}'

  router_unblock_device:
    url: "http://<ROUTER_API_SERVER_IP>:8000/unblock"
    method: POST
    headers:
      content-type: "application/json"
    payload: '{"mac": "{{ mac }}"}'

sensor:
  - platform: rest
    name: "Router Connected Devices"
    resource: "http://<ROUTER_API_SERVER_IP>:8000/devices"
    value_template: "{{ value_json | length }}"
    json_attributes_path: "$"
    scan_interval: 60
```

---

## 🤖 3. MCP Server Usage (For AI Agents)

Expose your router tools directly to AI agents using the Model Context Protocol (MCP).

### Available MCP Tools

- `list_devices` — Returns formatted table with all network devices (hostname, IP, MAC, online status).
- `list_blocked_devices` — Returns all active access control policies.
- `block_device(mac_address, policy_name)` — Blocks internet access for a device.
- `unblock_device(mac_address)` — Removes the blocking policy for a device.

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

## 🐍 4. Python Library Usage

You can also import and use the client directly in your own Python scripts:

```python
from core import RouterAPI

# Initialize and authenticate
router = RouterAPI(ip_address="192.168.1.1", username="admin", password="admin_password")
if router.login():
    # 1. Get all connected devices
    devices = router.list_devices()
    for d in devices:
        print(f"[{'ONLINE' if d['active'] else 'OFFLINE'}] {d['hostname']} ({d['ip']}) - {d['mac']}")

    # 2. Block a device
    router.block_device("AA:BB:CC:DD:EE:FF", policy_name="StudyTime")

    # 3. List blocked devices
    blocked = router.list_blocked_devices()
    print("Blocked:", blocked)

    # 4. Unblock a device
    router.unblock_device("AA:BB:CC:DD:EE:FF")

    # Clean up session
    router.logout()
```

---

## 📁 Project Structure

```
routerapi/
├── core/                      # Core business logic (the engine)
│   ├── __init__.py            # Re-exports RouterAPI and crypto helpers
│   ├── client.py              # RouterAPI client class
│   └── crypto.py              # AES-CBC + RSA encryption implementation
│
├── cli/                       # Terminal interface
│   ├── __init__.py
│   └── main.py                # Argparse CLI entry point
│
├── api/                       # REST API interface
│   ├── __init__.py
│   └── server.py              # FastAPI server with CORS & Pydantic models
│
├── mcp_server/                # Model Context Protocol interface
│   ├── __init__.py
│   └── server.py              # MCP server exposing router tools to AI
│
├── .env                       # Credentials (git-ignored)
├── .env.example               # Template environment configuration
├── .gitignore
├── requirements.txt           # Project dependencies
└── Readme.md                  # Project documentation
```

---

## ⚠️ Notes & Disclaimer

- **Session Expiry:** Router sessions naturally time out after inactivity. The API and MCP servers automatically manage re-authentication on subsequent calls.
- **Parental Control:** Blocking is performed by enabling Parental Control / Access Control rules that restrict target MAC addresses 24/7 across all days of the week (`00:00-23:59`).
- **Compatibility:** Tested on **Nokia G-2425G-A GPON Home Gateway** (Airtel Xstream Fiber). May also work with similar Nokia ONT models with identical firmware interfaces.

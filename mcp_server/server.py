"""
MCP (Model Context Protocol) server for Nokia GPON Router API.

Exposes router control as MCP tools that AI agents can call:
    - list_devices         List all connected devices with nicknames and block status
    - list_blocked_devices List all blocked devices
    - block_device         Block a device by Nickname, Hostname, IP, or MAC
    - unblock_device       Unblock a device by Nickname, Hostname, IP, or MAC
    - set_device_nickname  Assign a friendly nickname to any device

Run:
    python -m mcp_server.server
"""
import os
import json
import logging
from typing import Any, Optional

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

from core import RouterAPI, normalize_mac, set_device_nickname as db_set_nickname

logger = logging.getLogger(__name__)

# --- MCP Server ---
mcp = MCPServer(
    "Nokia Router API",
    description="Control a Nokia G-2425G-A GPON Home Gateway router — list devices with nicknames, block/unblock by nickname/MAC.",
)

# --- Shared router instance ---
_router: RouterAPI | None = None


def _get_router() -> RouterAPI:
    """Get an authenticated RouterAPI instance, logging in if needed."""
    global _router
    if _router is None or not _router.is_authenticated:
        _router = RouterAPI(
            ip_address=os.getenv("ROUTER_IP", "192.168.1.1"),
            username=os.getenv("ROUTER_USERNAME", "admin"),
            password=os.getenv("ROUTER_PASSWORD", "admin"),
        )
        if not _router.login():
            raise RuntimeError("Failed to authenticate with router. Please check ROUTER_IP, ROUTER_USERNAME, and ROUTER_PASSWORD.")
    return _router


def _format_table(rows: list[dict], columns: list[str]) -> str:
    """Format a list of dicts as a readable text table."""
    if not rows:
        return "No results."

    # Calculate column widths
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            val = str(row.get(col, ""))
            widths[col] = max(widths[col], len(val))

    # Header
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    sep = "  ".join("-" * widths[col] for col in columns)

    # Rows
    lines = [header, sep]
    for row in rows:
        line = "  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns)
        lines.append(line)

    return "\n".join(lines)


@mcp.tool()
def list_devices() -> str:
    """List all connected/known devices on the network.

    Returns a table of devices with Nickname, Hostname, IP address, MAC address,
    Active status, Blocked status, and Interface type.
    """
    try:
        router = _get_router()
        devices = router.list_devices()
    except Exception as e:
        return f"Error connecting to router: {e}"

    if not devices:
        return "No devices found."

    display = []
    for d in devices:
        display.append({
            "nickname": d.get("nickname") or "-",
            "hostname": d.get("hostname") or "(unknown)",
            "ip": d.get("ip") or "-",
            "mac": d["mac"],
            "active": "Yes" if d.get("active") else "No",
            "blocked": "Yes" if d.get("is_blocked") else "No",
            "interface": d.get("interface") or "-",
        })

    return _format_table(display, ["nickname", "hostname", "ip", "mac", "active", "blocked", "interface"])


@mcp.tool()
def list_blocked_devices() -> str:
    """List all blocked devices (Access Control / Parental Control policies).

    Returns a table of blocked MAC addresses with their Nickname and policy info.
    """
    try:
        router = _get_router()
        blocked = router.list_blocked_devices()
    except Exception as e:
        return f"Error connecting to router: {e}"

    if not blocked:
        return "No blocked devices."

    display = []
    for b in blocked:
        display.append({
            "nickname": b.get("nickname") or "-",
            "mac": b["mac"],
            "policy": b["policy_name"],
            "enabled": "Yes" if b["policy_enabled"] else "No",
            "schedule": f"{b['start_time']}-{b['end_time']}",
            "days": b["days"],
        })

    return _format_table(display, ["nickname", "mac", "policy", "enabled", "schedule", "days"])


@mcp.tool()
def set_device_nickname(target: str, nickname: str, notes: str | None = None) -> str:
    """Assign or update a friendly nickname for a device.

    Args:
        target: Target device by MAC address, current Nickname, Hostname, or IP (e.g., 'f6:cf:28:1c:bd:e5', 'akanksha-s-A26', or '192.168.1.7')
        nickname: The friendly nickname to assign (e.g., 'Guestroom TV', 'Akanksha Phone')
        notes: Optional descriptive notes or location info
    """
    try:
        router = _get_router()
        success, mac, assigned_name = router.set_nickname(target, nickname, notes)
    except Exception as e:
        return f"Error setting nickname: {e}"

    if success:
        return f"Successfully set nickname '{assigned_name}' for device {mac}."
    return f"Failed to set nickname for '{target}'."


@mcp.tool()
def block_device(target: str, policy_name: str | None = None) -> str:
    """Block a device from internet access by its Nickname, Hostname, IP, or MAC address.

    Args:
        target: The device to block by Nickname (e.g. 'guestroom tv'), Hostname, IP, or MAC (e.g. 'AA:BB:CC:DD:EE:FF')
        policy_name: Optional custom name for the blocking policy
    """
    try:
        router = _get_router()
        mac, display_name = router.resolve_device(target)
        success = router.block_device(mac, policy_name)
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error communicating with router: {e}"

    if success:
        return f"Successfully blocked '{display_name}' ({mac})."
    return f"Failed to block '{display_name}' ({mac}). Check router status and logs."


@mcp.tool()
def unblock_device(target: str) -> str:
    """Unblock a device by its Nickname, Hostname, IP, or MAC address.

    Args:
        target: The device to unblock by Nickname (e.g. 'guestroom tv'), Hostname, IP, or MAC (e.g. 'AA:BB:CC:DD:EE:FF')
    """
    try:
        router = _get_router()
        mac, display_name = router.resolve_device(target)
        success = router.unblock_device(mac)
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error communicating with router: {e}"

    if success:
        return f"Successfully unblocked '{display_name}' ({mac})."
    return f"Failed to unblock '{display_name}' ({mac}). The device may not currently be blocked."


if __name__ == "__main__":
    mcp.run()


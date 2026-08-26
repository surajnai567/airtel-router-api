"""
MCP (Model Context Protocol) server for Nokia GPON Router API.

Exposes router control as MCP tools that AI agents can call:
    - list_devices         List all connected devices
    - list_blocked_devices List all blocked devices
    - block_device         Block a device by MAC address
    - unblock_device       Unblock a device by MAC address

Run:
    python -m mcp_server.server
"""
import os
import json
import logging
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

from core import RouterAPI

logger = logging.getLogger(__name__)

# --- MCP Server ---
mcp = MCPServer(
    "Nokia Router API",
    description="Control a Nokia G-2425G-A GPON Home Gateway router — list devices, block/unblock by MAC.",
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
            raise RuntimeError("Failed to authenticate with router")
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

    Returns a table of devices with hostname, IP address, MAC address,
    active status, and interface type.
    """
    router = _get_router()
    devices = router.list_devices()

    if not devices:
        return "No devices found."

    # Convert boolean 'active' to readable string
    display = []
    for d in devices:
        display.append({
            "hostname": d["hostname"] or "(unknown)",
            "ip": d["ip"],
            "mac": d["mac"],
            "active": "Yes" if d["active"] else "No",
            "interface": d["interface"],
        })

    return _format_table(display, ["hostname", "ip", "mac", "active", "interface"])


@mcp.tool()
def list_blocked_devices() -> str:
    """List all blocked devices (Access Control / Parental Control policies).

    Returns a table of blocked MAC addresses with their policy info.
    """
    router = _get_router()
    blocked = router.list_blocked_devices()

    if not blocked:
        return "No blocked devices."

    display = []
    for b in blocked:
        display.append({
            "mac": b["mac"],
            "policy": b["policy_name"],
            "enabled": "Yes" if b["policy_enabled"] else "No",
            "schedule": f"{b['start_time']}-{b['end_time']}",
            "days": b["days"],
        })

    return _format_table(display, ["mac", "policy", "enabled", "schedule", "days"])


@mcp.tool()
def block_device(mac_address: str, policy_name: str | None = None) -> str:
    """Block a device from internet access by its MAC address.

    Creates a Parental Control / Access Control policy that blocks the device 24/7.

    Args:
        mac_address: The MAC address to block (e.g., "AA:BB:CC:DD:EE:FF")
        policy_name: Optional custom name for the blocking policy
    """
    router = _get_router()
    success = router.block_device(mac_address, policy_name)

    if success:
        return f"Successfully blocked {mac_address}."
    return f"Failed to block {mac_address}. Check logs for details."


@mcp.tool()
def unblock_device(mac_address: str) -> str:
    """Unblock a device by removing the Access Control policy containing its MAC.

    Args:
        mac_address: The MAC address to unblock (e.g., "AA:BB:CC:DD:EE:FF")
    """
    router = _get_router()
    success = router.unblock_device(mac_address)

    if success:
        return f"Successfully unblocked {mac_address}."
    return f"Failed to unblock {mac_address}. The MAC may not be in any blocked policy."


if __name__ == "__main__":
    mcp.run()

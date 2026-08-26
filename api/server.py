"""
FastAPI REST server for Nokia GPON Router API.

Endpoints:
    GET  /devices     List all connected devices
    GET  /blocked     List all blocked devices
    POST /block       Block a device by MAC address
    POST /unblock     Unblock a device by MAC address
    GET  /health      Health check

Run:
    python -m api.server
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from core import RouterAPI

logger = logging.getLogger(__name__)

# --- Shared router instance ---
router_client: Optional[RouterAPI] = None


def get_router() -> RouterAPI:
    """Get the shared, authenticated RouterAPI instance."""
    global router_client
    if router_client is None or not router_client.is_authenticated:
        router_client = RouterAPI(
            ip_address=os.getenv("ROUTER_IP", "192.168.1.1"),
            username=os.getenv("ROUTER_USERNAME", "admin"),
            password=os.getenv("ROUTER_PASSWORD", "admin"),
        )
        if not router_client.login():
            raise HTTPException(status_code=503, detail="Failed to authenticate with router")
    return router_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: log in to router. Shutdown: log out."""
    logger.info("Starting Router API server...")
    try:
        get_router()
        logger.info("Authenticated with router.")
    except HTTPException:
        logger.warning("Could not authenticate with router at startup — will retry on first request.")
    yield
    if router_client and router_client.is_authenticated:
        router_client.logout()
        logger.info("Logged out from router.")


# --- Pydantic models ---
class MACRequest(BaseModel):
    mac: str = Field(..., description="MAC address (e.g., AA:BB:CC:DD:EE:FF)")
    policy_name: Optional[str] = Field(None, description="Custom policy name (block only)")


class DeviceResponse(BaseModel):
    hostname: str
    ip: str
    mac: str
    active: bool
    interface: str


class BlockedDeviceResponse(BaseModel):
    mac: str
    policy_name: str
    policy_enabled: bool
    days: str
    start_time: str
    end_time: str


class ActionResponse(BaseModel):
    success: bool
    message: str


# --- FastAPI app ---
app = FastAPI(
    title="Nokia GPON Router API",
    description="REST API for controlling a Nokia G-2425G-A GPON Home Gateway router.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    r = get_router()
    return {"status": "ok", "authenticated": r.is_authenticated}


@app.get("/devices", response_model=list[DeviceResponse])
async def list_devices():
    """List all connected/known devices on the network."""
    r = get_router()
    devices = r.list_devices()
    return devices


@app.get("/blocked", response_model=list[BlockedDeviceResponse])
async def list_blocked():
    """List all blocked devices (Access Control policies)."""
    r = get_router()
    blocked = r.list_blocked_devices()
    return blocked


@app.post("/block", response_model=ActionResponse)
async def block_device(req: MACRequest):
    """Block a device from internet access by MAC address."""
    r = get_router()
    success = r.block_device(req.mac, req.policy_name)
    if success:
        return ActionResponse(success=True, message=f"Blocked {req.mac}")
    raise HTTPException(status_code=500, detail=f"Failed to block {req.mac}")


@app.post("/unblock", response_model=ActionResponse)
async def unblock_device(req: MACRequest):
    """Unblock a device by MAC address."""
    r = get_router()
    success = r.unblock_device(req.mac)
    if success:
        return ActionResponse(success=True, message=f"Unblocked {req.mac}")
    raise HTTPException(status_code=500, detail=f"Failed to unblock {req.mac}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )

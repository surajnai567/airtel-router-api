"""
FastAPI REST server & Web Dashboard for Nokia GPON Router API.

Endpoints:
    GET  /api/devices            List all connected devices with nicknames & blocked status
    GET  /api/blocked            List all blocked devices
    POST /api/block              Block a device by MAC, Nickname, Hostname, or IP
    POST /api/unblock            Unblock a device by MAC, Nickname, Hostname, or IP
    POST /api/devices/nickname   Set or clear a device's friendly nickname
    GET  /api/health             Health check & router connection status
    GET  /                       Web Dashboard UI
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()

from core import RouterAPI, normalize_mac, set_device_nickname, get_all_devices, get_device

logger = logging.getLogger(__name__)

# --- Shared router instance ---
router_client: Optional[RouterAPI] = None

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


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
            raise HTTPException(status_code=503, detail="Failed to authenticate with router. Check credentials.")
    return router_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: log in to router. Shutdown: log out."""
    logger.info("Starting Router API server...")
    os.makedirs(STATIC_DIR, exist_ok=True)
    try:
        get_router()
        logger.info("Authenticated with router successfully.")
    except HTTPException:
        logger.warning("Could not authenticate with router at startup — will retry on first request.")
    yield
    if router_client and router_client.is_authenticated:
        router_client.logout()
        logger.info("Logged out from router.")


# --- Pydantic models ---
class TargetRequest(BaseModel):
    target: str = Field(..., description="Device MAC address, Nickname, Hostname, or IP")
    policy_name: Optional[str] = Field(None, description="Optional custom policy name (block only)")


class NicknameRequest(BaseModel):
    target: str = Field(..., description="Device MAC address, Nickname, Hostname, or IP")
    nickname: Optional[str] = Field(None, description="New friendly nickname (or null to clear)")
    notes: Optional[str] = Field(None, description="Optional notes")


class DeviceResponse(BaseModel):
    hostname: str
    ip: str
    mac: str
    active: bool
    interface: str
    nickname: Optional[str] = None
    is_blocked: bool = False


class BlockedDeviceResponse(BaseModel):
    mac: str
    nickname: Optional[str] = None
    policy_name: str
    policy_enabled: bool
    days: str
    start_time: str
    end_time: str


class ActionResponse(BaseModel):
    success: bool
    message: str
    target: Optional[str] = None
    mac: Optional[str] = None


# --- FastAPI app ---
app = FastAPI(
    title="Nokia GPON Router API & Dashboard",
    description="REST API and Dashboard for Nokia G-2425G-A GPON Home Gateway router.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
@app.get("/health")
async def health():
    """Health check endpoint."""
    r = get_router()
    return {"status": "ok", "authenticated": r.is_authenticated}


@app.get("/api/devices", response_model=list[DeviceResponse])
@app.get("/devices", response_model=list[DeviceResponse])
async def list_devices():
    """List all connected/known devices on the network with nicknames and blocked status."""
    r = get_router()
    devices = r.list_devices(sync_db=True)
    return devices


@app.get("/api/blocked", response_model=list[BlockedDeviceResponse])
@app.get("/blocked", response_model=list[BlockedDeviceResponse])
async def list_blocked():
    """List all blocked devices with nicknames."""
    r = get_router()
    blocked = r.list_blocked_devices()
    return blocked


@app.post("/api/devices/nickname", response_model=ActionResponse)
async def update_nickname(req: NicknameRequest):
    """Assign, update, or clear a device nickname."""
    r = get_router()
    try:
        mac, display_name = r.resolve_device(req.target)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    success = set_device_nickname(mac, req.nickname, req.notes)
    if success:
        action = f"Set nickname '{req.nickname}'" if req.nickname else "Cleared nickname"
        return ActionResponse(success=True, message=f"{action} for device {mac}", target=req.target, mac=mac)
    raise HTTPException(status_code=500, detail="Failed to save nickname to database")


@app.post("/api/block", response_model=ActionResponse)
@app.post("/block", response_model=ActionResponse)
async def block_device(req: TargetRequest):
    """Block a device from internet access by MAC address, Nickname, Hostname, or IP."""
    r = get_router()
    try:
        mac, display_name = r.resolve_device(req.target)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    success = r.block_device(mac, req.policy_name)
    if success:
        return ActionResponse(success=True, message=f"Successfully blocked '{display_name}' ({mac})", target=req.target, mac=mac)
    raise HTTPException(status_code=500, detail=f"Failed to block '{display_name}' ({mac})")


@app.post("/api/unblock", response_model=ActionResponse)
@app.post("/unblock", response_model=ActionResponse)
async def unblock_device(req: TargetRequest):
    """Unblock a device by MAC address, Nickname, Hostname, or IP."""
    r = get_router()
    try:
        mac, display_name = r.resolve_device(req.target)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    success = r.unblock_device(mac)
    if success:
        return ActionResponse(success=True, message=f"Successfully unblocked '{display_name}' ({mac})", target=req.target, mac=mac)
    raise HTTPException(status_code=500, detail=f"Failed to unblock '{display_name}' ({mac})")


# Mount static files for web dashboard
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    """Serve the Web Dashboard."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Nokia GPON Router API is running. Dashboard is building."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )


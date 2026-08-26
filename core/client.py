"""
Nokia GPON Home Gateway (G-2425G-A) Router API Client.
Provides programmatic control of the router without browser automation.

Features:
- Login with RSA/AES encrypted authentication
- List all connected devices (hostname, IP, MAC, active status)
- Block a device by MAC address (via Parental Control / Access Control)
- Unblock a device by MAC address
- List all blocked devices / access control policies
"""
import requests
import logging
import urllib.parse
import base64
import os
import re
from dotenv import load_dotenv

load_dotenv()
from .crypto import (
    extract_login_params,
    base64url_escape,
    encrypt_post_data,
    aes_cbc_decrypt,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class RouterAPI:
    def __init__(self, ip_address="192.168.1.1", username="admin", password="admin"):
        """Initialize the Router API client for Nokia GPON Router."""
        self.base_url = f"http://{ip_address}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": self.base_url,
        })
        self.is_authenticated = False
        self.dec_key = None
        self.dec_iv = None
        self.sid = None
        self.pubkey = None
        self.csrf_token = None

    def login(self):
        """
        Authenticate with the router using RSA/AES encrypted login.
        Returns True on success, False on failure.
        """
        logger.info(f"Logging into {self.base_url} as '{self.username}'...")

        try:
            # Step 1: Fetch login page
            r = self.session.get(self.base_url, timeout=10)
            r.raise_for_status()

            self.pubkey, nonce, token = extract_login_params(r.text)
            logger.info("Extracted crypto parameters.")

            # Step 2: Build plaintext payload (matches the inline submit() JS function)
            self.dec_key = os.urandom(16)
            self.dec_iv = os.urandom(16)
            dec_key_b64 = base64.b64encode(self.dec_key).decode('utf-8')
            dec_iv_b64 = base64.b64encode(self.dec_iv).decode('utf-8')

            payload_str = (
                f"&username={self.username}"
                f"&password={urllib.parse.quote(self.password)}"
                f"&csrf_token={token}"
                f"&nonce={nonce}"
                f"&enckey={base64url_escape(dec_key_b64)}"
                f"&enciv={base64url_escape(dec_iv_b64)}"
            )

            # Step 3: Encrypt the payload
            encrypted_data, _, _ = encrypt_post_data(self.pubkey, payload_str)

            # Step 4: POST to /login.cgi
            login_response = self.session.post(
                f"{self.base_url}/login.cgi",
                data=encrypted_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
                allow_redirects=False,
            )

            # Step 5: Check for success (status 299 + X-SID header)
            if login_response.status_code == 299:
                self.sid = login_response.headers.get("X-SID")
                self.is_authenticated = True
                logger.info(f"Login successful! SID: {self.sid}")
                return True

            logger.error(f"Login failed. Status: {login_response.status_code}")
            return False

        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    def _get_page(self, path, timeout=10):
        """Fetch an authenticated page. Returns the response text or None."""
        if not self.is_authenticated:
            logger.warning("Not authenticated. Call login() first.")
            return None

        url = f"{self.base_url}{path}"
        try:
            r = self.session.get(url, timeout=timeout)
            if len(r.text) <= 150:
                logger.warning(f"Empty/redirect response for {path} - session may have expired.")
                return None
            # Extract the csrf_token from the page for subsequent POSTs
            csrf_match = re.search(r'csrf_token["\s]*value="([^"]+)"', r.text)
            if csrf_match:
                self.csrf_token = csrf_match.group(1)
            # Also try extracting pubkey in case it changed
            try:
                self.pubkey, _, _ = extract_login_params(r.text)
            except ValueError:
                pass
            return r.text
        except Exception as e:
            logger.error(f"Error fetching {path}: {e}")
            return None

    def _encrypted_post(self, path, post_data, timeout=10):
        """
        POST encrypted data to the router, replicating the browser's ajaxSend interceptor.
        The browser's JS intercepts all AJAX POSTs and:
        1. Appends csrf_token if not present
        2. Encrypts the entire payload via crypto_page.encrypt_post_data
        """
        if not self.is_authenticated:
            logger.warning("Not authenticated. Call login() first.")
            return None

        # Append csrf_token if not already in data
        if "csrf_token" not in post_data:
            if self.csrf_token:
                post_data += f"&csrf_token={self.csrf_token}"

        # Encrypt the post data
        encrypted_data, _, _ = encrypt_post_data(self.pubkey, post_data)

        url = f"{self.base_url}{path}"
        try:
            r = self.session.post(
                url,
                data=encrypted_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
            )
            return r
        except Exception as e:
            logger.error(f"Error posting to {path}: {e}")
            return None

    def _parse_device_cfg(self, html):
        """
        Parse the 'var device_cfg = [...]' JavaScript array from the HTML.
        Returns a list of device dicts.
        """
        match = re.search(r'var device_cfg\s*=\s*\[(.*?)\];', html, re.DOTALL)
        if not match:
            return []

        raw = match.group(1)
        devices = []

        # Parse each {_oid:N, HostName:'...', IPAddress:'...', MACAddress:'...', Active:N, InterfaceType:'...'} block
        pattern = re.compile(
            r"\{_oid:(\d+),\s*HostName:'([^']*)',\s*"
            r"IPAddress:'([^']*)',\s*"
            r"MACAddress:'([^']*)',\s*"
            r"Active:(\d),\s*"
            r"InterfaceType:'([^']*)'\s*\}",
            re.DOTALL
        )
        for m in pattern.finditer(raw):
            devices.append({
                "oid": int(m.group(1)),
                "hostname": m.group(2),
                "ip": m.group(3),
                "mac": m.group(4),
                "active": m.group(5) == "1",
                "interface": m.group(6),
            })

        return devices

    def _parse_pc_config(self, html):
        """
        Parse the 'var pc_config = {...}' JavaScript object from the HTML.
        Returns a dict with Enable and AccessPolicy list.
        """
        match = re.search(r'var pc_config\s*=\s*\{(.*?)\};', html, re.DOTALL)
        if not match:
            return {"Enable": 0, "AccessPolicy": []}

        raw = match.group(1)

        enable_match = re.search(r'Enable:(\d)', raw)
        enabled = int(enable_match.group(1)) if enable_match else 0

        # Parse AccessPolicy array
        policies = []
        # Actual field order from the router:
        # _oid, PolicyEnable, PolicyName, MACDeviceNumberOfEntries,
        # IPDeviceNumberOfEntries, URLFilterNumberOfEntries,
        # MAC:[...], IP:[...], URL:[...], StartTime, EndTime, DayOfWeek
        policy_pattern = re.compile(
            r"\{_oid:(\d+),\s*"
            r"PolicyEnable:(\d),\s*"
            r"PolicyName:'([^']*)',\s*"
            r"MACDeviceNumberOfEntries:(\d+),\s*"
            r"IPDeviceNumberOfEntries:(\d+),\s*"
            r"URLFilterNumberOfEntries:(\d+),\s*"
            r"MAC:\[(.*?)\],\s*"
            r"IP:\[(.*?)\],\s*"
            r"URL:\[(.*?)\],\s*"
            r"StartTime:'([^']*)',\s*"
            r"EndTime:'([^']*)',\s*"
            r"DayOfWeek:'([^']*)'",
            re.DOTALL
        )

        for pm in policy_pattern.finditer(raw):
            # Parse MAC addresses within this policy
            mac_list = []
            mac_pattern = re.compile(r"\{_oid:(\d+),\s*SourceMAC:'([^']*)'\s*\}")
            for mm in mac_pattern.finditer(pm.group(7)):
                mac_list.append({"_oid": int(mm.group(1)), "SourceMAC": mm.group(2)})

            ip_list = []
            ip_pattern = re.compile(r"\{_oid:(\d+),\s*SourceIP:'([^']*)'\s*\}")
            for im in ip_pattern.finditer(pm.group(8)):
                ip_list.append({"_oid": int(im.group(1)), "SourceIP": im.group(2)})

            policies.append({
                "oid": int(pm.group(1)),
                "name": pm.group(3),
                "enabled": pm.group(2) == "1",
                "days": pm.group(12),
                "start_time": pm.group(10),
                "end_time": pm.group(11),
                "macs": mac_list,
                "ips": ip_list,
            })

        return {"Enable": enabled, "AccessPolicy": policies}

    # ===================== PUBLIC API METHODS =====================

    def list_devices(self):
        """
        List all connected/known devices on the network.
        Returns a list of dicts: [{hostname, ip, mac, active, interface}, ...]
        """
        html = self._get_page("/parental_control.cgi")
        if not html:
            return []

        devices = self._parse_device_cfg(html)
        logger.info(f"Found {len(devices)} devices.")
        return devices

    def list_blocked_devices(self):
        """
        List all blocked devices (Parental Control / Access Control policies).
        Returns a list of dicts with policy info and blocked MAC addresses.
        """
        html = self._get_page("/parental_control.cgi")
        if not html:
            return []

        pc_config = self._parse_pc_config(html)

        blocked = []
        for policy in pc_config["AccessPolicy"]:
            for mac_entry in policy["macs"]:
                blocked.append({
                    "mac": mac_entry["SourceMAC"],
                    "mac_oid": mac_entry["_oid"],
                    "policy_name": policy["name"],
                    "policy_oid": policy["oid"],
                    "policy_enabled": policy["enabled"],
                    "days": policy["days"],
                    "start_time": policy["start_time"],
                    "end_time": policy["end_time"],
                })

        logger.info(f"Found {len(blocked)} blocked MAC entries across {len(pc_config['AccessPolicy'])} policies.")
        return blocked

    def block_device(self, mac_address, policy_name=None):
        """
        Block a device from internet access by its MAC address.
        Creates a new Access Control policy that blocks the device 24/7.

        Args:
            mac_address: The MAC address to block (e.g., "AA:BB:CC:DD:EE:FF")
            policy_name: Optional policy name (defaults to "Block_<MAC>")

        Returns:
            True on success, False on failure.
        """
        if not policy_name:
            policy_name = f"Block_{mac_address.replace(':', '')}"

        logger.info(f"Blocking device {mac_address} with policy '{policy_name}'...")

        # First, make sure parental control is enabled
        html = self._get_page("/parental_control.cgi")
        if not html:
            return False

        pc_config = self._parse_pc_config(html)
        if not pc_config["Enable"]:
            logger.info("Enabling Parental Control / Access Control...")
            r = self._encrypted_post("/parental_control.cgi?enable_pc", "Enable=1")
            if not r:
                logger.error("Failed to enable Access Control.")
                return False

            # Re-fetch to get fresh csrf_token
            html = self._get_page("/parental_control.cgi")
            if not html:
                return False

        # Create a new policy that blocks this MAC address 24/7
        post_data = (
            f"PolicyEnable=1"
            f"&oid=0"
            f"&PolicyName={urllib.parse.quote(policy_name)}"
            f"&addMAC={urllib.parse.quote(mac_address)}"
            f"&addIP="
            f"&addUrlAddress="
            f"&addPortNumber="
            f"&StartTime=00:00"
            f"&EndTime=23:59"
            f"&DayOfWeek=0,1,2,3,4,5,6"
        )

        r = self._encrypted_post("/parental_control.cgi?add", post_data)
        if r and r.status_code == 200:
            logger.info(f"Successfully blocked {mac_address}!")
            return True

        logger.error(f"Failed to block {mac_address}. Status: {r.status_code if r else 'N/A'}")
        return False

    def unblock_device(self, mac_address):
        """
        Remove a device from the blocked list by deleting the policy containing its MAC.

        Args:
            mac_address: The MAC address to unblock (e.g., "AA:BB:CC:DD:EE:FF")

        Returns:
            True on success, False on failure.
        """
        logger.info(f"Unblocking device {mac_address}...")

        blocked = self.list_blocked_devices()
        if not blocked:
            logger.info("No blocked devices found.")
            return False

        # Find the policy containing this MAC
        target_policy_oid = None
        for entry in blocked:
            if entry["mac"].lower() == mac_address.lower():
                target_policy_oid = entry["policy_oid"]
                break

        if target_policy_oid is None:
            logger.warning(f"MAC {mac_address} not found in any blocked policy.")
            return False

        # Delete the policy
        post_data = f"oid={target_policy_oid}"
        r = self._encrypted_post("/parental_control.cgi?del_pc_rule", post_data)
        if r and r.status_code == 200:
            logger.info(f"Successfully unblocked {mac_address} (deleted policy oid={target_policy_oid})!")
            return True

        logger.error(f"Failed to unblock {mac_address}. Status: {r.status_code if r else 'N/A'}")
        return False

    def logout(self):
        """Logout from the router."""
        try:
            self.session.get(f"{self.base_url}/login.cgi?out", timeout=5)
            self.is_authenticated = False
            logger.info("Logged out.")
        except Exception:
            pass

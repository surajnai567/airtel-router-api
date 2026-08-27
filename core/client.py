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
    extract_pubkey,
    base64url_escape,
    encrypt_post_data,
    aes_cbc_decrypt,
)

import warnings
import urllib3

# Suppress Nokia GPON proc header parsing warning
warnings.filterwarnings("ignore", category=urllib3.exceptions.HTTPWarning)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MAC_PATTERN = re.compile(r"^([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})$")


def normalize_mac(mac: str) -> str | None:
    """Validate and normalize MAC address to lowercase colon-separated format."""
    if not mac or not isinstance(mac, str):
        return None
    mac = mac.strip().lower()
    if not MAC_PATTERN.match(mac):
        return None
    return mac.replace("-", ":")


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

            logger.error(f"Login failed with status {login_response.status_code}. Verify username and password.")
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Cannot connect to router at {self.base_url}: {e}")
            return False
        except requests.exceptions.Timeout:
            logger.error(f"Connection to router at {self.base_url} timed out.")
            return False
        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    def _get_page(self, path, timeout=10, retry_on_auth_fail=True):
        """Fetch an authenticated page. Automatically re-logs in if session expired."""
        if not self.is_authenticated:
            if not self.login():
                return None

        url = f"{self.base_url}{path}"
        try:
            r = self.session.get(url, timeout=timeout)

            # Check for session expiration / redirection to login page
            is_expired = len(r.text) <= 150 or "submit_login" in r.text or "var nonce" in r.text
            if is_expired and retry_on_auth_fail:
                logger.warning(f"Session expired while requesting {path}, attempting re-login...")
                self.is_authenticated = False
                if self.login():
                    return self._get_page(path, timeout=timeout, retry_on_auth_fail=False)
                return None

            if len(r.text) <= 150:
                logger.warning(f"Empty response from {path}.")
                return None

            # Extract csrf_token from the page for subsequent POSTs
            csrf_match = re.search(r'csrf_token["\s]*value="([^"]+)"', r.text)
            if not csrf_match:
                csrf_match = re.search(r'var token\s*=\s*"([^"]+)"', r.text)
            if csrf_match:
                self.csrf_token = csrf_match.group(1)

            # Also refresh pubkey if page contains one
            page_pubkey = extract_pubkey(r.text)
            if page_pubkey:
                self.pubkey = page_pubkey

            return r.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching {path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {path}: {e}")
            return None

    def _encrypted_post(self, path, post_data, timeout=10, retry_on_auth_fail=True):
        """
        POST encrypted data to the router, replicating the browser's ajaxSend interceptor.
        """
        if not self.is_authenticated:
            if not self.login():
                return None

        # Append csrf_token if not already in data
        if "csrf_token" not in post_data:
            if self.csrf_token:
                post_data += f"&csrf_token={self.csrf_token}"

        # Encrypt the post data
        try:
            encrypted_data, _, _ = encrypt_post_data(self.pubkey, post_data)
        except Exception as e:
            logger.error(f"Failed to encrypt payload for {path}: {e}")
            return None

        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/parental_control.cgi",
        }
        try:
            r = self.session.post(
                url,
                data=encrypted_data,
                headers=headers,
                timeout=timeout,
            )

            # Check if router returned an Errorinfo cookie/auth error
            if r and "Errorinfo" in r.text and retry_on_auth_fail:
                logger.warning("Router reported Errorinfo in POST response. Re-authenticating...")
                self.is_authenticated = False
                if self.login():
                    return self._encrypted_post(path, post_data, timeout=timeout, retry_on_auth_fail=False)

            return r
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error posting to {path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error posting to {path}: {e}")
            return None

    def _parse_device_cfg(self, html):
        """
        Parse the 'var deviceCfg = [...]' or 'var device_cfg = [...]' JavaScript array from the HTML.
        Returns a list of device dicts.
        """
        match = re.search(r'var device_?cfg\s*=\s*\[(.*?)\];', html, re.DOTALL | re.IGNORECASE)
        if not match:
            return []

        raw = match.group(1)
        devices = []

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

    def _parse_pc_config_old(self, html):
        """
        Parse the 'var pc_config = {...}' JavaScript object from the HTML (OLD mode).
        Returns a dict with Enable and AccessPolicy list.
        """
        match = re.search(r'var pc_config\s*=\s*\{(.*?)\};', html, re.DOTALL)
        if not match:
            return None

        raw = match.group(1)
        enable_match = re.search(r'Enable:(\d)', raw)
        enabled = int(enable_match.group(1)) if enable_match else 0

        policies = []
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

    def _parse_parental_control_new(self, html):
        """
        Parse the 'var parentalCtrlList = {...}' JavaScript object (NEW mode).
        Returns a list of profile/group dicts.
        """
        match = re.search(r'var parentalCtrlList\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not match:
            return None

        raw = match.group(1)
        # Parse profile objects from NPCProfileList
        profile_blocks = re.findall(
            r'\{"_oid":(\d+),\s*Name:\'([^\']*)\',\s*HomeGroup:(\d),\s*AccessInternet:(\d).*?"Device":\[(.*?)\]\s*\}',
            raw, re.DOTALL
        )

        groups = []
        for p_oid, name, home_grp, access_net, dev_raw in profile_blocks:
            devices = []
            dev_matches = re.finditer(
                r'\{"_oid":(\d+),\s*MACAddress:\'([^\']*)\'',
                dev_raw
            )
            for dm in dev_matches:
                devices.append({
                    "_oid": int(dm.group(1)),
                    "MACAddress": dm.group(2),
                })

            groups.append({
                "oid": int(p_oid),
                "name": name,
                "home_group": home_grp == "1",
                "access_internet": int(access_net),
                "devices": devices,
            })

        return groups

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

        # Try NEW mode first
        new_groups = self._parse_parental_control_new(html)
        if new_groups is not None:
            blocked = []
            for grp in new_groups:
                if grp["access_internet"] == 0 or (not grp["home_group"] and grp["name"].lower() == "blocked"):
                    for dev in grp["devices"]:
                        blocked.append({
                            "mac": dev["MACAddress"],
                            "mac_oid": dev["_oid"],
                            "policy_name": grp["name"],
                            "policy_oid": grp["oid"],
                            "policy_enabled": True,
                            "days": "All",
                            "start_time": "00:00",
                            "end_time": "23:59",
                        })
            logger.info(f"Found {len(blocked)} blocked devices in NEW mode.")
            return blocked

        # Fallback to OLD mode
        pc_config = self._parse_pc_config_old(html)
        if pc_config is not None:
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
            logger.info(f"Found {len(blocked)} blocked MAC entries in OLD mode.")
            return blocked

        return []

    def block_device(self, mac_address, policy_name=None):
        """
        Block a device from internet access by its MAC address.

        Args:
            mac_address: The MAC address to block (e.g., "AA:BB:CC:DD:EE:FF")
            policy_name: Optional policy name

        Returns:
            True on success, False on failure.
        """
        clean_mac = normalize_mac(mac_address)
        if not clean_mac:
            logger.error(f"Invalid MAC address format: '{mac_address}'. Expected format: AA:BB:CC:DD:EE:FF")
            return False
        mac_address = clean_mac
        logger.info(f"Blocking device {mac_address}...")

        html = self._get_page("/parental_control.cgi")
        if not html:
            return False

        # Check for NEW mode
        new_groups = self._parse_parental_control_new(html)
        if new_groups is not None:
            # 1. Find or create a 'Blocked' group with AccessInternet=0
            blocked_group = None
            home_group = None
            for grp in new_groups:
                if grp["home_group"]:
                    home_group = grp
                if grp["name"].lower() == (policy_name.lower() if policy_name else "blocked"):
                    blocked_group = grp
                elif blocked_group is None and grp["access_internet"] == 0:
                    blocked_group = grp

            if blocked_group is None:
                # Create a Blocked group
                group_name = policy_name or "Blocked"
                logger.info(f"Creating new parental control group '{group_name}'...")
                r = self._encrypted_post("/parental_control.cgi?add_group_N", f"group_name_input={urllib.parse.quote(group_name)}")
                if not r or r.status_code != 200:
                    logger.error("Failed to create group.")
                    return False

                # Refresh page to get new group OID
                html = self._get_page("/parental_control.cgi")
                new_groups = self._parse_parental_control_new(html)
                for grp in new_groups:
                    if grp["name"].lower() == group_name.lower():
                        blocked_group = grp
                    if grp["home_group"]:
                        home_group = grp

            if not blocked_group:
                logger.error("Could not find or create blocked group.")
                return False

            # Ensure internet is disabled for the blocked group
            if blocked_group["access_internet"] != 0:
                logger.info(f"Disabling internet on group '{blocked_group['name']}' (oid={blocked_group['oid']})...")
                self._encrypted_post("/parental_control.cgi?chg_internet_N", f"enable=0&group_id={blocked_group['oid']}")
                html = self._get_page("/parental_control.cgi")
                new_groups = self._parse_parental_control_new(html)

            # 2. Check if device is already in the blocked group
            for dev in blocked_group.get("devices", []):
                if dev["MACAddress"].lower() == mac_address:
                    logger.info(f"Device {mac_address} is already blocked.")
                    return True

            # 3. Find device in Home group (or any group) to move it
            dev_oid_in_source = None
            source_grp_oid = home_group["oid"] if home_group else 1
            for grp in new_groups:
                for dev in grp.get("devices", []):
                    if dev["MACAddress"].lower() == mac_address:
                        dev_oid_in_source = dev["_oid"]
                        source_grp_oid = grp["oid"]
                        break
                if dev_oid_in_source is not None:
                    break

            if dev_oid_in_source is not None and source_grp_oid != blocked_group["oid"]:
                # Move device to blocked group
                post_data = f"move_id={blocked_group['oid']}&device_id={dev_oid_in_source}&group_id={source_grp_oid}"
                r = self._encrypted_post("/parental_control.cgi?move_device_N", post_data)
                if r and r.status_code == 200:
                    logger.info(f"Successfully blocked {mac_address} (moved to group {blocked_group['name']})!")
                    return True
            else:
                # Add device to blocked group directly
                post_data = f"group_id_device={blocked_group['oid']}&add_device_mac={urllib.parse.quote(mac_address)}"
                r = self._encrypted_post("/parental_control.cgi?add_device_N", post_data)
                if r and r.status_code == 200:
                    logger.info(f"Successfully blocked {mac_address} (added to group {blocked_group['name']})!")
                    return True

            logger.error(f"Failed to move/add device {mac_address} to blocked group.")
            return False

        # Fallback to OLD mode
        if not policy_name:
            policy_name = f"Block_{mac_address.replace(':', '')}"

        pc_config = self._parse_pc_config_old(html)
        if pc_config and not pc_config["Enable"]:
            logger.info("Enabling Parental Control / Access Control...")
            self._encrypted_post("/parental_control.cgi?enable_pc", "Enable=1")
            html = self._get_page("/parental_control.cgi")

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

        return False

    def unblock_device(self, mac_address):
        """
        Remove a device from the blocked list.

        Args:
            mac_address: The MAC address to unblock (e.g., "AA:BB:CC:DD:EE:FF")

        Returns:
            True on success, False on failure.
        """
        clean_mac = normalize_mac(mac_address)
        if not clean_mac:
            logger.error(f"Invalid MAC address format: '{mac_address}'. Expected format: AA:BB:CC:DD:EE:FF")
            return False
        mac_address = clean_mac
        logger.info(f"Unblocking device {mac_address}...")

        html = self._get_page("/parental_control.cgi")
        if not html:
            return False

        # Try NEW mode first
        new_groups = self._parse_parental_control_new(html)
        if new_groups is not None:
            home_group = next((g for g in new_groups if g["home_group"]), None)
            home_oid = home_group["oid"] if home_group else 1

            # Find which non-home / blocked group contains the device
            target_device_oid = None
            source_group_oid = None
            for grp in new_groups:
                if grp["oid"] != home_oid:
                    for dev in grp.get("devices", []):
                        if dev["MACAddress"].lower() == mac_address:
                            target_device_oid = dev["_oid"]
                            source_group_oid = grp["oid"]
                            break
                if target_device_oid is not None:
                    break

            if target_device_oid is None:
                logger.info(f"Device {mac_address} not found in any blocked group.")
                return True

            # Move back to Home group
            post_data = f"move_id={home_oid}&device_id={target_device_oid}&group_id={source_group_oid}"
            r = self._encrypted_post("/parental_control.cgi?move_device_N", post_data)
            if r and r.status_code == 200:
                logger.info(f"Successfully unblocked {mac_address} (moved back to Home group)!")
                return True

            logger.error(f"Failed to unblock {mac_address}.")
            return False

        # Fallback to OLD mode
        blocked = self.list_blocked_devices()
        target_policy_oid = None
        for entry in blocked:
            if entry["mac"].lower() == mac_address:
                target_policy_oid = entry["policy_oid"]
                break

        if target_policy_oid is None:
            logger.warning(f"MAC {mac_address} not found in any blocked policy.")
            return False

        post_data = f"oid={target_policy_oid}"
        r = self._encrypted_post("/parental_control.cgi?del_pc_rule", post_data)
        if r and r.status_code == 200:
            logger.info(f"Successfully unblocked {mac_address}!")
            return True

        return False

    def logout(self):
        """Logout from the router."""
        try:
            self.session.get(f"{self.base_url}/login.cgi?out", timeout=5)
            self.is_authenticated = False
            logger.info("Logged out.")
        except Exception:
            pass


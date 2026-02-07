#!/usr/bin/env python3
"""
One.com DynDNS Updater for Home Assistant

This script runs as the main entry point for the Home Assistant add-on.
It periodically checks the public IP address and updates DNS records
at One.com when changes are detected. It also supports automatic SSL
certificate generation using Let's Encrypt with DNS-01 challenge.
"""

import filecmp
import json
import logging
import os
import shutil
import signal
import sys
import threading
import time
from typing import Optional

import requests

from onecom_api import OneComAPI, OneComAPIError
from certificate_manager import CertificateManager, CertificateManagerError

# Configure logging
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

# IP service endpoints
IP_SERVICES = {
    "ipify": "https://api.ipify.org",
    "ifconfig": "https://ifconfig.me/ip",
    "icanhazip": "https://icanhazip.com",
}

# File to store the last known IP
LAST_IP_FILE = "/data/last_ip.txt"
OPTIONS_FILE = "/data/options.json"
ACME_CHALLENGE_FILE = "/data/acme_challenge.json"

# Shared state/command files (accessible by both add-on and HA core via /config/)
ADDON_STATE_FILE = "/config/.onecom_dyndns_state.json"
ADDON_COMMAND_FILE = "/config/.onecom_dyndns_commands.json"

# Home Assistant Supervisor API
def get_supervisor_token():
    """Get the Supervisor token from various possible sources."""
    # Try environment variables first
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if token:
        return token
    
    # Try reading from s6 container environment
    token_paths = [
        "/run/s6/container_environment/SUPERVISOR_TOKEN",
        "/run/s6/container_environment/HASSIO_TOKEN",
        "/data/.supervisor_token",
    ]
    for path in token_paths:
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    token = f.read().strip()
                    if token:
                        return token
        except Exception:
            pass
    
    return ""

SUPERVISOR_TOKEN = get_supervisor_token()
HA_API_URL = "http://supervisor/core/api"


def send_ha_notification(title: str, message: str, notification_id: str = None):
    """Send a persistent notification to Home Assistant.
    
    Args:
        title: Notification title
        message: Notification message
        notification_id: Optional ID for the notification (allows updates)
    """
    if not SUPERVISOR_TOKEN:
        logging.warning("No SUPERVISOR_TOKEN available, cannot send notification")
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        }
        
        data = {
            "title": title,
            "message": message,
        }
        if notification_id:
            data["notification_id"] = notification_id
        
        response = requests.post(
            f"{HA_API_URL}/services/persistent_notification/create",
            headers=headers,
            json=data,
            timeout=10
        )
        response.raise_for_status()
        logging.debug("Notification sent: %s", title)
        return True
    except Exception as e:
        logging.warning("Failed to send notification: %s", e)
        return False


# Paths for custom component deployment
_COMPONENT_SOURCE = "/app/custom_components/onecom_dyndns"
_COMPONENT_TARGET = "/config/custom_components/onecom_dyndns"


def deploy_custom_component():
    """Deploy or update the custom component into the HA config directory.

    Copies ``/app/custom_components/onecom_dyndns`` (bundled in the Docker
    image) to ``/config/custom_components/onecom_dyndns`` so that the
    integration is available in Home Assistant without manual installation.

    The function compares the bundled ``manifest.json`` version against the
    installed version and only overwrites when the version has changed or
    the target does not exist yet.
    """
    if not os.path.isdir(_COMPONENT_SOURCE):
        logging.debug(
            "Custom component source %s not found, skipping deployment",
            _COMPONENT_SOURCE,
        )
        return False

    # Read bundled version
    src_manifest = os.path.join(_COMPONENT_SOURCE, "manifest.json")
    if not os.path.isfile(src_manifest):
        logging.warning("manifest.json missing in bundled component")
        return False

    try:
        with open(src_manifest, "r") as f:
            src_version = json.load(f).get("version", "0.0.0")
    except (IOError, json.JSONDecodeError) as exc:
        logging.warning("Cannot read bundled manifest.json: %s", exc)
        return False

    # Read currently installed version (if any)
    tgt_manifest = os.path.join(_COMPONENT_TARGET, "manifest.json")
    tgt_version = None
    if os.path.isfile(tgt_manifest):
        try:
            with open(tgt_manifest, "r") as f:
                tgt_version = json.load(f).get("version", "0.0.0")
        except (IOError, json.JSONDecodeError):
            tgt_version = None

    if tgt_version == src_version:
        logging.debug(
            "Custom component %s already installed (v%s)",
            _COMPONENT_TARGET,
            tgt_version,
        )
        return True

    # Deploy: create parent directory and copy the component tree
    try:
        os.makedirs(os.path.dirname(_COMPONENT_TARGET), exist_ok=True)

        if os.path.exists(_COMPONENT_TARGET):
            shutil.rmtree(_COMPONENT_TARGET)

        shutil.copytree(_COMPONENT_SOURCE, _COMPONENT_TARGET)

        logging.info(
            "Custom component deployed to %s (v%s → v%s)",
            _COMPONENT_TARGET,
            tgt_version or "none",
            src_version,
        )
        return True
    except Exception as exc:
        logging.error("Failed to deploy custom component: %s", exc)
        return False


def _build_discovery_config(options: dict) -> dict:
    """Build the discovery config payload from add-on options."""
    return {
        "username": options.get("username", ""),
        "password": options.get("password", ""),
        "domain": options.get("domain", ""),
        "subdomains": options.get("subdomains", [""]),
        "update_interval": options.get("update_interval", 5),
        "ip_service": options.get("ip_service", "ipify"),
        "ssl_enabled": options.get("ssl_enabled", False),
        "ssl_email": options.get("ssl_email", ""),
        "ssl_domains": options.get("ssl_domains", []),
        "ssl_staging": options.get("ssl_staging", False),
        "ssl_renewal_days": options.get("ssl_renewal_days", 30),
        "ssl_check_interval": options.get("ssl_check_interval", 12),
    }


def publish_addon_discovery(options: dict, retries: int = 5, delay: int = 10):
    """Publish discovery info via Supervisor so the custom component auto-configures.

    The Supervisor forwards the discovery to HA core which triggers
    ``async_step_hassio()`` in the integration's config flow.

    Because HA Core may not be ready immediately after the add-on starts
    (especially on first install), the function retries several times with
    an increasing delay.
    """
    if not SUPERVISOR_TOKEN:
        logging.warning("No SUPERVISOR_TOKEN, skipping discovery publication")
        return False

    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }

    discovery_data = {
        "service": "onecom_dyndns",
        "config": _build_discovery_config(options),
    }

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                "http://supervisor/discovery",
                headers=headers,
                json=discovery_data,
                timeout=10,
            )
            if response.ok:
                logging.info(
                    "Published discovery for onecom_dyndns integration "
                    "(attempt %d/%d)", attempt, retries,
                )
                return True
            else:
                logging.warning(
                    "Discovery publish attempt %d/%d returned %s: %s",
                    attempt, retries,
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            logging.warning(
                "Discovery publish attempt %d/%d failed: %s",
                attempt, retries, exc,
            )

        if attempt < retries:
            wait = delay * attempt
            logging.info(
                "Retrying discovery publication in %ds …", wait,
            )
            time.sleep(wait)

    logging.error(
        "Could not publish discovery after %d attempts", retries,
    )
    return False


def update_ha_sensor(entity_id: str, state: str, attributes: dict = None):
    """Update a Home Assistant sensor entity.
    
    Args:
        entity_id: Full entity ID (e.g., sensor.onecom_dyndns_ip)
        state: The state value
        attributes: Optional dictionary of attributes
    """
    if not SUPERVISOR_TOKEN:
        logging.debug("No SUPERVISOR_TOKEN available, cannot update sensor")
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        }
        
        data = {
            "state": state,
            "attributes": attributes or {},
        }
        
        # Add friendly name and icon if not provided
        if "friendly_name" not in data["attributes"]:
            if "ip" in entity_id:
                data["attributes"]["friendly_name"] = "One.com DynDNS IP"
                data["attributes"]["icon"] = "mdi:ip-network"
            elif "certificate" in entity_id:
                data["attributes"]["friendly_name"] = "One.com SSL Certificate"
                data["attributes"]["icon"] = "mdi:certificate"
            elif "dns" in entity_id:
                data["attributes"]["friendly_name"] = "One.com DNS Status"
                data["attributes"]["icon"] = "mdi:dns"
            elif "acme" in entity_id:
                data["attributes"]["friendly_name"] = "ACME Challenge"
                data["attributes"]["icon"] = "mdi:shield-key"
        
        response = requests.post(
            f"{HA_API_URL}/states/{entity_id}",
            headers=headers,
            json=data,
            timeout=10
        )
        response.raise_for_status()
        logging.debug("Sensor updated: %s = %s", entity_id, state)
        return True
    except Exception as e:
        logging.warning("Failed to update sensor %s: %s", entity_id, e)
        return False


def save_acme_challenge_info(domain: str, txt_name: str, txt_value: str):
    """Save ACME challenge information to file and send notification.
    
    Args:
        domain: The domain being validated
        txt_name: Full TXT record name
        txt_value: TXT record value
    """
    challenge_info = {
        "domain": domain,
        "txt_name": txt_name,
        "txt_value": txt_value,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "instruction": f"Create a TXT record with name '{txt_name}' and value '{txt_value}'"
    }
    
    # Save to file
    try:
        with open(ACME_CHALLENGE_FILE, "w") as f:
            json.dump(challenge_info, f, indent=2)
        logging.info(f"ACME challenge info saved to {ACME_CHALLENGE_FILE}")
    except Exception as e:
        logging.warning(f"Failed to save ACME challenge info: {e}")
    
    # Send Home Assistant notification
    notification_message = (
        f"**Domain:** {domain}\n\n"
        f"**TXT Record Name:**\n`{txt_name}`\n\n"
        f"**TXT Record Value:**\n`{txt_value}`\n\n"
        f"Create this TXT record at your DNS provider if automatic creation fails."
    )
    send_ha_notification(
        title="🔐 ACME DNS Challenge",
        message=notification_message,
        notification_id="onecom_dyndns_acme_challenge"
    )
    # The ACME challenge data is picked up by _write_state_file() from
    # the ACME_CHALLENGE_FILE, so the custom component gets it automatically.


class DynDNSUpdater:
    """Main DynDNS updater class."""

    def __init__(self, options: dict):
        """Initialize the updater with configuration options.

        Args:
            options: Configuration dictionary from Home Assistant
        """
        self.username = options.get("username", "")
        self.password = options.get("password", "")
        self.domain = options.get("domain", "")
        # Deduplicate subdomains while preserving order
        seen = set()
        subdomains_raw = options.get("subdomains", [""])
        self.subdomains = []
        for s in subdomains_raw:
            if s not in seen:
                seen.add(s)
                self.subdomains.append(s)
        self.update_interval = options.get("update_interval", 5)  # minutes
        self.ip_service = options.get("ip_service", "ipify")
        self.log_level = options.get("log_level", "info")

        # SSL options
        self.ssl_enabled = options.get("ssl_enabled", False)
        self.ssl_email = options.get("ssl_email", "")
        self.ssl_domains = options.get("ssl_domains", [])
        self.ssl_staging = options.get("ssl_staging", False)
        self.ssl_renewal_days = options.get("ssl_renewal_days", 30)
        self.ssl_check_interval = options.get("ssl_check_interval", 12)
        self.ssl_force_renewal = options.get("ssl_force_renewal", False)

        self._running = True
        self._stop_event = threading.Event()
        self._last_ip: Optional[str] = None
        self._last_ip_update: Optional[str] = None
        self._last_certificate_renewal: Optional[str] = None
        self._api: Optional[OneComAPI] = None
        self._cert_manager: Optional[CertificateManager] = None

        # Setup logging
        self._setup_logging()

        # Load last known IP
        self._load_last_ip()

        self._logger.info("One.com DynDNS Updater initialized")
        self._logger.info(f"Domain: {self.domain}")
        self._logger.info(f"Subdomains: {', '.join(s or '@' for s in self.subdomains)}")
        self._logger.info(f"Update interval: {self.update_interval} minutes")
        self._logger.info(f"SSL enabled: {self.ssl_enabled}")
        
        # Debug: Log available supervisor tokens
        self._logger.info(f"SUPERVISOR_TOKEN available: {bool(SUPERVISOR_TOKEN)}")
        if not SUPERVISOR_TOKEN:
            # List all environment variables starting with SUPER or HASS for debugging
            relevant_envs = {k: '***' for k, v in os.environ.items() 
                           if k.upper().startswith(('SUPER', 'HASS', 'HOME'))}
            self._logger.info(f"Relevant environment variables: {list(relevant_envs.keys())}")
            # Check for token files
            token_paths = [
                "/run/s6/container_environment/SUPERVISOR_TOKEN",
                "/run/s6/container_environment/HASSIO_TOKEN",
            ]
            for path in token_paths:
                exists = os.path.exists(path)
                self._logger.info(f"Token file {path}: {'exists' if exists else 'not found'}")

    def _setup_logging(self):
        """Configure logging based on options."""
        log_level = LOG_LEVELS.get(self.log_level.lower(), logging.INFO)

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler(sys.stdout)],
        )

        self._logger = logging.getLogger("onecom_dyndns")
        self._logger.setLevel(log_level)

    def _load_last_ip(self):
        """Load the last known IP from file."""
        try:
            if os.path.exists(LAST_IP_FILE):
                with open(LAST_IP_FILE, "r") as f:
                    self._last_ip = f.read().strip()
                    self._logger.debug("Loaded last IP: %s", self._last_ip)
        except IOError as e:
            self._logger.warning(f"Could not load last IP: {e}")

    def _save_last_ip(self, ip: str):
        """Save the current IP to file.

        Args:
            ip: The IP address to save
        """
        try:
            os.makedirs(os.path.dirname(LAST_IP_FILE), exist_ok=True)
            with open(LAST_IP_FILE, "w") as f:
                f.write(ip)
            self._last_ip = ip
            self._logger.debug("Saved IP: %s", ip)
        except IOError as e:
            self._logger.error(f"Could not save IP: {e}")

    def get_public_ip(self) -> Optional[str]:
        """Get the current public IP address.

        Returns:
            The public IP address or None if detection failed.
        """
        url = IP_SERVICES.get(self.ip_service, IP_SERVICES["ipify"])

        try:
            self._logger.debug("Fetching IP from %s", url)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            ip = response.text.strip()

            # Basic IP validation
            if self._is_valid_ip(ip):
                self._logger.debug("Detected IP: %s", ip)
                return ip
            else:
                self._logger.warning(f"Invalid IP response: {ip}")
                return None

        except requests.RequestException as e:
            self._logger.error(f"Failed to get public IP: {e}")
            return None

    def _is_valid_ip(self, ip: str) -> bool:
        """Validate an IPv4 address.

        Args:
            ip: The IP address string to validate

        Returns:
            True if valid IPv4 address, False otherwise.
        """
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False

    def update_dns(self, ip: str) -> bool:
        """Update DNS records with the new IP.

        Args:
            ip: The new IP address

        Returns:
            True if all updates were successful.
        """
        self._logger.info(f"Updating DNS records to {ip}")

        try:
            # Create API client and login
            api = OneComAPI(self.username, self.password, self.domain)
            api.login()

            # Update all subdomains
            results = api.update_all_subdomains(self.subdomains, ip)

            # Logout
            api.logout()

            # Check results
            success_count = sum(1 for r in results.values() if r["success"])
            total_count = len(results)

            self._logger.info(f"Updated {success_count}/{total_count} DNS records")

            # Log individual results
            for subdomain, result in results.items():
                if result["success"]:
                    self._logger.info(f"  ✓ {subdomain}.{self.domain}")
                else:
                    self._logger.error(f"  ✗ {subdomain}.{self.domain}: {result['error']}")

            return success_count == total_count

        except OneComAPIError as e:
            self._logger.error(f"DNS update failed: {e}")
            return False

    def check_and_update(self):
        """Check for IP changes and update DNS if needed."""
        self._logger.debug("Checking for IP changes...")

        # Get current public IP
        current_ip = self.get_public_ip()

        if not current_ip:
            self._logger.warning("Could not determine public IP")
            self._write_state_file(dns_status="error")
            return

        # Check if IP has changed
        if current_ip == self._last_ip:
            self._logger.debug("IP unchanged: %s", current_ip)
            self._write_state_file(current_ip=current_ip, dns_status="ok")
            return

        self._logger.info(f"IP changed: {self._last_ip or 'unknown'} -> {current_ip}")

        # Update DNS records
        if self.update_dns(current_ip):
            self._save_last_ip(current_ip)
            self._last_ip_update = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            self._logger.info("DNS update completed successfully")
            self._write_state_file(current_ip=current_ip, dns_status="ok")
        else:
            self._logger.error("DNS update failed - will retry on next interval")
            self._write_state_file(current_ip=current_ip, dns_status="error")

    # ------------------------------------------------------------------
    # Legacy sensor update methods (deprecated since 1.3.5)
    #
    # These pushed state directly to the HA REST API, creating orphaned
    # entities not linked to any device.  Replaced by _write_state_file()
    # which the custom component reads via its DataUpdateCoordinator.
    # Kept for backward compatibility but no longer called.
    # ------------------------------------------------------------------

    def _update_ip_sensor(self, ip: str):
        """Update the IP sensor in Home Assistant (deprecated)."""
        subdomains_list = [f"{s}.{self.domain}" if s else self.domain for s in self.subdomains]
        update_ha_sensor(
            "sensor.onecom_dyndns_ip",
            ip,
            {
                "friendly_name": "One.com DynDNS IP",
                "icon": "mdi:ip-network",
                "domain": self.domain,
                "subdomains": subdomains_list,
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    
    def _update_dns_sensor(self, status: str, ip: str):
        """Update the DNS status sensor in Home Assistant (deprecated)."""
        subdomains_list = [f"{s}.{self.domain}" if s else self.domain for s in self.subdomains]
        update_ha_sensor(
            "sensor.onecom_dyndns_dns_status",
            status,
            {
                "friendly_name": "One.com DNS Status",
                "icon": "mdi:dns" if status == "ok" else "mdi:dns-outline",
                "domain": self.domain,
                "current_ip": ip,
                "subdomains": subdomains_list,
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    
    def _update_certificate_sensor(self, cert_info: dict):
        """Update the certificate sensor in Home Assistant."""
        if not cert_info:
            return
        
        expiry_date = cert_info.get("not_valid_after", "unknown")
        days_remaining = cert_info.get("days_remaining", 0)
        
        update_ha_sensor(
            "sensor.onecom_dyndns_certificate",
            expiry_date,
            {
                "friendly_name": "One.com SSL Certificate",
                "icon": "mdi:certificate",
                "device_class": "timestamp",
                "days_remaining": days_remaining,
                "domains": cert_info.get("domains", []),
                "issuer": cert_info.get("issuer", "unknown"),
                "valid_from": cert_info.get("not_valid_before", "unknown"),
                "needs_renewal": cert_info.get("needs_renewal", False),
                "last_check": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    def _update_last_ip_update_sensor(self):
        """Update the 'last IP update' sensor in Home Assistant."""
        if not self._last_ip_update:
            return
        subdomains_list = [f"{s}.{self.domain}" if s else self.domain for s in self.subdomains]
        update_ha_sensor(
            "sensor.onecom_dyndns_last_ip_update",
            self._last_ip_update,
            {
                "friendly_name": "One.com DynDNS Last IP Update",
                "icon": "mdi:ip-network-outline",
                "device_class": "timestamp",
                "domain": self.domain,
                "current_ip": self._last_ip,
                "subdomains": subdomains_list,
            },
        )

    def _update_last_certificate_renewal_sensor(self):
        """Update the 'last certificate renewal' sensor in Home Assistant."""
        if not self._last_certificate_renewal:
            return
        update_ha_sensor(
            "sensor.onecom_dyndns_last_certificate_renewal",
            self._last_certificate_renewal,
            {
                "friendly_name": "One.com DynDNS Last Certificate Renewal",
                "icon": "mdi:certificate-outline",
                "device_class": "timestamp",
                "domains": self.ssl_domains if self.ssl_domains else [self.domain],
            },
        )

    # ------------------------------------------------------------------
    # Shared state / command files for the custom component integration
    # ------------------------------------------------------------------

    def _write_state_file(self, current_ip=None, dns_status="unknown"):
        """Write the current add-on state to a JSON file.

        The custom component reads this file via its DataUpdateCoordinator
        instead of independently polling IP services or DNS.
        """
        cert_info = None
        if self._cert_manager:
            try:
                cert_info = self._cert_manager.get_certificate_info()
            except Exception:
                pass

        # Read current ACME challenge (if any)
        acme_challenge = None
        try:
            if os.path.isfile(ACME_CHALLENGE_FILE):
                with open(ACME_CHALLENGE_FILE, "r") as f:
                    acme_challenge = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass

        subdomains_list = [
            f"{s}.{self.domain}" if s else self.domain
            for s in self.subdomains
        ]

        state = {
            "current_ip": current_ip or self._last_ip,
            "last_ip": self._last_ip,
            "domain": self.domain,
            "subdomains": subdomains_list,
            "ip_changed": current_ip is not None and current_ip != self._last_ip,
            "dns_status": dns_status,
            "last_update": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "last_ip_update": self._last_ip_update,
            "last_certificate_renewal": self._last_certificate_renewal,
            "ssl_enabled": self.ssl_enabled,
            "certificate_info": cert_info,
            "acme_challenge": acme_challenge,
        }

        try:
            tmp_path = ADDON_STATE_FILE + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2)
            # Atomic replace to avoid partial reads
            os.replace(tmp_path, ADDON_STATE_FILE)
            self._logger.debug("State file written: %s", ADDON_STATE_FILE)
        except Exception as exc:
            self._logger.debug("Failed to write state file: %s", exc)

    def _check_commands(self):
        """Check for and execute commands from the custom component.

        The custom component writes a command JSON file when a user presses
        a button (e.g. "Update DNS", "Renew Certificate").  The add-on
        picks up the command, executes it, and deletes the file.
        """
        if not os.path.isfile(ADDON_COMMAND_FILE):
            return

        try:
            with open(ADDON_COMMAND_FILE, "r") as f:
                cmd = json.load(f)
            # Remove the command file immediately so it isn't executed twice
            os.remove(ADDON_COMMAND_FILE)
        except (IOError, json.JSONDecodeError) as exc:
            self._logger.debug("Could not read command file: %s", exc)
            try:
                os.remove(ADDON_COMMAND_FILE)
            except OSError:
                pass
            return

        command = cmd.get("command", "")
        self._logger.info("Received command: %s", command)

        if command == "update_dns":
            if self._last_ip:
                if self.update_dns(self._last_ip):
                    self._last_ip_update = time.strftime(
                        "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()
                    )
                    self._write_state_file(
                        current_ip=self._last_ip, dns_status="ok"
                    )
                else:
                    self._write_state_file(
                        current_ip=self._last_ip, dns_status="error"
                    )
        elif command == "check_ip":
            self.check_and_update()
        elif command == "renew_certificate":
            if self._cert_manager and self.ssl_enabled:
                try:
                    if self._cert_manager.request_certificate(force=True):
                        self._logger.info("Forced certificate renewal succeeded")
                    else:
                        self._logger.error("Forced certificate renewal failed")
                except Exception as exc:
                    self._logger.error("Certificate renewal error: %s", exc)
                self._write_state_file(
                    current_ip=self._last_ip, dns_status="ok"
                )
        else:
            self._logger.warning("Unknown command: %s", command)

    def _ssl_event_callback(self, event_type: str, data: dict):
        """Handle SSL certificate events.

        Args:
            event_type: Type of event
            data: Event data
        """
        if event_type == "renewed":
            self._logger.info("SSL certificate renewed successfully")
            domains = data.get("domains", [])
            self._logger.info(f"Certificate domains: {', '.join(domains)}")
            cert_info = data.get("certificate", {})
            # Track renewal timestamp
            self._last_certificate_renewal = time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()
            )
            
            # Send notification to user
            expiry = cert_info.get("not_valid_after", "unknown") if cert_info else "unknown"
            send_ha_notification(
                title="🔒 SSL Certificate Renewed",
                message=(
                    f"**Domains:** {', '.join(domains)}\n\n"
                    f"**Valid until:** {expiry}\n\n"
                    f"**Certificate:** `/ssl/fullchain.pem`\n\n"
                    f"**Action required:** Restart NGINX or Home Assistant to use the new certificate!"
                ),
                notification_id="onecom_dyndns_certificate_renewed",
            )
            # Update state file so the custom component picks up the change
            self._write_state_file(current_ip=self._last_ip, dns_status="ok")
        elif event_type == "error":
            self._logger.error(f"SSL certificate error: {data.get('error', 'Unknown error')}")
        elif event_type == "expiring":
            days = data.get("days_remaining", 0)
            self._logger.warning(f"SSL certificate expiring in {days} days, renewal started")
        elif event_type == "expiring_soon":
            days = data.get("days_remaining", 0)
            self._logger.info(f"SSL certificate will expire in {days} days")
        elif event_type == "certificate_invalid_online":
            invalid_domains = data.get("invalid_domains", [])
            self._logger.warning(f"Online certificate check failed for: {', '.join(invalid_domains)}")
            for domain, result in data.get("results", {}).items():
                if not result.get("valid"):
                    error = result.get("error", "Unknown error")
                    self._logger.warning(f"  - {domain}: {error}")

    def _start_ssl_manager(self):
        """Start the SSL certificate manager if enabled."""
        if not self.ssl_enabled:
            return

        if not self.ssl_email:
            self._logger.error("SSL enabled but no email provided")
            return

        # Use domain if no specific SSL domains configured
        ssl_domains = self.ssl_domains if self.ssl_domains else [self.domain]

        # Add subdomains to SSL domains if they're not already included
        for subdomain in self.subdomains:
            if subdomain:
                full_domain = f"{subdomain}.{self.domain}"
                if full_domain not in ssl_domains:
                    ssl_domains.append(full_domain)

        self._logger.info(f"Starting SSL certificate manager for: {', '.join(ssl_domains)}")

        try:
            self._cert_manager = CertificateManager(
                username=self.username,
                password=self.password,
                domain=self.domain,
                email=self.ssl_email,
                ssl_domains=ssl_domains,
                staging=self.ssl_staging,
                renewal_days=self.ssl_renewal_days,
                check_interval_hours=self.ssl_check_interval,
                challenge_callback=save_acme_challenge_info,
            )

            # Register callback for SSL events
            self._cert_manager.add_callback(self._ssl_event_callback)

            # Force renewal if requested
            if self.ssl_force_renewal:
                self._logger.info("Force renewal requested - requesting new certificate...")
                if self._cert_manager.request_certificate(force=True):
                    self._logger.info("Force renewal completed successfully")
                else:
                    self._logger.error("Force renewal failed")

            # Start the certificate manager
            self._cert_manager.start()

            self._logger.info("SSL certificate manager started")

            # Write initial state so custom component can show cert info
            self._write_state_file(current_ip=self._last_ip, dns_status="ok")

        except Exception as e:
            self._logger.error(f"Failed to start SSL certificate manager: {e}")

    def _stop_ssl_manager(self):
        """Stop the SSL certificate manager."""
        if self._cert_manager:
            self._cert_manager.stop()
            self._cert_manager = None

    def run(self):
        """Main run loop."""
        self._logger.info("Starting DynDNS updater...")

        # Validate configuration
        if not all([self.username, self.password, self.domain]):
            self._logger.error("Missing required configuration (username, password, or domain)")
            sys.exit(1)

        # Start SSL certificate manager if enabled
        self._start_ssl_manager()

        # Initial check
        self.check_and_update()

        # Main loop – wake up every 5 seconds to check for commands,
        # but only run the full IP check on the configured interval.
        interval_seconds = self.update_interval * 60
        elapsed = 0.0
        poll_interval = 5  # seconds between command checks

        while self._running:
            if self._stop_event.wait(timeout=poll_interval):
                break  # stop() was called

            elapsed += poll_interval

            # Check for commands from the custom component every cycle
            if self._running:
                self._check_commands()

            # Full IP check on the configured interval
            if self._running and elapsed >= interval_seconds:
                elapsed = 0.0
                self.check_and_update()

        # Stop SSL manager
        self._stop_ssl_manager()

        self._logger.info("DynDNS updater stopped")

    def stop(self):
        """Stop the updater gracefully."""
        self._logger.info("Stopping DynDNS updater...")
        self._running = False
        self._stop_event.set()  # Wake up the main loop immediately
        self._stop_ssl_manager()


def load_options() -> dict:
    """Load configuration options from Home Assistant.

    Returns:
        Dictionary with configuration options.
    """
    logger = logging.getLogger("onecom_dyndns")

    # Try to load from Home Assistant options file
    if os.path.exists(OPTIONS_FILE):
        try:
            with open(OPTIONS_FILE, "r") as f:
                options = json.load(f)
                logger.info("Loaded configuration from Home Assistant")
                return options
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load options: {e}")

    # Fall back to environment variables (for testing)
    logger.warning("Using environment variables for configuration")

    # Parse SSL domains from comma-separated string
    ssl_domains_str = os.environ.get("ONECOM_SSL_DOMAINS", "")
    ssl_domains = [d.strip() for d in ssl_domains_str.split(",") if d.strip()]

    return {
        "username": os.environ.get("ONECOM_USERNAME", ""),
        "password": os.environ.get("ONECOM_PASSWORD", ""),
        "domain": os.environ.get("ONECOM_DOMAIN", ""),
        "subdomains": os.environ.get("ONECOM_SUBDOMAINS", "").split(","),
        "update_interval": int(os.environ.get("ONECOM_INTERVAL", "5")),
        "ip_service": os.environ.get("ONECOM_IP_SERVICE", "ipify"),
        "log_level": os.environ.get("ONECOM_LOG_LEVEL", "info"),
        "ssl_enabled": os.environ.get("ONECOM_SSL_ENABLED", "false").lower() == "true",
        "ssl_email": os.environ.get("ONECOM_SSL_EMAIL", ""),
        "ssl_domains": ssl_domains,
        "ssl_staging": os.environ.get("ONECOM_SSL_STAGING", "false").lower() == "true",
        "ssl_renewal_days": int(os.environ.get("ONECOM_SSL_RENEWAL_DAYS", "30")),
        "ssl_check_interval": int(os.environ.get("ONECOM_SSL_CHECK_INTERVAL", "12")),
        "ssl_force_renewal": os.environ.get("ONECOM_SSL_FORCE_RENEWAL", "false").lower() == "true",
    }


def main():
    """Main entry point."""
    # Load options
    options = load_options()

    # Deploy custom component into /config/custom_components/ so the
    # integration is available in Home Assistant without manual setup.
    deploy_custom_component()

    # Publish discovery so the HA custom component auto-configures
    publish_addon_discovery(options)

    # Create updater
    updater = DynDNSUpdater(options)

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        updater.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run the updater
    updater.run()


if __name__ == "__main__":
    main()

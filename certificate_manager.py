"""
Certificate Manager Module

This module provides high-level certificate management functionality,
including scheduling renewals and status monitoring.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from onecom_api import OneComAPI, OneComAPIError
from acme_manager import ACMEManager, ACMEManagerError

_LOGGER = logging.getLogger(__name__)

# Default paths
CERT_STATUS_FILE = "/data/ssl/cert_status.json"
DEFAULT_CERT_PATH = "/ssl/fullchain.pem"
DEFAULT_KEY_PATH = "/ssl/privkey.pem"


class CertificateManagerError(Exception):
    """Exception raised for Certificate Manager errors."""
    pass


class CertificateManager:
    """High-level certificate management with automatic renewal."""

    def __init__(
        self,
        username: str,
        password: str,
        domain: str,
        email: str,
        ssl_domains: Optional[List[str]] = None,
        staging: bool = False,
        cert_path: str = DEFAULT_CERT_PATH,
        key_path: str = DEFAULT_KEY_PATH,
        renewal_days: int = 30,
        check_interval_hours: int = 12,
    ):
        """Initialize the Certificate Manager.

        Args:
            username: One.com username
            password: One.com password
            domain: One.com domain
            email: Email for Let's Encrypt account
            ssl_domains: Domains to include in certificate (defaults to domain)
            staging: Use Let's Encrypt staging server
            cert_path: Path to save certificate
            key_path: Path to save private key
            renewal_days: Days before expiry to trigger renewal
            check_interval_hours: Hours between renewal checks
        """
        self.username = username
        self.password = password
        self.domain = domain
        self.email = email
        self.ssl_domains = ssl_domains or [domain]
        self.staging = staging
        self.cert_path = cert_path
        self.key_path = key_path
        self.renewal_days = renewal_days
        self.check_interval = check_interval_hours * 3600

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_check: Optional[datetime] = None
        self._last_renewal: Optional[datetime] = None
        self._callbacks: List[Callable[[str, Dict[str, Any]], None]] = []

        _LOGGER.info(f"Certificate Manager initialized for {domain}")
        _LOGGER.info(f"SSL domains: {', '.join(self.ssl_domains)}")
        _LOGGER.info(f"Staging mode: {staging}")

    def _ensure_directories(self):
        """Ensure all necessary directories exist."""
        for path in [self.cert_path, self.key_path, CERT_STATUS_FILE]:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)

    def add_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Add a callback for certificate events.

        Args:
            callback: Function to call with (event_type, event_data)
        """
        self._callbacks.append(callback)

    def _notify(self, event_type: str, data: Dict[str, Any]):
        """Notify all registered callbacks of an event.

        Args:
            event_type: Type of event (e.g., 'renewed', 'error', 'expiring')
            data: Event data dictionary
        """
        for callback in self._callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                _LOGGER.warning(f"Callback error: {e}")

    def get_certificate_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current certificate.

        Returns:
            Dictionary with certificate info or None if no certificate.
        """
        if not os.path.exists(self.cert_path):
            return None

        try:
            with open(self.cert_path, "rb") as f:
                cert_data = f.read()

            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Extract subject info
            subject = {}
            for attr in cert.subject:
                subject[attr.oid._name] = attr.value

            # Extract SAN domains
            try:
                san = cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                )
                domains = [name.value for name in san.value]
            except x509.ExtensionNotFound:
                domains = [subject.get("commonName", "")]

            # Calculate days remaining
            days_remaining = (cert.not_valid_after - datetime.now()).days

            return {
                "subject": subject,
                "issuer": {attr.oid._name: attr.value for attr in cert.issuer},
                "domains": domains,
                "not_valid_before": cert.not_valid_before.isoformat(),
                "not_valid_after": cert.not_valid_after.isoformat(),
                "days_remaining": days_remaining,
                "serial_number": str(cert.serial_number),
                "needs_renewal": days_remaining <= self.renewal_days,
            }

        except Exception as e:
            _LOGGER.error(f"Failed to read certificate info: {e}")
            return None

    def _save_status(self, status: Dict[str, Any]):
        """Save certificate status to file.

        Args:
            status: Status dictionary to save
        """
        self._ensure_directories()

        status["last_updated"] = datetime.now().isoformat()

        try:
            with open(CERT_STATUS_FILE, "w") as f:
                json.dump(status, f, indent=2)
        except IOError as e:
            _LOGGER.warning(f"Failed to save status: {e}")

    def _load_status(self) -> Dict[str, Any]:
        """Load certificate status from file.

        Returns:
            Status dictionary.
        """
        if not os.path.exists(CERT_STATUS_FILE):
            return {}

        try:
            with open(CERT_STATUS_FILE, "r") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            _LOGGER.warning(f"Failed to load status: {e}")
            return {}

    def request_certificate(self, force: bool = False) -> bool:
        """Request a new certificate.

        Args:
            force: Force renewal even if certificate is still valid

        Returns:
            True if successful.
        """
        _LOGGER.info("Starting certificate request...")

        # Check if renewal is needed
        cert_info = self.get_certificate_info()
        if cert_info and not force:
            if not cert_info["needs_renewal"]:
                _LOGGER.info(
                    f"Certificate still valid for {cert_info['days_remaining']} days, "
                    "skipping renewal"
                )
                return True

        api = None
        try:
            # Create One.com API client
            api = OneComAPI(self.username, self.password, self.domain)
            api.login()

            # Clean up any old ACME challenge records
            api.cleanup_acme_records()

            # Create ACME manager
            acme = ACMEManager(
                email=self.email,
                onecom_api=api,
                staging=self.staging,
                cert_path=self.cert_path,
                key_path=self.key_path,
            )

            # Obtain certificate
            if acme.obtain_and_save_certificate(self.ssl_domains):
                self._last_renewal = datetime.now()

                # Save status
                cert_info = self.get_certificate_info()
                self._save_status({
                    "status": "valid",
                    "last_renewal": self._last_renewal.isoformat(),
                    "certificate": cert_info,
                })

                # Notify callbacks
                self._notify("renewed", {
                    "domains": self.ssl_domains,
                    "certificate": cert_info,
                })

                _LOGGER.info("Certificate request completed successfully")
                return True
            else:
                self._save_status({
                    "status": "error",
                    "error": "Certificate issuance failed",
                })
                self._notify("error", {"error": "Certificate issuance failed"})
                return False

        except OneComAPIError as e:
            error_msg = f"One.com API error: {e}"
            _LOGGER.error(error_msg)
            self._save_status({"status": "error", "error": error_msg})
            self._notify("error", {"error": error_msg})
            return False

        except ACMEManagerError as e:
            error_msg = f"ACME error: {e}"
            _LOGGER.error(error_msg)
            self._save_status({"status": "error", "error": error_msg})
            self._notify("error", {"error": error_msg})
            return False

        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            _LOGGER.error(error_msg)
            self._save_status({"status": "error", "error": error_msg})
            self._notify("error", {"error": error_msg})
            return False

        finally:
            if api:
                api.logout()

    def _check_and_renew(self):
        """Check certificate and renew if needed."""
        self._last_check = datetime.now()
        _LOGGER.debug("Checking certificate status...")

        cert_info = self.get_certificate_info()

        if cert_info is None:
            _LOGGER.info("No certificate found, requesting new certificate...")
            self.request_certificate()
            return

        days_remaining = cert_info["days_remaining"]
        _LOGGER.info(f"Certificate expires in {days_remaining} days")

        if days_remaining <= self.renewal_days:
            _LOGGER.info(f"Certificate expiring soon, starting renewal...")
            self._notify("expiring", {
                "days_remaining": days_remaining,
                "domains": cert_info["domains"],
            })
            self.request_certificate()
        elif days_remaining <= self.renewal_days + 7:
            # Warn about upcoming renewal
            self._notify("expiring_soon", {
                "days_remaining": days_remaining,
                "domains": cert_info["domains"],
            })

    def _renewal_loop(self):
        """Background loop for automatic renewal checks."""
        _LOGGER.info("Starting certificate renewal loop...")

        # Initial check
        self._check_and_renew()

        while self._running:
            # Sleep in small intervals for responsive shutdown
            sleep_time = 0
            while sleep_time < self.check_interval and self._running:
                time.sleep(60)  # Check every minute for shutdown
                sleep_time += 60

            if self._running:
                self._check_and_renew()

        _LOGGER.info("Certificate renewal loop stopped")

    def start(self):
        """Start the automatic renewal background thread."""
        if self._running:
            _LOGGER.warning("Certificate manager already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._renewal_loop, daemon=True)
        self._thread.start()
        _LOGGER.info("Certificate manager started")

    def stop(self):
        """Stop the automatic renewal background thread."""
        if not self._running:
            return

        _LOGGER.info("Stopping certificate manager...")
        self._running = False

        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

        _LOGGER.info("Certificate manager stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the certificate manager.

        Returns:
            Status dictionary.
        """
        cert_info = self.get_certificate_info()
        saved_status = self._load_status()

        return {
            "running": self._running,
            "staging": self.staging,
            "ssl_domains": self.ssl_domains,
            "cert_path": self.cert_path,
            "key_path": self.key_path,
            "renewal_days": self.renewal_days,
            "check_interval_hours": self.check_interval / 3600,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "last_renewal": self._last_renewal.isoformat() if self._last_renewal else None,
            "certificate": cert_info,
            "saved_status": saved_status,
        }

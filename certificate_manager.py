"""
Certificate Manager Module

This module provides high-level certificate management functionality,
including scheduling renewals and status monitoring.
"""

import json
import logging
import os
import socket
import ssl
import threading
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from acme_manager import ACMEManager, ACMEManagerError
from onecom_api import OneComAPI, OneComAPIError

_LOGGER = logging.getLogger(__name__)

# Default paths
CERT_STATUS_FILE = "/data/ssl/cert_status.json"
DEFAULT_CERT_PATH = "/ssl/fullchain.pem"
DEFAULT_KEY_PATH = "/ssl/privkey.pem"


class CertificateManagerError(Exception):
    """Exception raised for Certificate Manager errors."""


class CertificateManager:
    """High-level certificate management with automatic renewal."""

    def __init__(
        self,
        username: str,
        password: str,
        domain: str,
        email: str,
        ssl_domains: list[str] | None = None,
        staging: bool = False,
        cert_path: str = DEFAULT_CERT_PATH,
        key_path: str = DEFAULT_KEY_PATH,
        renewal_days: int = 30,
        check_interval_hours: int = 12,
        challenge_callback: Callable[[str, str, str], None] | None = None,
        status_file: str | None = None,
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
            challenge_callback: Callback function(domain, txt_name, txt_value) for ACME challenges
            status_file: Path to certificate status file (defaults to CERT_STATUS_FILE)
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
        self.challenge_callback = challenge_callback
        self.status_file = status_file or CERT_STATUS_FILE

        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_check: datetime | None = None
        self._last_renewal: datetime | None = None
        self._callbacks: list[Callable[[str, dict[str, Any]], None]] = []
        self._directories_created = False

        # Certificate info cache: avoids re-reading and parsing the PEM
        # file on every state-write cycle.  Invalidated when a new
        # certificate is saved.
        self._cached_cert_info: dict[str, Any] | None = None

        _LOGGER.info("Certificate Manager initialized for %s", domain)
        _LOGGER.info("SSL domains: %s", ', '.join(self.ssl_domains))
        _LOGGER.info("Staging mode: %s", staging)

    def _ensure_directories(self):
        """Ensure all necessary directories exist.

        Only performs the filesystem check once; subsequent calls return
        immediately.
        """
        if self._directories_created:
            return
        for path in [self.cert_path, self.key_path, self.status_file]:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        self._directories_created = True

    def add_callback(self, callback: Callable[[str, dict[str, Any]], None]):
        """Add a callback for certificate events.

        Args:
            callback: Function to call with (event_type, event_data)
        """
        self._callbacks.append(callback)

    def _notify(self, event_type: str, data: dict[str, Any]):
        """Notify all registered callbacks of an event.

        Args:
            event_type: Type of event (e.g., 'renewed', 'error', 'expiring')
            data: Event data dictionary
        """
        for callback in self._callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                _LOGGER.warning("Callback error: %s", e)

    def get_certificate_info(self) -> dict[str, Any] | None:
        """Get information about the current certificate.

        Returns a cached result if the certificate has not changed since the
        last call.  The cache is invalidated when ``request_certificate``
        writes a new PEM file or when the certificate file no longer exists
        on disk (e.g. deleted by an external process).

        Returns:
            Dictionary with certificate info or None if no certificate.
        """
        if not os.path.exists(self.cert_path):
            self._cached_cert_info = None
            return None

        if self._cached_cert_info is not None:
            return self._cached_cert_info

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

            # Calculate days remaining (use UTC-aware methods to avoid deprecation)
            try:
                expiry = cert.not_valid_after_utc
                valid_from = cert.not_valid_before_utc
                now = datetime.now(timezone.utc)
            except AttributeError:
                # Fallback for older cryptography versions
                expiry = cert.not_valid_after
                valid_from = cert.not_valid_before
                now = datetime.now()

            days_remaining = (expiry - now).days

            info = {
                "subject": subject,
                "issuer": {attr.oid._name: attr.value for attr in cert.issuer},
                "domains": domains,
                "not_valid_before": valid_from.isoformat(),
                "not_valid_after": expiry.isoformat(),
                "days_remaining": days_remaining,
                "serial_number": str(cert.serial_number),
                "needs_renewal": days_remaining <= self.renewal_days,
            }
            self._cached_cert_info = info
            return info

        except Exception as e:
            _LOGGER.error("Failed to read certificate info: %s", e)
            return None

    def _save_status(self, status: dict[str, Any]):
        """Save certificate status to file.

        Args:
            status: Status dictionary to save
        """
        self._ensure_directories()

        status["last_updated"] = datetime.now().isoformat()

        try:
            with open(self.status_file, "w") as f:
                json.dump(status, f, indent=2)
        except OSError as e:
            _LOGGER.warning("Failed to save status: %s", e)

    def _load_status(self) -> dict[str, Any]:
        """Load certificate status from file.

        Returns:
            Status dictionary.
        """
        if not os.path.exists(self.status_file):
            return {}

        try:
            with open(self.status_file, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            _LOGGER.warning("Failed to load status: %s", e)
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
                    "Certificate still valid for %s days, skipping renewal",
                    cert_info['days_remaining'],
                )
                return True

        api = None
        try:
            # Create One.com API client
            api = OneComAPI(self.username, self.password, self.domain)
            api.login()

            # Clean up any old ACME challenge records
            api.cleanup_acme_records()

            # Create ACME manager (share stop_event for graceful shutdown)
            acme = ACMEManager(
                email=self.email,
                onecom_api=api,
                staging=self.staging,
                cert_path=self.cert_path,
                key_path=self.key_path,
                challenge_callback=self.challenge_callback,
                stop_event=self._stop_event,
            )

            # Obtain certificate
            if acme.obtain_and_save_certificate(self.ssl_domains):
                self._last_renewal = datetime.now()

                # Invalidate cached cert info so the next read picks up the
                # freshly saved certificate.
                self._cached_cert_info = None

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
            error_msg = f"Unexpected error ({type(e).__name__}): {e}"
            _LOGGER.error(error_msg)
            _LOGGER.error("Traceback:\n%s", traceback.format_exc())
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
        _LOGGER.info("Certificate expires in %s days", days_remaining)

        if days_remaining <= self.renewal_days:
            _LOGGER.info("Certificate expiring soon, starting renewal...")
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

        # Verify online certificates
        _LOGGER.debug("Verifying online certificates...")
        online_results = self.verify_all_domains()

        # Log summary
        valid_count = sum(1 for r in online_results.values() if r["valid"])
        total_count = len(online_results)
        _LOGGER.info("Online certificate verification: %s/%s domains valid", valid_count, total_count)

    def _renewal_loop(self):
        """Background loop for automatic renewal checks."""
        _LOGGER.info("Starting certificate renewal loop...")

        # Initial check
        self._check_and_renew()

        while self._running:
            # Block until timeout or stop signal; single syscall replaces
            # check_interval/60 individual sleep(60) calls.
            if self._stop_event.wait(timeout=self.check_interval):
                break  # stop() was called

            if self._running:
                self._check_and_renew()

        _LOGGER.info("Certificate renewal loop stopped")

    def start(self):
        """Start the automatic renewal background thread."""
        if self._running:
            _LOGGER.warning("Certificate manager already running")
            return

        # Clear the stop event so a previously stopped manager can be
        # restarted without the renewal loop exiting immediately.
        self._stop_event.clear()
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
        self._stop_event.set()  # Wake up the renewal loop immediately

        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

        _LOGGER.info("Certificate manager stopped")

    def verify_online_certificate(
        self,
        domain: str,
        port: int = 443,
        timeout: int = 10,
        ssl_context: ssl.SSLContext = None,
    ) -> dict[str, Any]:
        """Verify that a valid certificate is served for a domain.

        Args:
            domain: The domain to check
            port: The port to connect to (default 443)
            timeout: Connection timeout in seconds
            ssl_context: Optional pre-created SSLContext (avoids repeated
                         re-creation when checking multiple domains)

        Returns:
            Dictionary with verification results.
        """
        result = {
            "domain": domain,
            "valid": False,
            "reachable": False,
            "error": None,
            "certificate": None,
        }

        try:
            context = ssl_context or ssl.create_default_context()
            with socket.create_connection((domain, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    result["reachable"] = True
                    cert = ssock.getpeercert()

                    # Extract certificate info
                    subject = dict(x[0] for x in cert.get("subject", []))
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    sans = [x[1] for x in cert.get("subjectAltName", [])]

                    # Parse dates
                    not_after_str = cert.get("notAfter", "")
                    not_before_str = cert.get("notBefore", "")

                    result["certificate"] = {
                        "subject": subject.get("commonName", ""),
                        "issuer": issuer.get("organizationName", ""),
                        "issuer_cn": issuer.get("commonName", ""),
                        "not_before": not_before_str,
                        "not_after": not_after_str,
                        "sans": sans,
                    }

                    # Check if domain is covered
                    domain_covered = domain in sans
                    if not domain_covered:
                        # Check for wildcard
                        parts = domain.split(".", 1)
                        if len(parts) == 2:
                            wildcard = f"*.{parts[1]}"
                            domain_covered = wildcard in sans

                    result["domain_covered"] = domain_covered
                    result["valid"] = domain_covered

                    _LOGGER.info("Online certificate for %s: valid=%s, issuer=%s", domain, domain_covered, issuer.get('organizationName', 'Unknown'))

        except TimeoutError:
            result["error"] = "Connection timeout"
            _LOGGER.warning("Certificate check for %s: timeout", domain)
        except socket.gaierror as e:
            result["error"] = f"DNS resolution failed: {e}"
            _LOGGER.warning("Certificate check for %s: DNS failed", domain)
        except ssl.SSLCertVerificationError as e:
            result["error"] = f"Certificate verification failed: {e}"
            result["reachable"] = True
            _LOGGER.error("Certificate check for %s: SSL error - %s", domain, e)
        except ConnectionRefusedError:
            result["error"] = "Connection refused - no HTTPS server"
            _LOGGER.warning("Certificate check for %s: connection refused", domain)
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            _LOGGER.error("Certificate check for %s: %s", domain, e)

        return result

    def verify_all_domains(self) -> dict[str, dict[str, Any]]:
        """Verify certificates for all configured domains.

        Returns:
            Dictionary mapping domains to their verification results.
        """
        results = {}
        all_valid = True

        # Create SSL context once and reuse for all domain checks
        shared_ctx = ssl.create_default_context()

        for domain in self.ssl_domains:
            result = self.verify_online_certificate(domain, ssl_context=shared_ctx)
            results[domain] = result
            if not result["valid"]:
                all_valid = False

        # Notify if any domain has an invalid certificate
        if not all_valid:
            invalid_domains = [d for d, r in results.items() if not r["valid"]]
            self._notify("certificate_invalid_online", {
                "invalid_domains": invalid_domains,
                "results": results,
            })

        return results

    def get_status(self) -> dict[str, Any]:
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

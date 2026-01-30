"""
One.com DNS API Module for Home Assistant Integration.

This module provides functionality to interact with One.com's DNS management
through their web interface.
"""

import logging
import re
import time
from typing import Optional, List, Dict, Any

import requests

_LOGGER = logging.getLogger(__name__)


class OneComAPIError(Exception):
    """Exception raised for One.com API errors."""
    pass


class OneComAPI:
    """Class to interact with One.com DNS settings."""

    BASE_URL = "https://www.one.com"
    ADMIN_URL = f"{BASE_URL}/admin"
    LOGIN_URL = f"{BASE_URL}/admin/login.do"

    def __init__(self, username: str, password: str, domain: str):
        """Initialize the One.com API client."""
        self.username = username
        self.password = password
        self.domain = domain
        self.session: Optional[requests.Session] = None
        self._logged_in = False

    def _create_session(self) -> requests.Session:
        """Create a new requests session with appropriate headers."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })
        return session

    def _find_between(self, text: str, start: str, end: str) -> str:
        """Extract text between two markers."""
        try:
            start_idx = text.find(start) + len(start)
            end_idx = text.find(end, start_idx)
            return text[start_idx:end_idx]
        except (ValueError, IndexError):
            return ""

    def login(self) -> bool:
        """Log into the One.com admin panel."""
        _LOGGER.debug("Attempting to log into One.com")

        self.session = self._create_session()

        try:
            response = self.session.get(self.ADMIN_URL, allow_redirects=True)
            response.raise_for_status()
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to connect to One.com: {e}")

        form_action = self._find_between(
            response.text,
            '<form id="kc-form-login"',
            '">'
        )
        login_url = self._find_between(form_action, 'action="', '"')

        if not login_url:
            match = re.search(r'action="([^"]+)"', response.text)
            if match:
                login_url = match.group(1)
            else:
                raise OneComAPIError("Could not find login form URL")

        # Decode HTML entities in URL
        login_url = login_url.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')

        # Extract any hidden form fields (like CSRF tokens)
        hidden_fields = {}
        hidden_pattern = re.findall(
            r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
            response.text
        )
        for name, value in hidden_pattern:
            hidden_fields[name] = value

        # Also try alternative pattern (value before name)
        hidden_pattern2 = re.findall(
            r'<input[^>]*value=["\']([^"\']*)["\'][^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\']',
            response.text
        )
        for value, name in hidden_pattern2:
            if name not in hidden_fields:
                hidden_fields[name] = value

        # Perform login
        login_data = {
            "username": self.username,
            "password": self.password,
        }

        # Add any hidden fields (CSRF tokens, etc.)
        login_data.update(hidden_fields)

        # Set headers for form submission
        post_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://account.one.com",
            "Referer": response.url,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }

        try:
            response = self.session.post(
                login_url,
                data=login_data,
                headers=post_headers,
                allow_redirects=True
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise OneComAPIError(f"Login request failed: {e}")

        _LOGGER.debug(f"Login response URL: {response.url}")

        # Check if login was successful by looking for admin panel indicators
        if "logout" in response.text.lower() or "dns" in response.url.lower() or "/admin" in response.url:
            _LOGGER.info("Successfully logged into One.com")
            self._logged_in = True
            return True

        # Check for specific error messages indicating wrong credentials
        response_lower = response.text.lower()

        # Log detailed debug information if we're still on account.one.com
        if "account.one.com" in response.url:
            _LOGGER.debug(f"Still on account.one.com after login attempt")

            # Extract any error message from the page - try multiple patterns
            error_patterns = [
                r'<span[^>]*class="[^"]*error[^"]*"[^>]*>([^<]+)</span>',
                r'<div[^>]*class="[^"]*alert[^"]*"[^>]*>\s*<[^>]+>\s*([^<]+)',
                r'<div[^>]*class="[^"]*alert[^"]*"[^>]*>([^<]+)',
                r'class="kc-feedback-text">([^<]+)<',
                r'<span[^>]*id="input-error[^"]*"[^>]*>([^<]+)</span>',
            ]

            for pattern in error_patterns:
                match = re.search(pattern, response.text, re.IGNORECASE | re.DOTALL)
                if match and match.group(1).strip():
                    _LOGGER.error(f"Login error from One.com: {match.group(1).strip()}")
                    break

        # Check for specific credential errors (but not "ungültiger code" which is OAuth error)
        if "invalid username or password" in response_lower or "invalid credentials" in response_lower:
            raise OneComAPIError("Invalid credentials - please check username and password")

        # Check for German credential error (not OAuth code error)
        if "ungültige anmeldedaten" in response_lower or "ungültiger benutzername" in response_lower:
            raise OneComAPIError("Invalid credentials - please check username and password")

        # Check for OAuth code errors
        if "ungültiger code" in response_lower or "invalid code" in response_lower:
            _LOGGER.error("OAuth session code error - One.com rejected the login session")
            raise OneComAPIError("Login session expired or invalid. This may be a temporary issue - please try again.")

        # If we're still on the login page (account.one.com), login likely failed
        if "account.one.com" in response.url and "kc-form-login" in response.text:
            _LOGGER.error("Still on login page after authentication attempt")
            raise OneComAPIError("Login failed - still on login page. Please verify your One.com credentials and ensure 2FA is disabled.")

        # Try to access the admin panel to verify login
        _LOGGER.debug("Login status uncertain, verifying by accessing admin panel...")
        try:
            verify_response = self.session.get(f"{self.ADMIN_URL}/", allow_redirects=True)
            if "/admin" in verify_response.url and "account.one.com" not in verify_response.url:
                _LOGGER.info("Successfully logged into One.com (verified)")
                self._logged_in = True
                return True
        except Exception as e:
            _LOGGER.debug(f"Verification request failed: {e}")

        _LOGGER.warning("Login status uncertain - proceeding anyway")
        self._logged_in = True
        return True

    def _get_dns_records(self) -> dict:
        """Fetch current DNS records for the domain."""
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        dns_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records"

        try:
            response = self.session.get(dns_url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to fetch DNS records: {e}")
        except ValueError as e:
            raise OneComAPIError(f"Invalid JSON response: {e}")

    def _find_record_id(self, subdomain: str, records: dict) -> Optional[tuple]:
        """Find the record ID for a given subdomain."""
        result = records.get("result", {})
        data = result.get("data", [])

        target_prefix = subdomain if subdomain else "@"

        for record in data:
            record_type = record.get("type")
            # Accept both dns_service_records and dns_custom_records
            if record_type in ["dns_service_records", "dns_custom_records"]:
                attributes = record.get("attributes", {})
                prefix = attributes.get("prefix", "")

                if prefix == target_prefix or (not subdomain and prefix in ["", "@"]):
                    if attributes.get("type") == "A":
                        return (record.get("id"), record_type)

        return None

    def get_domains(self) -> List[str]:
        """Get list of domains in the account."""
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        try:
            response = self.session.get(f"{self.ADMIN_URL}/api/domains")
            response.raise_for_status()
            data = response.json()

            domains = []
            result = data.get("result", {})
            for domain_data in result.get("data", []):
                domain_name = domain_data.get("attributes", {}).get("domain")
                if domain_name:
                    domains.append(domain_name)

            return domains
        except Exception as e:
            _LOGGER.warning(f"Could not fetch domains: {e}")
            return []

    def get_subdomains(self) -> List[str]:
        """Get list of existing A record subdomains."""
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        records = self._get_dns_records()
        result = records.get("result", {})
        data = result.get("data", [])

        subdomains = []
        for record in data:
            if record.get("type") == "dns_service_records":
                attributes = record.get("attributes", {})
                if attributes.get("type") == "A":
                    prefix = attributes.get("prefix", "")
                    subdomains.append(prefix if prefix != "@" else "")

        return subdomains

    def update_dns_record(self, subdomain: str, ip_address: str) -> bool:
        """Update a DNS A record for a subdomain."""
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug(f"Updating DNS record for '{subdomain or '@'}' to {ip_address}")

        records = self._get_dns_records()
        record_id = self._find_record_id(subdomain, records)

        if not record_id:
            raise OneComAPIError(
                f"DNS record for '{subdomain or 'root domain'}' not found."
            )

        update_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records/{record_id}"

        update_data = {
            "type": "dns_service_records",
            "id": record_id,
            "attributes": {
                "type": "A",
                "prefix": subdomain if subdomain else "@",
                "content": ip_address,
                "ttl": 3600
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = self.session.patch(
                update_url,
                json=update_data,
                headers=headers
            )
            response.raise_for_status()
            _LOGGER.info(f"Successfully updated '{subdomain or '@'}.{self.domain}' to {ip_address}")
            return True
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to update DNS record: {e}")

    def create_txt_record(self, subdomain: str, content: str, ttl: int = 60) -> str:
        """Create a TXT DNS record."""
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        create_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records"

        create_data = {
            "type": "dns_service_records",
            "attributes": {
                "type": "TXT",
                "prefix": subdomain,
                "content": content,
                "ttl": ttl
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = self.session.post(
                create_url,
                json=create_data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

            record_id = result.get("result", {}).get("data", {}).get("id")
            if not record_id:
                raise OneComAPIError("Could not get record ID from response")

            return record_id

        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to create TXT record: {e}")

    def delete_txt_record(self, record_id: str) -> bool:
        """Delete a DNS record by ID."""
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        delete_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records/{record_id}"

        try:
            response = self.session.delete(delete_url)
            response.raise_for_status()
            return True

        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to delete DNS record: {e}")

    def logout(self):
        """Close the session."""
        if self.session:
            self.session.close()
            self.session = None
        self._logged_in = False
        _LOGGER.debug("Logged out from One.com")


async def async_validate_credentials(
    username: str,
    password: str,
    domain: str | None = None
) -> Dict[str, Any]:
    """Validate One.com credentials and optionally fetch domain info.

    Returns dict with:
        - valid: bool
        - domains: list of domains (if login successful)
        - subdomains: list of subdomains for specified domain
        - error: error message if failed
    """
    import asyncio

    def _validate():
        api = OneComAPI(username, password, domain or "placeholder.com")
        try:
            api.login()

            result = {
                "valid": True,
                "domains": [],
                "subdomains": [],
                "error": None,
            }

            # Try to get domains
            try:
                result["domains"] = api.get_domains()
            except Exception:
                pass

            # If domain specified, get subdomains
            if domain:
                api.domain = domain
                try:
                    result["subdomains"] = api.get_subdomains()
                except Exception:
                    pass

            api.logout()
            return result

        except OneComAPIError as e:
            return {
                "valid": False,
                "domains": [],
                "subdomains": [],
                "error": str(e),
            }
        finally:
            if api.session:
                api.logout()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _validate)

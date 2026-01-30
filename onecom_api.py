"""
One.com DNS API Module

This module provides functionality to interact with One.com's DNS management
through their web interface. Since One.com doesn't provide an official API,
this uses web scraping techniques.

WARNING: This may break if One.com changes their web interface.
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
        """Initialize the One.com API client.

        Args:
            username: One.com account email
            password: One.com account password
            domain: The domain to manage (e.g., example.com)
        """
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
        """Log into the One.com admin panel.

        Returns:
            True if login was successful, False otherwise.

        Raises:
            OneComAPIError: If login fails due to connection or auth issues.
        """
        _LOGGER.debug("Attempting to log into One.com")

        self.session = self._create_session()

        try:
            # Get the login page to find the form action URL
            response = self.session.get(self.ADMIN_URL, allow_redirects=True)
            response.raise_for_status()
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to connect to One.com: {e}")

        # Extract the login form action URL
        form_action = self._find_between(
            response.text,
            '<form id="kc-form-login"',
            '">'
        )
        login_url = self._find_between(form_action, 'action="', '"')

        if not login_url:
            # Try alternative form detection
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
            _LOGGER.debug(f"Found hidden field: {name}")

        # Also try alternative pattern (value before name)
        hidden_pattern2 = re.findall(
            r'<input[^>]*value=["\']([^"\']*)["\'][^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\']',
            response.text
        )
        for value, name in hidden_pattern2:
            if name not in hidden_fields:
                hidden_fields[name] = value
                _LOGGER.debug(f"Found hidden field (alt): {name}")

        # Perform login
        login_data = {
            "username": self.username,
            "password": self.password,
        }

        # Add any hidden fields (CSRF tokens, etc.)
        login_data.update(hidden_fields)

        _LOGGER.debug(f"Login data fields: {list(login_data.keys())}")

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

            # Log part of the response body to see what One.com returns
            # Find the main content area
            body_snippet = ""
            main_match = re.search(r'<div[^>]*id="kc-form"[^>]*>(.*?)</div>', response.text, re.DOTALL)
            if main_match:
                body_snippet = main_match.group(1)[:500]
            else:
                # Just get a portion around any error
                body_snippet = response.text[response.text.find('<body'):response.text.find('<body')+1000] if '<body' in response.text else response.text[:500]

            _LOGGER.debug(f"Response snippet: {body_snippet[:300]}...")

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
            _LOGGER.debug(f"Response URL: {response.url}")
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
        """Fetch current DNS records for the domain.

        Returns:
            Dictionary containing DNS records.
        """
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
        """Find the record ID for a given subdomain.

        Args:
            subdomain: The subdomain to find (empty string for root domain)
            records: The DNS records dictionary

        Returns:
            Tuple of (record_id, record_type) if found, None otherwise.
        """
        result = records.get("result", {})
        data = result.get("data", [])

        target_prefix = subdomain if subdomain else "@"
        _LOGGER.debug(f"Looking for record with prefix '{target_prefix}'")

        for record in data:
            record_type = record.get("type")
            attributes = record.get("attributes", {})
            prefix = attributes.get("prefix", "")
            dns_type = attributes.get("type", "")

            _LOGGER.debug(f"Found record: type={record_type}, prefix='{prefix}', dns_type={dns_type}")

            # Accept both dns_service_records and dns_custom_records
            if record_type in ["dns_service_records", "dns_custom_records"]:
                # Match subdomain or root domain (@)
                if prefix == target_prefix or (not subdomain and prefix in ["", "@"]):
                    if dns_type == "A":
                        _LOGGER.debug(f"Match found! Record ID: {record.get('id')}, type: {record_type}")
                        return (record.get("id"), record_type)

        _LOGGER.debug(f"No matching record found for '{target_prefix}'")
        return None

    def update_dns_record(self, subdomain: str, ip_address: str) -> bool:
        """Update a DNS A record for a subdomain.

        Args:
            subdomain: The subdomain to update (empty string for root domain)
            ip_address: The new IP address

        Returns:
            True if update was successful.

        Raises:
            OneComAPIError: If the update fails.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug(f"Updating DNS record for '{subdomain or '@'}' to {ip_address}")

        # Get current records to find the record ID
        records = self._get_dns_records()
        result = self._find_record_id(subdomain, records)

        if not result:
            raise OneComAPIError(
                f"DNS record for '{subdomain or 'root domain'}' not found. "
                "Please create the record manually in the One.com control panel first."
            )

        record_id, record_type = result

        # Prepare update request
        update_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records/{record_id}"

        update_data = {
            "type": record_type,  # Use the actual record type from the API
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

    def update_all_subdomains(self, subdomains: list, ip_address: str) -> dict:
        """Update DNS records for multiple subdomains.

        Args:
            subdomains: List of subdomains to update
            ip_address: The new IP address

        Returns:
            Dictionary with results for each subdomain.
        """
        results = {}

        for subdomain in subdomains:
            display_name = subdomain if subdomain else "@"
            try:
                self.update_dns_record(subdomain, ip_address)
                results[display_name] = {"success": True, "error": None}
            except OneComAPIError as e:
                _LOGGER.error(f"Failed to update {display_name}: {e}")
                results[display_name] = {"success": False, "error": str(e)}

        return results

    def logout(self):
        """Close the session."""
        if self.session:
            self.session.close()
            self.session = None
        self._logged_in = False
        _LOGGER.debug("Logged out from One.com")

    def create_txt_record(self, subdomain: str, content: str, ttl: int = 60) -> str:
        """Create a TXT DNS record.

        Args:
            subdomain: The subdomain for the TXT record (e.g., '_acme-challenge')
            content: The TXT record content
            ttl: Time to live in seconds (default 60 for ACME challenges)

        Returns:
            The ID of the created record.

        Raises:
            OneComAPIError: If creation fails.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug(f"Creating TXT record for '{subdomain}' with content '{content}'")

        create_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records"

        # Use dns_custom_records type which One.com expects for custom DNS entries
        create_data = {
            "type": "dns_custom_records",
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

        _LOGGER.debug(f"Creating TXT record with data: {create_data}")

        try:
            response = self.session.post(
                create_url,
                json=create_data,
                headers=headers
            )

            # Log response details for debugging
            _LOGGER.debug(f"Create TXT record response: {response.status_code}")
            if response.status_code >= 400:
                _LOGGER.debug(f"Response body: {response.text}")

            response.raise_for_status()
            result = response.json()

            # Extract the record ID from response
            record_id = result.get("result", {}).get("data", {}).get("id")
            if not record_id:
                raise OneComAPIError("Could not get record ID from response")

            _LOGGER.info(f"Successfully created TXT record '{subdomain}.{self.domain}'")
            return record_id

        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to create TXT record: {e}")

    def delete_txt_record(self, record_id: str) -> bool:
        """Delete a DNS record by ID.

        Args:
            record_id: The ID of the record to delete

        Returns:
            True if deletion was successful.

        Raises:
            OneComAPIError: If deletion fails.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug(f"Deleting DNS record with ID '{record_id}'")

        delete_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records/{record_id}"

        headers = {
            "Accept": "application/json"
        }

        try:
            response = self.session.delete(delete_url, headers=headers)
            response.raise_for_status()
            _LOGGER.info(f"Successfully deleted DNS record '{record_id}'")
            return True

        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to delete DNS record: {e}")

    def find_txt_records(self, subdomain: str) -> List[Dict[str, Any]]:
        """Find all TXT records for a subdomain.

        Args:
            subdomain: The subdomain to search for

        Returns:
            List of matching TXT records with their IDs and content.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        records = self._get_dns_records()
        result = records.get("result", {})
        data = result.get("data", [])

        matching_records = []
        for record in data:
            # Check both dns_service_records and dns_custom_records types
            if record.get("type") in ["dns_service_records", "dns_custom_records"]:
                attributes = record.get("attributes", {})
                if attributes.get("type") == "TXT" and attributes.get("prefix") == subdomain:
                    matching_records.append({
                        "id": record.get("id"),
                        "content": attributes.get("content"),
                        "ttl": attributes.get("ttl")
                    })

        return matching_records

    def cleanup_acme_records(self, subdomain: str = "_acme-challenge") -> int:
        """Remove all ACME challenge TXT records for a subdomain.

        Args:
            subdomain: The subdomain to clean up (default: _acme-challenge)

        Returns:
            Number of records deleted.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug(f"Cleaning up ACME records for '{subdomain}'")

        records = self.find_txt_records(subdomain)
        deleted_count = 0

        for record in records:
            try:
                self.delete_txt_record(record["id"])
                deleted_count += 1
            except OneComAPIError as e:
                _LOGGER.warning(f"Failed to delete record {record['id']}: {e}")

        _LOGGER.info(f"Cleaned up {deleted_count} ACME challenge records")
        return deleted_count

    def wait_for_dns_propagation(
        self,
        subdomain: str,
        expected_content: str,
        timeout: int = 120,
        interval: int = 5
    ) -> bool:
        """Wait for DNS propagation of a TXT record.

        This uses a public DNS resolver to verify the record is visible.

        Args:
            subdomain: The subdomain to check
            expected_content: The expected TXT record content
            timeout: Maximum time to wait in seconds
            interval: Time between checks in seconds

        Returns:
            True if the record is visible, False if timeout reached.
        """
        import socket

        full_domain = f"{subdomain}.{self.domain}"
        _LOGGER.info(f"Waiting for DNS propagation of '{full_domain}'...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Use DNS over HTTPS for reliable checking
                dns_check_url = f"https://dns.google/resolve?name={full_domain}&type=TXT"
                response = requests.get(dns_check_url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    answers = data.get("Answer", [])

                    for answer in answers:
                        txt_data = answer.get("data", "").strip('"')
                        if expected_content in txt_data:
                            _LOGGER.info(f"DNS propagation complete for '{full_domain}'")
                            return True

            except Exception as e:
                _LOGGER.debug(f"DNS check failed: {e}")

            _LOGGER.debug(f"Record not yet visible, waiting {interval}s...")
            time.sleep(interval)

        _LOGGER.warning(f"DNS propagation timeout for '{full_domain}'")
        return False

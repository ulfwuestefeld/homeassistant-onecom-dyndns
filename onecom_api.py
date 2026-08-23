"""
One.com DNS API Module

This module provides functionality to interact with One.com's DNS management
through their web interface. Since One.com doesn't provide an official API,
this uses web scraping techniques.

WARNING: This may break if One.com changes their web interface.
"""

import logging
import re
import threading
import time
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)


class OneComAPIError(Exception):
    """Exception raised for One.com API errors."""


class OneComAPI:
    """Class to interact with One.com DNS settings."""

    BASE_URL = "https://www.one.com"
    ADMIN_URL = f"{BASE_URL}/admin"
    LOGIN_URL = f"{BASE_URL}/admin/login.do"

    # Default timeout in seconds for all HTTP requests to One.com.
    # Prevents the add-on from hanging indefinitely if One.com becomes
    # unresponsive (returns headers but stalls on the body).
    REQUEST_TIMEOUT = 30

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
        self.session: requests.Session | None = None
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
            response = self.session.get(self.ADMIN_URL, allow_redirects=True, timeout=self.REQUEST_TIMEOUT)
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
            _LOGGER.debug("Found hidden field: %s", name)

        # Also try alternative pattern (value before name)
        hidden_pattern2 = re.findall(
            r'<input[^>]*value=["\']([^"\']*)["\'][^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\']',
            response.text
        )
        for value, name in hidden_pattern2:
            if name not in hidden_fields:
                hidden_fields[name] = value
                _LOGGER.debug("Found hidden field (alt): %s", name)

        # Perform login
        login_data = {
            "username": self.username,
            "password": self.password,
        }

        # Add any hidden fields (CSRF tokens, etc.)
        login_data.update(hidden_fields)

        _LOGGER.debug("Login data fields: %s", list(login_data.keys()))

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
                allow_redirects=True,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise OneComAPIError(f"Login request failed: {e}")

        _LOGGER.debug("Login response URL: %s", response.url)

        # Check if login was successful by looking for admin panel indicators
        if "logout" in response.text.lower() or "dns" in response.url.lower() or "/admin" in response.url:
            _LOGGER.info("Successfully logged into One.com")
            self._logged_in = True
            return True

        # Check for specific error messages indicating wrong credentials
        response_lower = response.text.lower()

        # Log detailed debug information if we're still on account.one.com
        if "account.one.com" in response.url:
            _LOGGER.debug("Still on account.one.com after login attempt")

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
                    _LOGGER.error("Login error from One.com: %s", match.group(1).strip())
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

            _LOGGER.debug("Response snippet: %s...", body_snippet[:300])

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
            _LOGGER.debug("Response URL: %s", response.url)
            raise OneComAPIError("Login failed - still on login page. Please verify your One.com credentials and ensure 2FA is disabled.")

        # Try to access the admin panel to verify login
        _LOGGER.debug("Login status uncertain, verifying by accessing admin panel...")
        try:
            verify_response = self.session.get(f"{self.ADMIN_URL}/", allow_redirects=True, timeout=self.REQUEST_TIMEOUT)
            if "/admin" in verify_response.url and "account.one.com" not in verify_response.url:
                _LOGGER.info("Successfully logged into One.com (verified)")
                self._logged_in = True
                return True
        except Exception as e:
            _LOGGER.debug("Verification request failed: %s", e)

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
            response = self.session.get(dns_url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to fetch DNS records: {e}")
        except ValueError as e:
            raise OneComAPIError(f"Invalid JSON response: {e}")

    def _find_record_id(self, subdomain: str, records: dict) -> tuple | None:
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
        _LOGGER.debug("Looking for record with prefix '%s'", target_prefix)

        for record in data:
            record_type = record.get("type")
            attributes = record.get("attributes", {})
            prefix = attributes.get("prefix", "")
            dns_type = attributes.get("type", "")

            _LOGGER.debug("Found record: type=%s, prefix='%s', dns_type=%s", record_type, prefix, dns_type)

            # Accept both dns_service_records and dns_custom_records
            if record_type in ["dns_service_records", "dns_custom_records"]:
                # Match subdomain or root domain (@)
                if prefix == target_prefix or (not subdomain and prefix in ["", "@"]):
                    if dns_type == "A":
                        _LOGGER.debug("Match found! Record ID: %s, type: %s", record.get('id'), record_type)
                        return (record.get("id"), record_type)

        _LOGGER.debug("No matching record found for '%s'", target_prefix)
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

        _LOGGER.debug("Updating DNS record for '%s' to %s", subdomain or '@', ip_address)

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
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            _LOGGER.info("Successfully updated '%s.%s' to %s", subdomain or '@', self.domain, ip_address)
            return True
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to update DNS record: {e}")

    def update_all_subdomains(self, subdomains: list, ip_address: str) -> dict:
        """Update DNS records for multiple subdomains.

        Fetches DNS records once and resolves record IDs for all subdomains
        from the cached result, avoiding N redundant API calls.

        Args:
            subdomains: List of subdomains to update
            ip_address: The new IP address

        Returns:
            Dictionary with results for each subdomain.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        results = {}

        # Fetch DNS records once for all subdomains
        try:
            records = self._get_dns_records()
        except OneComAPIError as e:
            # If we cannot even load the records, mark all as failed
            for subdomain in subdomains:
                display_name = subdomain if subdomain else "@"
                results[display_name] = {"success": False, "error": str(e)}
            return results

        for subdomain in subdomains:
            display_name = subdomain if subdomain else "@"
            try:
                self._update_dns_record_with_cache(subdomain, ip_address, records)
                results[display_name] = {"success": True, "error": None}
            except OneComAPIError as e:
                _LOGGER.error("Failed to update %s: %s", display_name, e)
                results[display_name] = {"success": False, "error": str(e)}

        return results

    def _update_dns_record_with_cache(
        self, subdomain: str, ip_address: str, records: dict
    ) -> bool:
        """Update a DNS A record using pre-fetched records.

        Args:
            subdomain: The subdomain to update (empty string for root domain)
            ip_address: The new IP address
            records: Pre-fetched DNS records dict

        Returns:
            True if update was successful.

        Raises:
            OneComAPIError: If the update fails.
        """
        result = self._find_record_id(subdomain, records)

        if not result:
            raise OneComAPIError(
                f"DNS record for '{subdomain or 'root domain'}' not found. "
                "Please create the record manually in the One.com control panel first."
            )

        record_id, record_type = result

        update_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records/{record_id}"

        update_data = {
            "type": record_type,
            "id": record_id,
            "attributes": {
                "type": "A",
                "prefix": subdomain if subdomain else "@",
                "content": ip_address,
                "ttl": 3600,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = self.session.patch(
                update_url, json=update_data, headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            _LOGGER.info(
                "Successfully updated '%s.%s' to %s",
                subdomain or "@",
                self.domain,
                ip_address,
            )
            return True
        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to update DNS record: {e}")

    def logout(self):
        """Close the session."""
        if self.session:
            self.session.close()
            self.session = None
        self._logged_in = False
        _LOGGER.debug("Logged out from One.com")

    def create_txt_record(self, subdomain: str, content: str, ttl: int = 600) -> str:
        """Create a TXT DNS record.

        Args:
            subdomain: The subdomain for the TXT record (e.g., '_acme-challenge')
            content: The TXT record content
            ttl: Time to live in seconds (default 600, One.com minimum)

        Returns:
            The ID of the created record (or existing record ID if already exists).

        Raises:
            OneComAPIError: If creation fails.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug("Creating TXT record for '%s' with content '%s'", subdomain, content)

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

        _LOGGER.debug("Creating TXT record with data: %s", create_data)

        try:
            response = self.session.post(
                create_url,
                json=create_data,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )

            # Log response details for debugging
            _LOGGER.debug("Create TXT record response: %s", response.status_code)
            
            # Check for conflict error (record already exists)
            if response.status_code >= 400:
                response_text = response.text
                _LOGGER.debug("Response body: %s", response_text)
                
                    # One.com returns 500 with a conflict message when record already exists
                if "DNS_RECORD_CONFLICTING" in response_text or "ConflictingDnsRecordException" in response_text:
                    # Check if it's the same content - extract record ID from error
                    # Error format: "conflicts with existing TXT record (36316970)"
                    match = re.search(r'existing TXT record \((\d+)\)', response_text)
                    
                    if match and "same content" in response_text:
                        existing_id = match.group(1)
                        _LOGGER.info("TXT record already exists with same content (ID: %s), treating as success", existing_id)
                        return existing_id
                    
                    # If conflict but different content, we need to delete old and create new
                    if match:
                        existing_id = match.group(1)
                        _LOGGER.info("TXT record exists with different content, replacing (ID: %s)", existing_id)
                        try:
                            self.delete_txt_record(existing_id)
                            # Retry creation after deletion
                            response = self.session.post(
                                create_url,
                                json=create_data,
                                headers=headers,
                                timeout=self.REQUEST_TIMEOUT,
                            )
                            _LOGGER.debug("Retry create TXT record response: %s", response.status_code)
                        except OneComAPIError as e:
                            _LOGGER.warning("Failed to delete conflicting record: %s", e)

            response.raise_for_status()
            result = response.json()

            # Extract the record ID from response
            record_id = result.get("result", {}).get("data", {}).get("id")
            if not record_id:
                raise OneComAPIError("Could not get record ID from response")

            _LOGGER.info("Successfully created TXT record '%s.%s'", subdomain, self.domain)
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

        _LOGGER.debug("Deleting DNS record with ID '%s'", record_id)

        delete_url = f"{self.ADMIN_URL}/api/domains/{self.domain}/dns/custom_records/{record_id}"

        headers = {
            "Accept": "application/json"
        }

        try:
            response = self.session.delete(delete_url, headers=headers, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            _LOGGER.info("Successfully deleted DNS record '%s'", record_id)
            return True

        except requests.RequestException as e:
            raise OneComAPIError(f"Failed to delete DNS record: {e}")

    def find_txt_records(self, subdomain: str, exact_match: bool = False) -> list[dict[str, Any]]:
        """Find all TXT records for a subdomain.

        Args:
            subdomain: The subdomain to search for
            exact_match: If True, match prefix exactly. If False, match records
                        that start with the subdomain (useful for finding all
                        ACME challenge records like _acme-challenge.*)

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
                prefix = attributes.get("prefix", "")
                
                if attributes.get("type") == "TXT":
                    # Match either exactly or by prefix
                    if exact_match:
                        matches = prefix == subdomain
                    else:
                        # Match if prefix equals subdomain or starts with subdomain.
                        # e.g., "_acme-challenge" matches "_acme-challenge" and "_acme-challenge.homeassistant"
                        matches = prefix == subdomain or prefix.startswith(f"{subdomain}.")
                    
                    if matches:
                        matching_records.append({
                            "id": record.get("id"),
                            "prefix": prefix,
                            "content": attributes.get("content"),
                            "ttl": attributes.get("ttl")
                        })

        return matching_records

    def cleanup_acme_records(self, subdomain: str = "_acme-challenge") -> int:
        """Remove all ACME challenge TXT records for a subdomain.

        This finds and removes ALL TXT records that start with the given subdomain,
        e.g., "_acme-challenge" will also match "_acme-challenge.homeassistant".

        Args:
            subdomain: The subdomain prefix to clean up (default: _acme-challenge)

        Returns:
            Number of records deleted.
        """
        if not self._logged_in or not self.session:
            raise OneComAPIError("Not logged in")

        _LOGGER.debug("Cleaning up ACME records starting with '%s'", subdomain)

        # Find all records that start with the subdomain (not exact match)
        records = self.find_txt_records(subdomain, exact_match=False)
        
        if records:
            _LOGGER.debug("Found %s ACME record(s) to clean up:", len(records))
            for r in records:
                _LOGGER.debug("  - ID: %s, prefix: %s", r['id'], r.get('prefix', 'N/A'))
        
        deleted_count = 0

        for record in records:
            try:
                self.delete_txt_record(record["id"])
                deleted_count += 1
            except OneComAPIError as e:
                _LOGGER.warning("Failed to delete record %s: %s", record['id'], e)

        _LOGGER.info("Cleaned up %s ACME challenge records", deleted_count)
        return deleted_count

    def wait_for_dns_propagation(
        self,
        subdomain: str,
        expected_content: str,
        timeout: int = 120,
        interval: int = 5,
        stop_event: "threading.Event | None" = None,
    ) -> bool:
        """Wait for DNS propagation of a TXT record.

        This uses a public DNS resolver to verify the record is visible.

        Args:
            subdomain: The subdomain to check
            expected_content: The expected TXT record content
            timeout: Maximum time to wait in seconds
            interval: Time between checks in seconds
            stop_event: Optional threading.Event for interruptible waiting

        Returns:
            True if the record is visible, False if timeout reached.
        """

        full_domain = f"{subdomain}.{self.domain}"
        _LOGGER.info("Waiting for DNS propagation of '%s'...", full_domain)

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Use DNS over HTTPS for reliable checking.
                # Reuse the authenticated session for connection pooling
                # (avoids a new TLS handshake on every propagation check).
                dns_check_url = f"https://dns.google/resolve?name={full_domain}&type=TXT"
                http_session = self.session or requests
                response = http_session.get(dns_check_url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    answers = data.get("Answer", [])

                    for answer in answers:
                        txt_data = answer.get("data", "").strip('"')
                        if expected_content in txt_data:
                            _LOGGER.info("DNS propagation complete for '%s'", full_domain)
                            return True

            except Exception as e:
                _LOGGER.debug("DNS check failed: %s", e)

            _LOGGER.debug("Record not yet visible, waiting %ss...", interval)
            if stop_event is not None:
                if stop_event.wait(timeout=interval):
                    return False  # Shutdown requested
            else:
                time.sleep(interval)

        _LOGGER.warning("DNS propagation timeout for '%s'", full_domain)
        return False

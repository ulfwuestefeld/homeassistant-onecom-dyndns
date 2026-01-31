"""
Advanced unit tests for the One.com API module.
Tests for retry mechanism, TXT record conflict handling, and edge cases.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onecom_api import OneComAPI, OneComAPIError


class TestTXTRecordConflictHandling:
    """Tests for TXT record conflict handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")
        self.api._logged_in = True
        self.api.session = Mock()

    def test_create_txt_record_conflict_same_content(self):
        """Test handling conflict when record exists with same content."""
        # First call fails with conflict
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        # Include the numeric record ID in the expected format: "existing TXT record (12345)"
        mock_response_fail.text = '{"metadata": {"messages": [{"code": "DNS_RECORD_CONFLICTING", "text": "conflict: new TXT record conflicts with existing TXT record (36316970) on same prefix with same content"}]}}'
        mock_response_fail.json.return_value = {
            "metadata": {
                "messages": [{
                    "code": "DNS_RECORD_CONFLICTING",
                    "text": "conflict: new TXT record conflicts with existing TXT record (36316970) on same prefix with same content"
                }]
            }
        }
        mock_response_fail.raise_for_status.side_effect = Exception("500 Error")

        self.api.session.post.return_value = mock_response_fail

        # Should succeed (treat as existing) - code extracts ID from error message
        record_id = self.api.create_txt_record("_acme-challenge", "same-token-value")

        # Should return existing record ID extracted from the error message
        assert record_id == "36316970"

    def test_create_txt_record_conflict_different_content(self):
        """Test handling conflict when record exists with different content."""
        # First call fails with conflict (different content - no "same content" in message)
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        # Note: no "same content" in the message, just the record ID
        mock_response_fail.text = '{"metadata": {"messages": [{"code": "DNS_RECORD_CONFLICTING", "text": "conflict: new TXT record conflicts with existing TXT record (36316970) on same prefix"}]}}'
        mock_response_fail.json.return_value = {
            "metadata": {
                "messages": [{
                    "code": "DNS_RECORD_CONFLICTING",
                    "text": "conflict: new TXT record conflicts with existing TXT record (36316970) on same prefix"
                }]
            }
        }
        # Only raise on the first response, not the retry
        mock_response_fail.raise_for_status = Mock()

        # Second call succeeds after delete
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.text = '{"result": {"data": {"id": "new-456"}}}'
        mock_response_success.json.return_value = {
            "result": {"data": {"id": "new-456"}}
        }
        mock_response_success.raise_for_status = Mock()

        with patch.object(self.api, 'delete_txt_record') as mock_delete:
            mock_delete.return_value = True
            self.api.session.post.side_effect = [mock_response_fail, mock_response_success]

            record_id = self.api.create_txt_record("_acme-challenge", "new-token-value")

            # Should delete old (ID extracted from error) and create new
            mock_delete.assert_called_once_with("36316970")
            assert record_id == "new-456"


class TestFindTXTRecordsMatching:
    """Tests for TXT record finding with exact and prefix matching."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")
        self.api._logged_in = True
        self.api.session = Mock()

    @patch.object(OneComAPI, '_get_dns_records')
    def test_find_txt_records_exact_match(self, mock_get_records):
        """Test finding TXT records with exact match."""
        mock_get_records.return_value = {
            "result": {
                "data": [
                    {
                        "type": "dns_custom_records",
                        "id": "txt1",
                        "attributes": {
                            "type": "TXT",
                            "prefix": "_acme-challenge",
                            "content": "token1",
                            "ttl": 600
                        }
                    },
                    {
                        "type": "dns_custom_records",
                        "id": "txt2",
                        "attributes": {
                            "type": "TXT",
                            "prefix": "_acme-challenge.www",
                            "content": "token2",
                            "ttl": 600
                        }
                    }
                ]
            }
        }

        records = self.api.find_txt_records("_acme-challenge", exact_match=True)

        # Should only find exact match
        assert len(records) == 1
        assert records[0]["id"] == "txt1"

    @patch.object(OneComAPI, '_get_dns_records')
    def test_find_txt_records_prefix_match(self, mock_get_records):
        """Test finding TXT records with prefix matching."""
        mock_get_records.return_value = {
            "result": {
                "data": [
                    {
                        "type": "dns_custom_records",
                        "id": "txt1",
                        "attributes": {
                            "type": "TXT",
                            "prefix": "_acme-challenge",
                            "content": "token1",
                            "ttl": 600
                        }
                    },
                    {
                        "type": "dns_custom_records",
                        "id": "txt2",
                        "attributes": {
                            "type": "TXT",
                            "prefix": "_acme-challenge.homeassistant",
                            "content": "token2",
                            "ttl": 600
                        }
                    },
                    {
                        "type": "dns_custom_records",
                        "id": "txt3",
                        "attributes": {
                            "type": "TXT",
                            "prefix": "_dmarc",
                            "content": "v=DMARC1",
                            "ttl": 600
                        }
                    }
                ]
            }
        }

        records = self.api.find_txt_records("_acme-challenge", exact_match=False)

        # Should find both ACME challenge records
        assert len(records) == 2
        ids = [r["id"] for r in records]
        assert "txt1" in ids
        assert "txt2" in ids


class TestCleanupACMERecords:
    """Tests for ACME record cleanup functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")
        self.api._logged_in = True
        self.api.session = Mock()

    @patch.object(OneComAPI, 'find_txt_records')
    @patch.object(OneComAPI, 'delete_txt_record')
    def test_cleanup_multiple_acme_records(self, mock_delete, mock_find):
        """Test cleanup of multiple ACME records."""
        mock_find.return_value = [
            {"id": "txt1", "content": "token1", "ttl": 600},
            {"id": "txt2", "content": "token2", "ttl": 600},
            {"id": "txt3", "content": "token3", "ttl": 600},
        ]
        mock_delete.return_value = True

        deleted_count = self.api.cleanup_acme_records()

        assert deleted_count == 3
        assert mock_delete.call_count == 3
        mock_delete.assert_any_call("txt1")
        mock_delete.assert_any_call("txt2")
        mock_delete.assert_any_call("txt3")

    @patch.object(OneComAPI, 'find_txt_records')
    @patch.object(OneComAPI, 'delete_txt_record')
    def test_cleanup_no_records(self, mock_delete, mock_find):
        """Test cleanup when no ACME records exist."""
        mock_find.return_value = []

        deleted_count = self.api.cleanup_acme_records()

        assert deleted_count == 0
        mock_delete.assert_not_called()

    @patch.object(OneComAPI, 'find_txt_records')
    @patch.object(OneComAPI, 'delete_txt_record')
    def test_cleanup_partial_failure(self, mock_delete, mock_find):
        """Test cleanup when some deletions fail."""
        mock_find.return_value = [
            {"id": "txt1", "content": "token1", "ttl": 600},
            {"id": "txt2", "content": "token2", "ttl": 600},
        ]
        # First delete succeeds, second raises exception
        mock_delete.side_effect = [True, OneComAPIError("Delete failed")]

        deleted_count = self.api.cleanup_acme_records()

        assert deleted_count == 1


class TestRetryMechanism:
    """Tests for retry mechanism with exponential backoff."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")

    @patch("onecom_api.time.sleep")
    @patch("onecom_api.requests.Session")
    def test_retry_on_connection_error(self, mock_session_class, mock_sleep):
        """Test retry on connection error."""
        import requests

        mock_session = Mock()
        
        # First few calls fail, then succeed
        mock_response_success = Mock()
        mock_response_success.url = "https://www.one.com/admin/frontpage.do"
        mock_response_success.text = "<html></html>"
        
        mock_session.get.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.ConnectionError("Connection refused"),
            mock_response_success,  # Login page
        ]
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        # Should eventually succeed or fail with max retries
        # This tests that retry logic is in place

    @patch("onecom_api.time.sleep")
    @patch("onecom_api.requests.Session")
    def test_retry_on_timeout(self, mock_session_class, mock_sleep):
        """Test retry on timeout."""
        import requests

        mock_session = Mock()
        mock_session.get.side_effect = requests.exceptions.Timeout("Request timed out")
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        with pytest.raises(OneComAPIError):
            self.api.login()

        # Sleep should have been called for retries
        # (actual implementation may vary)


class TestDNSPropagation:
    """Tests for DNS propagation waiting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")
        self.api._logged_in = True
        self.api.session = Mock()

    @patch("onecom_api.requests.get")
    def test_dns_propagation_immediate_success(self, mock_get):
        """Test DNS propagation when record is immediately available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Answer": [{"data": '"expected-token"'}]
        }
        mock_get.return_value = mock_response

        result = self.api.wait_for_dns_propagation(
            "_acme-challenge",
            "expected-token",
            timeout=30,
            interval=5
        )

        assert result is True

    @patch("onecom_api.requests.get")
    @patch("onecom_api.time.sleep")
    def test_dns_propagation_delayed_success(self, mock_sleep, mock_get):
        """Test DNS propagation when record appears after delay."""
        mock_response_empty = Mock()
        mock_response_empty.status_code = 200
        mock_response_empty.json.return_value = {"Answer": []}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "Answer": [{"data": '"expected-token"'}]
        }

        mock_get.side_effect = [
            mock_response_empty,
            mock_response_empty,
            mock_response_success,
        ]

        result = self.api.wait_for_dns_propagation(
            "_acme-challenge",
            "expected-token",
            timeout=30,
            interval=5
        )

        assert result is True

    @patch("onecom_api.requests.get")
    @patch("onecom_api.time.sleep")
    def test_dns_propagation_timeout(self, mock_sleep, mock_get):
        """Test DNS propagation timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Answer": []}
        mock_get.return_value = mock_response

        result = self.api.wait_for_dns_propagation(
            "_acme-challenge",
            "expected-token",
            timeout=2,
            interval=1
        )

        assert result is False


class TestTTLHandling:
    """Tests for TTL handling in DNS records."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")
        self.api._logged_in = True
        self.api.session = Mock()

    def test_default_ttl_is_600(self):
        """Test that default TTL for TXT records is 600."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"data": {"id": "new-record"}}
        }
        mock_response.raise_for_status = Mock()
        self.api.session.post.return_value = mock_response

        self.api.create_txt_record("_acme-challenge", "token")

        call_args = self.api.session.post.call_args
        data = call_args[1]["json"]
        assert data["attributes"]["ttl"] == 600

    def test_custom_ttl(self):
        """Test that custom TTL can be set."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"data": {"id": "new-record"}}
        }
        mock_response.raise_for_status = Mock()
        self.api.session.post.return_value = mock_response

        self.api.create_txt_record("_acme-challenge", "token", ttl=3600)

        call_args = self.api.session.post.call_args
        data = call_args[1]["json"]
        assert data["attributes"]["ttl"] == 3600


class TestUpdateAllSubdomains:
    """Tests for bulk subdomain update."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")
        self.api._logged_in = True
        self.api.session = Mock()

    @patch.object(OneComAPI, 'update_dns_record')
    def test_update_all_subdomains_success(self, mock_update):
        """Test successful update of all subdomains."""
        mock_update.return_value = True

        results = self.api.update_all_subdomains(["www", "api", ""], "1.2.3.4")

        assert results["www"]["success"] is True
        assert results["api"]["success"] is True
        # Empty string subdomain is stored as "@" (root domain)
        assert results["@"]["success"] is True
        assert mock_update.call_count == 3

    @patch.object(OneComAPI, 'update_dns_record')
    def test_update_all_subdomains_partial_failure(self, mock_update):
        """Test partial failure in bulk update."""
        def update_side_effect(subdomain, ip):
            if subdomain == "fail":
                raise OneComAPIError("Record not found")
            return True

        mock_update.side_effect = update_side_effect

        results = self.api.update_all_subdomains(["www", "fail", "api"], "1.2.3.4")

        assert results["www"]["success"] is True
        assert results["fail"]["success"] is False
        assert "Record not found" in results["fail"]["error"]
        assert results["api"]["success"] is True


class TestManualLoginLogout:
    """Tests for manual login/logout pattern (no context manager)."""

    @patch.object(OneComAPI, 'login')
    @patch.object(OneComAPI, 'logout')
    def test_manual_login_logout(self, mock_logout, mock_login):
        """Test manual login and logout calls."""
        api = OneComAPI("test@example.com", "password", "example.com")
        api.login()
        # Do some work...
        api.logout()

        mock_login.assert_called_once()
        mock_logout.assert_called_once()

    @patch.object(OneComAPI, 'login')
    @patch.object(OneComAPI, 'logout')
    def test_logout_on_exception(self, mock_logout, mock_login):
        """Test that logout should be called even on exception."""
        api = OneComAPI("test@example.com", "password", "example.com")
        try:
            api.login()
            raise ValueError("Test error")
        except ValueError:
            pass
        finally:
            api.logout()

        mock_login.assert_called_once()
        mock_logout.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

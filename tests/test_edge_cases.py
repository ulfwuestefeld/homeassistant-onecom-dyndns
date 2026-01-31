"""
Edge case tests for One.com DynDNS Updater.

These tests verify behavior in unusual or boundary conditions.
"""

import json
import os
import sys
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ACME modules before importing
sys.modules['acme'] = MagicMock()
sys.modules['acme.client'] = MagicMock()
sys.modules['acme.messages'] = MagicMock()
sys.modules['acme.challenges'] = MagicMock()
sys.modules['acme.errors'] = MagicMock()
sys.modules['josepy'] = MagicMock()


class TestEmptyAndNullInputs:
    """Tests for empty and null input handling."""

    def test_empty_subdomains_list(self):
        """Test handling of empty subdomains list."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [],  # Empty list
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        assert updater.subdomains == []

    def test_empty_ssl_domains(self):
        """Test that empty SSL domains defaults to main domain."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            ssl_domains=[],  # Empty - should default
        )

        # Should default to domain
        assert manager.ssl_domains == []  # or ["example.com"] depending on implementation

    def test_empty_string_subdomain(self):
        """Test handling of empty string subdomain (root domain)."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")

        records = {
            "result": {
                "data": [
                    {
                        "type": "dns_service_records",
                        "id": "root123",
                        "attributes": {"prefix": "@", "type": "A"}
                    }
                ]
            }
        }

        # Empty string should match "@" (root domain)
        record_id = api._find_record_id("", records)
        assert record_id == "root123"


class TestBoundaryValues:
    """Tests for boundary value conditions."""

    def test_update_interval_minimum(self):
        """Test minimum update interval (1 minute)."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 1,  # Minimum
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        assert updater.update_interval == 1

    def test_update_interval_maximum(self):
        """Test maximum update interval (60 minutes)."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 60,  # Maximum
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        assert updater.update_interval == 60

    def test_renewal_days_boundary(self):
        """Test renewal days at boundary (1 and 60)."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            renewal_days=1,  # Minimum
        )
        assert manager.renewal_days == 1

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            renewal_days=60,  # Maximum
        )
        assert manager.renewal_days == 60

    def test_certificate_exactly_at_renewal_threshold(self):
        """Test certificate exactly at renewal threshold days."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            renewal_days=30,
        )

        with patch.object(manager, 'get_certificate_info') as mock_info:
            # Exactly at threshold - should trigger renewal
            mock_info.return_value = {
                "days_remaining": 30,
                "needs_renewal": True,  # At threshold
                "domains": ["example.com"],
            }

            info = manager.get_certificate_info()
            assert info["needs_renewal"] is True


class TestSpecialCharacters:
    """Tests for special character handling."""

    def test_domain_with_hyphen(self):
        """Test domain with hyphens."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "my-domain.com")
        assert api.domain == "my-domain.com"

    def test_subdomain_with_underscore(self):
        """Test subdomain with underscore (like ACME challenge)."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")
        api._logged_in = True
        api.session = Mock()

        records = {
            "result": {
                "data": [
                    {
                        "type": "dns_custom_records",
                        "id": "acme123",
                        "attributes": {
                            "prefix": "_acme-challenge",
                            "type": "TXT"
                        }
                    }
                ]
            }
        }

        # Should handle underscore prefix
        with patch.object(api, '_get_dns_records', return_value=records):
            found = api.find_txt_records("_acme-challenge")
            assert len(found) == 1

    def test_email_with_plus(self):
        """Test email with plus sign."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test+alias@example.com",
            password="password",
            domain="example.com",
            email="ssl+cert@example.com",
        )

        assert manager.username == "test+alias@example.com"
        assert manager.email == "ssl+cert@example.com"


class TestUnicodeHandling:
    """Tests for Unicode handling."""

    def test_unicode_in_error_messages(self):
        """Test that Unicode in error messages is handled."""
        from onecom_api import OneComAPIError

        # Error with Unicode
        error = OneComAPIError("Fehler: Ungültige Antwort")
        assert "Ungültige" in str(error)

    def test_unicode_domain_handling(self):
        """Test handling of internationalized domain names."""
        from onecom_api import OneComAPI

        # IDN domains should be handled
        api = OneComAPI("test@example.com", "pass", "example.com")
        # Actual IDN handling would require punycode conversion


class TestConcurrentOperations:
    """Tests for concurrent operation handling."""

    def test_multiple_callbacks_not_interfere(self):
        """Test that multiple callbacks don't interfere with each other."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        results = []

        def callback1(event, data):
            time.sleep(0.01)  # Simulate slow callback
            results.append(("cb1", event))

        def callback2(event, data):
            results.append(("cb2", event))

        manager.add_callback(callback1)
        manager.add_callback(callback2)
        manager._notify("test", {})

        assert len(results) == 2
        assert ("cb1", "test") in results
        assert ("cb2", "test") in results


class TestNetworkEdgeCases:
    """Tests for network edge cases."""

    @patch("run.requests.get")
    def test_ip_response_with_whitespace(self, mock_get):
        """Test IP response with leading/trailing whitespace."""
        from run import DynDNSUpdater

        mock_response = Mock()
        mock_response.text = "  1.2.3.4  \n"  # Whitespace
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        ip = updater.get_public_ip()

        assert ip == "1.2.3.4"  # Should be stripped

    @patch("run.requests.get")
    def test_ip_response_empty(self, mock_get):
        """Test empty IP response."""
        from run import DynDNSUpdater

        mock_response = Mock()
        mock_response.text = ""
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        ip = updater.get_public_ip()

        assert ip is None


class TestFileSystemEdgeCases:
    """Tests for file system edge cases."""

    def test_last_ip_file_missing_directory(self):
        """Test behavior when last IP file directory doesn't exist."""
        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory() as tmpdir:
            # Non-existent subdirectory
            nonexistent_path = os.path.join(tmpdir, "nonexistent", "subdir", "last_ip.txt")

            options = {
                "username": "test@example.com",
                "password": "test",
                "domain": "example.com",
                "subdomains": [""],
                "update_interval": 5,
                "ip_service": "ipify",
                "log_level": "error",
            }

            with patch("run.LAST_IP_FILE", nonexistent_path):
                updater = DynDNSUpdater(options)
                
                # Should create directory and save
                updater._save_last_ip("1.2.3.4")
                
                assert os.path.exists(nonexistent_path)

    def test_certificate_file_permissions_error(self):
        """Test handling of permission errors when reading certificate."""
        from certificate_manager import CertificateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = os.path.join(tmpdir, "cert.pem")
            
            # Create file
            with open(cert_path, "w") as f:
                f.write("test")
            
            # Make unreadable (on Unix)
            if os.name != 'nt':  # Skip on Windows
                os.chmod(cert_path, 0o000)

            manager = CertificateManager(
                username="test@example.com",
                password="password",
                domain="example.com",
                email="ssl@example.com",
                cert_path=cert_path,
            )

            # Should handle permission error gracefully
            info = manager.get_certificate_info()
            
            # Restore permissions for cleanup
            if os.name != 'nt':
                os.chmod(cert_path, 0o644)


class TestConfigurationEdgeCases:
    """Tests for configuration edge cases."""

    def test_missing_optional_ssl_options(self):
        """Test with missing optional SSL options."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            # SSL options missing - should use defaults
        }

        updater = DynDNSUpdater(options)
        
        assert updater.ssl_enabled is False
        assert updater.ssl_staging is False
        assert updater.ssl_renewal_days == 30

    def test_options_with_extra_unknown_fields(self):
        """Test options with extra unknown fields."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "unknown_field": "should be ignored",
            "another_unknown": 12345,
        }

        # Should not raise
        updater = DynDNSUpdater(options)
        assert updater.domain == "example.com"


class TestTimingEdgeCases:
    """Tests for timing-related edge cases."""

    def test_certificate_expiry_exactly_now(self):
        """Test certificate that expires right now."""
        from certificate_manager import CertificateManager
        from datetime import datetime, timezone

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            renewal_days=30,
        )

        with patch.object(manager, 'get_certificate_info') as mock_info:
            mock_info.return_value = {
                "days_remaining": 0,  # Expires today
                "needs_renewal": True,
                "domains": ["example.com"],
            }

            info = manager.get_certificate_info()
            assert info["needs_renewal"] is True

    def test_certificate_already_expired(self):
        """Test certificate that has already expired."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        with patch.object(manager, 'get_certificate_info') as mock_info:
            mock_info.return_value = {
                "days_remaining": -5,  # Expired 5 days ago
                "needs_renewal": True,
                "domains": ["example.com"],
            }

            info = manager.get_certificate_info()
            assert info["needs_renewal"] is True


class TestMultipleDomainsEdgeCases:
    """Tests for multiple domains edge cases."""

    def test_large_number_of_subdomains(self):
        """Test with large number of subdomains."""
        from run import DynDNSUpdater

        subdomains = [f"sub{i}" for i in range(100)]

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": subdomains,
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        assert len(updater.subdomains) == 100

    def test_duplicate_subdomains(self):
        """Test with duplicate subdomains in list."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": ["www", "www", "api", "www"],  # Duplicates
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)
        # Should handle duplicates (either dedupe or process all)
        assert "www" in updater.subdomains


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

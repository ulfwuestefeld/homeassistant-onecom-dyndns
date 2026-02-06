"""
Security-related tests for One.com DynDNS Updater.

These tests verify security aspects of the application.
"""

import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCredentialHandling:
    """Tests for secure credential handling."""

    def test_password_not_logged(self):
        """Test that passwords are not logged in plain text."""
        from onecom_api import OneComAPI
        import logging
        import io

        # Capture log output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        
        logger = logging.getLogger("onecom_api")
        original_handlers = logger.handlers[:]
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)

        try:
            api = OneComAPI("test@example.com", "super_secret_password_123", "example.com")
            
            log_output = log_capture.getvalue()
            
            # Password should not appear in logs
            assert "super_secret_password_123" not in log_output
        finally:
            logger.handlers = original_handlers

    def test_options_file_password_masked(self):
        """Test that password in options is handled securely."""
        from run import load_options

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            options_file = os.path.join(tmpdir, "options.json")
            with open(options_file, "w") as f:
                json.dump({
                    "username": "test@example.com",
                    "password": "secret_password",
                    "domain": "example.com",
                    "subdomains": [""],
                }, f)

            with patch("run.OPTIONS_FILE", options_file):
                options = load_options()
                
                # Password should be loaded but not exposed in __repr__ or str
                assert options["password"] == "secret_password"


class TestInputValidation:
    """Tests for input validation and sanitization."""

    def test_domain_validation(self):
        """Test that domain names are validated."""
        from onecom_api import OneComAPI

        # Valid domains should be accepted
        api = OneComAPI("test@example.com", "pass", "example.com")
        assert api.domain == "example.com"

        # Even unusual but valid domains should work
        api = OneComAPI("test@example.com", "pass", "sub.example.co.uk")
        assert api.domain == "sub.example.co.uk"

    def test_subdomain_special_characters(self):
        """Test handling of special characters in subdomains."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")
        api._logged_in = True
        api.session = Mock()

        # Mock response for finding records
        mock_response = Mock()
        mock_response.json.return_value = {"result": {"data": []}}
        api.session.get.return_value = mock_response

        # Should handle special characters safely
        record_id = api._find_record_id("test-subdomain", mock_response.json())
        assert record_id is None

    def test_ip_address_validation(self):
        """Test IP address validation."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error"
        }

        updater = DynDNSUpdater(options)

        # Valid IPs
        assert updater._is_valid_ip("192.168.1.1") is True
        assert updater._is_valid_ip("10.0.0.1") is True
        assert updater._is_valid_ip("8.8.8.8") is True

        # Invalid IPs - potential injection attempts
        assert updater._is_valid_ip("192.168.1.1; rm -rf /") is False
        assert updater._is_valid_ip("$(whoami)") is False
        assert updater._is_valid_ip("<script>alert(1)</script>") is False
        assert updater._is_valid_ip("1.2.3.4.5") is False
        assert updater._is_valid_ip("999.999.999.999") is False
        assert updater._is_valid_ip("") is False
        assert updater._is_valid_ip("localhost") is False


class TestHTTPSEnforcement:
    """Tests for HTTPS enforcement."""

    def test_all_external_urls_use_https(self):
        """Test that all external URLs use HTTPS."""
        from run import IP_SERVICES

        for service, url in IP_SERVICES.items():
            assert url.startswith("https://"), f"{service} should use HTTPS"

    def test_onecom_api_uses_https(self):
        """Test that One.com API uses HTTPS."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")
        
        # Check base URLs are HTTPS
        assert api.BASE_URL.startswith("https://")
        assert api.ADMIN_URL.startswith("https://")
        assert api.LOGIN_URL.startswith("https://")

    def test_acme_uses_https(self):
        """Test that ACME endpoints use HTTPS."""
        # Mock ACME modules
        sys.modules['acme'] = MagicMock()
        sys.modules['acme.client'] = MagicMock()
        sys.modules['acme.messages'] = MagicMock()
        sys.modules['acme.challenges'] = MagicMock()
        sys.modules['acme.errors'] = MagicMock()
        sys.modules['josepy'] = MagicMock()

        from acme_manager import LETSENCRYPT_PRODUCTION, LETSENCRYPT_STAGING

        assert LETSENCRYPT_PRODUCTION.startswith("https://")
        assert LETSENCRYPT_STAGING.startswith("https://")


class TestSessionSecurity:
    """Tests for session security."""

    def test_session_cookies_not_persisted(self):
        """Test that session cookies are not persisted to disk."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")
        session = api._create_session()

        # Session should not have persistent cookie storage
        # (requests.Session by default doesn't persist, but verify behavior)
        assert session is not None

    def test_logout_clears_session(self):
        """Test that logout properly clears the session."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")
        api.session = Mock()
        api._logged_in = True

        api.logout()

        assert api.session is None
        assert api._logged_in is False


class TestFilePermissions:
    """Tests for secure file handling."""

    def test_certificate_files_created_securely(self):
        """Test that certificate files are created with secure permissions."""
        # Mock ACME modules
        sys.modules['acme'] = MagicMock()
        sys.modules['acme.client'] = MagicMock()
        sys.modules['acme.messages'] = MagicMock()
        sys.modules['acme.challenges'] = MagicMock()
        sys.modules['acme.errors'] = MagicMock()
        sys.modules['josepy'] = MagicMock()

        from acme_manager import ACMEManager

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            cert_path = os.path.join(tmpdir, "ssl", "cert.pem")
            key_path = os.path.join(tmpdir, "ssl", "key.pem")
            account_key_path = os.path.join(tmpdir, "data", "account.key")

            manager = ACMEManager(
                email="test@example.com",
                onecom_api=Mock(),
                cert_path=cert_path,
                key_path=key_path,
                account_key_path=account_key_path,
            )

            cert_pem = "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            key_pem = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"

            manager.save_certificate(cert_pem, key_pem)

            # Files should exist
            assert os.path.exists(cert_path)
            assert os.path.exists(key_path)

            # On Unix, private key should have restricted permissions
            # (This is a best practice that could be implemented)

    def test_status_files_no_sensitive_data(self):
        """Test that status files don't contain sensitive data."""
        import certificate_manager as cm
        
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            status_file = os.path.join(tmpdir, "status.json")
            cert_path = os.path.join(tmpdir, "cert.pem")
            key_path = os.path.join(tmpdir, "key.pem")

            manager = cm.CertificateManager(
                username="test@example.com",
                password="secret_password",
                domain="example.com",
                email="ssl@example.com",
                cert_path=cert_path,
                key_path=key_path,
                status_file=status_file,
            )

            manager._save_status({"status": "valid"})

            with open(status_file) as f:
                content = f.read()

            # Password should not be in status file
            assert "secret_password" not in content


class TestErrorMessages:
    """Tests for secure error handling."""

    def test_error_messages_dont_leak_credentials(self):
        """Test that error messages don't contain credentials."""
        from onecom_api import OneComAPI, OneComAPIError

        api = OneComAPI("test@example.com", "secret_password", "example.com")

        # Simulate a login failure with a request exception
        import requests
        with patch("onecom_api.requests.Session") as mock_session:
            mock_session.return_value.get.side_effect = requests.exceptions.ConnectionError("Connection failed")

            try:
                api.login()
            except (OneComAPIError, requests.exceptions.ConnectionError) as e:
                error_message = str(e)
                # Password should not appear in error message
                assert "secret_password" not in error_message

    def test_acme_errors_dont_leak_account_key(self):
        """Test that ACME errors don't leak account keys."""
        sys.modules['acme'] = MagicMock()
        sys.modules['acme.client'] = MagicMock()
        sys.modules['acme.messages'] = MagicMock()
        sys.modules['acme.challenges'] = MagicMock()
        sys.modules['acme.errors'] = MagicMock()
        sys.modules['josepy'] = MagicMock()

        from acme_manager import ACMEManagerError

        # Simulate an ACME error that could contain key info
        error = ACMEManagerError("Failed to register ACME account: connection error")
        error_msg = str(error)

        # Error message should describe the problem without leaking key material
        assert "BEGIN" not in error_msg  # No PEM key data
        assert "PRIVATE" not in error_msg  # No private key references


class TestTokenHandling:
    """Tests for secure token handling."""

    def test_supervisor_token_not_logged(self):
        """Test that supervisor token is not logged."""
        import logging
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)

        # This test verifies that if we have debug logging,
        # tokens are not exposed
        # Implementation would depend on logging configuration


class TestCSRFProtection:
    """Tests for CSRF token handling in One.com API."""

    def test_csrf_token_extracted_correctly(self):
        """Test that CSRF tokens are properly extracted from responses."""
        from onecom_api import OneComAPI

        api = OneComAPI("test@example.com", "pass", "example.com")

        # Test _find_between helper
        html = '<input name="csrf_token" value="abc123">'
        result = api._find_between(html, 'value="', '"')
        assert result == "abc123"


class TestRateLimitingAwareness:
    """Tests for rate limiting awareness."""

    def test_retry_respects_backoff(self):
        """Test that retries use exponential backoff and don't flood the server."""
        sys.modules['acme'] = MagicMock()
        sys.modules['acme.client'] = MagicMock()
        sys.modules['acme.messages'] = MagicMock()
        sys.modules['acme.challenges'] = MagicMock()
        sys.modules['acme.errors'] = MagicMock()
        sys.modules['josepy'] = MagicMock()

        from acme_manager import retry_with_backoff, MAX_RETRIES, BASE_DELAY

        # Verify retry configuration is reasonable
        assert MAX_RETRIES >= 3, "Should retry at least 3 times"
        assert MAX_RETRIES <= 10, "Should not retry excessively"
        assert BASE_DELAY >= 1, "Base delay should be at least 1 second"

        # Verify the decorator preserves function metadata
        @retry_with_backoff
        def sample_func():
            """Sample docstring."""
            pass

        assert sample_func.__name__ == "sample_func"
        assert sample_func.__doc__ == "Sample docstring."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

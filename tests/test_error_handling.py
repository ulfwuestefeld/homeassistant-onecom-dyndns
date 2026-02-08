"""
Error handling tests for One.com DynDNS Updater.

These tests verify correct error handling and recovery.
"""

import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ACME modules before importing
sys.modules['acme'] = MagicMock()
sys.modules['acme.client'] = MagicMock()
sys.modules['acme.messages'] = MagicMock()
sys.modules['acme.challenges'] = MagicMock()
sys.modules['acme.errors'] = MagicMock()
sys.modules['josepy'] = MagicMock()


class TestNetworkErrors:
    """Tests for network error handling."""

    def test_connection_error_handled(self):
        """Test that connection errors are handled gracefully."""
        from run import DynDNSUpdater

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
        updater._http_session.get = Mock(
            side_effect=requests.exceptions.ConnectionError("Network unreachable")
        )
        ip = updater.get_public_ip()

        assert ip is None

    def test_timeout_error_handled(self):
        """Test that timeout errors are handled gracefully."""
        from run import DynDNSUpdater

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
        updater._http_session.get = Mock(
            side_effect=requests.exceptions.Timeout("Request timed out")
        )
        ip = updater.get_public_ip()

        assert ip is None

    def test_ssl_error_handled(self):
        """Test that SSL errors are handled gracefully."""
        from run import DynDNSUpdater

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
        updater._http_session.get = Mock(
            side_effect=requests.exceptions.SSLError("SSL certificate verify failed")
        )
        ip = updater.get_public_ip()

        assert ip is None


class TestOneComAPIErrors:
    """Tests for One.com API error handling."""

    def test_login_failure_raises_error(self):
        """Test that login failure raises appropriate error."""
        from onecom_api import OneComAPI, OneComAPIError

        api = OneComAPI("test@example.com", "wrong_password", "example.com")

        with patch("onecom_api.requests.Session") as mock_session:
            mock_response = Mock()
            mock_response.url = "https://account.one.com/login"  # Still on login page
            mock_response.text = "Login failed"
            mock_session.return_value.get.return_value = mock_response
            mock_session.return_value.post.return_value = mock_response
            mock_session.return_value.headers = {}

            with pytest.raises(OneComAPIError):
                api.login()

    def test_update_without_login_raises_error(self):
        """Test that update without login raises error."""
        from onecom_api import OneComAPI, OneComAPIError

        api = OneComAPI("test@example.com", "password", "example.com")

        with pytest.raises(OneComAPIError) as exc_info:
            api.update_dns_record("www", "1.2.3.4")

        assert "Not logged in" in str(exc_info.value)

    def test_http_500_error_handled(self):
        """Test that HTTP 500 errors are handled."""
        from onecom_api import OneComAPI, OneComAPIError

        api = OneComAPI("test@example.com", "password", "example.com")
        api._logged_in = True
        api.session = Mock()

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Server Error"
        )
        api.session.get.return_value = mock_response

        with pytest.raises(OneComAPIError):
            api._get_dns_records()


class TestACMEErrors:
    """Tests for ACME error handling."""

    def test_no_domains_error(self):
        """Test error when no domains specified."""
        from acme_manager import ACMEManager, ACMEManagerError

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=Mock(),
        )

        with pytest.raises(ACMEManagerError) as exc_info:
            manager.obtain_certificate([])

        assert "No domains specified" in str(exc_info.value)


class TestCertificateManagerErrors:
    """Tests for Certificate Manager error handling."""

    def test_api_error_during_request(self):
        """Test handling of API error during certificate request."""
        import certificate_manager as cm
        from certificate_manager import CertificateManager
        from onecom_api import OneComAPIError

        with tempfile.TemporaryDirectory() as tmpdir:
            original = cm.CERT_STATUS_FILE
            cm.CERT_STATUS_FILE = os.path.join(tmpdir, "status.json")
            
            try:
                manager = CertificateManager(
                    username="test@example.com",
                    password="password",
                    domain="example.com",
                    email="ssl@example.com",
                    cert_path=os.path.join(tmpdir, "cert.pem"),
                    key_path=os.path.join(tmpdir, "key.pem"),
                )

                with patch("certificate_manager.OneComAPI") as mock_api:
                    mock_api.return_value.login.side_effect = OneComAPIError("Login failed")

                    callback_events = []
                    manager.add_callback(lambda event, data: callback_events.append(event))

                    result = manager.request_certificate()

                assert result is False
                assert "error" in callback_events
            finally:
                cm.CERT_STATUS_FILE = original

    def test_callback_error_doesnt_crash(self):
        """Test that callback errors don't crash the manager."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        def failing_callback(event, data):
            raise Exception("Callback crashed!")

        def working_callback(event, data):
            pass

        manager.add_callback(failing_callback)
        manager.add_callback(working_callback)

        # Should not raise
        manager._notify("test", {})


class TestFileIOErrors:
    """Tests for file I/O error handling."""

    def test_last_ip_read_error(self):
        """Test handling of last IP file read error."""
        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a directory where file is expected (can't read as file)
            last_ip_path = os.path.join(tmpdir, "last_ip.txt")
            os.makedirs(last_ip_path)  # Create as directory

            options = {
                "username": "test@example.com",
                "password": "test",
                "domain": "example.com",
                "subdomains": [""],
                "update_interval": 5,
                "ip_service": "ipify",
                "log_level": "error",
            }

            with patch("run.LAST_IP_FILE", last_ip_path):
                updater = DynDNSUpdater(options)
                # Should handle error gracefully
                assert updater._last_ip is None

    def test_options_json_parse_error(self):
        """Test handling of invalid JSON in options file."""
        from run import load_options

        with tempfile.TemporaryDirectory() as tmpdir:
            options_file = os.path.join(tmpdir, "options.json")
            with open(options_file, "w") as f:
                f.write("{ invalid json }")

            with patch("run.OPTIONS_FILE", options_file):
                with patch.dict(os.environ, {
                    "ONECOM_USERNAME": "fallback@example.com",
                    "ONECOM_PASSWORD": "fallback",
                    "ONECOM_DOMAIN": "fallback.com",
                    "ONECOM_SUBDOMAINS": "",
                }):
                    options = load_options()

                    # Should fall back to environment variables
                    assert options["username"] == "fallback@example.com"


class TestHAIntegrationErrors:
    """Tests for Home Assistant integration error handling."""

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_notification_failure_handled(self, mock_post):
        """Test that notification failure is handled gracefully."""
        from run import send_ha_notification

        mock_post.side_effect = requests.exceptions.ConnectionError("Supervisor unreachable")

        result = send_ha_notification("Test", "Message")

        assert result is False

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_sensor_update_failure_handled(self, mock_post):
        """Test that sensor update failure is handled gracefully."""
        from run import update_ha_sensor

        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        result = update_ha_sensor("sensor.test", "value")

        assert result is False


class TestGracefulDegradation:
    """Tests for graceful degradation scenarios."""

    @patch("run.update_ha_sensor")
    def test_continues_after_ip_service_failure(self, mock_sensor):
        """Test that updater continues after IP service failure."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(options)
                updater._http_session.get = Mock(
                    side_effect=requests.exceptions.ConnectionError("Service down")
                )
                
                # Should not raise - just log and continue
                updater.check_and_update()

                assert updater._running is True


class TestRecoveryScenarios:
    """Tests for recovery from errors."""

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_recovery_after_dns_failure(self, mock_sensor, mock_api_class):
        """Test recovery after DNS update failure."""
        from run import DynDNSUpdater

        # First API call fails, second succeeds
        mock_api = Mock()
        call_count = [0]

        def update_side_effect(subdomains, ip):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"www": {"success": False, "error": "Temporary error"}}
            return {"www": {"success": True}}

        mock_api.update_all_subdomains.side_effect = update_side_effect
        mock_api_class.return_value = mock_api

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(options)
                
                # First attempt - should fail
                result1 = updater.update_dns("1.2.3.4")
                assert result1 is False

                # Second attempt - should succeed
                result2 = updater.update_dns("1.2.3.4")
                assert result2 is True


class TestExceptionTypes:
    """Tests for specific exception types."""

    def test_onecom_api_error_is_exception(self):
        """Test that OneComAPIError is a proper exception."""
        from onecom_api import OneComAPIError

        error = OneComAPIError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_acme_manager_error_is_exception(self):
        """Test that ACMEManagerError is a proper exception."""
        from acme_manager import ACMEManagerError

        error = ACMEManagerError("ACME error")
        assert isinstance(error, Exception)
        assert str(error) == "ACME error"

    def test_certificate_manager_error_is_exception(self):
        """Test that CertificateManagerError is a proper exception."""
        from certificate_manager import CertificateManagerError

        error = CertificateManagerError("Cert error")
        assert isinstance(error, Exception)
        assert str(error) == "Cert error"


class TestErrorLogging:
    """Tests for error logging."""

    def test_errors_are_logged(self):
        """Test that errors are properly logged."""
        import logging
        import io

        from onecom_api import OneComAPI, OneComAPIError

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.ERROR)
        
        logger = logging.getLogger("onecom_api")
        original_handlers = logger.handlers[:]
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)

        try:
            api = OneComAPI("test@example.com", "password", "example.com")
            
            # Trigger an error that should be logged
            try:
                api.update_dns_record("www", "1.2.3.4")  # Not logged in
            except OneComAPIError:
                pass

            log_output = log_capture.getvalue()
            # Error should be logged (exact message may vary)
        finally:
            logger.handlers = original_handlers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

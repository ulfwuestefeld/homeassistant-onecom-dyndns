"""
End-to-End (E2E) tests for One.com DynDNS Updater.

These tests simulate full workflows with mocked external services.
"""

import json
import os
import sys
import tempfile
import threading
import time
from unittest.mock import MagicMock, Mock, patch

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


class TestE2EDynDNSFlow:
    """End-to-end tests for DynDNS update flow."""

    @pytest.fixture
    def mock_options(self):
        """Standard test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www", "api", ""],
            "update_interval": 1,  # 1 minute for testing
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_full_dyndns_update_flow(self, mock_sensor, mock_api_class, mock_options):
        """Test complete DynDNS update flow when IP changes."""
        from run import DynDNSUpdater

        # Setup mocks
        mock_response = Mock()
        mock_response.text = "1.2.3.4"
        mock_response.raise_for_status = Mock()

        mock_api = Mock()
        mock_api.update_all_subdomains.return_value = {
            "www": {"success": True},
            "api": {"success": True},
            "": {"success": True},
        }
        mock_api_class.return_value = mock_api

        # Create updater with no previous IP
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")), \
                 patch("run.ADDON_STATE_FILE", os.path.join(tmpdir, "state.json")):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_response)
                
                # Run check and update
                updater.check_and_update()

                # Verify IP was detected
                updater._http_session.get.assert_called()
                
                # Verify DNS was updated
                mock_api.login.assert_called_once()
                mock_api.update_all_subdomains.assert_called_once_with(
                    ["www", "api", ""],
                    "1.2.3.4"
                )
                mock_api.logout.assert_called_once()

                # Verify state file was written (replaces update_ha_sensor)
                state_file = os.path.join(tmpdir, "state.json")
                assert os.path.isfile(state_file)
                with open(state_file) as f:
                    state = json.load(f)
                assert state["current_ip"] == "1.2.3.4"
                assert state["dns_status"] == "ok"

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_no_update_when_ip_unchanged(self, mock_sensor, mock_api_class, mock_options):
        """Test that DNS is not updated when IP hasn't changed."""
        from run import DynDNSUpdater

        mock_response = Mock()
        mock_response.text = "1.2.3.4"
        mock_response.raise_for_status = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with existing IP
            last_ip_file = os.path.join(tmpdir, "last_ip.txt")
            with open(last_ip_file, "w") as f:
                f.write("1.2.3.4")

            with patch("run.LAST_IP_FILE", last_ip_file):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_response)
                updater.check_and_update()

                # DNS API should NOT be called
                mock_api_class.assert_not_called()

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_ip_change_detection(self, mock_sensor, mock_api_class, mock_options):
        """Test IP change detection and update."""
        from run import DynDNSUpdater

        mock_response = Mock()
        mock_response.text = "5.6.7.8"  # New IP
        mock_response.raise_for_status = Mock()

        mock_api = Mock()
        mock_api.update_all_subdomains.return_value = {
            "www": {"success": True},
            "api": {"success": True},
            "": {"success": True},
        }
        mock_api_class.return_value = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with old IP
            last_ip_file = os.path.join(tmpdir, "last_ip.txt")
            with open(last_ip_file, "w") as f:
                f.write("1.2.3.4")  # Old IP

            with patch("run.LAST_IP_FILE", last_ip_file):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_response)
                updater.check_and_update()

                # DNS should be updated with new IP
                mock_api.update_all_subdomains.assert_called_once_with(
                    ["www", "api", ""],
                    "5.6.7.8"
                )

                # Last IP file should be updated
                with open(last_ip_file) as f:
                    assert f.read() == "5.6.7.8"


class TestE2ESSLCertificateFlow:
    """End-to-end tests for SSL certificate flow."""

    @pytest.fixture
    def ssl_options(self):
        """SSL-enabled test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 1,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": True,
            "ssl_email": "ssl@example.com",
            "ssl_domains": ["example.com", "www.example.com"],
            "ssl_staging": True,
            "ssl_renewal_days": 30,
            "ssl_check_interval": 12,
            "ssl_force_renewal": False,
        }

    @patch("run.CertificateManager")
    @patch("run.update_ha_sensor")
    def test_ssl_manager_initialization(self, mock_sensor, mock_cert_manager, ssl_options):
        """Test SSL certificate manager is initialized correctly."""
        from run import DynDNSUpdater

        mock_cert = Mock()
        mock_cert.get_certificate_info.return_value = {
            "not_valid_after": "2026-04-30",
            "days_remaining": 89,
        }
        mock_cert_manager.return_value = mock_cert

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(ssl_options)
                updater._start_ssl_manager()

                # Verify CertificateManager was created
                mock_cert_manager.assert_called_once()
                call_kwargs = mock_cert_manager.call_args[1]
                
                assert call_kwargs["email"] == "ssl@example.com"
                assert call_kwargs["staging"] is True
                assert "example.com" in call_kwargs["ssl_domains"]
                assert "www.example.com" in call_kwargs["ssl_domains"]

                # Verify manager was started
                mock_cert.start.assert_called_once()

    @patch("run.CertificateManager")
    @patch("run.update_ha_sensor")
    @patch("run.send_ha_notification")
    def test_ssl_force_renewal(self, mock_notify, mock_sensor, mock_cert_manager, ssl_options):
        """Test forced SSL certificate renewal."""
        from run import DynDNSUpdater

        mock_cert = Mock()
        mock_cert.request_certificate.return_value = True
        mock_cert.get_certificate_info.return_value = {
            "not_valid_after": "2026-04-30",
            "days_remaining": 89,
        }
        mock_cert_manager.return_value = mock_cert

        ssl_options["ssl_force_renewal"] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(ssl_options)
                updater._start_ssl_manager()

                # Verify force renewal was called
                mock_cert.request_certificate.assert_called_once_with(force=True)


class TestE2EErrorRecovery:
    """End-to-end tests for error recovery scenarios."""

    @pytest.fixture
    def mock_options(self):
        """Standard test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 1,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    @patch("run.update_ha_sensor")
    def test_recovery_from_ip_service_failure(self, mock_sensor, mock_options):
        """Test recovery when IP service fails then succeeds."""
        import requests

        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(mock_options)

                # First call fails, second succeeds
                updater._http_session.get = Mock(side_effect=[
                    requests.RequestException("Service unavailable"),
                    Mock(text="1.2.3.4", raise_for_status=Mock()),
                ])
                
                # First check - should fail gracefully
                updater.check_and_update()
                
                # Manually call again to simulate retry
                ip = updater.get_public_ip()
                assert ip == "1.2.3.4"

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_recovery_from_dns_update_failure(self, mock_sensor, mock_api_class, mock_options):
        """Test behavior when DNS update fails."""
        from onecom_api import OneComAPIError
        from run import DynDNSUpdater

        mock_response = Mock()
        mock_response.text = "1.2.3.4"
        mock_response.raise_for_status = Mock()

        # API login fails
        mock_api = Mock()
        mock_api.login.side_effect = OneComAPIError("Login failed")
        mock_api_class.return_value = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            last_ip_file = os.path.join(tmpdir, "last_ip.txt")
            
            with patch("run.LAST_IP_FILE", last_ip_file):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_response)
                updater.check_and_update()

                # IP should NOT be saved because DNS update failed
                assert not os.path.exists(last_ip_file) or open(last_ip_file).read() != "1.2.3.4"

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_partial_dns_update_failure(self, mock_sensor, mock_api_class, mock_options):
        """Test behavior when some DNS updates fail."""
        from run import DynDNSUpdater

        mock_options["subdomains"] = ["www", "api", "fail"]

        mock_api = Mock()
        mock_api.update_all_subdomains.return_value = {
            "www": {"success": True},
            "api": {"success": True},
            "fail": {"success": False, "error": "Record not found"},
        }
        mock_api_class.return_value = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(mock_options)
                result = updater.update_dns("1.2.3.4")

                # Should return False because not all updates succeeded
                assert result is False


class TestE2EGracefulShutdown:
    """End-to-end tests for graceful shutdown."""

    @pytest.fixture
    def mock_options(self):
        """Standard test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 1,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    @patch("run.update_ha_sensor")
    def test_graceful_stop(self, mock_sensor, mock_options):
        """Test graceful shutdown of updater."""
        from run import DynDNSUpdater

        mock_response = Mock()
        mock_response.text = "1.2.3.4"
        mock_response.raise_for_status = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_response)
                
                # Start in a thread
                def run_updater():
                    try:
                        updater.run()
                    except SystemExit:
                        pass

                thread = threading.Thread(target=run_updater)
                thread.daemon = True
                thread.start()

                # Let it run briefly
                time.sleep(0.5)

                # Stop gracefully
                updater.stop()

                # Wait for thread to finish
                thread.join(timeout=2)

                assert updater._running is False

    @patch("run.CertificateManager")
    @patch("run.update_ha_sensor")
    def test_ssl_manager_stopped_on_shutdown(self, mock_sensor, mock_cert_manager, mock_options):
        """Test SSL manager is stopped on shutdown."""
        from run import DynDNSUpdater

        mock_options["ssl_enabled"] = True
        mock_options["ssl_email"] = "ssl@example.com"

        mock_cert = Mock()
        mock_cert.get_certificate_info.return_value = None
        mock_cert_manager.return_value = mock_cert

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(mock_options)
                updater._start_ssl_manager()

                # Stop updater
                updater.stop()

                # Verify SSL manager was stopped
                mock_cert.stop.assert_called_once()


class TestE2EMultipleSubdomains:
    """End-to-end tests for multiple subdomain handling."""

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_update_multiple_subdomains(self, mock_sensor, mock_api_class):
        """Test updating multiple subdomains in one flow."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www", "api", "mail", "ftp", ""],
            "update_interval": 1,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

        mock_api = Mock()
        mock_api.update_all_subdomains.return_value = {
            "www": {"success": True},
            "api": {"success": True},
            "mail": {"success": True},
            "ftp": {"success": True},
            "": {"success": True},
        }
        mock_api_class.return_value = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(options)
                result = updater.update_dns("1.2.3.4")

                assert result is True
                mock_api.update_all_subdomains.assert_called_once_with(
                    ["www", "api", "mail", "ftp", ""],
                    "1.2.3.4"
                )


class TestE2EConfigurationValidation:
    """End-to-end tests for configuration validation."""

    def test_missing_required_config_stops_updater(self):
        """Test that missing required config prevents run."""
        from run import DynDNSUpdater

        options = {
            "username": "",  # Missing
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
        }

        updater = DynDNSUpdater(options)

        with pytest.raises(SystemExit):
            updater.run()

    def test_missing_ssl_email_when_ssl_enabled(self):
        """Test that SSL without email logs error but continues."""
        from run import DynDNSUpdater

        options = {
            "username": "test@example.com",
            "password": "test",
            "domain": "example.com",
            "subdomains": [""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": True,
            "ssl_email": "",  # Missing
        }

        updater = DynDNSUpdater(options)
        updater._start_ssl_manager()

        # SSL manager should not be started
        assert updater._cert_manager is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

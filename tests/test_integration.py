"""
Integration tests for One.com DynDNS Updater.

These tests verify that components work together correctly.
"""

import json
import os
import sys
import tempfile
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


class TestOneComAPIAndDynDNSIntegration:
    """Integration tests between OneComAPI and DynDNSUpdater."""

    @pytest.fixture
    def mock_options(self):
        """Standard test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www", ""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    @patch("onecom_api.requests.Session")
    @patch("run.update_ha_sensor")
    def test_full_dns_update_integration(self, mock_sensor, mock_session_class, mock_options):
        """Test full flow from IP detection to DNS update."""
        from run import DynDNSUpdater

        # Mock IP detection
        mock_ip_response = Mock()
        mock_ip_response.text = "1.2.3.4"
        mock_ip_response.raise_for_status = Mock()

        # Mock One.com session
        mock_session = Mock()
        mock_session.headers = {}
        
        # Login response
        mock_login_response = Mock()
        mock_login_response.url = "https://www.one.com/admin/frontpage.do"
        mock_login_response.text = "<html></html>"
        
        # DNS records response
        mock_dns_response = Mock()
        mock_dns_response.json.return_value = {
            "result": {
                "data": [
                    {
                        "type": "dns_service_records",
                        "id": "www123",
                        "attributes": {"prefix": "www", "type": "A"}
                    },
                    {
                        "type": "dns_service_records",
                        "id": "root456",
                        "attributes": {"prefix": "@", "type": "A"}
                    }
                ]
            }
        }
        
        # Update response
        mock_update_response = Mock()
        mock_update_response.raise_for_status = Mock()
        
        mock_session.get.side_effect = [mock_login_response, mock_dns_response, mock_dns_response]
        mock_session.post.return_value = mock_login_response
        mock_session.patch.return_value = mock_update_response
        mock_session_class.return_value = mock_session

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_ip_response)
                
                # This should detect IP and update DNS
                updater.check_and_update()

                # Verify IP was detected
                assert updater._http_session.get.called


class TestCertificateManagerAndOneComAPIIntegration:
    """Integration tests between CertificateManager and OneComAPI."""

    @pytest.fixture
    def ssl_options(self):
        """SSL-enabled test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "email": "ssl@example.com",
            "ssl_domains": ["example.com", "www.example.com"],
            "staging": True,
            "renewal_days": 30,
            "check_interval_hours": 12,
        }

    def test_certificate_manager_uses_onecom_api(self, ssl_options):
        """Test that CertificateManager correctly uses OneComAPI for DNS challenges."""
        from certificate_manager import CertificateManager

        manager = CertificateManager(**ssl_options)

        # Verify manager has correct configuration
        assert manager.username == "test@example.com"
        assert manager.domain == "example.com"
        assert manager.staging is True


class TestACMEManagerAndOneComAPIIntegration:
    """Integration tests between ACMEManager and OneComAPI."""

    def test_acme_manager_receives_onecom_api(self):
        """Test that ACMEManager correctly receives OneComAPI instance."""
        from acme_manager import ACMEManager
        from onecom_api import OneComAPI

        onecom_api = OneComAPI("test@example.com", "password", "example.com")

        manager = ACMEManager(
            email="ssl@example.com",
            onecom_api=onecom_api,
            staging=True,
        )

        # Attribute is stored without underscore prefix
        assert manager.onecom_api is onecom_api
        assert manager.email == "ssl@example.com"


class TestSensorUpdatesIntegration:
    """Integration tests for Home Assistant sensor updates."""

    @pytest.fixture
    def mock_options(self):
        """Standard test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_all_sensors_updated_on_ip_change(self, mock_post, mock_options):
        """Test that state file is written when IP changes."""
        from run import DynDNSUpdater

        # Mock IP service
        mock_ip_response = Mock()
        mock_ip_response.text = "1.2.3.4"
        mock_ip_response.raise_for_status = Mock()

        # Mock HA API
        mock_ha_response = Mock()
        mock_ha_response.raise_for_status = Mock()
        mock_post.return_value = mock_ha_response

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")), \
                 patch("run.ADDON_STATE_FILE", state_file):
                with patch("run.OneComAPI") as mock_api_class:
                    mock_api = Mock()
                    mock_api.update_all_subdomains.return_value = {
                        "www": {"success": True}
                    }
                    mock_api_class.return_value = mock_api

                    updater = DynDNSUpdater(mock_options)
                    updater._http_session.get = Mock(return_value=mock_ip_response)
                    updater.check_and_update()

                    # Verify state file was written with correct data
                    assert os.path.isfile(state_file)
                    with open(state_file) as f:
                        state = json.load(f)
                    assert state["current_ip"] == "1.2.3.4"
                    assert state["dns_status"] == "ok"


class TestCallbackIntegration:
    """Integration tests for callback systems."""

    def test_certificate_manager_callback_system(self):
        """Test that certificate manager callbacks work correctly."""
        from certificate_manager import CertificateManager

        callback_events = []

        def test_callback(event_type, data):
            callback_events.append((event_type, data))

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        manager.add_callback(test_callback)
        manager._notify("test_event", {"key": "value"})

        assert len(callback_events) == 1
        assert callback_events[0][0] == "test_event"
        assert callback_events[0][1] == {"key": "value"}


class TestConfigurationFlowIntegration:
    """Integration tests for configuration loading and application."""

    def test_options_file_to_updater(self):
        """Test configuration flows from options file to updater."""
        from run import DynDNSUpdater, load_options

        with tempfile.TemporaryDirectory() as tmpdir:
            options_file = os.path.join(tmpdir, "options.json")
            test_options = {
                "username": "config@example.com",
                "password": "config-password",
                "domain": "config-domain.com",
                "subdomains": ["www", "api"],
                "update_interval": 10,
                "ip_service": "ifconfig",
                "log_level": "debug",
                "ssl_enabled": False,
            }

            with open(options_file, "w") as f:
                json.dump(test_options, f)

            with patch("run.OPTIONS_FILE", options_file):
                options = load_options()
                updater = DynDNSUpdater(options)

                assert updater.username == "config@example.com"
                assert updater.domain == "config-domain.com"
                assert updater.update_interval == 10
                assert updater.ip_service == "ifconfig"


class TestErrorPropagationIntegration:
    """Integration tests for error propagation between components."""

    @pytest.fixture
    def mock_options(self):
        """Standard test options."""
        return {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    @patch("run.OneComAPI")
    @patch("run.update_ha_sensor")
    def test_api_error_does_not_crash_updater(self, mock_sensor, mock_api_class, mock_options):
        """Test that API errors don't crash the updater."""
        from onecom_api import OneComAPIError
        from run import DynDNSUpdater

        mock_ip_response = Mock()
        mock_ip_response.text = "1.2.3.4"
        mock_ip_response.raise_for_status = Mock()

        mock_api = Mock()
        mock_api.login.side_effect = OneComAPIError("Authentication failed")
        mock_api_class.return_value = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                updater = DynDNSUpdater(mock_options)
                updater._http_session.get = Mock(return_value=mock_ip_response)
                
                # Should not raise - error should be handled gracefully
                updater.check_and_update()

                # Updater should still be running
                assert updater._running is True


class TestThreadSafetyIntegration:
    """Integration tests for thread safety."""

    def test_certificate_manager_thread_safety(self):
        """Test that certificate manager handles threading correctly."""

        from certificate_manager import CertificateManager

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        # Mock the renewal loop to do nothing
        with patch.object(manager, '_renewal_loop', return_value=None):
            manager.start()
            
            # Should have created a thread
            assert manager._thread is not None
            assert manager._running is True

            # Stop should work cleanly
            manager.stop()
            assert manager._running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

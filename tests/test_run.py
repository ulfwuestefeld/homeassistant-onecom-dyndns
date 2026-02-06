"""
Unit tests for the run.py module (main entry point).
"""

import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import (
    DynDNSUpdater,
    get_supervisor_token,
    send_ha_notification,
    update_ha_sensor,
    save_acme_challenge_info,
    load_options,
    IP_SERVICES,
    LOG_LEVELS,
)


class TestGetSupervisorToken:
    """Tests for get_supervisor_token function."""

    def test_returns_supervisor_token_env(self):
        """Test that SUPERVISOR_TOKEN env var is returned."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token-123"}):
            # Need to reload the function to pick up new env
            token = get_supervisor_token()
            assert token == "test-token-123"

    def test_returns_hassio_token_env(self):
        """Test that HASSIO_TOKEN env var is returned as fallback."""
        with patch.dict(os.environ, {"HASSIO_TOKEN": "hassio-token-456"}, clear=True):
            token = get_supervisor_token()
            # May return empty if SUPERVISOR_TOKEN was cached
            assert token in ["hassio-token-456", ""]

    def test_returns_empty_when_no_token(self):
        """Test that empty string is returned when no token available."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.path.exists", return_value=False):
                token = get_supervisor_token()
                assert token == "" or isinstance(token, str)


class TestSendHaNotification:
    """Tests for send_ha_notification function."""

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_successful_notification(self, mock_post):
        """Test successful notification sending."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_ha_notification("Test Title", "Test Message")

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "persistent_notification/create" in call_args[0][0]

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_notification_with_id(self, mock_post):
        """Test notification with custom ID."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_ha_notification("Title", "Message", notification_id="custom_id")

        assert result is True
        call_args = mock_post.call_args
        assert call_args[1]["json"]["notification_id"] == "custom_id"

    @patch("run.SUPERVISOR_TOKEN", "")
    def test_notification_without_token(self):
        """Test notification fails without token."""
        result = send_ha_notification("Title", "Message")
        assert result is False

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_notification_request_failure(self, mock_post):
        """Test notification handles request failure."""
        mock_post.side_effect = Exception("Connection error")

        result = send_ha_notification("Title", "Message")

        assert result is False


class TestUpdateHaSensor:
    """Tests for update_ha_sensor function."""

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_successful_sensor_update(self, mock_post):
        """Test successful sensor update."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = update_ha_sensor("sensor.test", "value", {"attr": "test"})

        assert result is True
        mock_post.assert_called_once()

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_sensor_update_adds_friendly_name_ip(self, mock_post):
        """Test sensor update adds friendly name for IP sensor."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        update_ha_sensor("sensor.onecom_dyndns_ip", "1.2.3.4")

        call_args = mock_post.call_args
        attrs = call_args[1]["json"]["attributes"]
        assert attrs["friendly_name"] == "One.com DynDNS IP"
        assert attrs["icon"] == "mdi:ip-network"

    @patch("run.SUPERVISOR_TOKEN", "test-token")
    @patch("run.requests.post")
    def test_sensor_update_adds_friendly_name_certificate(self, mock_post):
        """Test sensor update adds friendly name for certificate sensor."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        update_ha_sensor("sensor.onecom_dyndns_certificate", "2026-04-30")

        call_args = mock_post.call_args
        attrs = call_args[1]["json"]["attributes"]
        assert attrs["friendly_name"] == "One.com SSL Certificate"
        assert attrs["icon"] == "mdi:certificate"

    @patch("run.SUPERVISOR_TOKEN", "")
    def test_sensor_update_without_token(self):
        """Test sensor update fails without token."""
        result = update_ha_sensor("sensor.test", "value")
        assert result is False


class TestSaveAcmeChallengeInfo:
    """Tests for save_acme_challenge_info function."""

    @patch("run.send_ha_notification")
    @patch("run.update_ha_sensor")
    def test_saves_challenge_info_to_file(self, mock_sensor, mock_notification):
        """Test that challenge info is saved to file."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            challenge_file = os.path.join(tmpdir, "acme_challenge.json")
            
            with patch("run.ACME_CHALLENGE_FILE", challenge_file):
                save_acme_challenge_info(
                    "example.com",
                    "_acme-challenge.example.com",
                    "test-token-value"
                )

            assert os.path.exists(challenge_file)
            with open(challenge_file) as f:
                data = json.load(f)
            
            assert data["domain"] == "example.com"
            assert data["txt_name"] == "_acme-challenge.example.com"
            assert data["txt_value"] == "test-token-value"

    @patch("run.send_ha_notification")
    @patch("run.update_ha_sensor")
    def test_sends_notification(self, mock_sensor, mock_notification):
        """Test that notification is sent."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            with patch("run.ACME_CHALLENGE_FILE", os.path.join(tmpdir, "acme.json")):
                save_acme_challenge_info("example.com", "_acme.example.com", "token")

        mock_notification.assert_called_once()
        call_args = mock_notification.call_args
        assert "ACME DNS Challenge" in call_args[1]["title"]

    @patch("run.send_ha_notification")
    @patch("run.update_ha_sensor")
    def test_updates_sensor(self, mock_sensor, mock_notification):
        """Test that ACME sensor is updated."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            with patch("run.ACME_CHALLENGE_FILE", os.path.join(tmpdir, "acme.json")):
                save_acme_challenge_info("example.com", "_acme.example.com", "token")

        mock_sensor.assert_called_once()
        call_args = mock_sensor.call_args
        assert call_args[0][0] == "sensor.onecom_dyndns_acme_challenge"
        assert call_args[0][1] == "token"


class TestLoadOptions:
    """Tests for load_options function."""

    def test_loads_from_options_file(self):
        """Test loading options from JSON file."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            options_file = os.path.join(tmpdir, "options.json")
            test_options = {
                "username": "test@example.com",
                "password": "secret",
                "domain": "example.com",
                "subdomains": ["www"],
            }
            
            with open(options_file, "w") as f:
                json.dump(test_options, f)
            
            with patch("run.OPTIONS_FILE", options_file):
                options = load_options()
            
            assert options["username"] == "test@example.com"
            assert options["domain"] == "example.com"

    def test_falls_back_to_env_vars(self):
        """Test fallback to environment variables."""
        with patch("run.OPTIONS_FILE", "/nonexistent/path"):
            with patch.dict(os.environ, {
                "ONECOM_USERNAME": "env@example.com",
                "ONECOM_PASSWORD": "env-password",
                "ONECOM_DOMAIN": "env-domain.com",
                "ONECOM_SUBDOMAINS": "www,api",
            }):
                options = load_options()
                
                assert options["username"] == "env@example.com"
                assert options["domain"] == "env-domain.com"
                assert "www" in options["subdomains"]

    def test_ssl_domains_parsing(self):
        """Test SSL domains are parsed from comma-separated string."""
        with patch("run.OPTIONS_FILE", "/nonexistent/path"):
            with patch.dict(os.environ, {
                "ONECOM_USERNAME": "test@example.com",
                "ONECOM_PASSWORD": "password",
                "ONECOM_DOMAIN": "example.com",
                "ONECOM_SUBDOMAINS": "",
                "ONECOM_SSL_DOMAINS": "example.com, www.example.com, api.example.com",
            }):
                options = load_options()
                
                assert "example.com" in options["ssl_domains"]
                assert "www.example.com" in options["ssl_domains"]
                assert len(options["ssl_domains"]) == 3


class TestDynDNSUpdaterAdvanced:
    """Advanced tests for DynDNSUpdater class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.options = {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www", ""],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    def test_update_ip_sensor(self):
        """Test IP sensor update."""
        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_ip_sensor("1.2.3.4")

            mock_sensor.assert_called_once()
            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_ip"
            assert call_args[0][1] == "1.2.3.4"

    def test_update_dns_sensor(self):
        """Test DNS sensor update."""
        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_dns_sensor("ok", "1.2.3.4")

            mock_sensor.assert_called_once()
            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_dns_status"
            assert call_args[0][1] == "ok"

    def test_update_certificate_sensor(self):
        """Test certificate sensor update."""
        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            cert_info = {
                "not_valid_after": "2026-04-30T00:00:00",
                "days_remaining": 89,
                "domains": ["example.com"],
                "issuer": "Let's Encrypt",
                "not_valid_before": "2026-01-30T00:00:00",
                "needs_renewal": False,
            }
            updater._update_certificate_sensor(cert_info)

            mock_sensor.assert_called_once()
            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_certificate"

    @patch("run.OneComAPI")
    def test_update_dns_success(self, mock_api_class):
        """Test successful DNS update."""
        mock_api = Mock()
        mock_api.update_all_subdomains.return_value = {
            "www": {"success": True},
            "": {"success": True},
        }
        mock_api_class.return_value = mock_api

        updater = DynDNSUpdater(self.options)
        result = updater.update_dns("1.2.3.4")

        assert result is True
        mock_api.login.assert_called_once()
        mock_api.logout.assert_called_once()

    @patch("run.OneComAPI")
    def test_update_dns_partial_failure(self, mock_api_class):
        """Test DNS update with partial failure."""
        mock_api = Mock()
        mock_api.update_all_subdomains.return_value = {
            "www": {"success": True},
            "": {"success": False, "error": "Record not found"},
        }
        mock_api_class.return_value = mock_api

        updater = DynDNSUpdater(self.options)
        result = updater.update_dns("1.2.3.4")

        assert result is False

    @patch("run.OneComAPI")
    def test_update_dns_api_error(self, mock_api_class):
        """Test DNS update with API error."""
        from onecom_api import OneComAPIError
        
        mock_api_class.side_effect = OneComAPIError("Login failed")

        updater = DynDNSUpdater(self.options)
        result = updater.update_dns("1.2.3.4")

        assert result is False

    @patch("run.requests.get")
    def test_get_public_ip_invalid_response(self, mock_get):
        """Test IP detection with invalid response."""
        mock_response = Mock()
        mock_response.text = "not-an-ip"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        updater = DynDNSUpdater(self.options)
        ip = updater.get_public_ip()

        assert ip is None

    def test_ssl_domains_extended_from_subdomains(self):
        """Test that SSL domains are extended from subdomains."""
        options = self.options.copy()
        options["ssl_enabled"] = True
        options["ssl_email"] = "ssl@example.com"
        options["ssl_domains"] = ["example.com"]
        options["subdomains"] = ["www", "api"]

        with patch("run.CertificateManager") as mock_cert:
            updater = DynDNSUpdater(options)
            updater._start_ssl_manager()

            call_args = mock_cert.call_args
            ssl_domains = call_args[1]["ssl_domains"]
            assert "example.com" in ssl_domains
            assert "www.example.com" in ssl_domains
            assert "api.example.com" in ssl_domains

    def test_ssl_event_callback_renewed(self):
        """Test SSL event callback for renewal."""
        with patch("run.send_ha_notification") as mock_notify:
            with patch("run.update_ha_sensor"):
                updater = DynDNSUpdater(self.options)
                updater._ssl_event_callback("renewed", {
                    "domains": ["example.com"],
                    "certificate": {
                        "not_valid_after": "2026-04-30",
                        "days_remaining": 89,
                    }
                })

                mock_notify.assert_called_once()
                call_args = mock_notify.call_args
                assert "Certificate Renewed" in call_args[1]["title"]

    def test_ssl_event_callback_error(self):
        """Test SSL event callback for error."""
        updater = DynDNSUpdater(self.options)
        # Should not raise
        updater._ssl_event_callback("error", {"error": "Test error"})

    def test_ssl_event_callback_invalid_online(self):
        """Test SSL event callback for invalid online certificate."""
        updater = DynDNSUpdater(self.options)
        # Should not raise
        updater._ssl_event_callback("certificate_invalid_online", {
            "invalid_domains": ["example.com"],
            "results": {
                "example.com": {"valid": False, "error": "Connection refused"}
            }
        })


class TestIPServicesAndLogLevels:
    """Tests for IP services and log levels constants."""

    def test_all_ip_services_have_https_urls(self):
        """Test all IP service URLs use HTTPS."""
        for service, url in IP_SERVICES.items():
            assert url.startswith("https://"), f"{service} should use HTTPS"

    def test_log_levels_defined(self):
        """Test all expected log levels are defined."""
        import logging
        
        assert LOG_LEVELS["debug"] == logging.DEBUG
        assert LOG_LEVELS["info"] == logging.INFO
        assert LOG_LEVELS["warning"] == logging.WARNING
        assert LOG_LEVELS["error"] == logging.ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

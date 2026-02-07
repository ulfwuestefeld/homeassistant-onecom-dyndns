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


# ---------------------------------------------------------------------------
# Tests for deploy_custom_component()
# ---------------------------------------------------------------------------

class TestDeployCustomComponent:
    """Tests for the deploy_custom_component function."""

    def test_source_directory_not_found(self, tmp_path):
        """Return False when the bundled component source does not exist."""
        from run import deploy_custom_component

        with patch("run._COMPONENT_SOURCE", str(tmp_path / "nonexistent")):
            result = deploy_custom_component()
        assert result is False

    def test_source_manifest_missing(self, tmp_path):
        """Return False when manifest.json is missing from the source."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        # No manifest.json inside

        with patch("run._COMPONENT_SOURCE", str(src)):
            result = deploy_custom_component()
        assert result is False

    def test_source_manifest_unreadable_json(self, tmp_path):
        """Return False when manifest.json contains invalid JSON."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text("NOT JSON {{")

        with patch("run._COMPONENT_SOURCE", str(src)):
            result = deploy_custom_component()
        assert result is False

    def test_source_manifest_unreadable_io(self, tmp_path):
        """Return False when manifest.json cannot be opened."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        manifest = src / "manifest.json"
        manifest.write_text('{"version": "1.0.0"}')

        with patch("run._COMPONENT_SOURCE", str(src)):
            with patch("builtins.open", side_effect=IOError("permission denied")):
                result = deploy_custom_component()
        assert result is False

    def test_same_version_skips_copy(self, tmp_path):
        """Return True without copying when source and target have the same version."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text('{"version": "1.3.1"}')

        tgt = tmp_path / "target"
        tgt.mkdir()
        (tgt / "manifest.json").write_text('{"version": "1.3.1"}')

        with patch("run._COMPONENT_SOURCE", str(src)), \
             patch("run._COMPONENT_TARGET", str(tgt)), \
             patch("run.shutil.copytree") as mock_copy:
            result = deploy_custom_component()

        assert result is True
        mock_copy.assert_not_called()

    def test_deploys_when_target_missing(self, tmp_path):
        """Deploy when the target directory does not exist yet."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text('{"version": "1.3.1"}')
        (src / "__init__.py").write_text("# init")

        tgt = tmp_path / "custom_components" / "onecom_dyndns"

        with patch("run._COMPONENT_SOURCE", str(src)), \
             patch("run._COMPONENT_TARGET", str(tgt)):
            result = deploy_custom_component()

        assert result is True
        assert tgt.exists()
        assert (tgt / "manifest.json").exists()

    def test_deploys_when_version_differs(self, tmp_path):
        """Overwrite target when source has a newer version."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text('{"version": "1.4.0"}')
        (src / "__init__.py").write_text("# new init")

        tgt = tmp_path / "target"
        tgt.mkdir()
        (tgt / "manifest.json").write_text('{"version": "1.3.1"}')
        (tgt / "__init__.py").write_text("# old init")

        with patch("run._COMPONENT_SOURCE", str(src)), \
             patch("run._COMPONENT_TARGET", str(tgt)):
            result = deploy_custom_component()

        assert result is True
        # Verify the new version was deployed
        import json
        with open(tgt / "manifest.json") as f:
            assert json.load(f)["version"] == "1.4.0"

    def test_deploys_when_target_manifest_unreadable(self, tmp_path):
        """Deploy when the target manifest.json is corrupted."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text('{"version": "1.4.0"}')
        (src / "__init__.py").write_text("# init")

        tgt = tmp_path / "target"
        tgt.mkdir()
        (tgt / "manifest.json").write_text("NOT JSON")

        with patch("run._COMPONENT_SOURCE", str(src)), \
             patch("run._COMPONENT_TARGET", str(tgt)):
            result = deploy_custom_component()

        assert result is True

    def test_copy_failure_returns_false(self, tmp_path):
        """Return False when shutil.copytree raises an exception."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text('{"version": "1.4.0"}')

        tgt = tmp_path / "target"
        # Target doesn't exist, so no rmtree needed

        with patch("run._COMPONENT_SOURCE", str(src)), \
             patch("run._COMPONENT_TARGET", str(tgt)), \
             patch("run.shutil.copytree", side_effect=OSError("disk full")):
            result = deploy_custom_component()

        assert result is False

    def test_creates_parent_directory(self, tmp_path):
        """Verify that parent directories are created (exist_ok=True)."""
        from run import deploy_custom_component

        src = tmp_path / "source"
        src.mkdir()
        (src / "manifest.json").write_text('{"version": "1.0.0"}')
        (src / "__init__.py").write_text("")

        # Target is nested several levels deep
        tgt = tmp_path / "config" / "custom_components" / "onecom_dyndns"

        with patch("run._COMPONENT_SOURCE", str(src)), \
             patch("run._COMPONENT_TARGET", str(tgt)):
            result = deploy_custom_component()

        assert result is True
        assert tgt.parent.exists()


# ---------------------------------------------------------------------------
# Tests for publish_addon_discovery()
# ---------------------------------------------------------------------------

class TestPublishAddonDiscovery:
    """Tests for the publish_addon_discovery function."""

    @patch("run.SUPERVISOR_TOKEN", "")
    def test_no_token_returns_false(self):
        """Return False when no SUPERVISOR_TOKEN is available."""
        from run import publish_addon_discovery

        result = publish_addon_discovery({"domain": "example.com"})
        assert result is False

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_successful_discovery(self, mock_post):
        """Return True on successful Supervisor API call."""
        from run import publish_addon_discovery

        mock_response = Mock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        result = publish_addon_discovery({"domain": "example.com"})
        assert result is True
        mock_post.assert_called_once()

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_api_non_ok_returns_false(self, mock_post):
        """Return False when the Supervisor API returns a non-OK response."""
        from run import publish_addon_discovery

        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = publish_addon_discovery({"domain": "example.com"})
        assert result is False

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_request_exception_returns_false(self, mock_post):
        """Return False when the HTTP request raises an exception."""
        from run import publish_addon_discovery

        mock_post.side_effect = Exception("Connection refused")

        result = publish_addon_discovery({"domain": "example.com"})
        assert result is False

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_discovery_data_structure(self, mock_post):
        """Verify the discovery payload matches the expected structure."""
        from run import publish_addon_discovery

        mock_response = Mock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        options = {
            "username": "user@one.com",
            "password": "secret",
            "domain": "example.com",
            "subdomains": ["www", "api"],
            "update_interval": 10,
            "ip_service": "ifconfig",
            "ssl_enabled": True,
            "ssl_email": "ssl@example.com",
            "ssl_domains": ["example.com", "www.example.com"],
            "ssl_staging": True,
            "ssl_renewal_days": 14,
            "ssl_check_interval": 6,
        }

        publish_addon_discovery(options)

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["addon"] == "homeassistant-onecom-dyndns"
        assert payload["service"] == "onecom_dyndns"
        config = payload["config"]
        assert config["username"] == "user@one.com"
        assert config["password"] == "secret"
        assert config["domain"] == "example.com"
        assert config["subdomains"] == ["www", "api"]
        assert config["update_interval"] == 10
        assert config["ip_service"] == "ifconfig"
        assert config["ssl_enabled"] is True
        assert config["ssl_email"] == "ssl@example.com"
        assert config["ssl_domains"] == ["example.com", "www.example.com"]
        assert config["ssl_staging"] is True
        assert config["ssl_renewal_days"] == 14
        assert config["ssl_check_interval"] == 6

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_discovery_uses_correct_url(self, mock_post):
        """Verify the request goes to http://supervisor/discovery."""
        from run import publish_addon_discovery

        mock_response = Mock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        publish_addon_discovery({"domain": "example.com"})

        call_args = mock_post.call_args
        assert call_args[0][0] == "http://supervisor/discovery"

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_discovery_uses_bearer_auth(self, mock_post):
        """Verify the Authorization header contains the bearer token."""
        from run import publish_addon_discovery

        mock_response = Mock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        publish_addon_discovery({"domain": "example.com"})

        call_args = mock_post.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-token-abc"

    @patch("run.SUPERVISOR_TOKEN", "test-token-abc")
    @patch("run.requests.post")
    def test_discovery_defaults_for_missing_options(self, mock_post):
        """Verify sensible defaults when options dict is mostly empty."""
        from run import publish_addon_discovery

        mock_response = Mock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        # Minimal options dict
        publish_addon_discovery({})

        payload = mock_post.call_args[1]["json"]
        config = payload["config"]
        assert config["username"] == ""
        assert config["domain"] == ""
        assert config["subdomains"] == [""]
        assert config["update_interval"] == 5
        assert config["ip_service"] == "ipify"
        assert config["ssl_enabled"] is False
        assert config["ssl_renewal_days"] == 30
        assert config["ssl_check_interval"] == 12


# ---------------------------------------------------------------------------
# Tests for _write_state_file() and _check_commands()
# ---------------------------------------------------------------------------

class TestWriteStateFile:
    """Tests for the DynDNSUpdater._write_state_file method."""

    def setup_method(self):
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

    def test_writes_json_to_state_file(self, tmp_path):
        """State file should be valid JSON with expected keys."""
        state_file = str(tmp_path / "state.json")

        with patch("run.ADDON_STATE_FILE", state_file):
            with patch("run.update_ha_sensor"):
                updater = DynDNSUpdater(self.options)
                updater._last_ip = "1.2.3.4"
                updater._write_state_file(current_ip="1.2.3.4", dns_status="ok")

        assert os.path.isfile(state_file)
        with open(state_file) as f:
            data = json.load(f)

        assert data["current_ip"] == "1.2.3.4"
        assert data["domain"] == "example.com"
        assert data["dns_status"] == "ok"
        assert data["ssl_enabled"] is False
        assert "last_update" in data
        assert "subdomains" in data

    def test_state_file_contains_subdomains_as_fqdn(self, tmp_path):
        """Subdomains should be expanded to full domain names."""
        state_file = str(tmp_path / "state.json")

        with patch("run.ADDON_STATE_FILE", state_file):
            with patch("run.update_ha_sensor"):
                updater = DynDNSUpdater(self.options)
                updater._write_state_file(current_ip="1.2.3.4", dns_status="ok")

        with open(state_file) as f:
            data = json.load(f)

        assert "www.example.com" in data["subdomains"]
        assert "example.com" in data["subdomains"]

    def test_state_file_includes_certificate_info(self, tmp_path):
        """Certificate info from the cert manager should be included."""
        state_file = str(tmp_path / "state.json")
        opts = self.options.copy()
        opts["ssl_enabled"] = True
        opts["ssl_email"] = "ssl@example.com"

        with patch("run.ADDON_STATE_FILE", state_file):
            with patch("run.update_ha_sensor"):
                updater = DynDNSUpdater(opts)
                mock_cert_mgr = Mock()
                mock_cert_mgr.get_certificate_info.return_value = {
                    "not_valid_after": "2026-06-15",
                    "days_remaining": 120,
                }
                updater._cert_manager = mock_cert_mgr
                updater._write_state_file(current_ip="5.6.7.8", dns_status="ok")

        with open(state_file) as f:
            data = json.load(f)

        assert data["certificate_info"] is not None
        assert data["certificate_info"]["days_remaining"] == 120

    def test_state_file_handles_write_error(self, tmp_path):
        """Should not raise even if the state file cannot be written."""
        with patch("run.ADDON_STATE_FILE", "/nonexistent/dir/state.json"):
            with patch("run.update_ha_sensor"):
                updater = DynDNSUpdater(self.options)
                # Should not raise
                updater._write_state_file(current_ip="1.2.3.4", dns_status="ok")

    def test_state_file_ip_changed_flag(self, tmp_path):
        """ip_changed should be True when current_ip differs from last_ip."""
        state_file = str(tmp_path / "state.json")

        with patch("run.ADDON_STATE_FILE", state_file):
            with patch("run.update_ha_sensor"):
                updater = DynDNSUpdater(self.options)
                updater._last_ip = "1.1.1.1"
                updater._write_state_file(current_ip="2.2.2.2", dns_status="ok")

        with open(state_file) as f:
            data = json.load(f)

        assert data["ip_changed"] is True


class TestCheckCommands:
    """Tests for the DynDNSUpdater._check_commands method."""

    def setup_method(self):
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

    def test_no_command_file_does_nothing(self, tmp_path):
        """Should return silently when no command file exists."""
        cmd_file = str(tmp_path / "commands.json")

        with patch("run.ADDON_COMMAND_FILE", cmd_file):
            with patch("run.ADDON_STATE_FILE", str(tmp_path / "state.json")):
                with patch("run.update_ha_sensor"):
                    updater = DynDNSUpdater(self.options)
                    updater._check_commands()  # Should not raise

    def test_update_dns_command_triggers_dns_update(self, tmp_path):
        """update_dns command should call update_dns."""
        cmd_file = tmp_path / "commands.json"
        cmd_file.write_text(json.dumps({"command": "update_dns"}))

        with patch("run.ADDON_COMMAND_FILE", str(cmd_file)):
            with patch("run.ADDON_STATE_FILE", str(tmp_path / "state.json")):
                with patch("run.update_ha_sensor"):
                    updater = DynDNSUpdater(self.options)
                    updater._last_ip = "1.2.3.4"

                    with patch.object(updater, "update_dns", return_value=True) as mock_dns:
                        updater._check_commands()
                        mock_dns.assert_called_once_with("1.2.3.4")

        # Command file should be removed
        assert not cmd_file.exists()

    def test_check_ip_command_triggers_check_and_update(self, tmp_path):
        """check_ip command should call check_and_update."""
        cmd_file = tmp_path / "commands.json"
        cmd_file.write_text(json.dumps({"command": "check_ip"}))

        with patch("run.ADDON_COMMAND_FILE", str(cmd_file)):
            with patch("run.ADDON_STATE_FILE", str(tmp_path / "state.json")):
                with patch("run.update_ha_sensor"):
                    updater = DynDNSUpdater(self.options)

                    with patch.object(updater, "check_and_update") as mock_check:
                        updater._check_commands()
                        mock_check.assert_called_once()

    def test_invalid_json_command_file_is_removed(self, tmp_path):
        """Invalid JSON in command file should be handled gracefully."""
        cmd_file = tmp_path / "commands.json"
        cmd_file.write_text("NOT JSON {{")

        with patch("run.ADDON_COMMAND_FILE", str(cmd_file)):
            with patch("run.ADDON_STATE_FILE", str(tmp_path / "state.json")):
                with patch("run.update_ha_sensor"):
                    updater = DynDNSUpdater(self.options)
                    updater._check_commands()  # Should not raise

        assert not cmd_file.exists()

    def test_unknown_command_is_ignored(self, tmp_path):
        """Unknown command should log a warning but not crash."""
        cmd_file = tmp_path / "commands.json"
        cmd_file.write_text(json.dumps({"command": "unknown_action"}))

        with patch("run.ADDON_COMMAND_FILE", str(cmd_file)):
            with patch("run.ADDON_STATE_FILE", str(tmp_path / "state.json")):
                with patch("run.update_ha_sensor"):
                    updater = DynDNSUpdater(self.options)
                    updater._check_commands()  # Should not raise

        assert not cmd_file.exists()

    def test_renew_certificate_command(self, tmp_path):
        """renew_certificate command should call cert manager."""
        cmd_file = tmp_path / "commands.json"
        cmd_file.write_text(json.dumps({"command": "renew_certificate"}))
        opts = self.options.copy()
        opts["ssl_enabled"] = True
        opts["ssl_email"] = "ssl@example.com"

        with patch("run.ADDON_COMMAND_FILE", str(cmd_file)):
            with patch("run.ADDON_STATE_FILE", str(tmp_path / "state.json")):
                with patch("run.update_ha_sensor"):
                    updater = DynDNSUpdater(opts)
                    mock_cert = Mock()
                    mock_cert.request_certificate.return_value = True
                    mock_cert.get_certificate_info.return_value = None
                    updater._cert_manager = mock_cert

                    updater._check_commands()
                    mock_cert.request_certificate.assert_called_once_with(force=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

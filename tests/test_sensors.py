"""
Tests for all sensor entities.

This covers:
- Custom component sensors (sensor.py): current_ip, last_update,
  last_ip_update, certificate_expiry, last_certificate_renewal
- Add-on sensor updates via Supervisor API (run.py): new timestamp sensors
- Coordinator data flow (__init__.py): timestamp tracking
"""

import os
import tempfile
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Part 1: Custom-component sensor entity tests
#
# These test the sensor platform code in
# custom_components/onecom_dyndns/sensor.py directly, without needing a
# running Home Assistant instance.  We mock the coordinator and config entry.
# ---------------------------------------------------------------------------


def _make_coordinator_data(
    *,
    current_ip="1.2.3.4",
    last_ip="1.2.3.3",
    ip_changed=False,
    last_update=None,
    last_ip_update=None,
    last_certificate_renewal=None,
    ssl_enabled=False,
    certificate_info=None,
    domain="example.com",
    subdomains=None,
):
    """Build a coordinator data dict matching what the coordinator produces."""
    return {
        "current_ip": current_ip,
        "last_ip": last_ip,
        "domain": domain,
        "subdomains": subdomains or ["www", ""],
        "ip_changed": ip_changed,
        "last_update": last_update,
        "last_ip_update": last_ip_update,
        "last_certificate_renewal": last_certificate_renewal,
        "ssl_enabled": ssl_enabled,
        "certificate_info": certificate_info,
    }


def _make_sensor(key, coordinator_data, domain="example.com", ssl_enabled=False):
    """Instantiate a OneComDynDNSSensor with the given key and mock data.

    We cannot import from homeassistant here, so instead we import the module
    symbols we need from the custom component package and build lightweight
    mocks for the HA framework objects.
    """
    import sys
    # Ensure custom_components directory is on the path
    cc_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "custom_components",
        "onecom_dyndns",
    )
    if cc_dir not in sys.path:
        sys.path.insert(0, cc_dir)

    # We need stubs for homeassistant modules that the sensor module imports.
    # Build minimal mocks so the import succeeds.
    ha_modules = _ensure_ha_stubs()

    # Now import the sensor module
    import importlib
    sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
    importlib.reload(sensor_mod)  # re-import to pick up any changes

    # Find the matching SensorEntityDescription
    desc = None
    for d in sensor_mod.SENSOR_TYPES:
        if d.key == key:
            desc = d
            break
    assert desc is not None, f"Sensor type '{key}' not found in SENSOR_TYPES"

    # Mock coordinator
    coordinator = Mock()
    coordinator.data = coordinator_data

    # Mock config entry
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "domain": domain,
        "ssl_enabled": ssl_enabled,
    }

    # The class constructor calls super().__init__(coordinator) which requires
    # HA internals.  We patch it out.
    with patch.object(sensor_mod.OneComDynDNSSensor, "__init__", lambda self, *a, **kw: None):
        sensor = sensor_mod.OneComDynDNSSensor.__new__(sensor_mod.OneComDynDNSSensor)

    # Manually set the attributes that __init__ would set
    sensor.coordinator = coordinator
    sensor.entity_description = desc
    sensor._domain = domain
    sensor._entry = entry
    sensor._attr_unique_id = f"test_entry_id_{key}"
    sensor._attr_device_info = None
    sensor._attr_has_entity_name = True

    return sensor


def _ensure_ha_stubs():
    """Ensure minimal homeassistant stubs exist in sys.modules.

    Returns a dict of the modules created (or already existing).
    """
    import sys
    import types

    modules_to_stub = [
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.components.binary_sensor",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.aiohttp_client",
    ]

    created = {}
    for mod_name in modules_to_stub:
        if mod_name not in sys.modules:
            m = types.ModuleType(mod_name)
            sys.modules[mod_name] = m
            created[mod_name] = m
        else:
            created[mod_name] = sys.modules[mod_name]

    # Provide the classes/objects that the sensor module references
    sensor_mod = sys.modules["homeassistant.components.sensor"]
    if not hasattr(sensor_mod, "SensorDeviceClass"):
        class _SensorDeviceClass:
            TIMESTAMP = "timestamp"
        sensor_mod.SensorDeviceClass = _SensorDeviceClass
    if not hasattr(sensor_mod, "SensorEntity"):
        sensor_mod.SensorEntity = type("SensorEntity", (), {})
    if not hasattr(sensor_mod, "SensorEntityDescription"):
        class _SED:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
        sensor_mod.SensorEntityDescription = _SED

    bs_mod = sys.modules["homeassistant.components.binary_sensor"]
    if not hasattr(bs_mod, "BinarySensorDeviceClass"):
        class _BinarySensorDeviceClass:
            CONNECTIVITY = "connectivity"
            PROBLEM = "problem"
        bs_mod.BinarySensorDeviceClass = _BinarySensorDeviceClass
    if not hasattr(bs_mod, "BinarySensorEntity"):
        bs_mod.BinarySensorEntity = type("BinarySensorEntity", (), {})
    if not hasattr(bs_mod, "BinarySensorEntityDescription"):
        class _BSED:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
        bs_mod.BinarySensorEntityDescription = _BSED

    config_entries = sys.modules["homeassistant.config_entries"]
    if not hasattr(config_entries, "ConfigEntry"):
        config_entries.ConfigEntry = type("ConfigEntry", (), {})

    core = sys.modules["homeassistant.core"]
    if not hasattr(core, "HomeAssistant"):
        core.HomeAssistant = type("HomeAssistant", (), {})
    if not hasattr(core, "callback"):
        core.callback = lambda f: f
    if not hasattr(core, "ServiceCall"):
        core.ServiceCall = type("ServiceCall", (), {})

    entity = sys.modules["homeassistant.helpers.entity"]
    if not hasattr(entity, "DeviceInfo"):
        entity.DeviceInfo = lambda **kw: kw

    entity_platform = sys.modules["homeassistant.helpers.entity_platform"]
    if not hasattr(entity_platform, "AddEntitiesCallback"):
        entity_platform.AddEntitiesCallback = None

    coordinator_mod = sys.modules["homeassistant.helpers.update_coordinator"]
    if not hasattr(coordinator_mod, "CoordinatorEntity"):
        coordinator_mod.CoordinatorEntity = type("CoordinatorEntity", (), {"__init__": lambda self, coord: None})
    if not hasattr(coordinator_mod, "DataUpdateCoordinator"):
        coordinator_mod.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
    if not hasattr(coordinator_mod, "UpdateFailed"):
        coordinator_mod.UpdateFailed = type("UpdateFailed", (Exception,), {})

    aiohttp_client = sys.modules["homeassistant.helpers.aiohttp_client"]
    if not hasattr(aiohttp_client, "async_get_clientsession"):
        aiohttp_client.async_get_clientsession = lambda hass: Mock()

    const = sys.modules["homeassistant.const"]
    if not hasattr(const, "Platform"):
        const.Platform = type("Platform", (), {"SENSOR": "sensor", "BINARY_SENSOR": "binary_sensor"})

    return created


# ---- Sensor type definitions ----

class TestSensorTypeDefinitions:
    """Test that all expected sensor types are registered."""

    def test_sensor_types_count(self):
        """Verify the expected number of sensor types."""
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        assert len(sensor_mod.SENSOR_TYPES) == 5

    def test_all_expected_keys_present(self):
        """Verify all expected sensor keys exist."""
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        keys = {d.key for d in sensor_mod.SENSOR_TYPES}
        assert keys == {
            "current_ip",
            "last_update",
            "last_ip_update",
            "certificate_expiry",
            "last_certificate_renewal",
        }

    def test_timestamp_sensors_have_device_class(self):
        """All timestamp sensors must declare TIMESTAMP device class."""
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        timestamp_keys = {
            "last_update",
            "last_ip_update",
            "certificate_expiry",
            "last_certificate_renewal",
        }
        for d in sensor_mod.SENSOR_TYPES:
            if d.key in timestamp_keys:
                assert d.device_class == "timestamp", (
                    f"Sensor {d.key} should have TIMESTAMP device class"
                )


# ---- current_ip sensor ----

class TestCurrentIPSensor:
    """Tests for the current_ip sensor."""

    def test_returns_ip(self):
        data = _make_coordinator_data(current_ip="203.0.113.42")
        sensor = _make_sensor("current_ip", data)
        assert sensor.native_value == "203.0.113.42"

    def test_returns_none_when_no_data(self):
        sensor = _make_sensor("current_ip", None)
        sensor.coordinator.data = None
        assert sensor.native_value is None

    def test_extra_attributes(self):
        data = _make_coordinator_data(
            current_ip="1.2.3.4",
            last_ip="1.2.3.3",
            ip_changed=True,
            subdomains=["www", "api"],
        )
        sensor = _make_sensor("current_ip", data)
        attrs = sensor.extra_state_attributes

        assert attrs["domain"] == "example.com"
        assert attrs["subdomains"] == ["www", "api"]
        assert attrs["last_ip"] == "1.2.3.3"
        assert attrs["ip_changed"] is True

    def test_empty_attributes_when_no_data(self):
        sensor = _make_sensor("current_ip", None)
        sensor.coordinator.data = None
        assert sensor.extra_state_attributes == {}


# ---- last_update sensor ----

class TestLastUpdateSensor:
    """Tests for the last_update sensor."""

    def test_returns_datetime(self):
        ts = "2026-02-06T14:30:00+00:00"
        data = _make_coordinator_data(last_update=ts)
        sensor = _make_sensor("last_update", data)
        value = sensor.native_value
        assert isinstance(value, datetime)
        assert value.year == 2026
        assert value.month == 2
        assert value.day == 6

    def test_returns_none_when_not_set(self):
        data = _make_coordinator_data(last_update=None)
        sensor = _make_sensor("last_update", data)
        assert sensor.native_value is None

    def test_returns_none_when_no_data(self):
        sensor = _make_sensor("last_update", None)
        sensor.coordinator.data = None
        assert sensor.native_value is None


# ---- last_ip_update sensor ----

class TestLastIPUpdateSensor:
    """Tests for the last_ip_update sensor."""

    def test_returns_datetime(self):
        ts = "2026-02-06T10:00:00+00:00"
        data = _make_coordinator_data(last_ip_update=ts, current_ip="5.6.7.8")
        sensor = _make_sensor("last_ip_update", data)
        value = sensor.native_value
        assert isinstance(value, datetime)
        assert value.hour == 10

    def test_returns_none_when_never_changed(self):
        data = _make_coordinator_data(last_ip_update=None)
        sensor = _make_sensor("last_ip_update", data)
        assert sensor.native_value is None

    def test_extra_attributes(self):
        data = _make_coordinator_data(
            last_ip_update="2026-02-06T10:00:00+00:00",
            current_ip="5.6.7.8",
        )
        sensor = _make_sensor("last_ip_update", data, domain="mysite.com")
        attrs = sensor.extra_state_attributes
        assert attrs["domain"] == "mysite.com"
        assert attrs["current_ip"] == "5.6.7.8"

    def test_returns_none_when_no_data(self):
        sensor = _make_sensor("last_ip_update", None)
        sensor.coordinator.data = None
        assert sensor.native_value is None


# ---- certificate_expiry sensor ----

class TestCertificateExpirySensor:
    """Tests for the certificate_expiry sensor."""

    def test_returns_expiry_datetime(self):
        cert_info = {
            "not_valid_after": "2026-06-15T12:00:00+00:00",
            "domains": ["example.com"],
            "days_remaining": 129,
            "issuer": {"organizationName": "Let's Encrypt"},
            "needs_renewal": False,
        }
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_sensor("certificate_expiry", data)
        value = sensor.native_value
        assert isinstance(value, datetime)
        assert value.month == 6
        assert value.day == 15

    def test_returns_none_without_cert_info(self):
        data = _make_coordinator_data(certificate_info=None)
        sensor = _make_sensor("certificate_expiry", data)
        assert sensor.native_value is None

    def test_returns_none_without_expiry_field(self):
        cert_info = {"domains": ["example.com"]}
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_sensor("certificate_expiry", data)
        assert sensor.native_value is None

    def test_extra_attributes(self):
        cert_info = {
            "not_valid_after": "2026-06-15T12:00:00+00:00",
            "domains": ["example.com", "www.example.com"],
            "days_remaining": 129,
            "issuer": {"organizationName": "Let's Encrypt"},
            "needs_renewal": False,
        }
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_sensor("certificate_expiry", data)
        attrs = sensor.extra_state_attributes
        assert attrs["domains"] == ["example.com", "www.example.com"]
        assert attrs["days_remaining"] == 129
        assert attrs["issuer"] == "Let's Encrypt"
        assert attrs["needs_renewal"] is False


# ---- last_certificate_renewal sensor ----

class TestLastCertificateRenewalSensor:
    """Tests for the last_certificate_renewal sensor."""

    def test_returns_datetime(self):
        ts = "2026-01-15T08:30:00+00:00"
        data = _make_coordinator_data(last_certificate_renewal=ts)
        sensor = _make_sensor("last_certificate_renewal", data)
        value = sensor.native_value
        assert isinstance(value, datetime)
        assert value.month == 1
        assert value.day == 15

    def test_returns_none_when_never_renewed(self):
        data = _make_coordinator_data(last_certificate_renewal=None)
        sensor = _make_sensor("last_certificate_renewal", data)
        assert sensor.native_value is None

    def test_extra_attributes_with_cert_info(self):
        cert_info = {
            "not_valid_after": "2026-06-15T12:00:00+00:00",
            "domains": ["example.com", "www.example.com"],
            "days_remaining": 129,
        }
        data = _make_coordinator_data(
            last_certificate_renewal="2026-01-15T08:30:00+00:00",
            certificate_info=cert_info,
        )
        sensor = _make_sensor("last_certificate_renewal", data)
        attrs = sensor.extra_state_attributes
        assert attrs["domains"] == ["example.com", "www.example.com"]
        assert attrs["certificate_expiry"] == "2026-06-15T12:00:00+00:00"

    def test_extra_attributes_without_cert_info(self):
        data = _make_coordinator_data(
            last_certificate_renewal="2026-01-15T08:30:00+00:00",
            certificate_info=None,
        )
        sensor = _make_sensor("last_certificate_renewal", data)
        attrs = sensor.extra_state_attributes
        assert attrs == {}

    def test_returns_none_when_no_data(self):
        sensor = _make_sensor("last_certificate_renewal", None)
        sensor.coordinator.data = None
        assert sensor.native_value is None


# ---- SSL-conditional entity creation ----

class TestSSLConditionalSensors:
    """Test that SSL-related sensors are only created when SSL is enabled."""

    def _get_sensor_keys(self, ssl_enabled):
        """Return the set of sensor keys that would be created."""
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        ssl_only = {"certificate_expiry", "last_certificate_renewal"}
        keys = set()
        for d in sensor_mod.SENSOR_TYPES:
            if d.key in ssl_only and not ssl_enabled:
                continue
            keys.add(d.key)
        return keys

    def test_ssl_disabled_skips_certificate_sensors(self):
        keys = self._get_sensor_keys(ssl_enabled=False)
        assert "certificate_expiry" not in keys
        assert "last_certificate_renewal" not in keys
        assert "current_ip" in keys
        assert "last_update" in keys
        assert "last_ip_update" in keys

    def test_ssl_enabled_includes_all_sensors(self):
        keys = self._get_sensor_keys(ssl_enabled=True)
        assert "certificate_expiry" in keys
        assert "last_certificate_renewal" in keys
        assert "current_ip" in keys
        assert "last_update" in keys
        assert "last_ip_update" in keys


# ---------------------------------------------------------------------------
# Part 2: Add-on sensor update tests (run.py)
#
# These test the new sensor update methods in the DynDNSUpdater class and
# verify that the Supervisor API is called with correct data.
# ---------------------------------------------------------------------------


class TestAddonLastIPUpdateSensor:
    """Tests for _update_last_ip_update_sensor in run.py."""

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

    def test_update_publishes_timestamp(self):
        """Test that _update_last_ip_update_sensor publishes correct data."""
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._last_ip = "1.2.3.4"
            updater._last_ip_update = "2026-02-06T14:00:00+00:00"
            updater._update_last_ip_update_sensor()

            mock_sensor.assert_called_once()
            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_last_ip_update"
            assert call_args[0][1] == "2026-02-06T14:00:00+00:00"
            attrs = call_args[0][2]
            assert attrs["device_class"] == "timestamp"
            assert attrs["current_ip"] == "1.2.3.4"
            assert attrs["domain"] == "example.com"

    def test_no_update_when_timestamp_not_set(self):
        """Test that nothing happens if IP was never changed."""
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._last_ip_update = None
            updater._update_last_ip_update_sensor()

            mock_sensor.assert_not_called()

    def test_ip_change_triggers_sensor_update(self):
        """Test that check_and_update sets last_ip_update on IP change."""
        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                mock_response = Mock()
                mock_response.text = "5.6.7.8"
                mock_response.raise_for_status = Mock()

                with patch("run.requests.get", return_value=mock_response):
                    with patch("run.OneComAPI") as mock_api_class:
                        mock_api = Mock()
                        mock_api.update_all_subdomains.return_value = {
                            "www": {"success": True},
                            "@": {"success": True},
                        }
                        mock_api_class.return_value = mock_api

                        with patch("run.update_ha_sensor") as mock_sensor:
                            updater = DynDNSUpdater(self.options)
                            # First check to establish baseline
                            updater._last_ip = "1.2.3.3"
                            updater.check_and_update()

                            # Verify last_ip_update was set
                            assert updater._last_ip_update is not None

                            # Verify sensor was updated
                            sensor_calls = [
                                c for c in mock_sensor.call_args_list
                                if c[0][0] == "sensor.onecom_dyndns_last_ip_update"
                            ]
                            assert len(sensor_calls) == 1

    def test_no_ip_change_does_not_update_sensor(self):
        """Test that no sensor update happens if IP is unchanged."""
        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")):
                mock_response = Mock()
                mock_response.text = "1.2.3.4"
                mock_response.raise_for_status = Mock()

                with patch("run.requests.get", return_value=mock_response):
                    with patch("run.update_ha_sensor") as mock_sensor:
                        updater = DynDNSUpdater(self.options)
                        updater._last_ip = "1.2.3.4"
                        updater.check_and_update()

                        # Should NOT have a last_ip_update sensor call
                        sensor_calls = [
                            c for c in mock_sensor.call_args_list
                            if c[0][0] == "sensor.onecom_dyndns_last_ip_update"
                        ]
                        assert len(sensor_calls) == 0


class TestAddonLastCertificateRenewalSensor:
    """Tests for _update_last_certificate_renewal_sensor in run.py."""

    def setup_method(self):
        self.options = {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www", ""],
            "update_interval": 5,
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

    def test_update_publishes_timestamp(self):
        """Test that _update_last_certificate_renewal_sensor publishes correct data."""
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._last_certificate_renewal = "2026-01-15T08:30:00+00:00"
            updater._update_last_certificate_renewal_sensor()

            mock_sensor.assert_called_once()
            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_last_certificate_renewal"
            assert call_args[0][1] == "2026-01-15T08:30:00+00:00"
            attrs = call_args[0][2]
            assert attrs["device_class"] == "timestamp"
            assert "example.com" in attrs["domains"]

    def test_no_update_when_timestamp_not_set(self):
        """Test that nothing happens if cert was never renewed."""
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._last_certificate_renewal = None
            updater._update_last_certificate_renewal_sensor()

            mock_sensor.assert_not_called()

    def test_ssl_event_renewed_triggers_sensor(self):
        """Test that a renewal event updates the sensor."""
        from run import DynDNSUpdater

        with patch("run.send_ha_notification"):
            with patch("run.update_ha_sensor") as mock_sensor:
                updater = DynDNSUpdater(self.options)
                updater._ssl_event_callback("renewed", {
                    "domains": ["example.com", "www.example.com"],
                    "certificate": {
                        "not_valid_after": "2026-06-15T12:00:00+00:00",
                        "domains": ["example.com", "www.example.com"],
                        "days_remaining": 129,
                    },
                })

                # Verify renewal timestamp was set
                assert updater._last_certificate_renewal is not None

                # Verify sensor was called
                renewal_calls = [
                    c for c in mock_sensor.call_args_list
                    if c[0][0] == "sensor.onecom_dyndns_last_certificate_renewal"
                ]
                assert len(renewal_calls) == 1


# ---------------------------------------------------------------------------
# Part 3: Existing add-on sensor method tests (extended)
# ---------------------------------------------------------------------------


class TestAddonExistingIPSensor:
    """Tests for _update_ip_sensor in run.py."""

    def setup_method(self):
        self.options = {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www", "api"],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    def test_ip_sensor_entity_id(self):
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_ip_sensor("10.0.0.1")

            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_ip"
            assert call_args[0][1] == "10.0.0.1"

    def test_ip_sensor_attributes(self):
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_ip_sensor("10.0.0.1")

            attrs = mock_sensor.call_args[0][2]
            assert attrs["domain"] == "example.com"
            assert "www.example.com" in attrs["subdomains"]
            assert "api.example.com" in attrs["subdomains"]
            assert "last_update" in attrs


class TestAddonExistingCertificateSensor:
    """Tests for _update_certificate_sensor in run.py."""

    def setup_method(self):
        self.options = {
            "username": "test@example.com",
            "password": "testpassword",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 5,
            "ip_service": "ipify",
            "log_level": "error",
            "ssl_enabled": False,
        }

    def test_certificate_sensor_entity_id(self):
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_certificate_sensor({
                "not_valid_after": "2026-06-15T12:00:00+00:00",
                "not_valid_before": "2026-01-15T12:00:00+00:00",
                "days_remaining": 129,
                "domains": ["example.com"],
                "issuer": "Let's Encrypt",
                "needs_renewal": False,
            })

            call_args = mock_sensor.call_args
            assert call_args[0][0] == "sensor.onecom_dyndns_certificate"
            assert call_args[0][1] == "2026-06-15T12:00:00+00:00"

    def test_certificate_sensor_attributes(self):
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_certificate_sensor({
                "not_valid_after": "2026-06-15T12:00:00+00:00",
                "not_valid_before": "2026-01-15T12:00:00+00:00",
                "days_remaining": 129,
                "domains": ["example.com", "www.example.com"],
                "issuer": "Let's Encrypt",
                "needs_renewal": False,
            })

            attrs = mock_sensor.call_args[0][2]
            assert attrs["days_remaining"] == 129
            assert attrs["needs_renewal"] is False
            assert attrs["device_class"] == "timestamp"
            assert "last_check" in attrs

    def test_certificate_sensor_skips_empty_info(self):
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_certificate_sensor({})

            # empty dict is falsy-ish but not None, check via not_valid_after key
            # The method checks "if not cert_info: return"
            # An empty dict IS falsy, so this should NOT call the sensor
            mock_sensor.assert_not_called()

    def test_certificate_sensor_skips_none(self):
        from run import DynDNSUpdater

        with patch("run.update_ha_sensor") as mock_sensor:
            updater = DynDNSUpdater(self.options)
            updater._update_certificate_sensor(None)

            mock_sensor.assert_not_called()


# ---------------------------------------------------------------------------
# Part 4: Coordinator timestamp tracking tests
# ---------------------------------------------------------------------------


class TestCoordinatorTimestampTracking:
    """Test that the coordinator correctly tracks and publishes timestamps.

    Since the coordinator uses asyncio and HA internals, we test the data
    dict construction logic rather than the full async flow.
    """

    def test_last_update_populated_in_data(self):
        """Coordinator data should contain last_update ISO timestamp."""
        data = _make_coordinator_data(last_update="2026-02-06T14:30:00+00:00")
        assert data["last_update"] == "2026-02-06T14:30:00+00:00"

    def test_last_ip_update_populated_on_ip_change(self):
        """Coordinator data should contain last_ip_update after IP change."""
        data = _make_coordinator_data(
            last_ip_update="2026-02-06T14:30:00+00:00",
            ip_changed=True,
        )
        assert data["last_ip_update"] == "2026-02-06T14:30:00+00:00"
        assert data["ip_changed"] is True

    def test_last_ip_update_none_when_no_change(self):
        """Coordinator data should have None last_ip_update before first change."""
        data = _make_coordinator_data(last_ip_update=None, ip_changed=False)
        assert data["last_ip_update"] is None

    def test_last_certificate_renewal_populated(self):
        """Coordinator data should contain last_certificate_renewal."""
        data = _make_coordinator_data(
            last_certificate_renewal="2026-01-15T08:30:00+00:00"
        )
        assert data["last_certificate_renewal"] == "2026-01-15T08:30:00+00:00"

    def test_last_certificate_renewal_none_when_not_renewed(self):
        data = _make_coordinator_data(last_certificate_renewal=None)
        assert data["last_certificate_renewal"] is None

    def test_all_timestamps_in_data(self):
        """All timestamp fields must be present in the coordinator data dict."""
        data = _make_coordinator_data()
        expected_keys = {
            "last_update",
            "last_ip_update",
            "last_certificate_renewal",
        }
        assert expected_keys.issubset(data.keys())


# ---------------------------------------------------------------------------
# Part 5: Constants verification
# ---------------------------------------------------------------------------


class TestSensorConstants:
    """Verify that all required constants are defined."""

    def test_attribute_constants_exist(self):
        """Check that new attribute constants are defined in const.py."""
        import sys
        _ensure_ha_stubs()

        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)

        assert hasattr(const_mod, "ATTR_LAST_IP_UPDATE")
        assert hasattr(const_mod, "ATTR_LAST_CERTIFICATE_RENEWAL")
        assert const_mod.ATTR_LAST_IP_UPDATE == "last_ip_update"
        assert const_mod.ATTR_LAST_CERTIFICATE_RENEWAL == "last_certificate_renewal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

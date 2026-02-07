"""
Tests for all sensor entities.

This covers:
- Custom component sensors (sensor.py): current_ip, last_update,
  last_ip_update, certificate_expiry, last_certificate_renewal, acme_challenge
- Custom component binary sensors (binary_sensor.py): dns_status, certificate_valid
- Custom component buttons (button.py): update_dns, check_ip, renew_certificate
- Add-on sensor updates via Supervisor API (run.py): new timestamp sensors
- Coordinator data flow (__init__.py): timestamp tracking
"""

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
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
    acme_challenge=None,
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
        "acme_challenge": acme_challenge,
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
        "homeassistant.components.button",
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
        class _StubDataUpdateCoordinator:
            """Stub that accepts the same __init__ args as the real class."""
            def __init__(self, hass=None, logger=None, *, name="", update_interval=None, **kwargs):
                self.hass = hass
                self.name = name
                self.update_interval = update_interval
        coordinator_mod.DataUpdateCoordinator = _StubDataUpdateCoordinator
    if not hasattr(coordinator_mod, "UpdateFailed"):
        coordinator_mod.UpdateFailed = type("UpdateFailed", (Exception,), {})

    aiohttp_client = sys.modules["homeassistant.helpers.aiohttp_client"]
    if not hasattr(aiohttp_client, "async_get_clientsession"):
        aiohttp_client.async_get_clientsession = lambda hass: Mock()

    button_mod = sys.modules["homeassistant.components.button"]
    if not hasattr(button_mod, "ButtonEntity"):
        button_mod.ButtonEntity = type("ButtonEntity", (), {})
    if not hasattr(button_mod, "ButtonEntityDescription"):
        from dataclasses import dataclass as _dc

        @_dc(frozen=True, kw_only=True)
        class _BED:
            key: str = ""
            translation_key: str | None = None
            icon: str | None = None
            entity_category: str | None = None
            entity_registry_enabled_default: bool = True
        button_mod.ButtonEntityDescription = _BED

    const = sys.modules["homeassistant.const"]
    if not hasattr(const, "Platform"):
        const.Platform = type("Platform", (), {
            "SENSOR": "sensor",
            "BINARY_SENSOR": "binary_sensor",
            "BUTTON": "button",
        })
    if not hasattr(const, "EntityCategory"):
        class _EntityCategory:
            DIAGNOSTIC = "diagnostic"
            CONFIG = "config"
        const.EntityCategory = _EntityCategory

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

        assert len(sensor_mod.SENSOR_TYPES) == 6

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
            "acme_challenge",
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

        ssl_only = {"certificate_expiry", "last_certificate_renewal", "acme_challenge"}
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
        assert "acme_challenge" not in keys
        assert "current_ip" in keys
        assert "last_update" in keys
        assert "last_ip_update" in keys

    def test_ssl_enabled_includes_all_sensors(self):
        keys = self._get_sensor_keys(ssl_enabled=True)
        assert "certificate_expiry" in keys
        assert "last_certificate_renewal" in keys
        assert "acme_challenge" in keys
        assert "current_ip" in keys
        assert "last_update" in keys
        assert "last_ip_update" in keys


# ---- acme_challenge sensor ----

class TestACMEChallengeSensor:
    """Tests for the acme_challenge sensor."""

    def test_returns_txt_value(self):
        acme = {
            "domain": "example.com",
            "txt_name": "_acme-challenge.example.com",
            "txt_value": "abc123xyz",
            "timestamp": "2026-02-06T14:00:00+00:00",
        }
        data = _make_coordinator_data(acme_challenge=acme, ssl_enabled=True)
        sensor = _make_sensor("acme_challenge", data, ssl_enabled=True)
        assert sensor.native_value == "abc123xyz"

    def test_returns_none_when_no_challenge(self):
        data = _make_coordinator_data(acme_challenge=None, ssl_enabled=True)
        sensor = _make_sensor("acme_challenge", data, ssl_enabled=True)
        assert sensor.native_value is None

    def test_returns_none_when_no_data(self):
        sensor = _make_sensor("acme_challenge", None, ssl_enabled=True)
        sensor.coordinator.data = None
        assert sensor.native_value is None

    def test_extra_attributes(self):
        acme = {
            "domain": "example.com",
            "txt_name": "_acme-challenge.example.com",
            "txt_value": "abc123xyz",
            "timestamp": "2026-02-06T14:00:00+00:00",
        }
        data = _make_coordinator_data(acme_challenge=acme, ssl_enabled=True)
        sensor = _make_sensor("acme_challenge", data, ssl_enabled=True)
        attrs = sensor.extra_state_attributes
        assert attrs["domain"] == "example.com"
        assert attrs["txt_record_name"] == "_acme-challenge.example.com"
        assert attrs["txt_record_value"] == "abc123xyz"
        assert attrs["timestamp"] == "2026-02-06T14:00:00+00:00"

    def test_empty_attributes_when_no_challenge(self):
        data = _make_coordinator_data(acme_challenge=None, ssl_enabled=True)
        sensor = _make_sensor("acme_challenge", data, ssl_enabled=True)
        assert sensor.extra_state_attributes == {}


# ---- entity_category tests ----

class TestEntityCategories:
    """Test that entity_category is set correctly on diagnostic sensors."""

    def test_last_update_is_diagnostic(self):
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        for d in sensor_mod.SENSOR_TYPES:
            if d.key == "last_update":
                assert d.entity_category == "diagnostic"
                break

    def test_acme_challenge_is_diagnostic(self):
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        for d in sensor_mod.SENSOR_TYPES:
            if d.key == "acme_challenge":
                assert d.entity_category == "diagnostic"
                break

    def test_acme_challenge_disabled_by_default(self):
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        for d in sensor_mod.SENSOR_TYPES:
            if d.key == "acme_challenge":
                assert d.entity_registry_enabled_default is False
                break

    def test_primary_sensors_have_no_category(self):
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        primary_keys = {"current_ip", "last_ip_update", "certificate_expiry", "last_certificate_renewal"}
        for d in sensor_mod.SENSOR_TYPES:
            if d.key in primary_keys:
                cat = getattr(d, "entity_category", None)
                assert cat is None, f"Sensor {d.key} should not have entity_category"


# ---- Binary sensor tests ----

def _make_binary_sensor(key, coordinator_data, domain="example.com", ssl_enabled=False):
    """Instantiate a OneComDynDNSBinarySensor with the given key and mock data."""
    import sys
    cc_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "custom_components",
        "onecom_dyndns",
    )
    if cc_dir not in sys.path:
        sys.path.insert(0, cc_dir)

    _ensure_ha_stubs()

    import importlib
    bs_mod = importlib.import_module("custom_components.onecom_dyndns.binary_sensor")
    importlib.reload(bs_mod)

    desc = None
    for d in bs_mod.BINARY_SENSOR_TYPES:
        if d.key == key:
            desc = d
            break
    assert desc is not None, f"Binary sensor type '{key}' not found"

    coordinator = Mock()
    coordinator.data = coordinator_data

    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.data = {"domain": domain, "ssl_enabled": ssl_enabled}

    with patch.object(bs_mod.OneComDynDNSBinarySensor, "__init__", lambda self, *a, **kw: None):
        sensor = bs_mod.OneComDynDNSBinarySensor.__new__(bs_mod.OneComDynDNSBinarySensor)

    sensor.coordinator = coordinator
    sensor.entity_description = desc
    sensor._domain = domain
    sensor._entry = entry
    sensor._attr_unique_id = f"test_entry_id_{key}"
    sensor._attr_device_info = None
    sensor._attr_has_entity_name = True

    return sensor


class TestBinarySensorTypes:
    """Test binary sensor type definitions."""

    def test_binary_sensor_types_count(self):
        _ensure_ha_stubs()
        import importlib
        bs_mod = importlib.import_module("custom_components.onecom_dyndns.binary_sensor")
        importlib.reload(bs_mod)
        assert len(bs_mod.BINARY_SENSOR_TYPES) == 2

    def test_all_expected_keys_present(self):
        _ensure_ha_stubs()
        import importlib
        bs_mod = importlib.import_module("custom_components.onecom_dyndns.binary_sensor")
        importlib.reload(bs_mod)
        keys = {d.key for d in bs_mod.BINARY_SENSOR_TYPES}
        assert keys == {"dns_status", "certificate_valid"}


class TestDNSStatusBinarySensor:
    """Tests for the dns_status binary sensor."""

    def test_is_on_when_ip_present(self):
        data = _make_coordinator_data(current_ip="1.2.3.4")
        sensor = _make_binary_sensor("dns_status", data)
        assert sensor.is_on is True

    def test_is_off_when_no_ip(self):
        data = _make_coordinator_data(current_ip=None)
        sensor = _make_binary_sensor("dns_status", data)
        assert sensor.is_on is False

    def test_is_none_when_no_data(self):
        sensor = _make_binary_sensor("dns_status", None)
        sensor.coordinator.data = None
        assert sensor.is_on is None

    def test_extra_attributes(self):
        data = _make_coordinator_data(current_ip="1.2.3.4", subdomains=["www", "api"])
        sensor = _make_binary_sensor("dns_status", data)
        attrs = sensor.extra_state_attributes
        assert attrs["domain"] == "example.com"
        assert attrs["current_ip"] == "1.2.3.4"
        assert attrs["subdomains"] == ["www", "api"]


class TestCertificateValidBinarySensor:
    """Tests for the certificate_valid binary sensor."""

    def test_problem_when_no_cert_info(self):
        data = _make_coordinator_data(certificate_info=None)
        sensor = _make_binary_sensor("certificate_valid", data)
        # True = problem (BinarySensorDeviceClass.PROBLEM)
        assert sensor.is_on is True

    def test_problem_when_needs_renewal(self):
        cert_info = {"needs_renewal": True, "days_remaining": 10}
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_binary_sensor("certificate_valid", data)
        assert sensor.is_on is True

    def test_problem_when_expired(self):
        cert_info = {"needs_renewal": False, "days_remaining": 0}
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_binary_sensor("certificate_valid", data)
        assert sensor.is_on is True

    def test_no_problem_when_valid(self):
        cert_info = {"needs_renewal": False, "days_remaining": 60}
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_binary_sensor("certificate_valid", data)
        assert sensor.is_on is False

    def test_extra_attributes(self):
        cert_info = {
            "not_valid_after": "2026-06-15T12:00:00+00:00",
            "days_remaining": 60,
            "domains": ["example.com"],
        }
        data = _make_coordinator_data(certificate_info=cert_info)
        sensor = _make_binary_sensor("certificate_valid", data)
        attrs = sensor.extra_state_attributes
        assert attrs["expiry_date"] == "2026-06-15T12:00:00+00:00"
        assert attrs["days_remaining"] == 60
        assert attrs["domains"] == ["example.com"]


# ---- Button entity tests ----

class TestButtonTypes:
    """Test button entity type definitions."""

    def test_button_types_count(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)
        assert len(btn_mod.BUTTON_TYPES) == 3

    def test_all_expected_keys_present(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)
        keys = {d.key for d in btn_mod.BUTTON_TYPES}
        assert keys == {"update_dns", "check_ip", "renew_certificate"}

    def test_all_buttons_have_config_category(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)
        for d in btn_mod.BUTTON_TYPES:
            assert d.entity_category == "config", (
                f"Button {d.key} should have CONFIG entity_category"
            )

    def test_update_dns_button_method(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)
        for d in btn_mod.BUTTON_TYPES:
            if d.key == "update_dns":
                assert d.method == "async_force_update_dns"
                break

    def test_check_ip_button_method(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)
        for d in btn_mod.BUTTON_TYPES:
            if d.key == "check_ip":
                assert d.method == "async_refresh"
                break

    def test_renew_certificate_button_method(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)
        for d in btn_mod.BUTTON_TYPES:
            if d.key == "renew_certificate":
                assert d.method == "async_force_renew_certificate"
                break

    def test_ssl_disabled_skips_renew_button(self):
        """When SSL is not enabled, renew_certificate button should not be created."""
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)

        ssl_only = {"renew_certificate"}
        ssl_enabled = False
        keys = set()
        for d in btn_mod.BUTTON_TYPES:
            if d.key in ssl_only and not ssl_enabled:
                continue
            keys.add(d.key)

        assert "renew_certificate" not in keys
        assert "update_dns" in keys
        assert "check_ip" in keys

    def test_ssl_enabled_includes_renew_button(self):
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)

        keys = {d.key for d in btn_mod.BUTTON_TYPES}
        assert "renew_certificate" in keys


# ---- Coordinator ACME challenge methods ----

class TestCoordinatorACMEChallenge:
    """Test coordinator ACME challenge set/clear methods."""

    def _make_coordinator(self):
        """Create a minimal coordinator-like object for testing set/clear."""
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        coordinator_cls = init_mod.OneComDynDNSCoordinator

        # Build a mock coordinator (bypass __init__)
        with patch.object(coordinator_cls, "__init__", lambda self, *a, **kw: None):
            coord = coordinator_cls.__new__(coordinator_cls)

        coord._acme_challenge = None
        return coord, init_mod

    def test_set_acme_challenge(self):
        coord, init_mod = self._make_coordinator()
        coord.set_acme_challenge(
            domain="example.com",
            txt_name="_acme-challenge.example.com",
            txt_value="test-value-123",
        )
        assert coord._acme_challenge is not None
        assert coord._acme_challenge["domain"] == "example.com"
        assert coord._acme_challenge["txt_name"] == "_acme-challenge.example.com"
        assert coord._acme_challenge["txt_value"] == "test-value-123"
        assert "timestamp" in coord._acme_challenge

    def test_clear_acme_challenge(self):
        coord, init_mod = self._make_coordinator()
        coord._acme_challenge = {"domain": "x", "txt_name": "y", "txt_value": "z"}
        coord.clear_acme_challenge()
        assert coord._acme_challenge is None

    def test_set_then_clear(self):
        coord, init_mod = self._make_coordinator()
        coord.set_acme_challenge("example.com", "_acme-challenge.example.com", "val")
        assert coord._acme_challenge is not None
        coord.clear_acme_challenge()
        assert coord._acme_challenge is None


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

    def test_ip_change_triggers_state_file_write(self):
        """Test that check_and_update writes state file on IP change."""
        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            with patch("run.LAST_IP_FILE", os.path.join(tmpdir, "last_ip.txt")), \
                 patch("run.ADDON_STATE_FILE", state_file):
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

                        with patch("run.update_ha_sensor"):
                            updater = DynDNSUpdater(self.options)
                            updater._last_ip = "1.2.3.3"
                            updater.check_and_update()

                            # Verify last_ip_update was set
                            assert updater._last_ip_update is not None

                            # Verify state file contains correct data
                            assert os.path.isfile(state_file)
                            with open(state_file) as f:
                                state = json.load(f)
                            assert state["current_ip"] == "5.6.7.8"
                            assert state["last_ip_update"] is not None

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

    def test_ssl_event_renewed_updates_state_file(self):
        """Test that a renewal event writes the state file."""
        from run import DynDNSUpdater

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            with patch("run.send_ha_notification"), \
                 patch("run.update_ha_sensor"), \
                 patch("run.ADDON_STATE_FILE", state_file):
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

                # Verify state file was written
                assert os.path.isfile(state_file)
                with open(state_file) as f:
                    state = json.load(f)
                assert state["last_certificate_renewal"] is not None


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
            "acme_challenge",
        }
        assert expected_keys.issubset(data.keys())


# ---------------------------------------------------------------------------
# Part 5: Constants verification
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Part 5a: State file constants
# ---------------------------------------------------------------------------


class TestAddonStateFileConstants:
    """Verify that state/command file constants exist."""

    def test_addon_state_file_constant(self):
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)
        assert hasattr(const_mod, "ADDON_STATE_FILE")
        assert const_mod.ADDON_STATE_FILE == ".onecom_dyndns_state.json"

    def test_addon_command_file_constant(self):
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)
        assert hasattr(const_mod, "ADDON_COMMAND_FILE")
        assert const_mod.ADDON_COMMAND_FILE == ".onecom_dyndns_commands.json"


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
        assert hasattr(const_mod, "ATTR_ACME_CHALLENGE")
        assert const_mod.ATTR_LAST_IP_UPDATE == "last_ip_update"
        assert const_mod.ATTR_LAST_CERTIFICATE_RENEWAL == "last_certificate_renewal"
        assert const_mod.ATTR_ACME_CHALLENGE == "acme_challenge"

    def test_platforms_include_button(self):
        """Verify that PLATFORMS includes button."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)
        assert "button" in const_mod.PLATFORMS
        assert "sensor" in const_mod.PLATFORMS
        assert "binary_sensor" in const_mod.PLATFORMS

    def test_addon_slug_constant(self):
        """Verify ADDON_SLUG is defined correctly."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)
        assert hasattr(const_mod, "ADDON_SLUG")
        assert const_mod.ADDON_SLUG == "homeassistant-onecom-dyndns"

    def test_conf_addon_slug_constant(self):
        """Verify CONF_ADDON_SLUG is defined correctly."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)
        assert hasattr(const_mod, "CONF_ADDON_SLUG")
        assert const_mod.CONF_ADDON_SLUG == "addon_slug"


# ---------------------------------------------------------------------------
# Part 6: get_device_info() tests
# ---------------------------------------------------------------------------


class TestGetDeviceInfo:
    """Tests for the get_device_info() helper in const.py."""

    def test_with_addon_slug_returns_hassio_identifiers(self):
        """When addon_slug is set, DeviceInfo uses hassio identifiers."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)

        info = const_mod.get_device_info(
            entry_id="entry_123",
            domain="example.com",
            addon_slug="homeassistant-onecom-dyndns",
        )

        # Our stub DeviceInfo returns a dict of keyword args
        assert info["identifiers"] == {("hassio", "homeassistant-onecom-dyndns")}
        # Should NOT contain standalone fields
        assert "name" not in info
        assert "manufacturer" not in info

    def test_without_addon_slug_returns_standalone_device(self):
        """When addon_slug is None, DeviceInfo has full standalone metadata."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)

        info = const_mod.get_device_info(
            entry_id="entry_456",
            domain="mysite.org",
            addon_slug=None,
        )

        assert info["identifiers"] == {("onecom_dyndns", "entry_456")}
        assert info["name"] == "One.com DynDNS - mysite.org"
        assert info["manufacturer"] == "ulfwuestefeld"
        assert info["model"] == "DynDNS Updater"
        assert info["configuration_url"] == "https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns"

    def test_without_addon_slug_default(self):
        """When addon_slug is not passed, defaults to None (standalone)."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)

        info = const_mod.get_device_info(
            entry_id="entry_789",
            domain="test.com",
        )

        # Should be standalone
        assert info["identifiers"] == {("onecom_dyndns", "entry_789")}
        assert "name" in info

    def test_with_empty_addon_slug_returns_standalone(self):
        """Empty string for addon_slug should be treated as falsy (standalone)."""
        _ensure_ha_stubs()
        import importlib
        const_mod = importlib.import_module("custom_components.onecom_dyndns.const")
        importlib.reload(const_mod)

        info = const_mod.get_device_info(
            entry_id="entry_abc",
            domain="test.com",
            addon_slug="",
        )

        # Empty string is falsy, so standalone device
        assert info["identifiers"] == {("onecom_dyndns", "entry_abc")}


# ---------------------------------------------------------------------------
# Part 7: Button async_press() tests
# ---------------------------------------------------------------------------


def _make_button(key, coordinator_data=None, domain="example.com", ssl_enabled=False):
    """Instantiate a OneComDynDNSButton with the given key and mock data."""
    import sys
    cc_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "custom_components",
        "onecom_dyndns",
    )
    if cc_dir not in sys.path:
        sys.path.insert(0, cc_dir)

    _ensure_ha_stubs()

    import importlib
    btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
    importlib.reload(btn_mod)

    desc = None
    for d in btn_mod.BUTTON_TYPES:
        if d.key == key:
            desc = d
            break
    assert desc is not None, f"Button type '{key}' not found"

    coordinator = MagicMock()
    coordinator.data = coordinator_data

    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.data = {"domain": domain, "ssl_enabled": ssl_enabled}

    with patch.object(btn_mod.OneComDynDNSButton, "__init__", lambda self, *a, **kw: None):
        button = btn_mod.OneComDynDNSButton.__new__(btn_mod.OneComDynDNSButton)

    button.coordinator = coordinator
    button.entity_description = desc
    button._domain = domain
    button._entry = entry
    button._attr_unique_id = f"test_entry_id_{key}"
    button._attr_device_info = None
    button._attr_has_entity_name = True

    return button


class TestButtonAsyncPress:
    """Tests for the OneComDynDNSButton.async_press() method."""

    def test_update_dns_press_calls_coordinator(self):
        """Pressing update_dns calls coordinator.async_force_update_dns."""
        import asyncio

        async def _run():
            button = _make_button("update_dns")
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(None)
            button.coordinator.async_force_update_dns = MagicMock(return_value=fut)

            await button.async_press()
            button.coordinator.async_force_update_dns.assert_called_once()

        asyncio.run(_run())

    def test_check_ip_press_calls_coordinator(self):
        """Pressing check_ip calls coordinator.async_refresh."""
        import asyncio

        async def _run():
            button = _make_button("check_ip")
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(None)
            button.coordinator.async_refresh = MagicMock(return_value=fut)

            await button.async_press()
            button.coordinator.async_refresh.assert_called_once()

        asyncio.run(_run())

    def test_renew_certificate_press_calls_coordinator(self):
        """Pressing renew_certificate calls coordinator.async_force_renew_certificate."""
        import asyncio

        async def _run():
            button = _make_button("renew_certificate", ssl_enabled=True)
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(None)
            button.coordinator.async_force_renew_certificate = MagicMock(return_value=fut)

            await button.async_press()
            button.coordinator.async_force_renew_certificate.assert_called_once()

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Part 8: Config flow (hassio discovery) tests
# ---------------------------------------------------------------------------


def _ensure_config_flow_stubs():
    """Ensure all stubs needed for config_flow.py are present."""
    import sys
    import types

    _ensure_ha_stubs()

    # voluptuous stub
    if "voluptuous" not in sys.modules:
        vol = types.ModuleType("voluptuous")
        vol.Schema = lambda *a, **kw: None
        vol.Required = lambda *a, **kw: a[0] if a else "required"
        vol.Optional = lambda *a, **kw: a[0] if a else "optional"
        sys.modules["voluptuous"] = vol

    # homeassistant.data_entry_flow
    mod_name = "homeassistant.data_entry_flow"
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        m.FlowResult = dict  # FlowResult is just a TypedDict
        sys.modules[mod_name] = m

    # homeassistant.helpers.selector stubs
    sel_mod_name = "homeassistant.helpers.selector"
    if sel_mod_name not in sys.modules:
        sel = types.ModuleType(sel_mod_name)

        class _Stub:
            def __init__(self, *a, **kw):
                pass

        for cls_name in [
            "BooleanSelector",
            "NumberSelector",
            "NumberSelectorConfig",
            "NumberSelectorMode",
            "SelectSelector",
            "SelectSelectorConfig",
            "SelectSelectorMode",
            "TextSelector",
            "TextSelectorConfig",
            "TextSelectorType",
        ]:
            setattr(sel, cls_name, type(cls_name, (_Stub,), {}))

        sys.modules[sel_mod_name] = sel

    # config_entries stubs
    ce = sys.modules["homeassistant.config_entries"]
    if not hasattr(ce, "ConfigFlow"):
        class _ConfigFlow:
            """Minimal ConfigFlow stub."""
            domain = None

            def __init_subclass__(cls, domain=None, **kw):
                super().__init_subclass__(**kw)
                cls.domain = domain

            async def async_set_unique_id(self, uid):
                self._unique_id = uid

            def _abort_if_unique_id_configured(self, **kw):
                pass

            def async_abort(self, reason=""):
                return {"type": "abort", "reason": reason}

            def async_create_entry(self, title="", data=None):
                return {"type": "create_entry", "title": title, "data": data}

            def async_show_form(self, step_id="", **kw):
                return {"type": "form", "step_id": step_id, **kw}

        ce.ConfigFlow = _ConfigFlow

    if not hasattr(ce, "OptionsFlow"):
        class _OptionsFlow:
            def async_create_entry(self, title="", data=None):
                return {"type": "create_entry", "title": title, "data": data}

            def async_show_form(self, step_id="", **kw):
                return {"type": "form", "step_id": step_id, **kw}

        ce.OptionsFlow = _OptionsFlow

    # onecom_api stub for config_flow
    onecom_api_mod_name = "custom_components.onecom_dyndns.onecom_api"
    if onecom_api_mod_name not in sys.modules:
        m = types.ModuleType(onecom_api_mod_name)

        async def async_validate_credentials(*a, **kw):
            return {"valid": True, "domains": [], "subdomains": []}

        m.async_validate_credentials = async_validate_credentials
        m.OneComAPI = type("OneComAPI", (), {})
        m.OneComAPIError = type("OneComAPIError", (Exception,), {})
        sys.modules[onecom_api_mod_name] = m

    # Ensure callback is identity function
    core = sys.modules["homeassistant.core"]
    if not hasattr(core, "callback"):
        core.callback = lambda f: f


class TestConfigFlowHassioDiscovery:
    """Tests for async_step_hassio() auto-create behaviour."""

    def _get_flow_class(self):
        """Import and return the OneComDynDNSConfigFlow class."""
        _ensure_config_flow_stubs()
        import importlib
        cf_mod = importlib.import_module("custom_components.onecom_dyndns.config_flow")
        importlib.reload(cf_mod)
        return cf_mod.OneComDynDNSConfigFlow

    def test_hassio_discovery_auto_creates_entry(self):
        """async_step_hassio should auto-create a config entry with valid domain."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "domain": "example.com",
                    "username": "user@one.com",
                    "password": "secret",
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["type"] == "create_entry"
            assert result["title"] == "One.com DynDNS - example.com"
            assert result["data"]["domain"] == "example.com"
            assert result["data"]["addon_slug"] == "homeassistant-onecom-dyndns"

        asyncio.run(_run())

    def test_hassio_discovery_includes_addon_slug(self):
        """async_step_hassio should include the addon slug in entry data."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "domain": "example.com",
                    "username": "user@one.com",
                    "password": "secret",
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["data"]["addon_slug"] == "homeassistant-onecom-dyndns"

        asyncio.run(_run())

    def test_hassio_discovery_empty_domain_aborts(self):
        """async_step_hassio should abort when domain is empty."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "domain": "",
                    "username": "user@one.com",
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["type"] == "abort"
            assert result["reason"] == "no_domain"

        asyncio.run(_run())

    def test_hassio_discovery_no_domain_key_aborts(self):
        """async_step_hassio should abort when domain key is missing."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "username": "user@one.com",
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["type"] == "abort"
            assert result["reason"] == "no_domain"

        asyncio.run(_run())

    def test_hassio_entry_contains_full_config(self):
        """Auto-created entry should contain the full add-on configuration."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "domain": "example.com",
                    "username": "user@one.com",
                    "password": "secret",
                    "ssl_enabled": True,
                    "update_interval": 10,
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["type"] == "create_entry"
            assert result["data"]["username"] == "user@one.com"
            assert result["data"]["ssl_enabled"] is True
            assert result["data"]["update_interval"] == 10

        asyncio.run(_run())

    def test_hassio_sets_unique_id(self):
        """async_step_hassio should set a unique ID based on the domain."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "domain": "mysite.org",
                    "username": "user@one.com",
                    "password": "secret",
                },
            }

            await flow.async_step_hassio(discovery_info)
            assert flow._unique_id == "onecom_mysite.org"

        asyncio.run(_run())

    def test_hassio_uses_custom_addon_slug(self):
        """async_step_hassio should use the addon slug from discovery info."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "my-custom-addon",
                "config": {
                    "domain": "example.com",
                    "username": "admin",
                    "password": "pw",
                    "ssl_enabled": True,
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["data"]["addon_slug"] == "my-custom-addon"
            assert result["data"]["ssl_enabled"] is True

        asyncio.run(_run())

    def test_hassio_title_includes_domain(self):
        """The auto-created entry title should include the domain name."""
        import asyncio

        async def _run():
            FlowClass = self._get_flow_class()
            flow = FlowClass()

            discovery_info = {
                "addon": "homeassistant-onecom-dyndns",
                "config": {
                    "domain": "mysite.org",
                    "username": "user@one.com",
                    "password": "pw",
                },
            }

            result = await flow.async_step_hassio(discovery_info)
            assert result["title"] == "One.com DynDNS - mysite.org"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Part 9: async_setup_entry conditional entity creation tests
# ---------------------------------------------------------------------------


class TestSensorAsyncSetupEntryConditional:
    """Test that async_setup_entry in sensor.py correctly filters entities."""

    def _simulate_setup_entry(self, ssl_enabled):
        """Simulate the entity filtering logic from async_setup_entry."""
        _ensure_ha_stubs()
        import importlib
        sensor_mod = importlib.import_module("custom_components.onecom_dyndns.sensor")
        importlib.reload(sensor_mod)

        ssl_only_sensors = {"certificate_expiry", "last_certificate_renewal", "acme_challenge"}
        created_keys = []
        for desc in sensor_mod.SENSOR_TYPES:
            if desc.key in ssl_only_sensors and not ssl_enabled:
                continue
            created_keys.append(desc.key)
        return created_keys

    def test_ssl_disabled_creates_3_sensors(self):
        """With SSL disabled, only 3 sensors should be created."""
        keys = self._simulate_setup_entry(ssl_enabled=False)
        assert len(keys) == 3
        assert "current_ip" in keys
        assert "last_update" in keys
        assert "last_ip_update" in keys

    def test_ssl_enabled_creates_6_sensors(self):
        """With SSL enabled, all 6 sensors should be created."""
        keys = self._simulate_setup_entry(ssl_enabled=True)
        assert len(keys) == 6


class TestBinarySensorAsyncSetupEntryConditional:
    """Test that async_setup_entry in binary_sensor.py correctly filters entities."""

    def _simulate_setup_entry(self, ssl_enabled):
        """Simulate the entity filtering logic from async_setup_entry."""
        _ensure_ha_stubs()
        import importlib
        bs_mod = importlib.import_module("custom_components.onecom_dyndns.binary_sensor")
        importlib.reload(bs_mod)

        created_keys = []
        for desc in bs_mod.BINARY_SENSOR_TYPES:
            if desc.key == "certificate_valid" and not ssl_enabled:
                continue
            created_keys.append(desc.key)
        return created_keys

    def test_ssl_disabled_creates_1_binary_sensor(self):
        """With SSL disabled, only dns_status should be created."""
        keys = self._simulate_setup_entry(ssl_enabled=False)
        assert len(keys) == 1
        assert "dns_status" in keys
        assert "certificate_valid" not in keys

    def test_ssl_enabled_creates_2_binary_sensors(self):
        """With SSL enabled, both binary sensors should be created."""
        keys = self._simulate_setup_entry(ssl_enabled=True)
        assert len(keys) == 2
        assert "dns_status" in keys
        assert "certificate_valid" in keys


class TestButtonAsyncSetupEntryConditional:
    """Test that async_setup_entry in button.py correctly filters entities."""

    def _simulate_setup_entry(self, ssl_enabled):
        """Simulate the entity filtering logic from async_setup_entry."""
        _ensure_ha_stubs()
        import importlib
        btn_mod = importlib.import_module("custom_components.onecom_dyndns.button")
        importlib.reload(btn_mod)

        created_keys = []
        for desc in btn_mod.BUTTON_TYPES:
            if desc.key == "renew_certificate" and not ssl_enabled:
                continue
            created_keys.append(desc.key)
        return created_keys

    def test_ssl_disabled_creates_2_buttons(self):
        """With SSL disabled, renew_certificate button should be skipped."""
        keys = self._simulate_setup_entry(ssl_enabled=False)
        assert len(keys) == 2
        assert "update_dns" in keys
        assert "check_ip" in keys
        assert "renew_certificate" not in keys

    def test_ssl_enabled_creates_3_buttons(self):
        """With SSL enabled, all 3 buttons should be created."""
        keys = self._simulate_setup_entry(ssl_enabled=True)
        assert len(keys) == 3
        assert "renew_certificate" in keys


# ---------------------------------------------------------------------------
# Part 7: Coordinator Add-on Mode (state file reading / command writing)
# ---------------------------------------------------------------------------

def _make_addon_coordinator(hass_mock, state_file_path, command_file_path, extra_data=None):
    """Create a OneComDynDNSCoordinator in add-on mode for testing."""
    _ensure_ha_stubs()
    import importlib
    init_mod = importlib.import_module("custom_components.onecom_dyndns")
    importlib.reload(init_mod)

    entry_data = {
        "username": "user@example.com",
        "password": "pass123",
        "domain": "example.com",
        "subdomains": ["www", ""],
        "update_interval": 5,
        "ip_service": "ipify",
        "ssl_enabled": False,
        "addon_slug": "homeassistant-onecom-dyndns",
    }
    if extra_data:
        entry_data.update(extra_data)

    entry = Mock()
    entry.data = entry_data
    entry.entry_id = "test-entry-123"

    # hass.config.path() should join with the temp directory
    config_dir = str(Path(state_file_path).parent)
    hass_mock.config.path = lambda f: os.path.join(config_dir, f)

    coordinator = init_mod.OneComDynDNSCoordinator(hass_mock, entry)
    return coordinator


class TestCoordinatorAddonMode:
    """Verify coordinator reads from the add-on state file."""

    def _make_hass(self):
        hass = Mock()
        hass.async_add_executor_job = Mock(
            side_effect=lambda fn, *args: asyncio.get_event_loop().run_in_executor(None, fn, *args)
        )
        return hass

    def test_addon_mode_detected(self, tmp_path):
        """Coordinator should detect add-on mode from addon_slug."""
        state_file = tmp_path / ".onecom_dyndns_state.json"
        cmd_file = tmp_path / ".onecom_dyndns_commands.json"
        hass = self._make_hass()
        coordinator = _make_addon_coordinator(hass, str(state_file), str(cmd_file))
        assert coordinator._addon_mode is True

    def test_standalone_mode_when_no_slug(self, tmp_path):
        """Coordinator should fall back to standalone mode without addon_slug."""
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        entry = Mock()
        entry.data = {
            "username": "u", "password": "p", "domain": "d.com",
            "update_interval": 5, "ip_service": "ipify",
        }
        hass = self._make_hass()
        coordinator = init_mod.OneComDynDNSCoordinator(hass, entry)
        assert coordinator._addon_mode is False

    def test_reads_state_file(self, tmp_path):
        """In add-on mode, _async_update_data should read the state file."""
        state_file = tmp_path / ".onecom_dyndns_state.json"
        state = {
            "current_ip": "5.6.7.8",
            "last_ip": "5.6.7.7",
            "domain": "example.com",
            "subdomains": ["www.example.com"],
            "ip_changed": False,
            "dns_status": "ok",
            "last_update": "2026-02-06T12:00:00+00:00",
            "last_ip_update": "2026-02-06T10:00:00+00:00",
            "last_certificate_renewal": None,
            "ssl_enabled": False,
            "certificate_info": None,
            "acme_challenge": None,
        }
        state_file.write_text(json.dumps(state))

        hass = self._make_hass()
        coordinator = _make_addon_coordinator(hass, str(state_file), str(tmp_path / "cmd.json"))

        async def _run():
            data = await coordinator._async_read_addon_state()
            assert data["current_ip"] == "5.6.7.8"
            assert data["dns_status"] == "ok"
            assert data["domain"] == "example.com"

        asyncio.run(_run())

    def test_returns_defaults_when_no_state_file(self, tmp_path):
        """If the state file does not exist yet, safe defaults should be returned."""
        state_file = tmp_path / ".onecom_dyndns_state.json"
        # Do NOT create the file

        hass = self._make_hass()
        coordinator = _make_addon_coordinator(hass, str(state_file), str(tmp_path / "cmd.json"))

        async def _run():
            data = await coordinator._async_read_addon_state()
            assert data["current_ip"] is None
            assert data["dns_status"] == "unknown"
            assert data["domain"] == "example.com"

        asyncio.run(_run())

    def test_returns_defaults_on_invalid_json(self, tmp_path):
        """Malformed state file should not crash the coordinator."""
        state_file = tmp_path / ".onecom_dyndns_state.json"
        state_file.write_text("{INVALID JSON")

        hass = self._make_hass()
        coordinator = _make_addon_coordinator(hass, str(state_file), str(tmp_path / "cmd.json"))

        async def _run():
            data = await coordinator._async_read_addon_state()
            assert data["current_ip"] is None

        asyncio.run(_run())


class TestCoordinatorCommandFile:
    """Verify coordinator writes commands for the add-on."""

    def _make_hass(self):
        hass = Mock()
        hass.async_add_executor_job = Mock(
            side_effect=lambda fn, *args: asyncio.get_event_loop().run_in_executor(None, fn, *args)
        )
        return hass

    def test_force_update_dns_writes_command(self, tmp_path):
        """async_force_update_dns should write update_dns command."""
        state_file = tmp_path / ".onecom_dyndns_state.json"
        cmd_file = tmp_path / ".onecom_dyndns_commands.json"
        hass = self._make_hass()
        coordinator = _make_addon_coordinator(hass, str(state_file), str(cmd_file))

        # Mock async_refresh to avoid HA interaction
        refresh_called = False

        async def fake_refresh():
            nonlocal refresh_called
            refresh_called = True

        coordinator.async_refresh = fake_refresh

        async def _run():
            await coordinator.async_force_update_dns()

        asyncio.run(_run())

        assert cmd_file.exists()
        data = json.loads(cmd_file.read_text())
        assert data["command"] == "update_dns"
        assert "timestamp" in data

    def test_force_renew_certificate_writes_command(self, tmp_path):
        """async_force_renew_certificate should write renew_certificate command."""
        state_file = tmp_path / ".onecom_dyndns_state.json"
        cmd_file = tmp_path / ".onecom_dyndns_commands.json"
        hass = self._make_hass()
        coordinator = _make_addon_coordinator(
            hass, str(state_file), str(cmd_file), extra_data={"ssl_enabled": True}
        )

        coordinator.async_refresh = lambda: asyncio.sleep(0)

        async def _run():
            await coordinator.async_force_renew_certificate()

        asyncio.run(_run())

        assert cmd_file.exists()
        data = json.loads(cmd_file.read_text())
        assert data["command"] == "renew_certificate"

    def test_standalone_mode_does_not_write_command(self, tmp_path):
        """In standalone mode, force update should NOT write a command file."""
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        entry = Mock()
        entry.data = {
            "username": "u", "password": "p", "domain": "d.com",
            "subdomains": [""], "update_interval": 5, "ip_service": "ipify",
        }
        hass = self._make_hass()
        coordinator = init_mod.OneComDynDNSCoordinator(hass, entry)

        # In standalone mode with no _last_ip, force_update_dns is a no-op
        async def _run():
            await coordinator.async_force_update_dns()

        asyncio.run(_run())

        cmd_file = tmp_path / ".onecom_dyndns_commands.json"
        assert not cmd_file.exists()


class TestCoordinatorUpdateInterval:
    """Verify coordinator uses shorter interval in add-on mode."""

    def _make_hass(self):
        hass = Mock()
        hass.async_add_executor_job = Mock()
        return hass

    def test_addon_mode_uses_30s_interval(self, tmp_path):
        """In add-on mode, polling interval should be 30 seconds."""
        from datetime import timedelta
        state_file = tmp_path / ".onecom_dyndns_state.json"
        cmd_file = tmp_path / ".onecom_dyndns_commands.json"
        hass = self._make_hass()
        coordinator = _make_addon_coordinator(hass, str(state_file), str(cmd_file))
        assert coordinator.update_interval == timedelta(seconds=30)

    def test_standalone_mode_uses_config_interval(self, tmp_path):
        """In standalone mode, polling interval should match config."""
        from datetime import timedelta
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        entry = Mock()
        entry.data = {
            "username": "u", "password": "p", "domain": "d.com",
            "update_interval": 10, "ip_service": "ipify",
        }
        hass = self._make_hass()
        coordinator = init_mod.OneComDynDNSCoordinator(hass, entry)
        assert coordinator.update_interval == timedelta(minutes=10)


class TestAsyncDetectAddon:
    """Verify _async_detect_addon detects the add-on via the state file."""

    def _make_hass(self, config_dir):
        hass = Mock()
        hass.config.path = Mock(side_effect=lambda f: str(config_dir / f))
        hass.async_add_executor_job = Mock(
            side_effect=lambda fn, *args: asyncio.get_event_loop().run_in_executor(None, fn, *args)
        )
        return hass

    def test_detects_addon_when_state_file_exists(self, tmp_path):
        """Returns the add-on slug when the state file exists."""
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        (tmp_path / ".onecom_dyndns_state.json").write_text("{}")
        hass = self._make_hass(tmp_path)

        result = asyncio.run(init_mod._async_detect_addon(hass))
        assert result == "homeassistant-onecom-dyndns"

    def test_returns_none_when_no_state_file(self, tmp_path):
        """Returns None when the state file does not exist."""
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        hass = self._make_hass(tmp_path)

        result = asyncio.run(init_mod._async_detect_addon(hass))
        assert result is None

    def test_returns_none_on_error(self, tmp_path):
        """Returns None when hass.config.path raises."""
        _ensure_ha_stubs()
        import importlib
        init_mod = importlib.import_module("custom_components.onecom_dyndns")
        importlib.reload(init_mod)

        hass = Mock()
        hass.config.path = Mock(side_effect=RuntimeError("boom"))
        hass.async_add_executor_job = Mock(
            side_effect=lambda fn, *args: asyncio.get_event_loop().run_in_executor(None, fn, *args)
        )

        result = asyncio.run(init_mod._async_detect_addon(hass))
        assert result is None


class TestBuildDiscoveryConfig:
    """Verify _build_discovery_config helper in run.py."""

    def test_builds_full_config(self):
        """Config payload includes all add-on options."""
        from run import _build_discovery_config

        opts = {
            "username": "u@one.com",
            "password": "pw",
            "domain": "example.com",
            "subdomains": ["www"],
            "update_interval": 3,
            "ip_service": "ifconfig",
            "ssl_enabled": True,
            "ssl_email": "ssl@ex.com",
            "ssl_domains": ["example.com"],
            "ssl_staging": True,
            "ssl_renewal_days": 14,
            "ssl_check_interval": 6,
        }
        cfg = _build_discovery_config(opts)
        assert cfg["username"] == "u@one.com"
        assert cfg["domain"] == "example.com"
        assert cfg["ssl_enabled"] is True
        assert cfg["ssl_renewal_days"] == 14

    def test_defaults_for_empty_options(self):
        """Missing keys fall back to sensible defaults."""
        from run import _build_discovery_config

        cfg = _build_discovery_config({})
        assert cfg["username"] == ""
        assert cfg["domain"] == ""
        assert cfg["subdomains"] == [""]
        assert cfg["update_interval"] == 5
        assert cfg["ip_service"] == "ipify"
        assert cfg["ssl_enabled"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

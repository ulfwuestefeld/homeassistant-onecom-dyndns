"""Tests for the One.com DynDNS integration setup and teardown.

Requires ``pytest-homeassistant-custom-component`` to be installed.
Skipped automatically when the package is not available.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.onecom_dyndns.const import (
    CONF_DOMAIN,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    SERVICE_CHECK_IP,
    SERVICE_RENEW_CERTIFICATE,
    SERVICE_UPDATE_DNS,
)

MOCK_DATA = {
    CONF_USERNAME: "test@example.com",
    CONF_PASSWORD: "testpassword",
    CONF_DOMAIN: "example.com",
    "subdomains": ["www", ""],
    "update_interval": 5,
    "ip_service": "ipify",
    "ssl_enabled": False,
}


def _mock_coordinator_update():
    """Return a safe default for the coordinator first refresh."""
    return {
        "current_ip": "1.2.3.4",
        "last_ip": None,
        "domain": "example.com",
        "subdomains": ["www", ""],
        "ip_changed": False,
        "dns_status": "ok",
        "last_update": None,
        "last_ip_update": None,
        "last_certificate_renewal": None,
        "ssl_enabled": False,
        "certificate_info": None,
        "acme_challenge": None,
    }


# ---------------------------------------------------------------------------
# async_setup_entry / async_unload_entry
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_entry_creates_coordinator(hass: HomeAssistant) -> None:
    """Test that async_setup_entry creates a coordinator and forwards platforms."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)

    assert result is True
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    assert "coordinator" in hass.data[DOMAIN][entry.entry_id]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_unload_entry_cleans_up(hass: HomeAssistant) -> None:
    """Test that async_unload_entry removes data and services."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)

    # Verify entry is loaded
    assert entry.entry_id in hass.data[DOMAIN]

    # Unload
    result = await hass.config_entries.async_unload(entry.entry_id)
    assert result is True
    assert entry.entry_id not in hass.data[DOMAIN]


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_services_registered(hass: HomeAssistant) -> None:
    """Test that services are registered after setup."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)

    assert hass.services.has_service(DOMAIN, SERVICE_UPDATE_DNS)
    assert hass.services.has_service(DOMAIN, SERVICE_RENEW_CERTIFICATE)
    assert hass.services.has_service(DOMAIN, SERVICE_CHECK_IP)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_service_update_dns(hass: HomeAssistant) -> None:
    """Test calling the update_dns service."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    with patch.object(
        coordinator, "async_force_update_dns", new_callable=AsyncMock,
    ) as mock_update:
        await hass.services.async_call(
            DOMAIN, SERVICE_UPDATE_DNS, {}, blocking=True,
        )
        mock_update.assert_called_once()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_service_check_ip(hass: HomeAssistant) -> None:
    """Test calling the check_ip service."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    with patch.object(
        coordinator, "async_refresh", new_callable=AsyncMock,
    ) as mock_refresh:
        await hass.services.async_call(
            DOMAIN, SERVICE_CHECK_IP, {}, blocking=True,
        )
        mock_refresh.assert_called_once()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_service_renew_certificate(hass: HomeAssistant) -> None:
    """Test calling the renew_certificate service."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    with patch.object(
        coordinator, "async_force_renew_certificate", new_callable=AsyncMock,
    ) as mock_renew:
        await hass.services.async_call(
            DOMAIN, SERVICE_RENEW_CERTIFICATE, {}, blocking=True,
        )
        mock_renew.assert_called_once()


# ---------------------------------------------------------------------------
# Services removed after last entry unloaded
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_services_removed_after_unload(hass: HomeAssistant) -> None:
    """Test that services are removed when all entries are unloaded."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)

    assert hass.services.has_service(DOMAIN, SERVICE_UPDATE_DNS)

    await hass.config_entries.async_unload(entry.entry_id)

    assert not hass.services.has_service(DOMAIN, SERVICE_UPDATE_DNS)
    assert not hass.services.has_service(DOMAIN, SERVICE_RENEW_CERTIFICATE)
    assert not hass.services.has_service(DOMAIN, SERVICE_CHECK_IP)


# ---------------------------------------------------------------------------
# Options update triggers reload
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_update_triggers_reload(hass: HomeAssistant) -> None:
    """Test that changing options triggers an entry reload."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data=MOCK_DATA,
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Change options
    with patch(
        "custom_components.onecom_dyndns.OneComDynDNSCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=_mock_coordinator_update(),
    ):
        hass.config_entries.async_update_entry(
            entry, options={"update_interval": 10},
        )
        await hass.async_block_till_done()

    # Entry should still be loaded (reloaded)
    assert entry.state is config_entries.ConfigEntryState.LOADED

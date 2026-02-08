"""Tests for the One.com DynDNS config flow.

Requires ``pytest-homeassistant-custom-component`` to be installed.
Skipped automatically when the package is not available.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.onecom_dyndns.const import (
    CONF_DOMAIN,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)

VALID_CREDS_RESULT = {
    "valid": True,
    "domains": ["example.com", "test.com"],
    "subdomains": ["www", "api", ""],
    "error": None,
}

INVALID_CREDS_RESULT = {
    "valid": False,
    "domains": [],
    "subdomains": [],
    "error": "Invalid credentials - please check username and password",
}

CONNECT_ERROR_RESULT = {
    "valid": False,
    "domains": [],
    "subdomains": [],
    "error": "Failed to connect to One.com",
}


# ---------------------------------------------------------------------------
# User step tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test that the user step shows the credential form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_invalid_auth(hass: HomeAssistant) -> None:
    """Test user step with invalid credentials."""
    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value=INVALID_CREDS_RESULT,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: "bad@example.com",
                CONF_PASSWORD: "wrong",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_auth"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    """Test user step when connection fails."""
    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value=CONNECT_ERROR_RESULT,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_success_shows_domain(hass: HomeAssistant) -> None:
    """Test user step with valid credentials advances to domain step."""
    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value=VALID_CREDS_RESULT,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "domain"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_no_domains_shows_manual(hass: HomeAssistant) -> None:
    """Test that if no domains returned, manual entry is shown."""
    no_domains_result = {**VALID_CREDS_RESULT, "domains": []}
    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value=no_domains_result,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "domain_manual"


# ---------------------------------------------------------------------------
# Domain step tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_domain_step_advances_to_subdomains(hass: HomeAssistant) -> None:
    """Test that selecting a domain advances to subdomain selection."""
    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value=VALID_CREDS_RESULT,
    ):
        # Start the flow and pass credentials
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

        assert result["step_id"] == "domain"

        # Select a domain
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_DOMAIN: "example.com"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "subdomains"


# ---------------------------------------------------------------------------
# Full flow test
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_full_flow_creates_entry(hass: HomeAssistant) -> None:
    """Test a complete happy-path flow creates a config entry."""
    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value=VALID_CREDS_RESULT,
    ):
        # Step 1: User credentials
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )
        assert result["step_id"] == "domain"

        # Step 2: Domain selection
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_DOMAIN: "example.com"},
        )
        assert result["step_id"] == "subdomains"

        # Step 3: Subdomain selection
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"subdomains": ["www", ""]},
        )
        assert result["step_id"] == "options"

        # Step 4: Options (no SSL)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "update_interval": 5,
                "ip_service": "ipify",
                "ssl_enabled": False,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "One.com DynDNS Updater - example.com"
    assert result["data"][CONF_DOMAIN] == "example.com"
    assert result["data"][CONF_USERNAME] == "test@example.com"


# ---------------------------------------------------------------------------
# Hassio discovery step tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_hassio_discovery_creates_entry(hass: HomeAssistant) -> None:
    """Test that add-on discovery auto-creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_HASSIO},
        data={
            "addon": "homeassistant-onecom-dyndns",
            "config": {
                "domain": "example.com",
                "username": "test@example.com",
                "password": "secret",
                "subdomains": ["www"],
            },
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "example.com" in result["title"]
    assert result["data"]["addon_slug"] == "homeassistant-onecom-dyndns"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_hassio_discovery_no_domain_aborts(hass: HomeAssistant) -> None:
    """Test that add-on discovery aborts when no domain is provided."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_HASSIO},
        data={"addon": "homeassistant-onecom-dyndns", "config": {}},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_domain"


# ---------------------------------------------------------------------------
# Options flow tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Test that the options flow shows the form with current values."""
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "secret",
            CONF_DOMAIN: "example.com",
            "update_interval": 5,
            "ip_service": "ipify",
            "ssl_enabled": False,
        },
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_saves(hass: HomeAssistant) -> None:
    """Test that the options flow saves new values."""
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "secret",
            CONF_DOMAIN: "example.com",
            "update_interval": 5,
            "ip_service": "ipify",
            "ssl_enabled": False,
        },
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "update_interval": 10,
            "ip_service": "icanhazip",
            "ssl_enabled": True,
            "ssl_email": "admin@example.com",
            "ssl_staging": False,
            "ssl_renewal_days": 14,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["update_interval"] == 10
    assert entry.options["ip_service"] == "icanhazip"


# ---------------------------------------------------------------------------
# Reauth flow tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reauth_flow_shows_form(hass: HomeAssistant) -> None:
    """Test that the reauth flow shows a credential form."""
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "old_password",
            CONF_DOMAIN: "example.com",
            "subdomains": ["www"],
            "update_interval": 5,
            "ip_service": "ipify",
            "ssl_enabled": False,
        },
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reauth_flow_success(hass: HomeAssistant) -> None:
    """Test that reauth updates the entry on success."""
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="One.com DynDNS Updater - example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "old_password",
            CONF_DOMAIN: "example.com",
            "subdomains": ["www"],
            "update_interval": 5,
            "ip_service": "ipify",
            "ssl_enabled": False,
        },
        source=config_entries.SOURCE_USER,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.onecom_dyndns.config_flow.async_validate_credentials",
        new_callable=AsyncMock,
        return_value={**VALID_CREDS_RESULT, "domains": ["example.com"]},
    ), patch(
        "custom_components.onecom_dyndns.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "new_password",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new_password"

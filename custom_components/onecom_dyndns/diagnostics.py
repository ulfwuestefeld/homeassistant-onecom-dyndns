"""Diagnostics support for One.com DynDNS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Keys that contain sensitive data and must be redacted
TO_REDACT = {
    "password",
    "username",
    "ssl_email",
    "ssl_key",
    "private_key",
    "account_key",
    "token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "entry_id": entry.entry_id,
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "addon_mode": coordinator._addon_mode,
            "data": async_redact_data(
                dict(coordinator.data) if coordinator.data else {},
                TO_REDACT,
            ),
        },
    }

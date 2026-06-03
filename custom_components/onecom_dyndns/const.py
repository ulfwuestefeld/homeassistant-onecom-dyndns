"""Constants for the One.com DynDNS integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from homeassistant.const import (
    CONF_DOMAIN,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity import DeviceInfo

DOMAIN: Final = "onecom_dyndns"

# Add-on slug (used for Supervisor device attachment)
ADDON_SLUG: Final = "homeassistant-onecom-dyndns"
CONF_ADDON_SLUG: Final = "addon_slug"

# Configuration keys (CONF_USERNAME, CONF_PASSWORD, CONF_DOMAIN imported above)
CONF_SUBDOMAINS: Final = "subdomains"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_IP_SERVICE: Final = "ip_service"

# SSL Configuration keys
CONF_SSL_ENABLED: Final = "ssl_enabled"
CONF_SSL_EMAIL: Final = "ssl_email"
CONF_SSL_DOMAINS: Final = "ssl_domains"
CONF_SSL_STAGING: Final = "ssl_staging"
CONF_SSL_RENEWAL_DAYS: Final = "ssl_renewal_days"
CONF_SSL_CHECK_INTERVAL: Final = "ssl_check_interval"

# Default values
DEFAULT_UPDATE_INTERVAL: Final = 5
DEFAULT_IP_SERVICE: Final = "ipify"
DEFAULT_SSL_RENEWAL_DAYS: Final = 30
DEFAULT_SSL_CHECK_INTERVAL: Final = 12

# IP Service options
IP_SERVICES: Final = {
    "ipify": "https://api.ipify.org",
    "ifconfig": "https://ifconfig.me/ip",
    "icanhazip": "https://icanhazip.com",
}

# Platforms
PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

# Services
SERVICE_UPDATE_DNS: Final = "update_dns"
SERVICE_RENEW_CERTIFICATE: Final = "renew_certificate"
SERVICE_CHECK_IP: Final = "check_ip"

# Attributes
ATTR_CURRENT_IP: Final = "current_ip"
ATTR_LAST_UPDATE: Final = "last_update"
ATTR_LAST_IP_CHANGE: Final = "last_ip_change"
ATTR_LAST_IP_UPDATE: Final = "last_ip_update"
ATTR_LAST_CERTIFICATE_RENEWAL: Final = "last_certificate_renewal"
ATTR_CERTIFICATE_EXPIRY: Final = "certificate_expiry"
ATTR_CERTIFICATE_DOMAINS: Final = "certificate_domains"
ATTR_DAYS_UNTIL_EXPIRY: Final = "days_until_expiry"
ATTR_ACME_CHALLENGE: Final = "acme_challenge"

# Shared state file written by the add-on, read by the integration
ADDON_STATE_FILE: Final = ".onecom_dyndns_state.json"
# Command file written by the integration, read by the add-on
ADDON_COMMAND_FILE: Final = ".onecom_dyndns_commands.json"


def get_device_info(
    entry_id: str, domain: str, addon_slug: str | None = None,
) -> "DeviceInfo":
    """Build DeviceInfo, attaching to the Supervisor add-on device when possible.

    When *addon_slug* is set (i.e. the integration was auto-discovered from
    the running add-on), we use the Supervisor's own device identifiers
    so that our entities appear on the existing add-on device in the UI.
    We do NOT set name/manufacturer/model in add-on mode to avoid
    overwriting the Supervisor's own device metadata.
    Otherwise we create a standalone device.
    """
    # Import here to avoid circular / missing-HA issues during unit tests
    from homeassistant.helpers.entity import DeviceInfo  # noqa: E402

    if addon_slug:
        return DeviceInfo(
            identifiers={("hassio", addon_slug)},
        )

    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=f"One.com DynDNS Updater - {domain}",
        manufacturer="ulfwuestefeld",
        model="DynDNS Updater",
        configuration_url="https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns",
    )

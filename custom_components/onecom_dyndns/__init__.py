"""The One.com DynDNS integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DOMAIN,
    CONF_SUBDOMAINS,
    CONF_UPDATE_INTERVAL,
    CONF_IP_SERVICE,
    CONF_SSL_ENABLED,
    CONF_SSL_EMAIL,
    CONF_SSL_DOMAINS,
    CONF_SSL_STAGING,
    CONF_SSL_RENEWAL_DAYS,
    CONF_SSL_CHECK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    SERVICE_UPDATE_DNS,
    SERVICE_RENEW_CERTIFICATE,
    SERVICE_CHECK_IP,
    IP_SERVICES,
)
from .onecom_api import OneComAPI, OneComAPIError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up One.com DynDNS from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create coordinator
    coordinator = OneComDynDNSCoordinator(hass, entry)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "config": entry.data,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_setup_services(hass)

    # Register update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Remove services if no entries left
    if not hass.data[DOMAIN]:
        for service in [SERVICE_UPDATE_DNS, SERVICE_RENEW_CERTIFICATE, SERVICE_CHECK_IP]:
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for One.com DynDNS."""

    async def handle_update_dns(call: ServiceCall) -> None:
        """Handle the update DNS service call."""
        for entry_id, data in hass.data[DOMAIN].items():
            coordinator: OneComDynDNSCoordinator = data["coordinator"]
            await coordinator.async_force_update_dns()

    async def handle_renew_certificate(call: ServiceCall) -> None:
        """Handle the renew certificate service call."""
        for entry_id, data in hass.data[DOMAIN].items():
            coordinator: OneComDynDNSCoordinator = data["coordinator"]
            await coordinator.async_force_renew_certificate()

    async def handle_check_ip(call: ServiceCall) -> None:
        """Handle the check IP service call."""
        for entry_id, data in hass.data[DOMAIN].items():
            coordinator: OneComDynDNSCoordinator = data["coordinator"]
            await coordinator.async_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_DNS):
        hass.services.async_register(DOMAIN, SERVICE_UPDATE_DNS, handle_update_dns)

    if not hass.services.has_service(DOMAIN, SERVICE_RENEW_CERTIFICATE):
        hass.services.async_register(DOMAIN, SERVICE_RENEW_CERTIFICATE, handle_renew_certificate)

    if not hass.services.has_service(DOMAIN, SERVICE_CHECK_IP):
        hass.services.async_register(DOMAIN, SERVICE_CHECK_IP, handle_check_ip)


class OneComDynDNSCoordinator(DataUpdateCoordinator):
    """Coordinator for One.com DynDNS updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.session = async_get_clientsession(hass)

        # Configuration
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]
        self.domain = entry.data[CONF_DOMAIN]
        self.subdomains = entry.data.get(CONF_SUBDOMAINS, [""])
        self.ip_service = entry.data.get(CONF_IP_SERVICE, "ipify")
        self.update_interval_minutes = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

        # SSL Configuration
        self.ssl_enabled = entry.data.get(CONF_SSL_ENABLED, False)
        self.ssl_email = entry.data.get(CONF_SSL_EMAIL, "")
        self.ssl_domains = entry.data.get(CONF_SSL_DOMAINS, [])
        self.ssl_staging = entry.data.get(CONF_SSL_STAGING, False)

        # State
        self._last_ip: str | None = None
        self._last_update: str | None = None
        self._last_ip_update: str | None = None
        self._last_certificate_renewal: str | None = None
        self._certificate_info: dict[str, Any] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self.update_interval_minutes),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from One.com."""
        try:
            # Get current public IP
            current_ip = await self._async_get_public_ip()

            now_iso = datetime.now(timezone.utc).isoformat()
            self._last_update = now_iso

            ip_changed = current_ip != self._last_ip and self._last_ip is not None

            # Update DNS if IP changed
            if ip_changed:
                _LOGGER.info("IP changed from %s to %s", self._last_ip, current_ip)
                await self._async_update_dns(current_ip)
                self._last_ip_update = now_iso

            self._last_ip = current_ip

            data = {
                "current_ip": current_ip,
                "last_ip": self._last_ip,
                "domain": self.domain,
                "subdomains": self.subdomains,
                "ip_changed": ip_changed,
                "last_update": self._last_update,
                "last_ip_update": self._last_ip_update,
                "last_certificate_renewal": self._last_certificate_renewal,
                "ssl_enabled": self.ssl_enabled,
                "certificate_info": self._certificate_info,
            }

            return data

        except Exception as err:
            raise UpdateFailed(f"Error communicating with One.com: {err}") from err

    async def _async_get_public_ip(self) -> str:
        """Get the current public IP address."""
        url = IP_SERVICES.get(self.ip_service, IP_SERVICES["ipify"])

        try:
            async with self.session.get(url, timeout=10) as response:
                response.raise_for_status()
                ip = (await response.text()).strip()
                return ip
        except Exception as err:
            _LOGGER.error("Failed to get public IP: %s", err)
            raise

    async def _async_update_dns(self, ip: str) -> bool:
        """Update DNS records at One.com."""
        try:
            api = OneComAPI(self.username, self.password, self.domain)

            # Run blocking I/O in executor
            await self.hass.async_add_executor_job(api.login)

            for subdomain in self.subdomains:
                try:
                    await self.hass.async_add_executor_job(
                        api.update_dns_record, subdomain, ip
                    )
                    _LOGGER.info("Updated DNS for %s.%s to %s",
                                subdomain or "@", self.domain, ip)
                except OneComAPIError as err:
                    _LOGGER.error("Failed to update %s.%s: %s",
                                 subdomain or "@", self.domain, err)

            await self.hass.async_add_executor_job(api.logout)
            return True

        except OneComAPIError as err:
            _LOGGER.error("DNS update failed: %s", err)
            return False

    async def async_force_update_dns(self) -> None:
        """Force a DNS update."""
        if self._last_ip:
            await self._async_update_dns(self._last_ip)

    async def async_force_renew_certificate(self) -> None:
        """Force certificate renewal."""
        if not self.ssl_enabled:
            _LOGGER.warning("SSL is not enabled")
            return

        _LOGGER.info("Forcing certificate renewal...")
        # Certificate renewal logic would go here
        # This would use the CertificateManager from the add-on
        self._last_certificate_renewal = datetime.now(timezone.utc).isoformat()

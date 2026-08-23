"""The One.com DynDNS integration."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ADDON_COMMAND_FILE,
    ADDON_SLUG,
    ADDON_STATE_FILE,
    CONF_ADDON_SLUG,
    CONF_DOMAIN,
    CONF_IP_SERVICE,
    CONF_PASSWORD,
    CONF_SSL_CHECK_INTERVAL,
    CONF_SSL_DOMAINS,
    CONF_SSL_EMAIL,
    CONF_SSL_ENABLED,
    CONF_SSL_RENEWAL_DAYS,
    CONF_SSL_STAGING,
    CONF_SUBDOMAINS,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    IP_SERVICES,
    PLATFORMS,
    SERVICE_CHECK_IP,
    SERVICE_RENEW_CERTIFICATE,
    SERVICE_UPDATE_DNS,
)

_LOGGER = logging.getLogger(__name__)


async def _async_detect_addon(hass: HomeAssistant) -> str | None:
    """Detect the running add-on by checking for its state file.

    Returns the add-on slug if the state file exists (i.e. the add-on has
    written at least one state), otherwise ``None``.
    """
    try:
        state_path = Path(hass.config.path(ADDON_STATE_FILE))
        if await hass.async_add_executor_job(state_path.is_file):
            _LOGGER.info(
                "Detected running add-on via state file %s", state_path
            )
            return ADDON_SLUG
    except Exception:  # noqa: BLE001
        pass
    return None


async def _async_remove_standalone_device(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Remove the old standalone device after switching to add-on mode.

    When the integration was initially set up in standalone mode it created a
    device with ``identifiers={(DOMAIN, entry_id)}``.  After switching to
    add-on mode, entities attach to the Supervisor device instead, leaving the
    old device orphaned.  This helper cleans it up so the user does not see a
    stale "One.com DynDNS Updater - …" device alongside the add-on device.
    """
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    old_device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if old_device:
        dev_reg.async_remove_device(old_device.id)
        _LOGGER.info(
            "Removed old standalone device %s after switching to add-on mode",
            old_device.id,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up One.com DynDNS from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # If the entry was created manually (no addon_slug), try to detect the
    # running add-on so the entities attach to the add-on device and the
    # coordinator reads data from the state file instead of polling.
    if not entry.data.get(CONF_ADDON_SLUG):
        addon_slug = await _async_detect_addon(hass)
        if addon_slug:
            new_data = dict(entry.data)
            new_data[CONF_ADDON_SLUG] = addon_slug
            hass.config_entries.async_update_entry(entry, data=new_data)
            _LOGGER.info(
                "Switched to add-on mode (slug=%s) for entry %s",
                addon_slug,
                entry.entry_id,
            )
            # Remove the old standalone device so we don't leave orphans
            await _async_remove_standalone_device(hass, entry)

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
        for _entry_id, data in hass.data[DOMAIN].items():
            coordinator: OneComDynDNSCoordinator = data["coordinator"]
            await coordinator.async_force_update_dns()

    async def handle_renew_certificate(call: ServiceCall) -> None:
        """Handle the renew certificate service call."""
        for _entry_id, data in hass.data[DOMAIN].items():
            coordinator: OneComDynDNSCoordinator = data["coordinator"]
            await coordinator.async_force_renew_certificate()

    async def handle_check_ip(call: ServiceCall) -> None:
        """Handle the check IP service call."""
        for _entry_id, data in hass.data[DOMAIN].items():
            coordinator: OneComDynDNSCoordinator = data["coordinator"]
            await coordinator.async_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_DNS):
        hass.services.async_register(DOMAIN, SERVICE_UPDATE_DNS, handle_update_dns)

    if not hass.services.has_service(DOMAIN, SERVICE_RENEW_CERTIFICATE):
        hass.services.async_register(DOMAIN, SERVICE_RENEW_CERTIFICATE, handle_renew_certificate)

    if not hass.services.has_service(DOMAIN, SERVICE_CHECK_IP):
        hass.services.async_register(DOMAIN, SERVICE_CHECK_IP, handle_check_ip)


class OneComDynDNSCoordinator(DataUpdateCoordinator):
    """Coordinator for One.com DynDNS updates.

    When the integration was discovered from the add-on (``addon_slug`` is
    set in the config entry), the coordinator reads the shared state file
    written by the add-on instead of independently polling IP services.
    Button presses and service calls write a command file that the add-on
    picks up within seconds.

    When running standalone (no add-on), the coordinator falls back to
    direct IP polling and DNS updates.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry

        # Detect add-on mode
        self._addon_mode = bool(entry.data.get(CONF_ADDON_SLUG))

        if self._addon_mode:
            # In add-on mode we read from the state file.
            # Resolve the path relative to HA's config directory.
            self._state_file = Path(hass.config.path(ADDON_STATE_FILE))
            self._command_file = Path(hass.config.path(ADDON_COMMAND_FILE))
            _LOGGER.info(
                "Add-on mode: reading state from %s", self._state_file
            )
        else:
            self._state_file = None
            self._command_file = None
            self.session = async_get_clientsession(hass)

        # Configuration -- options take precedence over initial data so that
        # changes made through the Options Flow are actually applied.
        self.domain = entry.data.get(CONF_DOMAIN, "")
        self.subdomains = entry.data.get(CONF_SUBDOMAINS, [""])
        self.ip_service = entry.options.get(
            CONF_IP_SERVICE, entry.data.get(CONF_IP_SERVICE, "ipify"),
        )
        self.update_interval_minutes = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        # SSL Configuration -- options override data
        self.ssl_enabled = entry.options.get(
            CONF_SSL_ENABLED, entry.data.get(CONF_SSL_ENABLED, False),
        )
        self.ssl_email = entry.options.get(
            CONF_SSL_EMAIL, entry.data.get(CONF_SSL_EMAIL, ""),
        )
        self.ssl_domains = entry.data.get(CONF_SSL_DOMAINS, [])
        self.ssl_staging = entry.options.get(
            CONF_SSL_STAGING, entry.data.get(CONF_SSL_STAGING, False),
        )

        # State file caching: avoid re-parsing JSON when the file hasn't
        # changed since the last read (checked via mtime).
        self._last_state_mtime: float = 0.0
        self._last_state_data: dict[str, Any] | None = None

        # Standalone-mode state (not used in add-on mode)
        self._last_ip: str | None = None
        self._last_update: str | None = None
        self._last_ip_update: str | None = None
        self._last_certificate_renewal: str | None = None
        self._certificate_info: dict[str, Any] | None = None
        self._acme_challenge: dict[str, str] | None = None

        # In add-on mode, poll more frequently so button feedback is fast
        interval = timedelta(seconds=30) if self._addon_mode else timedelta(
            minutes=self.update_interval_minutes
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=interval,
            config_entry=entry,
        )

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data – from add-on state file or by direct polling."""
        if self._addon_mode:
            return await self._async_read_addon_state()
        return await self._async_poll_directly()

    async def _async_read_addon_state(self) -> dict[str, Any]:
        """Read the state file written by the add-on."""
        try:
            data = await self.hass.async_add_executor_job(
                self._read_state_file_sync
            )
            if data is not None:
                return data
        except Exception as err:
            _LOGGER.debug("Could not read add-on state file: %s", err)

        # State file not yet available – return safe defaults
        return {
            "current_ip": None,
            "last_ip": None,
            "domain": self.domain,
            "subdomains": self.subdomains,
            "ip_changed": False,
            "dns_status": "unknown",
            "last_update": None,
            "last_ip_update": None,
            "last_certificate_renewal": None,
            "ssl_enabled": self.ssl_enabled,
            "certificate_info": None,
            "acme_challenge": None,
        }

    def _read_state_file_sync(self) -> dict[str, Any] | None:
        """Synchronous helper to read the JSON state file.

        Uses mtime-based caching: if the file hasn't been modified since the
        last read, the previously parsed data is returned without re-opening
        and re-parsing the file.  This avoids ~9 out of 10 unnecessary JSON
        parses (the state file is written every 5 min, but polled every 30 s).
        """
        if self._state_file is None or not self._state_file.is_file():
            return None

        mtime = self._state_file.stat().st_mtime
        if mtime == self._last_state_mtime and self._last_state_data is not None:
            return self._last_state_data

        with open(self._state_file, "r") as fh:
            self._last_state_data = json.load(fh)
        self._last_state_mtime = mtime
        return self._last_state_data

    async def _async_poll_directly(self) -> dict[str, Any]:
        """Standalone mode: poll IP services and update DNS directly."""
        try:
            current_ip = await self._async_get_public_ip()

            now_iso = datetime.now(timezone.utc).isoformat()
            self._last_update = now_iso

            ip_changed = (
                current_ip != self._last_ip and self._last_ip is not None
            )

            if ip_changed:
                _LOGGER.info(
                    "IP changed from %s to %s", self._last_ip, current_ip
                )
                await self._async_update_dns(current_ip)
                self._last_ip_update = now_iso

            self._last_ip = current_ip

            return {
                "current_ip": current_ip,
                "last_ip": self._last_ip,
                "domain": self.domain,
                "subdomains": self.subdomains,
                "ip_changed": ip_changed,
                "dns_status": "ok" if current_ip else "error",
                "last_update": self._last_update,
                "last_ip_update": self._last_ip_update,
                "last_certificate_renewal": self._last_certificate_renewal,
                "ssl_enabled": self.ssl_enabled,
                "certificate_info": self._certificate_info,
                "acme_challenge": self._acme_challenge,
            }

        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with One.com: {err}"
            ) from err

    async def _async_get_public_ip(self) -> str:
        """Get the current public IP address (standalone mode only)."""
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
        """Update DNS records at One.com (standalone mode only).

        Uses ``update_all_subdomains`` to fetch DNS records once and update
        all subdomains in a single pass, avoiding N redundant API calls.
        The API session is always closed via ``finally`` to prevent TCP/TLS
        connection leaks.
        """
        from .onecom_api import OneComAPI, OneComAPIError

        username = self.entry.data[CONF_USERNAME]
        password = self.entry.data[CONF_PASSWORD]
        api = OneComAPI(username, password, self.domain)

        try:
            await self.hass.async_add_executor_job(api.login)

            results = await self.hass.async_add_executor_job(
                api.update_all_subdomains, self.subdomains, ip
            )

            for name, result in results.items():
                if result["success"]:
                    _LOGGER.info(
                        "Updated DNS for %s.%s to %s", name, self.domain, ip,
                    )
                else:
                    _LOGGER.error(
                        "Failed to update %s.%s: %s",
                        name, self.domain, result["error"],
                    )

            success_count = sum(1 for r in results.values() if r["success"])
            return success_count == len(results)

        except OneComAPIError as err:
            if "Invalid credentials" in str(err):
                raise ConfigEntryAuthFailed(str(err)) from err
            _LOGGER.error("DNS update failed: %s", err)
            return False
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            _LOGGER.error("DNS update failed: %s", err)
            return False
        finally:
            await self.hass.async_add_executor_job(api.logout)

    # ------------------------------------------------------------------
    # Commands (button presses / service calls)
    # ------------------------------------------------------------------

    def _write_command_sync(self, command: str) -> None:
        """Synchronous helper: write a command for the add-on to pick up."""
        if self._command_file is None:
            return
        payload = {
            "command": command,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        tmp = self._command_file.with_suffix(".json.tmp")
        with open(tmp, "w") as fh:
            json.dump(payload, fh)
        tmp.replace(self._command_file)

    async def async_force_update_dns(self) -> None:
        """Force a DNS update."""
        if self._addon_mode:
            await self.hass.async_add_executor_job(
                self._write_command_sync, "update_dns"
            )
            # Refresh after a short delay so the UI updates quickly
            await asyncio.sleep(2)
            await self.async_refresh()
        else:
            if self._last_ip:
                await self._async_update_dns(self._last_ip)

    async def async_force_renew_certificate(self) -> None:
        """Force certificate renewal."""
        if self._addon_mode:
            await self.hass.async_add_executor_job(
                self._write_command_sync, "renew_certificate"
            )
            await asyncio.sleep(2)
            await self.async_refresh()
        else:
            if not self.ssl_enabled:
                _LOGGER.warning("SSL is not enabled")
                return
            _LOGGER.info("Forcing certificate renewal...")
            self._last_certificate_renewal = datetime.now(
                timezone.utc
            ).isoformat()

    # ------------------------------------------------------------------
    # ACME challenge helpers (standalone mode)
    # ------------------------------------------------------------------

    def set_acme_challenge(
        self, domain: str, txt_name: str, txt_value: str
    ) -> None:
        """Store the current ACME DNS-01 challenge information."""
        self._acme_challenge = {
            "domain": domain,
            "txt_name": txt_name,
            "txt_value": txt_value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_acme_challenge(self) -> None:
        """Clear the ACME challenge after successful validation."""
        self._acme_challenge = None

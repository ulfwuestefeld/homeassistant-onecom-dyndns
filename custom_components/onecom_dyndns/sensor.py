"""Sensor platform for One.com DynDNS."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_DOMAIN,
    CONF_ADDON_SLUG,
    CONF_SSL_ENABLED,
    get_device_info,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        key="current_ip",
        translation_key="current_ip",
        icon="mdi:ip-network",
    ),
    SensorEntityDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="last_ip_update",
        translation_key="last_ip_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:ip-network-outline",
    ),
    SensorEntityDescription(
        key="certificate_expiry",
        translation_key="certificate_expiry",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:certificate",
    ),
    SensorEntityDescription(
        key="last_certificate_renewal",
        translation_key="last_certificate_renewal",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:certificate-outline",
    ),
    SensorEntityDescription(
        key="acme_challenge",
        translation_key="acme_challenge",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:shield-key",
    ),
)


def _safe_parse_datetime(value: str | None) -> datetime | None:
    """Safely parse an ISO datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        _LOGGER.warning("Could not parse datetime value: %s", value)
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up One.com DynDNS sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    domain = entry.data[CONF_DOMAIN]

    ssl_only_sensors = {"certificate_expiry", "last_certificate_renewal", "acme_challenge"}

    entities = []
    for description in SENSOR_TYPES:
        # Skip certificate-related sensors if SSL not enabled
        if description.key in ssl_only_sensors:
            if not entry.data.get(CONF_SSL_ENABLED, False):
                continue

        entities.append(OneComDynDNSSensor(coordinator, entry, description, domain))

    async_add_entities(entities)


class OneComDynDNSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a One.com DynDNS sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        domain: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._domain = domain

        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = get_device_info(
            entry.entry_id,
            domain,
            addon_slug=entry.data.get(CONF_ADDON_SLUG),
        )

    @property
    def native_value(self) -> str | datetime | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        key = self.entity_description.key

        if key == "current_ip":
            return self.coordinator.data.get("current_ip")

        if key == "last_update":
            return _safe_parse_datetime(self.coordinator.data.get("last_update"))

        if key == "last_ip_update":
            return _safe_parse_datetime(self.coordinator.data.get("last_ip_update"))

        if key == "certificate_expiry":
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info:
                return _safe_parse_datetime(cert_info.get("not_valid_after"))
            return None

        if key == "last_certificate_renewal":
            return _safe_parse_datetime(
                self.coordinator.data.get("last_certificate_renewal")
            )

        if key == "acme_challenge":
            acme = self.coordinator.data.get("acme_challenge")
            if acme:
                return acme.get("txt_value")
            return None

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        key = self.entity_description.key
        attrs: dict[str, Any] = {}

        if key == "current_ip":
            attrs["domain"] = self._domain
            attrs["subdomains"] = self.coordinator.data.get("subdomains", [])
            attrs["last_ip"] = self.coordinator.data.get("last_ip")
            attrs["ip_changed"] = self.coordinator.data.get("ip_changed", False)

        elif key == "last_ip_update":
            attrs["domain"] = self._domain
            attrs["current_ip"] = self.coordinator.data.get("current_ip")

        elif key == "certificate_expiry":
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info:
                attrs["domains"] = cert_info.get("domains", [])
                attrs["days_remaining"] = cert_info.get("days_remaining")
                attrs["issuer"] = cert_info.get("issuer", {}).get("organizationName", "Unknown")
                attrs["needs_renewal"] = cert_info.get("needs_renewal", False)

        elif key == "last_certificate_renewal":
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info:
                attrs["domains"] = cert_info.get("domains", [])
                attrs["certificate_expiry"] = cert_info.get("not_valid_after")

        elif key == "acme_challenge":
            acme = self.coordinator.data.get("acme_challenge")
            if acme:
                attrs["domain"] = acme.get("domain")
                attrs["txt_record_name"] = acme.get("txt_name")
                attrs["txt_record_value"] = acme.get("txt_value")
                attrs["timestamp"] = acme.get("timestamp")

        return attrs

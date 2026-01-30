"""Sensor platform for One.com DynDNS."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOMAIN,
    ATTR_CURRENT_IP,
    ATTR_LAST_UPDATE,
    ATTR_CERTIFICATE_EXPIRY,
    ATTR_CERTIFICATE_DOMAINS,
    ATTR_DAYS_UNTIL_EXPIRY,
)

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="current_ip",
        translation_key="current_ip",
        icon="mdi:ip-network",
    ),
    SensorEntityDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="certificate_expiry",
        translation_key="certificate_expiry",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:certificate",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up One.com DynDNS sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    domain = entry.data[CONF_DOMAIN]

    entities = []
    for description in SENSOR_TYPES:
        # Skip certificate sensor if SSL not enabled
        if description.key == "certificate_expiry":
            if not entry.data.get("ssl_enabled", False):
                continue

        entities.append(OneComDynDNSSensor(coordinator, entry, description, domain))

    async_add_entities(entities)


class OneComDynDNSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a One.com DynDNS sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        domain: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._domain = domain
        self._entry = entry

        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"One.com DynDNS - {domain}",
            manufacturer="One.com",
            model="DynDNS",
            configuration_url="https://www.one.com/admin",
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        key = self.entity_description.key

        if key == "current_ip":
            return self.coordinator.data.get("current_ip")

        if key == "last_update":
            last_update = self.coordinator.data.get("last_update")
            if last_update:
                return datetime.fromisoformat(last_update)
            return None

        if key == "certificate_expiry":
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info and cert_info.get("not_valid_after"):
                return datetime.fromisoformat(cert_info["not_valid_after"])
            return None

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        key = self.entity_description.key
        attrs = {}

        if key == "current_ip":
            attrs["domain"] = self._domain
            attrs["subdomains"] = self.coordinator.data.get("subdomains", [])
            attrs["last_ip"] = self.coordinator.data.get("last_ip")
            attrs["ip_changed"] = self.coordinator.data.get("ip_changed", False)

        if key == "certificate_expiry":
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info:
                attrs["domains"] = cert_info.get("domains", [])
                attrs["days_remaining"] = cert_info.get("days_remaining")
                attrs["issuer"] = cert_info.get("issuer", {}).get("organizationName", "Unknown")
                attrs["needs_renewal"] = cert_info.get("needs_renewal", False)

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

"""Binary sensor platform for One.com DynDNS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DOMAIN

BINARY_SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="dns_status",
        translation_key="dns_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:dns",
    ),
    BinarySensorEntityDescription(
        key="certificate_valid",
        translation_key="certificate_valid",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:certificate",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up One.com DynDNS binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    domain = entry.data[CONF_DOMAIN]

    entities = []
    for description in BINARY_SENSOR_TYPES:
        # Skip certificate sensor if SSL not enabled
        if description.key == "certificate_valid":
            if not entry.data.get("ssl_enabled", False):
                continue

        entities.append(OneComDynDNSBinarySensor(coordinator, entry, description, domain))

    async_add_entities(entities)


class OneComDynDNSBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a One.com DynDNS binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: BinarySensorEntityDescription,
        domain: str,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data is None:
            return None

        key = self.entity_description.key

        if key == "dns_status":
            # True if we have a current IP (connected)
            return self.coordinator.data.get("current_ip") is not None

        if key == "certificate_valid":
            # For PROBLEM class, True means there IS a problem
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info is None:
                return True  # No certificate = problem
            # Return True (problem) if needs renewal or days_remaining <= 0
            if cert_info.get("needs_renewal", False):
                return True
            days = cert_info.get("days_remaining", 0)
            return days <= 0

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        key = self.entity_description.key
        attrs = {}

        if key == "dns_status":
            attrs["domain"] = self._domain
            attrs["current_ip"] = self.coordinator.data.get("current_ip")
            attrs["subdomains"] = self.coordinator.data.get("subdomains", [])

        if key == "certificate_valid":
            cert_info = self.coordinator.data.get("certificate_info")
            if cert_info:
                attrs["expiry_date"] = cert_info.get("not_valid_after")
                attrs["days_remaining"] = cert_info.get("days_remaining")
                attrs["domains"] = cert_info.get("domains", [])

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

"""Button platform for One.com DynDNS."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN, CONF_DOMAIN, CONF_ADDON_SLUG, CONF_SSL_ENABLED, get_device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OneComButtonEntityDescription(ButtonEntityDescription):
    """Describes a One.com DynDNS button entity."""

    method: str


BUTTON_TYPES: Final[tuple[OneComButtonEntityDescription, ...]] = (
    OneComButtonEntityDescription(
        key="update_dns",
        translation_key="update_dns",
        icon="mdi:dns",
        entity_category=EntityCategory.CONFIG,
        method="async_force_update_dns",
    ),
    OneComButtonEntityDescription(
        key="check_ip",
        translation_key="check_ip",
        icon="mdi:ip-network-outline",
        entity_category=EntityCategory.CONFIG,
        method="async_refresh",
    ),
    OneComButtonEntityDescription(
        key="renew_certificate",
        translation_key="renew_certificate",
        icon="mdi:certificate-outline",
        entity_category=EntityCategory.CONFIG,
        method="async_force_renew_certificate",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up One.com DynDNS buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    domain = entry.data[CONF_DOMAIN]

    entities = []
    for description in BUTTON_TYPES:
        # Skip certificate button if SSL not enabled
        if description.key == "renew_certificate":
            if not entry.data.get(CONF_SSL_ENABLED, False):
                continue

        entities.append(OneComDynDNSButton(coordinator, entry, description, domain))

    async_add_entities(entities)


class OneComDynDNSButton(CoordinatorEntity, ButtonEntity):
    """Representation of a One.com DynDNS button."""

    _attr_has_entity_name = True
    entity_description: OneComButtonEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        description: OneComButtonEntityDescription,
        domain: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._domain = domain

        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = get_device_info(
            entry.entry_id,
            domain,
            addon_slug=entry.data.get(CONF_ADDON_SLUG),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        method = getattr(self.coordinator, self.entity_description.method, None)
        if method is None:
            _LOGGER.error(
                "Coordinator has no method %s", self.entity_description.method,
            )
            return
        try:
            await method()
        except Exception:
            _LOGGER.exception(
                "Error executing %s", self.entity_description.method,
            )
            raise

"""Config flow for One.com DynDNS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
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
    DEFAULT_IP_SERVICE,
    DEFAULT_SSL_RENEWAL_DAYS,
    DEFAULT_SSL_CHECK_INTERVAL,
    IP_SERVICES,
)
from .onecom_api import async_validate_credentials

_LOGGER = logging.getLogger(__name__)


class OneComDynDNSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for One.com DynDNS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._domains: list[str] = []
        self._subdomains: list[str] = []

    async def async_step_hassio(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Handle Supervisor add-on discovery.

        Called automatically when the add-on publishes its discovery
        info via the Supervisor API.  The config entry is created
        immediately so the user sees entities on the add-on device
        without any manual setup.
        """
        config = discovery_info.get("config", discovery_info)
        domain = config.get("domain", "")

        if not domain:
            return self.async_abort(reason="no_domain")

        # Prevent duplicate entries for the same domain
        await self.async_set_unique_id(f"onecom_{domain}")
        self._abort_if_unique_id_configured(updates=config)

        # Store the add-on slug so entities can attach to its device
        config["addon_slug"] = discovery_info.get(
            "addon", "homeassistant-onecom-dyndns"
        )

        # Auto-create the entry – no user confirmation required because
        # all configuration is already provided by the add-on.
        return self.async_create_entry(
            title=f"One.com DynDNS - {domain}",
            data=config,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate credentials
            result = await async_validate_credentials(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )

            if result["valid"]:
                self._data.update(user_input)
                self._domains = result["domains"]

                # If we got domains, go to domain selection
                if self._domains:
                    return await self.async_step_domain()

                # Otherwise, ask for manual domain input
                return await self.async_step_domain_manual()

            errors["base"] = "invalid_auth"
            if "Invalid credentials" in result.get("error", ""):
                errors["base"] = "invalid_auth"
            elif "connect" in result.get("error", "").lower():
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns"
            },
        )

    async def async_step_domain(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle domain selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_domain = user_input[CONF_DOMAIN]
            self._data[CONF_DOMAIN] = selected_domain

            # Check if this domain is already configured
            await self.async_set_unique_id(f"onecom_{selected_domain}")
            self._abort_if_unique_id_configured()

            # Fetch subdomains for selected domain
            result = await async_validate_credentials(
                self._data[CONF_USERNAME],
                self._data[CONF_PASSWORD],
                selected_domain,
            )

            self._subdomains = result.get("subdomains", [])

            return await self.async_step_subdomains()

        # Create domain selection
        domain_options = [
            {"value": d, "label": d} for d in self._domains
        ]

        return self.async_show_form(
            step_id="domain",
            data_schema=vol.Schema({
                vol.Required(CONF_DOMAIN): SelectSelector(
                    SelectSelectorConfig(
                        options=domain_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )

    async def async_step_domain_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual domain input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            domain = user_input[CONF_DOMAIN]
            self._data[CONF_DOMAIN] = domain

            # Check if this domain is already configured
            await self.async_set_unique_id(f"onecom_{domain}")
            self._abort_if_unique_id_configured()

            # Try to fetch subdomains
            result = await async_validate_credentials(
                self._data[CONF_USERNAME],
                self._data[CONF_PASSWORD],
                domain,
            )

            self._subdomains = result.get("subdomains", [])

            return await self.async_step_subdomains()

        return self.async_show_form(
            step_id="domain_manual",
            data_schema=vol.Schema({
                vol.Required(CONF_DOMAIN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )

    async def async_step_subdomains(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle subdomain selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_SUBDOMAINS] = user_input.get(CONF_SUBDOMAINS, [""])
            return await self.async_step_options()

        # Create subdomain options
        subdomain_options = []
        for sub in self._subdomains:
            label = f"{sub}.{self._data[CONF_DOMAIN]}" if sub else f"{self._data[CONF_DOMAIN]} (root)"
            subdomain_options.append({"value": sub, "label": label})

        # If no subdomains found, use a text input
        if not subdomain_options:
            subdomain_options = [
                {"value": "", "label": f"{self._data[CONF_DOMAIN]} (root)"}
            ]

        return self.async_show_form(
            step_id="subdomains",
            data_schema=vol.Schema({
                vol.Required(CONF_SUBDOMAINS, default=[""]): SelectSelector(
                    SelectSelectorConfig(
                        options=subdomain_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            errors=errors,
            description_placeholders={
                "domain": self._data[CONF_DOMAIN]
            },
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle general options step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # If SSL enabled, go to SSL configuration
            if user_input.get(CONF_SSL_ENABLED, False):
                return await self.async_step_ssl()

            # Otherwise, create the entry
            return self.async_create_entry(
                title=self._data[CONF_DOMAIN],
                data=self._data,
            )

        ip_service_options = [
            {"value": key, "label": key.capitalize()}
            for key in IP_SERVICES.keys()
        ]

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=DEFAULT_UPDATE_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_IP_SERVICE,
                    default=DEFAULT_IP_SERVICE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ip_service_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_SSL_ENABLED, default=False): BooleanSelector(),
            }),
            errors=errors,
        )

    async def async_step_ssl(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle SSL configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # Validate email is provided
            if not user_input.get(CONF_SSL_EMAIL):
                errors[CONF_SSL_EMAIL] = "ssl_email_required"
            else:
                return self.async_create_entry(
                    title=self._data[CONF_DOMAIN],
                    data=self._data,
                )

        # Create SSL domain options from selected subdomains
        ssl_domain_options = []
        for sub in self._data.get(CONF_SUBDOMAINS, [""]):
            full_domain = f"{sub}.{self._data[CONF_DOMAIN]}" if sub else self._data[CONF_DOMAIN]
            ssl_domain_options.append({"value": full_domain, "label": full_domain})

        # Add wildcard option
        ssl_domain_options.append({
            "value": f"*.{self._data[CONF_DOMAIN]}",
            "label": f"*.{self._data[CONF_DOMAIN]} (Wildcard)"
        })

        default_ssl_domains = [
            f"{sub}.{self._data[CONF_DOMAIN]}" if sub else self._data[CONF_DOMAIN]
            for sub in self._data.get(CONF_SUBDOMAINS, [""])
        ]

        return self.async_show_form(
            step_id="ssl",
            data_schema=vol.Schema({
                vol.Required(CONF_SSL_EMAIL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(
                    CONF_SSL_DOMAINS,
                    default=default_ssl_domains
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ssl_domain_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_SSL_STAGING, default=False): BooleanSelector(),
                vol.Required(
                    CONF_SSL_RENEWAL_DAYS,
                    default=DEFAULT_SSL_RENEWAL_DAYS
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Required(
                    CONF_SSL_CHECK_INTERVAL,
                    default=DEFAULT_SSL_CHECK_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=24,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="h",
                    )
                ),
            }),
            errors=errors,
            description_placeholders={
                "domain": self._data[CONF_DOMAIN]
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for One.com DynDNS."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Update the config entry
            return self.async_create_entry(title="", data=user_input)

        # Get current values
        current = self.config_entry.data

        ip_service_options = [
            {"value": key, "label": key.capitalize()}
            for key in IP_SERVICES.keys()
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_IP_SERVICE,
                    default=current.get(CONF_IP_SERVICE, DEFAULT_IP_SERVICE)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ip_service_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SSL_ENABLED,
                    default=current.get(CONF_SSL_ENABLED, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_SSL_EMAIL,
                    default=current.get(CONF_SSL_EMAIL, "")
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(
                    CONF_SSL_STAGING,
                    default=current.get(CONF_SSL_STAGING, False)
                ): BooleanSelector(),
                vol.Required(
                    CONF_SSL_RENEWAL_DAYS,
                    default=current.get(CONF_SSL_RENEWAL_DAYS, DEFAULT_SSL_RENEWAL_DAYS)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
            }),
            errors=errors,
        )

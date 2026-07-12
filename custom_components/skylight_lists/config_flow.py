"""Configuration flow for Skylight Lists."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import SkylightAuthError, SkylightConnectionError, SkylightClient
from .const import CONF_FRAME_ID, DOMAIN


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate configured credentials against Skylight."""
    client = SkylightClient(
        async_get_clientsession(hass),
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data[CONF_FRAME_ID],
    )
    await client.async_login()
    await client.async_get_lists()


class SkylightListsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Skylight Lists configuration flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_USERNAME]}_{user_input[CONF_FRAME_ID]}".lower()
            )
            self._abort_if_unique_id_configured()
            try:
                await validate_input(self.hass, user_input)
            except SkylightAuthError:
                errors["base"] = "invalid_auth"
            except SkylightConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Skylight Lists ({user_input[CONF_FRAME_ID]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_FRAME_ID): str,
                }
            ),
            errors=errors,
        )

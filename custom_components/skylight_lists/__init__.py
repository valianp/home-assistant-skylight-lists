"""Set up the Skylight Lists integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import SkylightClient
from .const import CONF_FRAME_ID, DOMAIN
from .const import CONF_SYNC_TARGET_ENTITY
from .sync import TodoSynchronizer

PLATFORMS = [Platform.TODO]


@dataclass
class SkylightListsData:
    """Runtime data for one configured Skylight account."""

    client: SkylightClient
    synchronizer: TodoSynchronizer | None = None


type SkylightListsConfigEntry = ConfigEntry[SkylightListsData]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the service that binds a Skylight list to another todo entity."""
    async def enable_todo_sync(call) -> None:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if not entry or entry.domain != DOMAIN:
            raise ValueError("Unknown Skylight Lists config entry")
        # Store the binding with the entry data. This integration has no
        # options flow, and Home Assistant does not persist ad-hoc options
        # for entries that do not advertise one.
        data = {**entry.data, CONF_SYNC_TARGET_ENTITY: call.data["target_entity_id"]}
        hass.config_entries.async_update_entry(entry, data=data)
        await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(
        DOMAIN,
        "enable_todo_sync",
        enable_todo_sync,
        schema=vol.Schema({vol.Required("entry_id"): str, vol.Required("target_entity_id"): str}),
    )

    async def disable_todo_sync(call) -> None:
        """Remove the optional external to-do binding without disabling Skylight."""
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if not entry or entry.domain != DOMAIN:
            raise ValueError("Unknown Skylight Lists config entry")
        data = {
            key: value
            for key, value in entry.data.items()
            if key != CONF_SYNC_TARGET_ENTITY
        }
        hass.config_entries.async_update_entry(entry, data=data)
        await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(
        DOMAIN,
        "disable_todo_sync",
        disable_todo_sync,
        schema=vol.Schema({vol.Required("entry_id"): str}),
    )

    async def sync_now(call) -> None:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if not entry or entry.domain != DOMAIN or not entry.runtime_data.synchronizer:
            raise ValueError("Enable to-do synchronization before requesting a sync")
        await entry.runtime_data.synchronizer.async_sync()

    hass.services.async_register(
        DOMAIN,
        "sync_now",
        sync_now,
        schema=vol.Schema({vol.Required("entry_id"): str}),
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: SkylightListsConfigEntry) -> bool:
    """Set up Skylight Lists from a configuration entry."""
    client = SkylightClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_FRAME_ID],
    )
    await client.async_login()
    entry.runtime_data = SkylightListsData(client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    target = entry.data.get(CONF_SYNC_TARGET_ENTITY)
    if target:
        # Grocery List is Skylight's default shopping list, and is the list
        # this integration exposes as todo.skylight_grocery_list.
        synchronizer = TodoSynchronizer(
            hass,
            "todo.skylight_grocery_list",
            target,
            f"{DOMAIN}.{entry.entry_id}.todo_sync",
        )
        entry.runtime_data.synchronizer = synchronizer
        await synchronizer.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SkylightListsConfigEntry) -> bool:
    """Unload a configuration entry."""
    if entry.runtime_data.synchronizer:
        await entry.runtime_data.synchronizer.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

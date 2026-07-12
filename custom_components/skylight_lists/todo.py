"""Expose Skylight lists as Home Assistant todo entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import SkylightListsConfigEntry


class SkylightListEntity(TodoListEntity):
    """A native Home Assistant to-do entity backed by one Skylight list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, entry: SkylightListsConfigEntry, resource: dict[str, Any]) -> None:
        """Initialize the entity."""
        self._client = entry.runtime_data.client
        self._list_id = str(resource["id"])
        self._attr_unique_id = f"{entry.entry_id}_{self._list_id}"
        self._attr_name = resource.get("attributes", {}).get("label", self._list_id)
        self.entity_id = f"todo.skylight_{slugify(self._attr_name)}"
        self._items: list[TodoItem] = []

    async def async_update(self) -> None:
        """Fetch the current list contents from Skylight."""
        response = await self._client.async_get_list(self._list_id)
        self._items = [
            TodoItem(
                uid=str(item["id"]),
                summary=item.get("attributes", {}).get("label", ""),
                status=(
                    TodoItemStatus.COMPLETED
                    if item.get("attributes", {}).get("status") == "completed"
                    else TodoItemStatus.NEEDS_ACTION
                ),
            )
            for item in response.get("included", [])
            if item.get("type") == "list_item"
        ]

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return cached items after Home Assistant refreshes the entity."""
        return self._items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create an item in Skylight."""
        await self._client.async_create_item(self._list_id, item.summary)
        await self.async_update()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update item text or checked state in Skylight."""
        attributes = {
            "label": item.summary,
            "status": "completed" if item.status == TodoItemStatus.COMPLETED else "pending",
        }
        await self._client.async_update_item(self._list_id, item.uid, attributes)
        await self.async_update()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete selected items from Skylight."""
        for uid in uids:
            await self._client.async_delete_item(self._list_id, uid)
        await self.async_update()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create an entity for every accessible Skylight list."""
    config_entry = entry  # Typed alias for runtime data supplied by __init__.
    lists = await config_entry.runtime_data.client.async_get_lists()
    async_add_entities([SkylightListEntity(config_entry, resource) for resource in lists], True)

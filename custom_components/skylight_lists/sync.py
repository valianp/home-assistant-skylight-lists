"""Conservative synchronization between a Skylight and another HA todo list."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

_PRESENTATION_HEADER_PREFIXES = ("[Route] ", "\U0001F4CD ")


def _is_presentation_header(summary: str | None) -> bool:
    """Return whether a row is target-only workflow presentation metadata."""
    return bool(summary and summary.startswith(_PRESENTATION_HEADER_PREFIXES))


class TodoSynchronizer:
    """Keep matching items synchronized; Skylight resolves simultaneous conflicts."""

    def __init__(
        self,
        hass: HomeAssistant,
        skylight_entity: str,
        target_entity: str,
        storage_key: str,
    ) -> None:
        self._hass = hass
        self._skylight_entity = skylight_entity
        self._target_entity = target_entity
        self._lock = asyncio.Lock()
        self._unsub = None
        self._store: Store[dict[str, Any]] = Store(hass, 1, storage_key)
        self._snapshot: dict[str, dict[str, Any]] = {}

    async def async_start(self) -> None:
        """Start periodic sync and immediately reconcile."""
        stored = await self._store.async_load()
        self._snapshot = (stored or {}).get("items", {})
        self._unsub = async_track_time_interval(
            self._hass, lambda _: self._hass.add_job(self.async_periodic_sync), timedelta(minutes=5)
        )
        await self.async_periodic_sync()

    async def async_periodic_sync(self) -> bool:
        """Synchronize, then refresh the route only when content changed."""
        return await self.async_sync()

    async def async_stop(self) -> None:
        """Stop periodic sync."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _items(self, entity_id: str) -> list[dict[str, Any]]:
        response = await self._hass.services.async_call(
            "todo", "get_items", target={"entity_id": entity_id}, blocking=True, return_response=True
        )
        return response.get(entity_id, {}).get("items", [])

    async def _add(self, entity_id: str, summary: str) -> None:
        await self._hass.services.async_call(
            "todo", "add_item", {"item": summary}, target={"entity_id": entity_id}, blocking=True
        )

    async def _status(self, entity_id: str, uid: str, status: str) -> None:
        await self._hass.services.async_call(
            "todo", "update_item", {"item": uid, "status": status}, target={"entity_id": entity_id}, blocking=True
        )

    async def _delete(self, entity_id: str, uid: str) -> None:
        await self._hass.services.async_call(
            "todo", "remove_item", {"item": uid}, target={"entity_id": entity_id}, blocking=True
        )

    @staticmethod
    def _index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            item["summary"].strip().casefold(): item
            for item in items
            if item.get("summary") and not _is_presentation_header(item["summary"])
        }

    async def _save_snapshot(self, skylight: list[dict[str, Any]], target: list[dict[str, Any]]) -> None:
        sky = self._index(skylight)
        other = self._index(target)
        self._snapshot = {
            key: {"skylight_uid": sky[key]["uid"], "target_uid": other[key]["uid"], "status": sky[key].get("status")}
            for key in sky.keys() & other.keys()
        }
        await self._store.async_save({"items": self._snapshot})

    async def async_sync(self) -> bool:
        """Reconcile both lists and return whether this run made a change."""
        if self._lock.locked():
            return False
        async with self._lock:
            try:
                changed = False
                skylight, target = await asyncio.gather(
                    self._items(self._skylight_entity), self._items(self._target_entity)
                )
                sky = self._index(skylight)
                other = self._index(target)

                # First run has no history. Merge safely and create a baseline;
                # it never treats an item as deleted until it has been observed
                # synchronized at least once.
                if not self._snapshot:
                    for key, item in sky.items():
                        if key not in other:
                            await self._add(self._target_entity, item["summary"])
                            changed = True
                    for key, item in other.items():
                        if key not in sky:
                            await self._add(self._skylight_entity, item["summary"])
                            changed = True
                    skylight, target = await asyncio.gather(self._items(self._skylight_entity), self._items(self._target_entity))
                    await self._save_snapshot(skylight, target)
                    return changed

                # New items are copied to the other side.
                for key, item in sky.items():
                    if key not in other and key not in self._snapshot:
                        await self._add(self._target_entity, item["summary"])
                        changed = True
                for key, item in other.items():
                    if key not in sky and key not in self._snapshot:
                        await self._add(self._skylight_entity, item["summary"])
                        changed = True

                for key, previous in self._snapshot.items():
                    source = sky.get(key)
                    destination = other.get(key)
                    if source and destination:
                        source_changed = source.get("status") != previous.get("status")
                        destination_changed = destination.get("status") != previous.get("status")
                        if source_changed and not destination_changed:
                            await self._status(self._target_entity, destination["uid"], source["status"])
                        elif destination_changed and not source_changed:
                            await self._status(self._skylight_entity, source["uid"], destination["status"])
                        elif source_changed and destination_changed and source.get("status") != destination.get("status"):
                            # Same-cycle conflict: Skylight wins deterministically.
                            await self._status(self._target_entity, destination["uid"], source["status"])
                    elif source and not destination:
                        if source.get("status") == previous.get("status"):
                            await self._delete(self._skylight_entity, source["uid"])
                            changed = True
                        else:
                            await self._add(self._target_entity, source["summary"])
                            changed = True
                    elif destination and not source:
                        if destination.get("status") == previous.get("status"):
                            await self._delete(self._target_entity, destination["uid"])
                            changed = True
                        else:
                            await self._add(self._skylight_entity, destination["summary"])
                            changed = True

                skylight, target = await asyncio.gather(self._items(self._skylight_entity), self._items(self._target_entity))
                await self._save_snapshot(skylight, target)
                return changed
            except Exception:  # Keep retrying on the next interval.
                _LOGGER.exception("Unable to synchronize %s and %s", self._skylight_entity, self._target_entity)
                return False

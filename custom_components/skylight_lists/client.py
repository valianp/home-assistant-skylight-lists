"""Current Skylight OAuth client used by the Lists integration."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs

import aiohttp

from .const import API_BASE_URL, API_VERSION, OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI


class SkylightAuthError(Exception):
    """Authentication with Skylight failed."""


class SkylightConnectionError(Exception):
    """A Skylight API request failed."""


class SkylightClient:
    """Authenticate with Skylight and manage list endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        frame_id: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._frame_id = frame_id
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0

    async def async_login(self) -> None:
        """Exchange a username and password for OAuth tokens using PKCE."""
        try:
            # Home Assistant shares this session's cookie jar between config
            # validation and entry setup. A successful validation leaves a
            # Skylight web session behind; on the second login request
            # Skylight redirects away from the form, so no CSRF input exists.
            # We need a fresh Skylight web session for every password login.
            self._session.cookie_jar.clear_domain(urlparse(API_BASE_URL).hostname)
            async with self._session.get(
                f"{API_BASE_URL}/auth/session/new", allow_redirects=False
            ) as response:
                login_page = await response.text()
            match = re.search(
                r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)',
                login_page,
            ) or re.search(
                r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token',
                login_page,
            )
            if not match:
                raise SkylightAuthError("Skylight did not return a login CSRF token")

            async with self._session.post(
                f"{API_BASE_URL}/auth/session",
                data={
                    "authenticity_token": match.group(1),
                    "email": self._username,
                    "password": self._password,
                },
                headers={"Origin": API_BASE_URL, "Referer": f"{API_BASE_URL}/auth/session/new"},
                allow_redirects=False,
            ) as response:
                if response.status != 302:
                    raise SkylightAuthError("Skylight rejected the configured credentials")

            verifier = secrets.token_urlsafe(64)
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            ).decode().rstrip("=")
            state = secrets.token_urlsafe(24)
            query = urlencode(
                {
                    "client_id": OAUTH_CLIENT_ID,
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "response_type": "code",
                    "scope": "everything",
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
            async with self._session.get(
                f"{API_BASE_URL}/oauth/authorize?{query}", allow_redirects=False
            ) as response:
                redirect = response.headers.get("Location")
                if response.status != 302 or not redirect:
                    raise SkylightAuthError("Skylight OAuth authorization failed")

            params = parse_qs(urlparse(redirect).query)
            code = params.get("code", [None])[0]
            if not code or params.get("state", [None])[0] != state:
                raise SkylightAuthError("Skylight OAuth state validation failed")

            async with self._session.post(
                f"{API_BASE_URL}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": OAUTH_CLIENT_ID,
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "code": code,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200 or not data.get("access_token"):
                    raise SkylightAuthError("Skylight OAuth token exchange failed")
            self._set_tokens(data)
        except aiohttp.ClientError as err:
            raise SkylightConnectionError(str(err)) from err

    def _set_tokens(self, tokens: dict[str, Any]) -> None:
        self._access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token", self._refresh_token)
        self._expires_at = time.time() + int(tokens.get("expires_in", 3600))

    async def _async_refresh(self) -> None:
        if not self._refresh_token:
            await self.async_login()
            return
        async with self._session.post(
            f"{API_BASE_URL}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": OAUTH_CLIENT_ID,
                "refresh_token": self._refresh_token,
            },
            headers={"Accept": "application/json"},
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200 or not data.get("access_token"):
                await self.async_login()
                return
        self._set_tokens(data)

    async def _async_request(
        self, method: str, path: str, payload: dict[str, Any] | None = None, retry: bool = True
    ) -> dict[str, Any]:
        """Make an authenticated request, refreshing the token when required."""
        if not self._access_token or time.time() >= self._expires_at - 300:
            await self._async_refresh()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": "SkylightMobile (web)",
            "Skylight-Api-Version": API_VERSION,
        }
        async with self._session.request(
            method,
            f"{API_BASE_URL}{path}",
            headers=headers,
            json=payload,
        ) as response:
            data = await response.json(content_type=None)
            if response.status == 401 and retry:
                self._expires_at = 0
                await self._async_refresh()
                return await self._async_request(method, path, payload, retry=False)
            if response.status >= 400:
                raise SkylightConnectionError(f"Skylight API returned HTTP {response.status}: {data}")
            return data

    async def async_get_lists(self) -> list[dict[str, Any]]:
        """Return all lists for the configured frame."""
        data = await self._async_request("GET", f"/api/frames/{self._frame_id}/lists")
        return data.get("data", [])

    async def async_get_list(self, list_id: str) -> dict[str, Any]:
        """Return one list and its included list items."""
        return await self._async_request("GET", f"/api/frames/{self._frame_id}/lists/{list_id}")

    async def async_create_item(self, list_id: str, summary: str) -> dict[str, Any]:
        """Create a list item."""
        return await self._async_request(
            "POST",
            f"/api/frames/{self._frame_id}/lists/{list_id}/list_items",
            # Skylight's list-item endpoint accepts a flat request body, even
            # though read responses use JSON:API-style `data` resources.
            {"label": summary},
        )

    async def async_update_item(self, list_id: str, item_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
        """Update a list item label or completion status."""
        return await self._async_request(
            "PUT",
            f"/api/frames/{self._frame_id}/lists/{list_id}/list_items/{item_id}",
            attributes,
        )

    async def async_delete_item(self, list_id: str, item_id: str) -> None:
        """Delete a list item."""
        await self._async_request(
            "DELETE", f"/api/frames/{self._frame_id}/lists/{list_id}/list_items/{item_id}"
        )

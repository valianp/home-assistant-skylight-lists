# Skylight Lists for Home Assistant

An unofficial Home Assistant custom integration that exposes Skylight shopping and to-do lists as native `todo` entities.

## Status

Initial development scaffold. The integration uses Skylight's current OAuth PKCE login flow rather than the obsolete `/api/sessions` endpoint used by older community integrations.

## Intended capabilities

- One `todo` entity per Skylight list.
- Create, edit, complete, uncomplete, and remove items.
- Refresh Skylight list changes on a configurable interval.
- Use with other Home Assistant to-do integrations, including Google Keep Sync.

Optional synchronization reconciles linked lists every five minutes. Use
`skylight_lists.sync_now` for an immediate reconciliation. Store-specific
formatting belongs in a separate workflow integration so this repository does
not contain anyone's physical store location or shopping route.

## Security

Skylight credentials are stored in Home Assistant's configuration entry and used only to obtain short-lived OAuth access tokens. Tokens are kept in memory and refreshed automatically.

## Direct config-flow setup (optional)

The normal Home Assistant UI flow is preferred. If the integration is installed
but the UI does not discover it, `scripts/configure-home-assistant.mjs` can
create the entry through Home Assistant's supported config-flow API.
It does not use browser automation or edit `.storage`.

Create a Home Assistant long-lived access token under your profile, then set
`HA_URL`, `HA_TOKEN`, `SKYLIGHT_USERNAME`, `SKYLIGHT_PASSWORD`, and
`SKYLIGHT_FRAME_ID` as environment variables and run:

```powershell
node scripts/configure-home-assistant.mjs
```

Do not commit a token or password to this repository.

On Windows, `scripts/configure-home-assistant.ps1` provides the same native
API setup without requiring Node.js.

## Development

Install this repository through HACS as a custom integration once the first usable release is ready. Do not copy it into an existing `skylight` custom component: this integration intentionally uses the distinct domain `skylight_lists`.

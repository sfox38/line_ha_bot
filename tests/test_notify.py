"""Tests for the notify entity platform."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.line_ha_bot.const import (
    CONF_CHANNEL_ACCESS_TOKEN,
    CONF_CHANNEL_SECRET,
    DOMAIN,
    EVENT_SEND_FAILED,
    LINE_PUSH_URL,
    RECIPIENTS_KEY,
)

from .conftest import GROUP_ID, SECRET, TOKEN, USER_ID, USER_ID_2


async def test_entities_created_per_recipient(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """One notify entity is created per recipient with the expected ids."""
    registry = er.async_get(hass)

    user_entity = registry.async_get_entity_id(
        Platform.NOTIFY, DOMAIN, f"{DOMAIN}_{USER_ID}"
    )
    group_entity = registry.async_get_entity_id(
        Platform.NOTIFY, DOMAIN, f"{DOMAIN}_{GROUP_ID}"
    )

    assert user_entity == "notify.line_bot_david"
    assert group_entity == "notify.line_bot_family"


async def test_friendly_name_used_as_display_name(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The friendly_name (which may contain emoji) becomes the entity name."""
    state = hass.states.get("notify.line_bot_david")
    assert state is not None
    # has_entity_name prefixes the device name; the emoji display name is used.
    assert "David 🤓" in state.attributes["friendly_name"]


async def test_stale_entities_removed_on_reload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A recipient removed from config is purged from the entity registry."""
    from .conftest import mock_quota_endpoints

    mock_quota_endpoints(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHANNEL_ACCESS_TOKEN: TOKEN,
            CONF_CHANNEL_SECRET: SECRET,
            RECIPIENTS_KEY: {
                "david": {
                    "user_id": USER_ID,
                    "display_name": "David",
                    "friendly_name": "David",
                    "type": "user",
                },
                "greta": {
                    "user_id": USER_ID_2,
                    "display_name": "Greta",
                    "friendly_name": "Greta",
                    "type": "user",
                },
            },
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert registry.async_get_entity_id(Platform.NOTIFY, DOMAIN, f"{DOMAIN}_{USER_ID_2}")

    # Drop greta and reload.
    new_data = dict(entry.data)
    new_recipients = dict(new_data[RECIPIENTS_KEY])
    del new_recipients["greta"]
    new_data[RECIPIENTS_KEY] = new_recipients
    hass.config_entries.async_update_entry(entry, data=new_data)
    await hass.async_block_till_done()

    assert (
        registry.async_get_entity_id(Platform.NOTIFY, DOMAIN, f"{DOMAIN}_{USER_ID_2}")
        is None
    )
    assert registry.async_get_entity_id(Platform.NOTIFY, DOMAIN, f"{DOMAIN}_{USER_ID}")


async def test_send_message_via_notify(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """notify.send_message posts a text payload to the LINE push API."""
    aioclient_mock.post(LINE_PUSH_URL, status=200, text="{}")

    await hass.services.async_call(
        Platform.NOTIFY,
        "send_message",
        {"entity_id": "notify.line_bot_david", "message": "hello"},
        blocking=True,
    )

    push_call = next(c for c in aioclient_mock.mock_calls if str(c[1]) == LINE_PUSH_URL)
    payload = push_call[2]
    assert payload["to"] == USER_ID
    assert payload["messages"] == [{"type": "text", "text": "hello"}]


async def test_send_message_via_notify_with_title(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A title is prepended to the body in the notify path."""
    aioclient_mock.post(LINE_PUSH_URL, status=200, text="{}")

    await hass.services.async_call(
        Platform.NOTIFY,
        "send_message",
        {
            "entity_id": "notify.line_bot_david",
            "message": "body",
            "title": "Alert",
        },
        blocking=True,
    )

    push_call = next(c for c in aioclient_mock.mock_calls if str(c[1]) == LINE_PUSH_URL)
    assert push_call[2]["messages"][0]["text"] == "Alert\nbody"


async def test_send_message_failure_fires_event(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A failed notify send fires line_bot_send_failed."""
    aioclient_mock.post(LINE_PUSH_URL, status=401, text="nope")
    events: list = []
    hass.bus.async_listen(EVENT_SEND_FAILED, events.append)

    await hass.services.async_call(
        Platform.NOTIFY,
        "send_message",
        {"entity_id": "notify.line_bot_david", "message": "hi"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert events[0].data["error_type"] == "token_invalid"
    assert events[0].data["entity_id"] == "notify.line_bot_david"

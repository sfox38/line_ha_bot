"""Tests for the shared LINE API helpers in api.py."""

from __future__ import annotations

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant

from custom_components.line_ha_bot.api import (
    async_get_group_name,
    async_get_profile_name,
    async_send_line_message,
    fire_send_failed,
)
from custom_components.line_ha_bot.const import (
    EVENT_SEND_FAILED,
    LINE_GROUP_SUMMARY_URL,
    LINE_PROFILE_URL,
    LINE_PUSH_URL,
    LINE_REPLY_URL,
)

from .conftest import GROUP_ID, USER_ID

TOKEN = "tok"


def capture_events(hass: HomeAssistant, event_type: str) -> list:
    """Subscribe to an event type and collect fired events."""
    events: list = []
    hass.bus.async_listen(event_type, events.append)
    return events


async def test_fire_send_failed(hass: HomeAssistant) -> None:
    """fire_send_failed puts a fully populated event on the bus."""
    events = capture_events(hass, EVENT_SEND_FAILED)

    fire_send_failed(
        hass,
        "notify.line_bot_david",
        "david",
        "bad_request",
        "boom",
        http_status=400,
    )
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["entity_id"] == "notify.line_bot_david"
    assert data["recipient_name"] == "david"
    assert data["error_type"] == "bad_request"
    assert data["error_message"] == "boom"
    assert data["http_status"] == 400
    assert isinstance(data["timestamp"], int)


async def test_fire_send_failed_default_http_status(hass: HomeAssistant) -> None:
    """http_status defaults to None when omitted."""
    events = capture_events(hass, EVENT_SEND_FAILED)
    fire_send_failed(hass, "notify.x", "x", "connection_error", "no net")
    await hass.async_block_till_done()
    assert events[0].data["http_status"] is None


async def test_send_message_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 200 response returns True and fires no failure event."""
    aioclient_mock.post(LINE_PUSH_URL, status=200, text="{}")
    events = capture_events(hass, EVENT_SEND_FAILED)

    result = await async_send_line_message(
        hass,
        TOKEN,
        LINE_PUSH_URL,
        {"to": USER_ID, "messages": []},
        entity_id="notify.line_bot_david",
        recipient_name="david",
    )
    await hass.async_block_till_done()

    assert result is True
    assert events == []
    # Authorization header carries the bearer token.
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_send_message_token_invalid(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 returns False and fires a token_invalid failure event."""
    aioclient_mock.post(LINE_PUSH_URL, status=401, text="unauthorized")
    events = capture_events(hass, EVENT_SEND_FAILED)

    result = await async_send_line_message(
        hass,
        TOKEN,
        LINE_PUSH_URL,
        {"to": USER_ID, "messages": []},
        entity_id="notify.line_bot_david",
        recipient_name="david",
    )
    await hass.async_block_till_done()

    assert result is False
    assert events[0].data["error_type"] == "token_invalid"
    assert events[0].data["http_status"] == 401


async def test_send_message_reply_token_expired(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 400 on a reply send is reported as reply_token_expired."""
    aioclient_mock.post(LINE_REPLY_URL, status=400, text="invalid reply token")
    events = capture_events(hass, EVENT_SEND_FAILED)

    result = await async_send_line_message(
        hass,
        TOKEN,
        LINE_REPLY_URL,
        {"replyToken": "x", "messages": []},
        entity_id="notify.line_bot_david",
        recipient_name="david",
        is_reply=True,
    )
    await hass.async_block_till_done()

    assert result is False
    assert events[0].data["error_type"] == "reply_token_expired"
    assert events[0].data["http_status"] == 400


async def test_send_message_bad_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 400 on a push send is reported as bad_request."""
    aioclient_mock.post(LINE_PUSH_URL, status=400, text="bad body")
    events = capture_events(hass, EVENT_SEND_FAILED)

    result = await async_send_line_message(
        hass,
        TOKEN,
        LINE_PUSH_URL,
        {"to": USER_ID, "messages": []},
        entity_id="notify.line_bot_david",
        recipient_name="david",
    )
    await hass.async_block_till_done()

    assert result is False
    assert events[0].data["error_type"] == "bad_request"
    assert "bad body" in events[0].data["error_message"]


async def test_send_message_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unexpected status is reported as http_error with the status code."""
    aioclient_mock.post(LINE_PUSH_URL, status=500, text="server error")
    events = capture_events(hass, EVENT_SEND_FAILED)

    result = await async_send_line_message(
        hass,
        TOKEN,
        LINE_PUSH_URL,
        {"to": USER_ID, "messages": []},
        entity_id="notify.line_bot_david",
        recipient_name="david",
    )
    await hass.async_block_till_done()

    assert result is False
    assert events[0].data["error_type"] == "http_error"
    assert events[0].data["http_status"] == 500


async def test_send_message_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A client connection error is reported as connection_error."""
    aioclient_mock.post(LINE_PUSH_URL, exc=aiohttp.ClientError("no route"))
    events = capture_events(hass, EVENT_SEND_FAILED)

    result = await async_send_line_message(
        hass,
        TOKEN,
        LINE_PUSH_URL,
        {"to": USER_ID, "messages": []},
        entity_id="notify.line_bot_david",
        recipient_name="david",
    )
    await hass.async_block_till_done()

    assert result is False
    assert events[0].data["error_type"] == "connection_error"
    assert events[0].data["http_status"] is None


async def test_get_profile_name_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 200 profile response returns the displayName."""
    aioclient_mock.get(
        LINE_PROFILE_URL.format(user_id=USER_ID), json={"displayName": "David"}
    )
    assert await async_get_profile_name(hass, TOKEN, USER_ID) == "David"


async def test_get_profile_name_missing_field(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 200 with no displayName falls back to the user_id."""
    aioclient_mock.get(LINE_PROFILE_URL.format(user_id=USER_ID), json={})
    assert await async_get_profile_name(hass, TOKEN, USER_ID) == USER_ID


async def test_get_profile_name_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-200 profile response returns None."""
    aioclient_mock.get(LINE_PROFILE_URL.format(user_id=USER_ID), status=404)
    assert await async_get_profile_name(hass, TOKEN, USER_ID) is None


async def test_get_profile_name_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A client error during profile lookup returns None."""
    aioclient_mock.get(
        LINE_PROFILE_URL.format(user_id=USER_ID), exc=aiohttp.ClientError("x")
    )
    assert await async_get_profile_name(hass, TOKEN, USER_ID) is None


async def test_get_group_name_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 200 group summary response returns the groupName."""
    aioclient_mock.get(
        LINE_GROUP_SUMMARY_URL.format(group_id=GROUP_ID),
        json={"groupName": "Family"},
    )
    assert await async_get_group_name(hass, TOKEN, GROUP_ID) == "Family"


async def test_get_group_name_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-200 group summary response returns None."""
    aioclient_mock.get(LINE_GROUP_SUMMARY_URL.format(group_id=GROUP_ID), status=403)
    assert await async_get_group_name(hass, TOKEN, GROUP_ID) is None


async def test_get_group_name_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A client error during group lookup returns None."""
    aioclient_mock.get(
        LINE_GROUP_SUMMARY_URL.format(group_id=GROUP_ID),
        exc=aiohttp.ClientError("x"),
    )
    assert await async_get_group_name(hass, TOKEN, GROUP_ID) is None

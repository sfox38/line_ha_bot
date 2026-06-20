"""Shared fixtures for the LINE Bot integration tests."""

from __future__ import annotations

import hashlib
import hmac
import base64
import json

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant

from custom_components.line_ha_bot.const import (
    CONF_CHANNEL_ACCESS_TOKEN,
    CONF_CHANNEL_SECRET,
    DOMAIN,
    LINE_QUOTA_CONSUMPTION_URL,
    LINE_QUOTA_URL,
    RECIPIENTS_KEY,
)

# Realistic-looking LINE IDs. Users start with "U", groups with "C".
USER_ID = "U" + "0123456789abcdef0123456789abcdef"
USER_ID_2 = "U" + "fedcba9876543210fedcba9876543210"
GROUP_ID = "C" + "0123456789abcdef0123456789abcdef"

TOKEN = "test-channel-access-token"
SECRET = "test-channel-secret"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration in every test."""
    yield


@pytest.fixture
def recipients() -> dict:
    """Return a recipients dict with one user and one group."""
    return {
        "david": {
            "user_id": USER_ID,
            "display_name": "David",
            "friendly_name": "David 🤓",
            "type": "user",
        },
        "family": {
            "user_id": GROUP_ID,
            "display_name": "Family",
            "friendly_name": "Family",
            "type": "group",
        },
    }


@pytest.fixture
def mock_config_entry(recipients) -> MockConfigEntry:
    """Return a config entry with credentials and two recipients."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="LINE Bot",
        data={
            CONF_CHANNEL_ACCESS_TOKEN: TOKEN,
            CONF_CHANNEL_SECRET: SECRET,
            RECIPIENTS_KEY: recipients,
        },
        entry_id="line_bot_test_entry",
    )


def mock_quota_endpoints(
    aioclient_mock: AiohttpClientMocker,
    *,
    limit: int | None = 500,
    quota_type: str = "limited",
    consumption: int = 42,
) -> None:
    """Register the LINE quota + consumption endpoints on the aioclient mock."""
    quota_payload: dict = {"type": quota_type}
    if limit is not None:
        quota_payload["value"] = limit
    aioclient_mock.get(LINE_QUOTA_URL, json=quota_payload)
    aioclient_mock.get(
        LINE_QUOTA_CONSUMPTION_URL, json={"totalUsage": consumption}
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> MockConfigEntry:
    """Set up the integration with the quota endpoints mocked."""
    mock_quota_endpoints(aioclient_mock)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


def sign(secret: str, body: bytes) -> str:
    """Return the LINE X-Line-Signature value for a body."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def webhook_body(events: list[dict], *, destination: str = "Udest") -> bytes:
    """Serialise a webhook payload to the exact bytes LINE would send."""
    return json.dumps({"destination": destination, "events": events}).encode("utf-8")

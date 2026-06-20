"""Tests for the quota sensor platform."""

from __future__ import annotations

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.line_ha_bot.const import (
    CONF_CHANNEL_ACCESS_TOKEN,
    CONF_CHANNEL_SECRET,
    DOMAIN,
    LINE_QUOTA_CONSUMPTION_URL,
    LINE_QUOTA_URL,
    RECIPIENTS_KEY,
)
from custom_components.line_ha_bot.sensor import (
    LineQuotaConsumptionSensor,
    LineQuotaCoordinator,
    LineQuotaLimitSensor,
)

from .conftest import SECRET, TOKEN, mock_quota_endpoints

LIMIT_SENSOR = "sensor.line_ha_bot_monthly_message_limit"
CONSUMPTION_SENSOR = "sensor.line_ha_bot_monthly_message_consumption"


async def test_quota_sensors_created(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Both quota sensors are created and report their fetched values."""
    limit = hass.states.get(LIMIT_SENSOR)
    consumption = hass.states.get(CONSUMPTION_SENSOR)

    assert limit is not None
    assert limit.state == "500"
    assert limit.attributes["plan_type"] == "limited"

    assert consumption is not None
    assert consumption.state == "42"
    assert consumption.attributes["remaining"] == 458


async def test_unlimited_plan_reports_no_limit(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A plan with no limit reports None for the limit and remaining."""
    mock_quota_endpoints(
        aioclient_mock, limit=None, quota_type="none", consumption=10
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHANNEL_ACCESS_TOKEN: TOKEN,
            CONF_CHANNEL_SECRET: SECRET,
            RECIPIENTS_KEY: {},
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    limit = hass.states.get(LIMIT_SENSOR)
    consumption = hass.states.get(CONSUMPTION_SENSOR)
    assert limit.state in ("unknown", "unavailable")
    assert limit.attributes["plan_type"] == "none"
    assert consumption.state == "10"
    assert consumption.attributes["remaining"] is None


def _make_coordinator(hass: HomeAssistant) -> LineQuotaCoordinator:
    """Build a coordinator backed by a config entry added to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHANNEL_ACCESS_TOKEN: TOKEN,
            CONF_CHANNEL_SECRET: SECRET,
            RECIPIENTS_KEY: {},
        },
    )
    entry.add_to_hass(hass)
    return LineQuotaCoordinator(hass, entry)


async def test_coordinator_raises_update_failed_on_non_200(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-200 quota response raises UpdateFailed."""
    aioclient_mock.get(LINE_QUOTA_URL, status=500)
    aioclient_mock.get(LINE_QUOTA_CONSUMPTION_URL, json={"totalUsage": 0})

    coordinator = _make_coordinator(hass)
    with pytest.raises(UpdateFailed, match="HTTP 500"):
        await coordinator._async_update_data()


async def test_coordinator_raises_update_failed_on_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A client error during the fetch raises UpdateFailed."""
    aioclient_mock.get(LINE_QUOTA_URL, exc=aiohttp.ClientError("boom"))
    aioclient_mock.get(LINE_QUOTA_CONSUMPTION_URL, json={"totalUsage": 0})

    coordinator = _make_coordinator(hass)
    with pytest.raises(UpdateFailed, match="fetch error"):
        await coordinator._async_update_data()


async def test_sensors_report_none_when_coordinator_has_no_data(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Before the first successful fetch the sensors report no value."""
    mock_config_entry.add_to_hass(hass)
    coordinator = LineQuotaCoordinator(hass, mock_config_entry)
    # coordinator.data is None until the first refresh succeeds.
    limit = LineQuotaLimitSensor(coordinator, mock_config_entry)
    consumption = LineQuotaConsumptionSensor(coordinator, mock_config_entry)

    assert limit.native_value is None
    assert limit.extra_state_attributes == {}
    assert consumption.native_value is None
    assert consumption.extra_state_attributes == {}

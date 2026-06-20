"""Tests for the message-building helpers in __init__.py.

_build_messages and _build_action are pure functions that translate validated
service-call data into the LINE messages array, so they are tested directly.
"""

from __future__ import annotations

import pytest

from homeassistant.exceptions import ServiceValidationError

from custom_components.line_ha_bot import _build_action, _build_messages


# --- _build_action ---------------------------------------------------------


def test_build_action_message_default() -> None:
    """A button with no action defaults to a message action."""
    action = _build_action({"label": "Hi", "data": "hello"})
    assert action == {"type": "message", "label": "Hi", "text": "hello"}


def test_build_action_uri() -> None:
    """A uri action maps data to the uri field."""
    action = _build_action(
        {"label": "Open", "action": "uri", "data": "https://example.com"}
    )
    assert action == {
        "type": "uri",
        "label": "Open",
        "uri": "https://example.com",
    }


def test_build_action_postback_with_display_text() -> None:
    """A postback action carries data and an explicit display_text."""
    action = _build_action(
        {
            "label": "Lock",
            "action": "postback",
            "data": "lock=true",
            "display_text": "Locking",
        }
    )
    assert action == {
        "type": "postback",
        "label": "Lock",
        "data": "lock=true",
        "displayText": "Locking",
    }


def test_build_action_postback_defaults_display_text_to_label() -> None:
    """display_text defaults to the label when omitted."""
    action = _build_action({"label": "Lock", "action": "postback", "data": "x"})
    assert action["displayText"] == "Lock"


# --- _build_messages: text / title -----------------------------------------


def test_build_messages_text_only() -> None:
    """A bare message produces a single text message object."""
    messages = _build_messages({"message": "hello"})
    assert messages == [{"type": "text", "text": "hello"}]


def test_build_messages_title_prepended() -> None:
    """A title is prepended to the message on its own line."""
    messages = _build_messages({"message": "body", "title": "Alert"})
    assert messages == [{"type": "text", "text": "Alert\nbody"}]


def test_build_messages_no_content_raises() -> None:
    """Empty data raises ServiceValidationError."""
    with pytest.raises(ServiceValidationError, match="No message content"):
        _build_messages({})


# --- _build_messages: media ------------------------------------------------


def test_build_messages_image() -> None:
    """An image_url adds an image message after the text."""
    messages = _build_messages(
        {"message": "look", "image_url": "https://x/y.jpg"}
    )
    assert messages[0]["type"] == "text"
    assert messages[1] == {
        "type": "image",
        "originalContentUrl": "https://x/y.jpg",
        "previewImageUrl": "https://x/y.jpg",
    }


def test_build_messages_image_takes_priority_over_location() -> None:
    """When both image and location are given, image wins."""
    messages = _build_messages(
        {
            "image_url": "https://x/y.jpg",
            "location_latitude": 1.0,
            "location_longitude": 2.0,
        }
    )
    assert len(messages) == 1
    assert messages[0]["type"] == "image"


def test_build_messages_location_full() -> None:
    """A location message uses provided title and address."""
    messages = _build_messages(
        {
            "location_title": "Home",
            "location_address": "123 Main St",
            "location_latitude": 13.75,
            "location_longitude": 100.5,
        }
    )
    assert messages == [
        {
            "type": "location",
            "title": "Home",
            "address": "123 Main St",
            "latitude": 13.75,
            "longitude": 100.5,
        }
    ]


def test_build_messages_location_defaults() -> None:
    """Location title defaults and address falls back to empty string."""
    messages = _build_messages(
        {"location_latitude": 1.0, "location_longitude": 2.0}
    )
    assert messages[0]["title"] == "Location"
    assert messages[0]["address"] == ""


def test_build_messages_audio() -> None:
    """Audio with a duration produces an audio message."""
    messages = _build_messages(
        {"audio_url": "https://x/a.m4a", "audio_duration": 3000}
    )
    assert messages == [
        {
            "type": "audio",
            "originalContentUrl": "https://x/a.m4a",
            "duration": 3000,
        }
    ]


def test_build_messages_audio_without_duration_raises() -> None:
    """Audio without a duration raises ServiceValidationError."""
    with pytest.raises(ServiceValidationError, match="audio_duration"):
        _build_messages({"audio_url": "https://x/a.m4a"})


def test_build_messages_video() -> None:
    """Video uses the preview url when provided."""
    messages = _build_messages(
        {"video_url": "https://x/v.mp4", "video_preview_url": "https://x/p.jpg"}
    )
    assert messages == [
        {
            "type": "video",
            "originalContentUrl": "https://x/v.mp4",
            "previewImageUrl": "https://x/p.jpg",
        }
    ]


def test_build_messages_video_without_preview() -> None:
    """A missing preview url falls back to an empty string."""
    messages = _build_messages({"video_url": "https://x/v.mp4"})
    assert messages[0]["previewImageUrl"] == ""


def test_build_messages_sticker() -> None:
    """A sticker requires both package and sticker id."""
    messages = _build_messages(
        {"sticker_package_id": "1", "sticker_id": "2"}
    )
    assert messages == [
        {"type": "sticker", "packageId": "1", "stickerId": "2"}
    ]


# --- _build_messages: flex -------------------------------------------------


def test_build_messages_flex_only() -> None:
    """A flex_message produces a flex message object."""
    contents = {"type": "bubble"}
    messages = _build_messages(
        {"flex_message": contents, "flex_alt_text": "alt"}
    )
    assert messages == [
        {"type": "flex", "altText": "alt", "contents": contents}
    ]


def test_build_messages_flex_with_text() -> None:
    """A message alongside flex is sent as a leading text message."""
    messages = _build_messages(
        {"flex_message": {"type": "bubble"}, "message": "hi", "title": "T"}
    )
    assert messages[0] == {"type": "text", "text": "T\nhi"}
    assert messages[1]["type"] == "flex"


def test_build_messages_flex_default_alt_text() -> None:
    """Flex alt text defaults to the standard fallback string."""
    messages = _build_messages({"flex_message": {"type": "bubble"}})
    assert messages[0]["altText"] == "LINE message"


# --- _build_messages: templates --------------------------------------------


def test_build_messages_buttons_template() -> None:
    """A buttons template carries title, thumbnail, and default action."""
    messages = _build_messages(
        {
            "message": "Pick",
            "template_type": "buttons",
            "template_title": "Control",
            "image_url": "https://x/t.jpg",
            "template_default_url": "https://x/card",
            "buttons": [
                {"label": "A", "action": "postback", "data": "a"},
            ],
        }
    )
    msg = messages[0]
    assert msg["type"] == "template"
    template = msg["template"]
    assert template["type"] == "buttons"
    assert template["text"] == "Pick"
    assert template["title"] == "Control"
    assert template["thumbnailImageUrl"] == "https://x/t.jpg"
    assert template["defaultAction"]["uri"] == "https://x/card"
    assert template["actions"][0]["type"] == "postback"


def test_build_messages_buttons_template_zero_buttons_raises() -> None:
    """A buttons template needs at least one button."""
    with pytest.raises(ServiceValidationError, match="between 1 and 4"):
        _build_messages({"template_type": "buttons", "buttons": []})


def test_build_messages_buttons_template_too_many_raises() -> None:
    """A buttons template allows at most four buttons."""
    buttons = [{"label": f"b{i}", "action": "message", "data": "x"} for i in range(5)]
    with pytest.raises(ServiceValidationError, match="between 1 and 4"):
        _build_messages({"template_type": "buttons", "buttons": buttons})


def test_build_messages_confirm_template() -> None:
    """A confirm template requires exactly two buttons."""
    messages = _build_messages(
        {
            "message": "Sure?",
            "template_type": "confirm",
            "buttons": [
                {"label": "Yes", "action": "postback", "data": "y"},
                {"label": "No", "action": "postback", "data": "n"},
            ],
        }
    )
    template = messages[0]["template"]
    assert template["type"] == "confirm"
    assert template["text"] == "Sure?"
    assert len(template["actions"]) == 2


def test_build_messages_confirm_template_wrong_count_raises() -> None:
    """A confirm template with one button raises."""
    with pytest.raises(ServiceValidationError, match="exactly 2 buttons"):
        _build_messages(
            {
                "template_type": "confirm",
                "buttons": [{"label": "Yes", "action": "message", "data": "y"}],
            }
        )


# --- _build_messages: quick replies ----------------------------------------


def test_build_messages_quick_replies_attached_to_last_message() -> None:
    """Quick replies are attached to the final message object."""
    messages = _build_messages(
        {
            "message": "hi",
            "quick_replies": [
                {"label": "Yes", "action": "postback", "data": "y"},
            ],
        }
    )
    quick = messages[-1]["quickReply"]
    assert quick["items"][0]["type"] == "action"
    assert quick["items"][0]["action"]["type"] == "postback"


def test_build_messages_too_many_quick_replies_raises() -> None:
    """More than 13 quick replies raises."""
    qrs = [
        {"label": f"q{i}", "action": "message", "data": "x"} for i in range(14)
    ]
    with pytest.raises(ServiceValidationError, match="maximum of 13"):
        _build_messages({"message": "hi", "quick_replies": qrs})

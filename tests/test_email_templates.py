from unittest.mock import patch
from app.services.email import (
    send_welcome_user_instructions,
    send_feature_update_announcement,
    get_v11_guide_plain_text,
    get_v11_guide_html,
)

def test_v11_guide_contents():
    """Verify that both plain text and HTML guides contain all 7 v1.1 capabilities."""
    plain = get_v11_guide_plain_text()
    html = get_v11_guide_html()

    capabilities = [
        # 1. Standard 7-Day & Flexible Planning
        ("Standard 7-Day & Flexible Planning", "Monday–Sunday", "<=20m"),
        # 2. Smart Calendar & Display Sync
        ("Calendar & Display Sync", "webcal://", "Skylight"),
        # 3. Household Pantry Staples
        ("Pantry Staples", "Salt", "excluded"),
        # 4. Dynamic Serving Sizes
        ("Serving", "stepper", "recalculate"),
        # 5. Supermarket Aisle & Department Ordering
        ("Department", "Produce", "checklist"),
        # 6. Fullscreen Cook Mode
        ("Cook Mode", "Wake Lock", "timer"),
        # 7. Dietary Preference Lock
        ("Lock", "tag", "accidental"),
    ]

    for keywords in capabilities:
        for kw in keywords:
            assert kw.lower() in plain.lower(), f"Keyword '{kw}' missing from plain-text guide"
            assert kw.lower() in html.lower(), f"Keyword '{kw}' missing from HTML guide"

def test_send_welcome_user_instructions():
    """Verify send_welcome_user_instructions constructs subject, recipient, and bodies."""
    with patch("app.services.email.send_email", return_value=True) as mock_send:
        ok = send_welcome_user_instructions(
            to_email="testuser@example.com",
            user_name="Alex Doe",
            household_name="The Doe Household",
            is_originator=True,
        )
        assert ok is True
        assert mock_send.called
        args, _ = mock_send.call_args
        to_email, subject, html_body, text_body = args

        assert to_email == "testuser@example.com"
        assert "The Doe Household" in subject
        assert "Alex Doe" in text_body
        assert "The Doe Household" in text_body
        assert "https://splitbites.tbannon80-hp-mini.stream" in text_body
        assert "Cook Mode" in text_body
        assert "Pantry Staples" in text_body
        assert "Calendar & Display Sync" in text_body
        assert "Cook Mode" in html_body

def test_send_feature_update_announcement():
    """Verify send_feature_update_announcement formats subject, note, and login URL."""
    with patch("app.services.email.send_email", return_value=True) as mock_send:
        ok = send_feature_update_announcement(
            to_email="family@example.com",
            user_name="Sarah",
        )
        assert ok is True
        assert mock_send.called
        args, _ = mock_send.call_args
        to_email, subject, html_body, text_body = args

        assert to_email == "family@example.com"
        assert subject == "SplitBites Update: New 7-Day Planning, Calendar Sync, Cook Mode & More!"
        assert "We've added major new features to your SplitBites kitchen dashboard" in text_body
        assert "https://splitbites.tbannon80-hp-mini.stream" in text_body
        assert "Standard 7-Day & Flexible Planning" in text_body
        assert "Smart Calendar & Display Sync" in text_body
        assert "Household Pantry Staples" in text_body
        assert "Dynamic Serving Sizes" in text_body
        assert "Supermarket Aisle & Department Ordering" in text_body
        assert "Fullscreen Cook Mode" in text_body
        assert "Dietary Preference Lock" in text_body
        assert "https://splitbites.tbannon80-hp-mini.stream" in html_body

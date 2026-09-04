import pytest
from unittest.mock import patch, MagicMock
from app.services.telegram import send_telegram_notification

def test_send_telegram_notification_success():
    """Verify send_telegram_notification properly formats request and dispatches."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = send_telegram_notification("🎉 *New SplitBites Registration*")
        assert result is True
        assert mock_urlopen.called

def test_send_telegram_notification_missing_credentials():
    """Verify function gracefully returns False if credentials missing."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
        result = send_telegram_notification("Test Alert")
        assert result is False

def test_signup_alert_formatting():
    """Verify signup alert message text structure."""
    new_user_name = "Jane Doe"
    new_user_email = "jane.doe@example.com"
    household = "The Doe Family"
    dietary = ["gluten-free", "dairy-free"]
    partner_email = "john.doe@example.com"
    partner_name = "John Doe"

    diet_str = ", ".join(dietary)
    partner_str = f"\n💍 *Invited Partner:* {partner_name} (`{partner_email}`)"
    
    tg_text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎉 *New SplitBites Registration*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *User:* {new_user_name}\n"
        f"📧 *Email:* `{new_user_email}`\n"
        f"🏠 *Household:* {household}\n"
        f"🥗 *Dietary:* {diet_str}"
        f"{partner_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    assert "🎉 *New SplitBites Registration*" in tg_text
    assert "Jane Doe" in tg_text
    assert "jane.doe@example.com" in tg_text
    assert "The Doe Family" in tg_text
    assert "gluten-free, dairy-free" in tg_text
    assert "John Doe" in tg_text

def test_member_invite_accepted_formatting():
    """Verify accepted invite message text structure."""
    member_name = "Samantha Bannon"
    member_email = "sabannon13@gmail.com"
    household = "The Bannon Family"

    tg_text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 *SplitBites Invitation Accepted*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *User:* {member_name}\n"
        f"📧 *Email:* `{member_email}`\n"
        f"🏠 *Household:* {household}\n"
        f"🔑 *Status:* Joined Household as Member\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    assert "👋 *SplitBites Invitation Accepted*" in tg_text
    assert "Samantha Bannon" in tg_text
    assert "The Bannon Family" in tg_text

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "timothy.bannon@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "mjrxdmqgorxmglqs")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "timothy.bannon@gmail.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "SplitBites")
APP_DOMAIN = os.getenv("APP_DOMAIN", "https://splitbites.tbannon80-hp-mini.stream")

def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Sends an email using configured SMTP credentials with STARTTLS."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[Email Warning] SMTP credentials not set. Would have sent '{subject}' to {to_email}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=12)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"[Email Success] Sent '{subject}' to {to_email}")
        return True
    except Exception as e:
        print(f"[Email Error] Failed to send email to {to_email}: {e}")
        return False

def send_spouse_invitation(to_email: str, spouse_name: str, inviter_name: str, household_name: str, invite_token: str) -> bool:
    """Dispatches a welcome invitation email to a spouse or family member."""
    invite_url = f"{APP_DOMAIN}/?invite={invite_token}"
    greeting = f"Hi {spouse_name}," if spouse_name else "Hello,"
    inviter_display = inviter_name or "Your family member"

    subject = f"You're invited to join {household_name} on SplitBites!"
    
    text_body = f"""
{greeting}

{inviter_display} has invited you to join {household_name} on SplitBites!

Together, you can plan weekly meals, customize recipes, and collaborate on a live in-store multi-store grocery checklist (Aldi, Walmart, Meijer, and Amazon).

Click the link below to accept the invitation and choose your password:
{invite_url}

If you did not expect this invitation, you can safely disregard this message.

Best,
The SplitBites Team
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #090d16; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    .logo {{ font-size: 28px; font-weight: 800; color: #10b981; margin-bottom: 20px; }}
    h1 {{ font-size: 20px; color: #f8fafc; margin-top: 0; }}
    p {{ font-size: 14px; line-height: 1.6; color: #94a3b8; }}
    .btn {{ display: inline-block; background-color: #059669; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; margin-top: 20px; margin-bottom: 20px; }}
    .footer {{ font-size: 11px; color: #64748b; margin-top: 24px; border-top: 1px solid #1e293b; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🥑 SplitBites</div>
    <h1>You're invited to {household_name}!</h1>
    <p>{greeting}</p>
    <p><strong style="color: #f8fafc;">{inviter_display}</strong> has invited you to join the <strong>{household_name}</strong> meal planner and shared grocery list.</p>
    <p>With SplitBites, you can share weekly meal schedules, customize recipes, and collaborate on a live, checkable grocery basket across Aldi, Walmart, Meijer, and Amazon.</p>
    <div style="text-align: center;">
      <a href="{invite_url}" class="btn">Accept Invitation & Set Password</a>
    </div>
    <p style="font-size: 12px;">Or copy and paste this link into your browser:<br><a href="{invite_url}" style="color: #34d399; word-break: break-all;">{invite_url}</a></p>
    <div class="footer">
      Sent by SplitBites Homelab. If you were not expecting this invitation, you can safely ignore this email.
    </div>
  </div>
</body>
</html>
"""
    return send_email(to_email, subject, html_body, text_body)

def send_password_reset(to_email: str, user_name: str, reset_token: str) -> bool:
    """Dispatches a password reset email."""
    reset_url = f"{APP_DOMAIN}/?reset={reset_token}"
    greeting = f"Hi {user_name}," if user_name else "Hello,"

    subject = "Reset Your SplitBites Password"
    text_body = f"""
{greeting}

We received a request to reset the password for your SplitBites account ({to_email}).

Click the link below to set a new password:
{reset_url}

This link is valid for 1 hour. If you did not request this, you can safely ignore this email.

Best,
The SplitBites Team
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #090d16; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    .logo {{ font-size: 28px; font-weight: 800; color: #10b981; margin-bottom: 20px; }}
    h1 {{ font-size: 20px; color: #f8fafc; margin-top: 0; }}
    p {{ font-size: 14px; line-height: 1.6; color: #94a3b8; }}
    .btn {{ display: inline-block; background-color: #059669; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; margin-top: 20px; margin-bottom: 20px; }}
    .footer {{ font-size: 11px; color: #64748b; margin-top: 24px; border-top: 1px solid #1e293b; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🥑 SplitBites</div>
    <h1>Password Reset Request</h1>
    <p>{greeting}</p>
    <p>We received a request to reset the password for your SplitBites account (<strong>{to_email}</strong>).</p>
    <div style="text-align: center;">
      <a href="{reset_url}" class="btn">Reset Your Password</a>
    </div>
    <p style="font-size: 12px;">This link will expire in 1 hour.<br>Link: <a href="{reset_url}" style="color: #34d399; word-break: break-all;">{reset_url}</a></p>
    <div class="footer">
      If you did not request a password reset, you can safely ignore this email.
    </div>
  </div>
</body>
</html>
"""
    return send_email(to_email, subject, html_body, text_body)

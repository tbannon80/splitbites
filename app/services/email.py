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

def get_v11_guide_plain_text() -> str:
    """Returns formatted plain-text instructions covering all SplitBites v1.1 capabilities."""
    return """1. Standard 7-Day & Flexible Planning (Step 2)
   - Full Monday–Sunday Schedules: Plan a complete 7-day week of dinners or customize to any subset of days.
   - Dynamic Day Control: Add or subtract schedule days anytime using the [+] and [-] buttons.
   - Smart Busy-Night Routing: Quick <=20m recipes automatically route to your designated busy family nights.
   - Swap & Shuffle: Click "🔄 Swap" on any meal for a semantic alternative, or "🔀 Shuffle" unlocked days.

2. Smart Calendar & Display Sync
   - Click "📅 Sync to Calendar" on the schedule bar.
   - One-Click Live Subscription: Subscribe via webcal:// or https:// ICS feeds.
   - Universal Display Support: Live meals automatically appear and sync with Apple Calendar, Google Calendar, Outlook, and kitchen smart displays (like Skylight Calendar).

3. Household Pantry Staples
   - Click the "🧂 Pantry Staples" button on your grocery list.
   - Track household basics you always keep in stock (e.g., Salt, Black Pepper, Olive Oil, Flour).
   - Ingredients in your pantry are automatically excluded from store grocery lists so you never re-buy staples.

4. Dynamic Serving Sizes
   - Adjust servings directly on the schedule for any day using the [-] / [+] stepper controls (1–12 portions).
   - Recipe ingredients and supermarket grocery purchase quantities automatically recalculate in real-time.

5. Supermarket Aisle & Department Ordering
   - Shopping lists are organized by store department: Produce 🥬, Meat & Seafood 🥩, Dairy & Eggs 🧀, Pantry & Dry Goods 🥫, Bakery 🍞, and Frozen ❄️.
   - Live mobile checklist with persistent checkmarks that stay checked as you navigate store aisles.
   - Filter with "Hide Completed" or export with department headers via "📋 Copy All".

6. Fullscreen Cook Mode
   - Tap "👨‍🍳 Cook Mode" on any recipe card to open a kitchen-optimized, hands-free view.
   - Screen Wake Lock keeps your mobile or tablet display awake while your hands are busy cooking.
   - Interactive step-by-step progress tracking with one-tap countdown timers for simmering and baking steps.
   - Personal kitchen notes & 5-star ratings saved specifically to your household.

7. Dietary Preference Lock
   - In Step 1 (Family Dietary Preferences), toggle the lock button (🔒 / 🔓) next to your dietary tags.
   - When locked (🔒), tag pills are guarded against accidental taps while scrolling on mobile devices.
   - Unlock (🔓) anytime to adjust your household restrictions (gluten-free, dairy-free, high-protein, etc.).

8. Multi-Store Price Savings & Family Collaboration
   - Price comparison across Aldi, Walmart, Meijer, and Amazon for optimal split-basket savings.
   - Switch to the "🍲 Recipes" tab to import online recipes via URL from your favorite cooking websites.
   - Invite your spouse or family members from the "👨‍👩‍👧‍👦 Family" tab to plan and shop together live."""


def get_v11_guide_html() -> str:
    """Returns formatted HTML markup covering all SplitBites v1.1 capabilities."""
    return """    <h2><span class="step-num">1</span> Standard 7-Day & Flexible Planning</h2>
    <p>Full Monday–Sunday schedules tailored to your family's routine:</p>
    <ul>
      <li><strong style="color: #f8fafc;">Full 7-Day Week:</strong> Build complete Monday–Sunday dinner schedules with one click.</li>
      <li><strong style="color: #f8fafc;">Add / Subtract Days:</strong> Dynamically add or remove days to fit your family's travel or dining plans.</li>
      <li><strong style="color: #f8fafc;">Smart Busy-Night Routing:</strong> Quick &le;20m (<=20m) recipes automatically route to your designated busy weeknights.</li>
      <li><strong style="color: #f8fafc;">Swap & Shuffle:</strong> Click <em>🔄 Swap</em> on any day for smart alternative recipes, or <em>🔀 Shuffle</em> unlocked meals.</li>
    </ul>

    <h2><span class="step-num">2</span> Smart Calendar & Display Sync</h2>
    <ul>
      <li><strong style="color: #f8fafc;">One-Click Subscription:</strong> Click <em>📅 Sync to Calendar</em> on the schedule bar for a live <code>webcal://</code> or <code>https://</code> ICS feed.</li>
      <li><strong style="color: #f8fafc;">Universal Display Sync:</strong> Syncs live with Apple Calendar, Google Calendar, Outlook, and kitchen smart displays (like Skylight Calendar).</li>
    </ul>

    <h2><span class="step-num">3</span> Household Pantry Staples</h2>
    <ul>
      <li><strong style="color: #f8fafc;">Track Basics:</strong> Click the <em>🧂 Pantry Staples</em> button to manage pantry essentials (Salt, Black Pepper, Olive Oil, Flour).</li>
      <li><strong style="color: #f8fafc;">Automatic Exclusion:</strong> Ingredients in your pantry are automatically excluded from store grocery purchase lists so you never overbuy.</li>
    </ul>

    <h2><span class="step-num">4</span> Dynamic Serving Sizes</h2>
    <ul>
      <li><strong style="color: #f8fafc;">Serving Steppers:</strong> Adjust portions directly on any day using the <strong>[-]</strong> / <strong>[+]</strong> steppers (1–12 portions).</li>
      <li><strong style="color: #f8fafc;">Automatic Recalculation:</strong> Ingredient quantities and supermarket purchasing units automatically recalculate to match your family's exact headcount.</li>
    </ul>

    <h2><span class="step-num">5</span> Supermarket Aisle & Department Ordering</h2>
    <ul>
      <li><strong style="color: #f8fafc;">Department Grouping:</strong> Grocery lists are categorized by store department (Produce 🥬, Meat & Seafood 🥩, Dairy & Eggs 🧀, Pantry & Dry Goods 🥫, Bakery 🍞, Frozen ❄️).</li>
      <li><strong style="color: #f8fafc;">Live Mobile Checklist:</strong> Check off items as you walk store aisles; checkmarks persist across browser refreshes so you never lose your place.</li>
      <li><strong style="color: #f8fafc;">Export Helpers:</strong> Easily export aisle-ordered lists to Apple Notes or Google Keep with <em>📋 Copy All</em>.</li>
    </ul>

    <h2><span class="step-num">6</span> Fullscreen Cook Mode</h2>
    <ul>
      <li><strong style="color: #f8fafc;">Hands-Free Kitchen View:</strong> Tap <em>👨‍🍳 Cook Mode</em> on any recipe for large, readable step-by-step instructions.</li>
      <li><strong style="color: #f8fafc;">Screen Wake Lock:</strong> Prevents your mobile or tablet screen from dimming or sleeping while cooking.</li>
      <li><strong style="color: #f8fafc;">Interactive Timers:</strong> Tap inline countdown timers for boiling, simmering, or baking steps.</li>
      <li><strong style="color: #f8fafc;">Personal Notes & Ratings:</strong> Save household recipe notes, tips, and 1–5 star ratings.</li>
    </ul>

    <h2><span class="step-num">7</span> Dietary Preference Lock</h2>
    <ul>
      <li><strong style="color: #f8fafc;">Accidental Tap Protection:</strong> Click the compact lock toggle (<strong>🔒</strong> / <strong>🔓</strong>) next to dietary tags in Step 1.</li>
      <li><strong style="color: #f8fafc;">Protected Browsing:</strong> When locked, tag pills ignore accidental taps while scrolling; unlock anytime to edit household restrictions.</li>
    </ul>

    <h2><span class="step-num">8</span> Multi-Store Price Savings & Family Collaboration</h2>
    <ul>
      <li><strong style="color: #f8fafc;">Store Arbitrage:</strong> Price analysis across Aldi, Walmart, Meijer, and Amazon for optimal multi-store split-basket savings.</li>
      <li><strong style="color: #f8fafc;">Web Recipe Import:</strong> Paste recipe URLs in the <em>🍲 Recipes</em> tab to auto-extract ingredients and instructions.</li>
      <li><strong style="color: #f8fafc;">Family Sharing:</strong> Invite family members from the <em>👨‍👩‍👧‍👦 Family</em> tab to plan and shop together in real time.</li>
    </ul>"""


def send_welcome_user_instructions(to_email: str, user_name: str, household_name: str, is_originator: bool = True) -> bool:
    """Dispatches a detailed end-user onboarding guide with instructions on how to use SplitBites."""
    greeting = f"Hi {user_name}," if user_name else "Hello,"
    role_text = "created" if is_originator else "joined"
    subject = f"Welcome to SplitBites! Your Quick-Start Guide for {household_name}"
    login_url = f"{APP_DOMAIN}"

    guide_text = get_v11_guide_plain_text()
    guide_html = get_v11_guide_html()

    text_body = f"""{greeting}

Welcome to SplitBites! You have successfully {role_text} your kitchen account for {household_name}.

Here is your complete quick-start guide to getting the most out of your kitchen dashboard:

{guide_text}

Sign in anytime to get started:
{login_url}

Happy cooking and happy saving!
The SplitBites Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #090d16; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 620px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    .logo {{ font-size: 28px; font-weight: 800; color: #10b981; margin-bottom: 8px; }}
    h1 {{ font-size: 22px; color: #f8fafc; margin-top: 0; }}
    h2 {{ font-size: 15px; color: #34d399; margin-top: 22px; margin-bottom: 8px; border-bottom: 1px solid #1e293b; padding-bottom: 6px; }}
    p {{ font-size: 13px; line-height: 1.6; color: #94a3b8; margin: 6px 0; }}
    ul {{ font-size: 13px; line-height: 1.6; color: #cbd5e1; padding-left: 18px; margin: 6px 0; }}
    li {{ margin-bottom: 5px; }}
    .btn {{ display: inline-block; background-color: #059669; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; margin-top: 20px; margin-bottom: 20px; }}
    .footer {{ font-size: 11px; color: #64748b; margin-top: 28px; border-top: 1px solid #1e293b; padding-top: 16px; text-align: center; }}
    .step-num {{ display: inline-block; background: #064e3b; color: #34d399; width: 22px; height: 22px; text-align: center; border-radius: 50%; font-size: 11px; font-weight: bold; line-height: 22px; margin-right: 8px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🥑 SplitBites</div>
    <h1>Welcome to SplitBites, {user_name or 'Friend'}!</h1>
    <p>You have successfully {role_text} your kitchen account for <strong>{household_name}</strong>. SplitBites makes weekly meal planning effortless and saves your household money through smart multi-store grocery price arbitrage.</p>
    
    <div style="text-align: center;">
      <a href="{login_url}" class="btn">Open Your Family Kitchen</a>
    </div>

{guide_html}

    <div style="text-align: center; margin-top: 24px;">
      <a href="{login_url}" class="btn">Open Your Family Kitchen</a>
    </div>

    <div class="footer">
      SplitBites Homelab Platform • Log in anytime at <a href="{login_url}" style="color: #34d399;">{login_url}</a>
    </div>
  </div>
</body>
</html>
"""
    return send_email(to_email, subject, html_body, text_body)


def send_feature_update_announcement(to_email: str, user_name: str) -> bool:
    """Dispatches a v1.1 feature update broadcast email to an existing user."""
    greeting = f"Hi {user_name}," if user_name else "Hello,"
    subject = "SplitBites Update: New 7-Day Planning, Calendar Sync, Cook Mode & More!"
    login_url = f"{APP_DOMAIN}"

    guide_text = get_v11_guide_plain_text()
    guide_html = get_v11_guide_html()
    personal_note = "We've added major new features to your SplitBites kitchen dashboard to make weekly meal planning and cooking even easier."

    text_body = f"""{greeting}

{personal_note}

Here is your complete guide to all the newly added features in SplitBites v1.1:

{guide_text}

Log in to your kitchen dashboard to try out the new features:
{login_url}

Happy cooking and happy saving!
The SplitBites Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #090d16; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 620px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    .logo {{ font-size: 28px; font-weight: 800; color: #10b981; margin-bottom: 8px; }}
    .badge {{ display: inline-block; background: #064e3b; color: #34d399; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; margin-bottom: 12px; }}
    h1 {{ font-size: 22px; color: #f8fafc; margin-top: 0; }}
    h2 {{ font-size: 15px; color: #34d399; margin-top: 22px; margin-bottom: 8px; border-bottom: 1px solid #1e293b; padding-bottom: 6px; }}
    p {{ font-size: 13px; line-height: 1.6; color: #94a3b8; margin: 6px 0; }}
    ul {{ font-size: 13px; line-height: 1.6; color: #cbd5e1; padding-left: 18px; margin: 6px 0; }}
    li {{ margin-bottom: 5px; }}
    .btn {{ display: inline-block; background-color: #059669; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; margin-top: 20px; margin-bottom: 20px; }}
    .footer {{ font-size: 11px; color: #64748b; margin-top: 28px; border-top: 1px solid #1e293b; padding-top: 16px; text-align: center; }}
    .step-num {{ display: inline-block; background: #064e3b; color: #34d399; width: 22px; height: 22px; text-align: center; border-radius: 50%; font-size: 11px; font-weight: bold; line-height: 22px; margin-right: 8px; }}
    .note-box {{ background: #064e3b26; border-left: 4px solid #10b981; padding: 14px 18px; border-radius: 0 8px 8px 0; margin: 16px 0; color: #e2e8f0; font-size: 13px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🥑 SplitBites</div>
    <span class="badge">v1.1 FEATURE UPDATE</span>
    <h1>Major New Features in SplitBites!</h1>
    <p>{greeting}</p>
    <div class="note-box">
      <strong>{personal_note}</strong>
    </div>
    
    <div style="text-align: center;">
      <a href="{login_url}" class="btn">Explore Your Kitchen Dashboard</a>
    </div>

{guide_html}

    <div style="text-align: center; margin-top: 24px;">
      <a href="{login_url}" class="btn">Log In to SplitBites</a>
    </div>

    <div class="footer">
      SplitBites Homelab Platform • Log in anytime at <a href="{login_url}" style="color: #34d399;">{login_url}</a>
    </div>
  </div>
</body>
</html>
"""
    return send_email(to_email, subject, html_body, text_body)

def send_system_report(to_email: str, subject: str, markdown_content: str) -> bool:
    """Sends a markdown formatted report as both text and styled HTML to an email."""
    import html as html_lib

    # Convert simple markdown headers and bold to html for clean rendering
    html_lines = []
    for line in markdown_content.split("\n"):
        if line.startswith("# "):
            html_lines.append(f"<h1 style='color: #10b981; font-size: 22px; border-bottom: 2px solid #1e293b; padding-bottom: 8px;'>{html_lib.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2 style='color: #34d399; font-size: 17px; margin-top: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 4px;'>{html_lib.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3 style='color: #f8fafc; font-size: 14px; margin-top: 14px;'>{html_lib.escape(line[4:])}</h3>")
        elif line.startswith("* ") or line.startswith("- "):
            html_lines.append(f"<li style='margin-bottom: 4px; color: #cbd5e1;'>{html_lib.escape(line[2:])}</li>")
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p style='margin: 4px 0; color: #94a3b8;'>{html_lib.escape(line)}</p>")

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace; background-color: #090d16; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 800px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); font-size: 13px; line-height: 1.6; }}
    code {{ background: #020617; padding: 2px 6px; border-radius: 4px; color: #34d399; font-family: monospace; font-size: 12px; }}
    pre {{ background: #020617; padding: 12px; border-radius: 8px; border: 1px solid #1e293b; overflow-x: auto; color: #e2e8f0; font-family: monospace; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    {''.join(html_lines)}
  </div>
</body>
</html>
"""
    return send_email(to_email, subject, html_body, markdown_content)

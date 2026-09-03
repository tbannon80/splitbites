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

def send_welcome_user_instructions(to_email: str, user_name: str, household_name: str, is_originator: bool = True) -> bool:
    """Dispatches a detailed end-user onboarding guide with instructions on how to use SplitBites."""
    greeting = f"Hi {user_name}," if user_name else "Hello,"
    role_text = "created" if is_originator else "joined"
    subject = f"Welcome to SplitBites! Your Quick-Start Guide for {household_name}"
    login_url = f"{APP_DOMAIN}"

    text_body = f"""
{greeting}

Welcome to SplitBites! You have successfully {role_text} your kitchen account for {household_name}.

Here is your complete quick-start guide to getting the most out of SplitBites:

1. FAMILY DIETARY PREFERENCES (Step 1)
   - On the Meal Planner tab, review your household dietary restrictions (e.g. gluten-free, dairy-free, high-protein).
   - Any recipes suggested will automatically respect these household restrictions.
   - Click "Save Preferences" whenever your household needs change.

2. GENERATING & CUSTOMIZING MEAL PLANS (Step 2)
   - Click "⚡ Generate Plan" to automatically build a Monday through Friday dinner schedule.
   - Don't like a specific meal? Click "🔄 Swap" on that day to replace it with another matching recipe.
   - Want to re-roll the entire week? Click "🔀 Shuffle".
   - When you are ready to shop, click "🔒 Lock Plan" to freeze your weekly schedule.

3. MULTI-STORE SPLIT-BASKET GROCERY SAVINGS (Step 3)
   - Click "🛒 Analyze Grocery Pricing" to scan real-time pricing across Aldi, Walmart, Meijer, and Amazon.
   - SplitBites calculates the cheapest combination (buying each ingredient where it costs the least) vs. the single best 1-stop store, showing you exact dollar savings.

4. LIVE IN-STORE MOBILE SHOPPING CHECKLIST
   - Take your phone with you to the store! Each retailer has its own itemized checklist.
   - Check off items as you place them in your cart. Your checkmarks are saved automatically in your phone's browser so you never lose your place.
   - Toggle "Hide Completed" to keep your screen focused on what's left.
   - Click "📋 Copy All" to paste the entire list into Apple Notes or Google Keep.

5. IMPORTING RECIPES FROM THE WEB
   - Found a recipe online? Switch to the "🍲 Upload Custom Recipe" tab.
   - Paste any recipe link (from Allrecipes, Food Network, NYT Cooking, food blogs, etc.) and click "📥 Fetch & Pre-Fill".
   - SplitBites automatically extracts title, cooking times, ingredient measurements, and instructions.
   - Click "Save & Index Recipe" to add it to your family's personal recipe rotation.

6. FAMILY COLLABORATION
   - Head over to the "👨‍👩‍👧‍👦 Family" tab to see who has access to your family kitchen.
   - Click "➕ Invite Spouse / Member" to send an invite so your family can share the exact same meal planner and live grocery list.

Sign in anytime to get started:
{login_url}

Happy cooking and happy saving!
The SplitBites Team
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #090d16; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 600px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    .logo {{ font-size: 28px; font-weight: 800; color: #10b981; margin-bottom: 8px; }}
    h1 {{ font-size: 22px; color: #f8fafc; margin-top: 0; }}
    h2 {{ font-size: 15px; color: #34d399; margin-top: 20px; margin-bottom: 6px; border-bottom: 1px solid #1e293b; padding-bottom: 4px; }}
    p {{ font-size: 13px; line-height: 1.6; color: #94a3b8; margin: 6px 0; }}
    ul {{ font-size: 13px; line-height: 1.6; color: #cbd5e1; padding-left: 18px; margin: 6px 0; }}
    li {{ margin-bottom: 4px; }}
    .btn {{ display: inline-block; background-color: #059669; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; margin-top: 24px; margin-bottom: 20px; }}
    .footer {{ font-size: 11px; color: #64748b; margin-top: 28px; border-top: 1px solid #1e293b; padding-top: 16px; text-align: center; }}
    .step-num {{ display: inline-block; background: #064e3b; color: #34d399; width: 20px; height: 20px; text-align: center; border-radius: 50%; font-size: 11px; font-weight: bold; line-height: 20px; margin-right: 6px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🥑 SplitBites</div>
    <h1>Welcome to SplitBites, {user_name or 'Friend'}!</h1>
    <p>You have successfully {role_text} your kitchen account for <strong>{household_name}</strong>. SplitBites is designed to eliminate meal planning friction and save your family money through smart multi-store grocery price arbitrage.</p>
    
    <div style="text-align: center;">
      <a href="{login_url}" class="btn">Open Your Family Kitchen</a>
    </div>

    <h2><span class="step-num">1</span> Family Dietary Preferences</h2>
    <p>On your dashboard, select your household restrictions (e.g. <code>gluten-free</code>, <code>dairy-free</code>, <code>high-protein</code>, <code>vegetarian</code>). SplitBites ensures all generated meals strictly comply with your family's needs.</p>

    <h2><span class="step-num">2</span> 5-Day Meal Planning (Mon-Fri)</h2>
    <ul>
      <li><strong>Generate:</strong> Click <em>⚡ Generate Plan</em> to create a curated dinner schedule.</li>
      <li><strong>Swap:</strong> Click <em>🔄 Swap</em> on any day to trade that meal for another compliant recipe.</li>
      <li><strong>Shuffle:</strong> Click <em>🔀 Shuffle</em> to randomize unlocked meals.</li>
      <li><strong>Lock:</strong> When satisfied, click <em>🔒 Lock Plan</em> to finalize your schedule for grocery shopping.</li>
    </ul>

    <h2><span class="step-num">3</span> Multi-Store Split-Basket Execution</h2>
    <p>Click <em>🛒 Analyze Grocery Pricing</em> to scan inventory across <strong>Aldi, Walmart, Meijer, and Amazon</strong>. SplitBites highlights:</p>
    <ul>
      <li><strong>Optimal Split Basket:</strong> Buying each item where it's cheapest for maximum savings.</li>
      <li><strong>Best 1-Stop Store:</strong> The lowest-cost single store if you only want to make one trip.</li>
    </ul>

    <h2><span class="step-num">4</span> Live In-Store Mobile Checklist</h2>
    <ul>
      <li>Use your smartphone while walking aisles! Check off items as you drop them in your basket.</li>
      <li>Checkmarks persist across browser refreshes so you never lose track.</li>
      <li>Toggle <em>Hide Completed</em> to only view items remaining in the store.</li>
      <li>Click <em>📋 Copy All</em> to paste your grocery list into Apple Notes or Google Keep.</li>
    </ul>

    <h2><span class="step-num">5</span> Import Online Recipes via URL</h2>
    <p>Paste any online recipe link (Allrecipes, Serious Eats, Food Network, blogs) in the <em>🍲 Upload Custom Recipe</em> tab. SplitBites will automatically parse ingredients, cooking times, steps, and dietary tags.</p>

    <h2><span class="step-num">6</span> Invite Family Members & Spouses</h2>
    <p>Visit the <em>👨‍👩‍👧‍👦 Family</em> tab anytime and click <em>➕ Invite Spouse / Member</em> to send an email invitation so your household can plan and shop together live.</p>

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

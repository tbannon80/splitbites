#!/usr/bin/env python3
import sys
import os
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import argparse

CENTRAL_TZ = ZoneInfo("America/Chicago")

def run_psql(query: str) -> list[str]:
    cmd = [
        "docker", "exec", "-i", "splitbites-postgres",
        "psql", "-U", "postgres", "-d", "splitbites",
        "-t", "-A", "-F", "|", "-c", query
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error querying Postgres: {res.stderr}", file=sys.stderr)
        return []
    lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
    return lines

def format_central_dt(dt_str: str) -> str:
    if not dt_str or dt_str.strip() == "":
        return "Never"
    try:
        # Handles 2026-09-03 19:55:37.67794+00 or ISO strings
        clean_str = dt_str.replace(" ", "T")
        dt = datetime.fromisoformat(clean_str)
        local_dt = dt.astimezone(CENTRAL_TZ)
        now_local = datetime.now(CENTRAL_TZ)

        if local_dt.date() == now_local.date():
            return f"Today at {local_dt.strftime('%-I:%M %p')} {local_dt.strftime('%Z')}"
        elif (now_local.date() - local_dt.date()).days == 1:
            return f"Yesterday at {local_dt.strftime('%-I:%M %p')} {local_dt.strftime('%Z')}"
        else:
            return local_dt.strftime("%b %-d, %Y at %-I:%M %p %Z")
    except Exception as e:
        return dt_str[:19]

def generate_report() -> str:
    now_central = datetime.now(CENTRAL_TZ)
    date_header = now_central.strftime("%A, %B %-d, %Y")

    # 1. Total counts
    summary_query = """
    SELECT 
        (SELECT count(*) FROM households) as total_households,
        (SELECT count(*) FROM users) as total_users,
        (SELECT count(*) FROM users WHERE last_login >= NOW() - INTERVAL '24 hours') as active_24h,
        (SELECT count(*) FROM users WHERE created_at >= NOW() - INTERVAL '24 hours') as new_users_24h,
        (SELECT count(*) FROM meal_plans WHERE created_at >= NOW() - INTERVAL '24 hours') as new_plans_24h,
        (SELECT count(*) FROM household_invitations WHERE status = 'pending') as pending_invites,
        (SELECT count(*) FROM recipes) as total_recipes;
    """
    summary_rows = run_psql(summary_query)
    total_h = total_u = active_24h = new_u_24h = new_plans_24h = pending_inv = total_rec = 0
    if summary_rows:
        parts = summary_rows[0].split("|")
        if len(parts) >= 7:
            total_h = int(parts[0])
            total_u = int(parts[1])
            active_24h = int(parts[2])
            new_u_24h = int(parts[3])
            new_plans_24h = int(parts[4])
            pending_inv = int(parts[5])
            total_rec = int(parts[6])

    # 2. Households and members
    members_query = """
    SELECT 
        h.household_id,
        h.household_name,
        h.created_at as household_created,
        u.user_id,
        u.full_name,
        u.email,
        hm.role,
        u.created_at as user_created,
        COALESCE(u.last_login, u.created_at) as last_login
    FROM households h
    JOIN household_members hm ON h.household_id = hm.household_id
    JOIN users u ON hm.user_id = u.user_id
    ORDER BY h.household_name, hm.role ASC, u.full_name;
    """
    member_rows = run_psql(members_query)

    households = {}
    for r in member_rows:
        parts = r.split("|")
        if len(parts) < 9:
            continue
        hid, hname, hcreated, uid, uname, uemail, urole, ucreated, ulogin = parts[:9]
        if hid not in households:
            households[hid] = {
                "name": hname,
                "created": hcreated,
                "members": [],
                "invites": []
            }
        households[hid]["members"].append({
            "name": uname,
            "email": uemail,
            "role": urole,
            "created": ucreated,
            "last_login": ulogin
        })

    # 3. Pending invitations
    inv_query = """
    SELECT 
        household_id,
        email,
        COALESCE(name, 'Spouse/Family Member') as name,
        created_at,
        expires_at
    FROM household_invitations
    WHERE status = 'pending'
    ORDER BY created_at DESC;
    """
    inv_rows = run_psql(inv_query)
    for r in inv_rows:
        parts = r.split("|")
        if len(parts) >= 5:
            hid, iemail, iname, icreated, iexpires = parts[:5]
            if hid in households:
                households[hid]["invites"].append({
                    "email": iemail,
                    "name": iname,
                    "created": icreated,
                    "expires": iexpires
                })

    # Format Markdown message
    lines = []
    lines.append("📊 *SplitBites Daily Activity Report (5:00 PM CST)*")
    lines.append(f"📅 _{date_header}_")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not households:
        lines.append("\n_No registered families currently in database._")
    else:
        lines.append(f"\n👥 *Registered Families & Members ({total_h} Family, {total_u} Users):*")
        for hid, hdata in households.items():
            h_created_fmt = format_central_dt(hdata["created"])
            lines.append(f"\n🏠 *{hdata['name']}*")
            for m in hdata["members"]:
                login_fmt = format_central_dt(m["last_login"])
                role_label = m["role"].capitalize()
                lines.append(f"  • *{m['name']}* (`{m['email']}`)")
                lines.append(f"    _{role_label}_ • Last Active: {login_fmt}")
            for inv in hdata["invites"]:
                sent_fmt = format_central_dt(inv["created"])
                lines.append(f"  • ⏳ *{inv['name']}* (`{inv['email']}`)")
                lines.append(f"    _Invite Pending_ (Sent: {sent_fmt})")

    lines.append("\n📈 *Activity Summary (Last 24h):*")
    lines.append(f"  • Active Users Today: *{active_24h}*")
    lines.append(f"  • New Registrations: *{new_u_24h}*")
    lines.append(f"  • Pending Invitations: *{pending_inv}*")
    lines.append(f"  • Meal Plans Generated: *{new_plans_24h}*")
    lines.append(f"  • Recipe Catalog Size: *{total_rec} recipes*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)

def send_notification(text: str):
    notify_cmd = "/home/tbannon80/.local/bin/notify_homelab"
    if os.path.exists(notify_cmd):
        res = subprocess.run([notify_cmd, text])
        return res.returncode == 0
    else:
        # Fallback to direct telegram API
        import urllib.request
        import json
        bot_token = "8950289524:AAGBA4jWhlNhdIVGLhD8G0spuATqdPLX2l4"
        chat_id = "8989112896"
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SplitBites Daily Activity Reporter")
    parser.add_argument("--dry-run", action="store_true", help="Print report to stdout without sending to Telegram")
    args = parser.parse_args()

    report = generate_report()
    if args.dry_run:
        print(report)
    else:
        success = send_notification(report)
        if success:
            print("Daily activity report dispatched successfully.")
            sys.exit(0)
        else:
            print("Failed to dispatch daily report.", file=sys.stderr)
            sys.exit(1)

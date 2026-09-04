import asyncio
import os
import time
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.services.email import send_feature_update_announcement

async def main():
    print("=" * 65)
    print("SplitBites v1.1 Feature Update Broadcast Script")
    print("=" * 65)

    include_test_users = os.getenv("INCLUDE_TEST_USERS", "0").lower() in ("1", "true", "yes")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).order_by(User.created_at))
        all_users = result.scalars().all()

    # Filter out synthetic test accounts (@example.com) to respect SMTP rate limits
    users_to_notify = []
    skipped_count = 0
    for u in all_users:
        is_test_email = u.email.endswith("@example.com") or u.email.endswith(".test") or u.email.endswith("@example.org")
        if is_test_email and not include_test_users:
            skipped_count += 1
            continue
        users_to_notify.append(u)

    print(f"Total registered users in database: {len(all_users)}")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} synthetic test accounts (@example.com).")
    print(f"Dispatching broadcast to {len(users_to_notify)} registered family member(s)...\n")

    success_count = 0
    failure_count = 0

    for idx, user in enumerate(users_to_notify, start=1):
        name = user.full_name or "Family Member"
        email = user.email
        print(f"[{idx}/{len(users_to_notify)}] Dispatching feature update to {name} <{email}>...")

        ok = send_feature_update_announcement(to_email=email, user_name=name)
        if ok:
            success_count += 1
            print(f" -> [SUCCESS] Successfully delivered to {email}")
        else:
            failure_count += 1
            print(f" -> [FAILED] Delivery failed for {email}")

        if idx < len(users_to_notify):
            print(" -> Sleeping 1.5s to respect SMTP rate limits...")
            time.sleep(1.5)

    print("\n" + "=" * 65)
    print(f"Broadcast Complete! Delivered: {success_count} | Failed: {failure_count}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())

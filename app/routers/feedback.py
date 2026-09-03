import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.schemas.feedback import FeedbackCreateRequest
from app.services.telegram import send_telegram_notification
from app.services.auth import decode_access_token
from app.models import User, Household, HouseholdMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/")
async def submit_feedback(
    payload: FeedbackCreateRequest,
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    sender_name = payload.user_name or "Anonymous Family Member"
    sender_email = payload.user_email or "Not Provided"
    household_name = payload.household_name or "Unknown Household"

    # If auth token provided, resolve user details
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif x_auth_token:
        token = x_auth_token

    if token:
        try:
            token_data = decode_access_token(token)
            if token_data and "sub" in token_data:
                user_res = await db.execute(select(User).where(User.user_id == UUID(token_data["sub"])))
                user = user_res.scalar_one_or_none()
                if user:
                    sender_name = user.full_name or sender_name
                    sender_email = user.email or sender_email
                if "hid" in token_data:
                    h_res = await db.execute(select(Household).where(Household.household_id == UUID(token_data["hid"])))
                    h = h_res.scalar_one_or_none()
                    if h:
                        household_name = h.household_name
        except Exception as auth_err:
            logger.debug(f"Auth header resolution error in feedback: {auth_err}")

    # Map category emoji & title
    category_map = {
        "bug": "🐞 *Bug Report*",
        "feature": "💡 *Feature Suggestion*",
        "feedback": "💬 *General Feedback*"
    }
    cat_header = category_map.get(payload.category.lower(), f"📝 *{payload.category.capitalize()}*")

    telegram_msg = (
        f"{cat_header}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *From:* {sender_name} (`{sender_email}`)\n"
        f"🏠 *Family:* {household_name}\n"
    )
    if payload.subject:
        telegram_msg += f"📌 *Subject:* {payload.subject.strip()}\n"
    if payload.page_url:
        telegram_msg += f"🔗 *Page:* {payload.page_url}\n"

    telegram_msg += f"\n📝 *Details:*\n{payload.message.strip()}\n"

    # Send telegram notification
    sent = send_telegram_notification(telegram_msg)

    return {
        "status": "success",
        "dispatched_to_telegram": sent,
        "message": "Thank you! Your feedback has been sent directly to Tim."
    }

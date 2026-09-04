from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID
import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database.session import AsyncSessionLocal
from app.models import User, Household, HouseholdMember, HouseholdInvitation, DietaryPreference, HouseholdDietaryRestriction, seed_default_pantry_staples
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    InviteMemberRequest,
    RegisterInvitedRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    AuthResponse,
    UserProfileResponse,
    HouseholdProfileResponse,
)
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    generate_random_token,
)
from app.services.email import send_spouse_invitation, send_password_reset, send_welcome_user_instructions

router = APIRouter(prefix="/api/auth", tags=["auth"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user_and_household(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    tok = None
    if authorization and authorization.startswith("Bearer "):
        tok = authorization.split(" ")[1]
    elif x_auth_token:
        tok = x_auth_token
    elif token:
        tok = token

    if not tok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required.")

    payload = decode_access_token(tok)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")

    user_id = payload["sub"]
    user_stmt = select(User).where(User.user_id == UUID(user_id))
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    # Find household
    member_stmt = (
        select(Household)
        .join(HouseholdMember, Household.household_id == HouseholdMember.household_id)
        .options(selectinload(Household.dietary_preferences))
        .where(HouseholdMember.user_id == user.user_id)
    )
    h_res = await db.execute(member_stmt)
    household = h_res.scalar_one_or_none()

    if not household:
        # Fallback create a household if missing
        household = Household(household_name=f"{user.full_name or 'My'} Family", calendar_feed_token=secrets.token_urlsafe(32))
        db.add(household)
        await db.flush()
        db.add(HouseholdMember(household_id=household.household_id, user_id=user.user_id, role="admin"))
        await seed_default_pantry_staples(household.household_id, db)
        await db.commit()
        h_res = await db.execute(member_stmt)
        household = h_res.scalar_one_or_none()

    # Update last_login if missing or older than 15 minutes
    now = datetime.now(timezone.utc)
    if user.last_login is None or (now - user.last_login).total_seconds() > 900:
        user.last_login = now
        await db.commit()

    return user, household

@router.post("/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if payload.confirm_password is not None and payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match. Please re-enter your password.")
    if not payload.household_name.strip():
        raise HTTPException(status_code=400, detail="Family/Household name is required.")

    # Check if email exists
    exist_stmt = select(User).where(User.email == clean_email)
    exist_res = await db.execute(exist_stmt)
    if exist_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in.")

    # 1. Create Household
    new_household = Household(
        household_name=payload.household_name.strip(),
        calendar_feed_token=secrets.token_urlsafe(32),
        busy_days=payload.busy_days if payload.busy_days is not None else ["Tuesday", "Thursday"],
        busy_max_prep_minutes=payload.busy_max_prep_minutes if payload.busy_max_prep_minutes is not None else 20
    )
    db.add(new_household)
    await db.flush()
    await seed_default_pantry_staples(new_household.household_id, db)

    # Link dietary preferences if provided
    if payload.dietary_preferences:
        for tag in payload.dietary_preferences:
            clean_tag = tag.strip().lower()
            if not clean_tag:
                continue
            pref_stmt = select(DietaryPreference).where(DietaryPreference.preference_name == clean_tag)
            pref_res = await db.execute(pref_stmt)
            pref = pref_res.scalar_one_or_none()
            if not pref:
                pref = DietaryPreference(preference_name=clean_tag)
                db.add(pref)
                await db.flush()
            
            await db.execute(
                text("INSERT INTO household_dietary_restrictions (household_id, preference_id) VALUES (:hid, :pid) ON CONFLICT DO NOTHING"),
                {"hid": new_household.household_id, "pid": pref.preference_id}
            )

    # 2. Create User
    pwd_hash = hash_password(payload.password)
    new_user = User(
        email=clean_email,
        password_hash=pwd_hash,
        full_name=payload.full_name.strip() if payload.full_name else clean_email.split("@")[0].capitalize(),
        last_login=datetime.now(timezone.utc)
    )
    db.add(new_user)
    await db.flush()

    # 3. Link as Admin
    member = HouseholdMember(
        household_id=new_household.household_id,
        user_id=new_user.user_id,
        role="admin"
    )
    db.add(member)
    await db.flush()

    # 4. Seed initial baseline recipes into household's recipe book
    await db.execute(
        text("""
            INSERT INTO household_recipes (household_id, recipe_id)
            SELECT :hid, recipe_id FROM recipes WHERE creator_id IS NULL
            ON CONFLICT DO NOTHING
        """),
        {"hid": new_household.household_id}
    )

    # 5. Optional Spouse Invitation
    if payload.spouse_email and payload.spouse_email.strip():
        spouse_clean = payload.spouse_email.strip().lower()
        invite_token = generate_random_token()
        invitation = HouseholdInvitation(
            household_id=new_household.household_id,
            email=spouse_clean,
            name=payload.spouse_name.strip() if payload.spouse_name else None,
            token=invite_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        )
        db.add(invitation)
        await db.flush()

        # Send welcome email asynchronously
        send_spouse_invitation(
            to_email=spouse_clean,
            spouse_name=payload.spouse_name or "",
            inviter_name=new_user.full_name or "Your family member",
            household_name=new_household.household_name,
            invite_token=invite_token
        )

    await db.commit()

    # Dispatch detailed onboarding instructions to the registered originator
    send_welcome_user_instructions(
        to_email=new_user.email,
        user_name=new_user.full_name or "Friend",
        household_name=new_household.household_name,
        is_originator=True
    )

    # Fetch fresh household with preferences
    h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == new_household.household_id)
    h_res = await db.execute(h_stmt)
    full_household = h_res.scalar_one()

    token = create_access_token({"sub": str(new_user.user_id), "email": new_user.email, "hid": str(full_household.household_id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": str(new_user.user_id),
            "full_name": new_user.full_name,
            "email": new_user.email
        },
        "household": {
            "household_id": str(full_household.household_id),
            "household_name": full_household.household_name,
            "calendar_feed_token": full_household.calendar_feed_token,
            "dietary_preferences": [p.preference_name for p in full_household.dietary_preferences],
            "busy_days": full_household.busy_days if full_household.busy_days is not None else ["Tuesday", "Thursday"],
            "busy_max_prep_minutes": full_household.busy_max_prep_minutes if full_household.busy_max_prep_minutes is not None else 20
        }
    }

@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    user_stmt = select(User).where(User.email == clean_email)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid email address or password.")

    # Find household
    member_stmt = (
        select(Household)
        .join(HouseholdMember, Household.household_id == HouseholdMember.household_id)
        .options(selectinload(Household.dietary_preferences))
        .where(HouseholdMember.user_id == user.user_id)
    )
    h_res = await db.execute(member_stmt)
    household = h_res.scalar_one_or_none()

    if not household:
        # Fallback create a household if missing
        household = Household(household_name=f"{user.full_name or 'My'} Family", calendar_feed_token=secrets.token_urlsafe(32))
        db.add(household)
        await db.flush()
        db.add(HouseholdMember(household_id=household.household_id, user_id=user.user_id, role="admin"))
        await seed_default_pantry_staples(household.household_id, db)
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token({"sub": str(user.user_id), "email": user.email, "hid": str(household.household_id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": str(user.user_id),
            "full_name": user.full_name,
            "email": user.email
        },
        "household": {
            "household_id": str(household.household_id),
            "household_name": household.household_name,
            "calendar_feed_token": household.calendar_feed_token,
            "dietary_preferences": [p.preference_name for p in household.dietary_preferences] if household.dietary_preferences else [],
            "busy_days": household.busy_days if household.busy_days is not None else ["Tuesday", "Thursday"],
            "busy_max_prep_minutes": household.busy_max_prep_minutes if household.busy_max_prep_minutes is not None else 20
        }
    }

@router.get("/me", response_model=AuthResponse)
async def get_me(current_auth = Depends(get_current_user_and_household)):
    user, household = current_auth
    token = create_access_token({"sub": str(user.user_id), "email": user.email, "hid": str(household.household_id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": str(user.user_id),
            "full_name": user.full_name,
            "email": user.email
        },
        "household": {
            "household_id": str(household.household_id),
            "household_name": household.household_name,
            "calendar_feed_token": household.calendar_feed_token,
            "dietary_preferences": [p.preference_name for p in household.dietary_preferences] if household.dietary_preferences else [],
            "busy_days": household.busy_days if household.busy_days is not None else ["Tuesday", "Thursday"],
            "busy_max_prep_minutes": household.busy_max_prep_minutes if household.busy_max_prep_minutes is not None else 20
        }
    }

@router.get("/family")
async def get_family_roster(
    current_auth = Depends(get_current_user_and_household),
    db: AsyncSession = Depends(get_db)
):
    user, household = current_auth
    
    # Query all members of this household
    stmt = (
        select(User, HouseholdMember.role)
        .join(HouseholdMember, User.user_id == HouseholdMember.user_id)
        .where(HouseholdMember.household_id == household.household_id)
        .order_by(HouseholdMember.role.asc(), User.created_at.asc())
    )
    res = await db.execute(stmt)
    members_raw = res.all()
    members = []
    for u, role in members_raw:
        members.append({
            "user_id": str(u.user_id),
            "full_name": u.full_name,
            "email": u.email,
            "role": role,
            "created_at": u.created_at,
            "last_login": u.last_login,
            "is_current_user": (u.user_id == user.user_id)
        })

    # Query pending invitations
    inv_stmt = select(HouseholdInvitation).where(
        HouseholdInvitation.household_id == household.household_id,
        HouseholdInvitation.status == "pending"
    )
    inv_res = await db.execute(inv_stmt)
    invitations = inv_res.scalars().all()
    invites_list = [
        {"email": inv.email, "name": inv.name, "created_at": inv.created_at, "expires_at": inv.expires_at}
        for inv in invitations
    ]

    return {
        "household_id": str(household.household_id),
        "household_name": household.household_name,
        "members": members,
        "pending_invitations": invites_list
    }

@router.post("/invite")
async def invite_family_member(
    payload: InviteMemberRequest,
    current_auth = Depends(get_current_user_and_household),
    db: AsyncSession = Depends(get_db)
):
    user, household = current_auth
    spouse_clean = payload.email.strip().lower()
    if not spouse_clean or "@" not in spouse_clean:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    # Check if user already registered
    u_stmt = select(User).where(User.email == spouse_clean)
    u_res = await db.execute(u_stmt)
    existing_u = u_res.scalar_one_or_none()
    if existing_u:
        # Check if already in this household
        m_stmt = select(HouseholdMember).where(HouseholdMember.household_id == household.household_id, HouseholdMember.user_id == existing_u.user_id)
        m_res = await db.execute(m_stmt)
        if m_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"{spouse_clean} is already a member of {household.household_name}.")

    invite_token = generate_random_token()
    invitation = HouseholdInvitation(
        household_id=household.household_id,
        email=spouse_clean,
        name=payload.name.strip() if payload.name else None,
        token=invite_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db.add(invitation)
    await db.commit()

    sent = send_spouse_invitation(
        to_email=spouse_clean,
        spouse_name=payload.name or "",
        inviter_name=user.full_name or "Your family member",
        household_name=household.household_name,
        invite_token=invite_token
    )

    return {
        "status": "success",
        "message": f"Invitation sent to {spouse_clean}",
        "email_dispatched": sent
    }

@router.get("/invitation/{token}")
async def validate_invitation(token: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(HouseholdInvitation, Household.household_name)
        .join(Household, HouseholdInvitation.household_id == Household.household_id)
        .where(HouseholdInvitation.token == token, HouseholdInvitation.status == "pending")
    )
    res = await db.execute(stmt)
    record = res.first()

    if not record:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation link.")

    inv, household_name = record
    if inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This invitation link has expired. Please request a new one.")

    return {
        "valid": True,
        "household_name": household_name,
        "spouse_name": inv.name,
        "spouse_email": inv.email
    }

@router.post("/register-invited", response_model=AuthResponse)
async def register_invited_member(payload: RegisterInvitedRequest, db: AsyncSession = Depends(get_db)):
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if payload.confirm_password is not None and payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match. Please re-enter your password.")

    stmt = select(HouseholdInvitation).where(HouseholdInvitation.token == payload.token, HouseholdInvitation.status == "pending")
    res = await db.execute(stmt)
    inv = res.scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation token.")
    if inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This invitation link has expired.")

    # Check if user already exists
    u_stmt = select(User).where(User.email == inv.email)
    u_res = await db.execute(u_stmt)
    user = u_res.scalar_one_or_none()

    if not user:
        pwd_hash = hash_password(payload.password)
        name = payload.full_name.strip() if payload.full_name else (inv.name or inv.email.split("@")[0].capitalize())
        user = User(email=inv.email, password_hash=pwd_hash, full_name=name, last_login=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()
    else:
        user.last_login = datetime.now(timezone.utc)

    # Link to household as member
    member = HouseholdMember(household_id=inv.household_id, user_id=user.user_id, role="member")
    db.add(member)

    # Mark invitation accepted
    inv.status = "accepted"
    await db.commit()

    # Fetch household
    h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == inv.household_id)
    h_res = await db.execute(h_stmt)
    full_household = h_res.scalar_one()

    # Dispatch detailed onboarding instructions to the invited family member
    send_welcome_user_instructions(
        to_email=user.email,
        user_name=user.full_name or "Family Member",
        household_name=full_household.household_name,
        is_originator=False
    )

    token = create_access_token({"sub": str(user.user_id), "email": user.email, "hid": str(full_household.household_id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": str(user.user_id),
            "full_name": user.full_name,
            "email": user.email
        },
        "household": {
            "household_id": str(full_household.household_id),
            "household_name": full_household.household_name,
            "calendar_feed_token": full_household.calendar_feed_token,
            "dietary_preferences": [p.preference_name for p in full_household.dietary_preferences]
        }
    }

@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    stmt = select(User).where(User.email == clean_email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if user:
        reset_token = generate_random_token()
        user.reset_token = reset_token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()

        send_password_reset(user.email, user.full_name or "", reset_token)

    # Always return 200 for privacy
    return {"message": "If an account exists with that email, a password reset link has been dispatched."}

@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    stmt = select(User).where(User.reset_token == payload.token)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    user.password_hash = hash_password(payload.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()

    return {"message": "Password reset successfully! You may now sign in."}

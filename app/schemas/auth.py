from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
from uuid import UUID

class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    confirm_password: Optional[str] = None
    household_name: str
    dietary_preferences: Optional[List[str]] = []
    spouse_name: Optional[str] = None
    spouse_email: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class InviteMemberRequest(BaseModel):
    name: Optional[str] = None
    email: str

class RegisterInvitedRequest(BaseModel):
    token: str
    password: str
    confirm_password: Optional[str] = None
    full_name: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class UserProfileResponse(BaseModel):
    user_id: str
    full_name: Optional[str]
    email: str

class HouseholdProfileResponse(BaseModel):
    household_id: str
    household_name: str
    dietary_preferences: List[str]

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileResponse
    household: HouseholdProfileResponse

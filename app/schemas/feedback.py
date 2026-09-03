from pydantic import BaseModel, Field
from typing import Optional

class FeedbackCreateRequest(BaseModel):
    category: str = Field(..., description="bug, feature, or feedback")
    subject: Optional[str] = None
    message: str = Field(..., min_length=3)
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    household_name: Optional[str] = None
    page_url: Optional[str] = None

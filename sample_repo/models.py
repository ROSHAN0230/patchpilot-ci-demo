"""
User data schemas using Pydantic v2 patterns.
"""
from pydantic import BaseModel, ConfigDict, field_validator


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: str = "member"

    model_config = ConfigDict(from_attributes=True)

    @field_validator('email')
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower()


def export_user_data(user: UserProfile) -> dict:
    return user.model_dump()

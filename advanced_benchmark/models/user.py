"""
User domain model inheriting from AuditBaseModel.
Updated to Pydantic V2 field validators.
"""
from typing import List
from pydantic import field_validator
from models.base import AuditBaseModel


class UserAccount(AuditBaseModel):
    user_id: int
    email: str
    tags: List[str]

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags_string(cls, v):
        if isinstance(v, str):
            return [t.strip().lower() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip().lower() for t in v if str(t).strip()]
        return v

    @field_validator("email")
    @classmethod
    def validate_email_syntax(cls, v):
        if "@" not in v:
            raise ValueError("Malformed email address")
        return v.strip().lower()

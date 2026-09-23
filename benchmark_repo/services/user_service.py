"""
User service handling ORM mapping and serialization.
Updated for Pydantic V2.
"""
from pydantic import BaseModel, ConfigDict, field_validator


class UserDTO(BaseModel):
    user_id: int
    email: str
    hashed_password: str
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        return v.strip().lower()


class MockDBUser:
    """Simulates an ORM object (e.g. SQLAlchemy model)."""
    def __init__(
        self,
        user_id: int,
        email: str,
        hashed_password: str,
        is_active: bool = True,
    ):
        self.user_id = user_id
        self.email = email
        self.hashed_password = hashed_password
        self.is_active = is_active


def serialize_db_user(db_user: MockDBUser) -> dict:
    dto = UserDTO.model_validate(db_user)
    return dto.model_dump(exclude={"hashed_password"})

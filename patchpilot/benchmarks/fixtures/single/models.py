from pydantic import BaseModel, validator


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: str = "member"

    class Config:
        orm_mode = True

    @validator("email")
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower()


def export_user_data(user: UserProfile) -> dict:
    return user.dict()

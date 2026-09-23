from pydantic import BaseModel, validator


class UserDTO(BaseModel):
    user_id: int
    email: str
    hashed_password: str
    is_active: bool = True

    class Config:
        orm_mode = True

    @validator("email")
    def normalize_email(cls, v):
        return v.strip().lower()


class MockDBUser:
    def __init__(self, user_id: int, email: str, hashed_password: str, is_active: bool = True):
        self.user_id = user_id
        self.email = email
        self.hashed_password = hashed_password
        self.is_active = is_active


def serialize_db_user(db_user: MockDBUser) -> dict:
    dto = UserDTO.from_orm(db_user)
    return dto.dict(exclude={"hashed_password"})

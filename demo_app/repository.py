from typing import List, Optional
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from models import UserModel


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int) -> Optional[UserModel]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        return self.session.execute(stmt).scalars().first()

    def get_all(self) -> List[UserModel]:
        stmt = select(UserModel)
        return self.session.execute(stmt).scalars().all()

    def count_raw(self) -> int:
        stmt = text("SELECT count(*) FROM users")
        result = self.session.execute(stmt).scalar()
        return result or 0

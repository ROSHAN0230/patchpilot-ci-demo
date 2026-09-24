from typing import List, Optional
from sqlalchemy.orm import Session
from models import UserModel

class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int) -> Optional[UserModel]:
        return self.session.query(UserModel).filter(UserModel.id == user_id).first()

    def get_all(self) -> List[UserModel]:
        return self.session.query(UserModel).all()

    def count_raw(self) -> int:
        result = self.session.execute("SELECT count(*) FROM users").scalar()
        return result or 0

from pydantic import BaseModel, Field
from core.config import TagList


class AccountPayload(BaseModel):
    account_id: str = Field(..., regex=r"^ACC-[0-9]{4}$")
    tags: TagList
    balance: float = 0.0

    class Config:
        validate_assignment = True


def update_account_balance(payload: AccountPayload, new_balance: float) -> AccountPayload:
    return payload.copy(update={"balance": new_balance})

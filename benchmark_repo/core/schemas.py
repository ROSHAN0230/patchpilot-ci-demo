"""
Domain schemas upgraded to Pydantic v2 patterns.
"""
from pydantic import BaseModel, Field, ConfigDict
from core.config import TagList


class AccountPayload(BaseModel):
    account_id: str = Field(..., pattern=r"^ACC-[0-9]{4}$")
    tags: TagList
    balance: float = 0.0

    model_config = ConfigDict(validate_assignment=True)


def update_account_balance(payload: AccountPayload, new_balance: float) -> AccountPayload:
    return payload.model_copy(update={"balance": new_balance})

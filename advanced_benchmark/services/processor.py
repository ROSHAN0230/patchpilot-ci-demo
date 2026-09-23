"""
Business service consuming UserAccount models.
Updated for Pydantic V2.
"""
from typing import Dict, Any
from models.user import UserAccount

class UserAccountProcessor:
    @staticmethod
    def process_raw_registration(raw_data: Dict[str, Any]) -> UserAccount:
        # In V2: UserAccount.model_validate(raw_data)
        account = UserAccount.model_validate(raw_data)
        return account

    @staticmethod
    def add_audit_tags(account: UserAccount, extra_tag: str) -> UserAccount:
        # In V2: account.model_copy(update={"tags": current + [extra]})
        current_tags = list(account.tags)
        if extra_tag.lower() not in current_tags:
            current_tags.append(extra_tag.lower())
        return account.model_copy(update={"tags": current_tags})

    @staticmethod
    def export_for_storage(account: UserAccount) -> Dict[str, Any]:
        # In V2: account.model_dump()
        return account.model_dump()

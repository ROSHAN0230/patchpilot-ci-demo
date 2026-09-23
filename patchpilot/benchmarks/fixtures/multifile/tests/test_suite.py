import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import TagList
from core.schemas import AccountPayload, update_account_balance
from services.user_service import MockDBUser, serialize_db_user


def test_1_tag_list_root_model():
    tags = TagList(["Alpha", "Beta12"])
    items = getattr(tags, "root", getattr(tags, "__root__", []))
    assert "alpha" in items
    assert "beta12" in items

    with pytest.raises(ValueError):
        TagList(["Invalid-Tag!"])


def test_2_account_schema_and_copy():
    tags = TagList(["web", "prod"])
    payload = AccountPayload(
        account_id="ACC-1234",
        tags=tags,
        balance=100.0,
    )
    assert payload.account_id == "ACC-1234"
    assert payload.balance == 100.0

    updated = update_account_balance(payload, 250.5)
    assert updated.balance == 250.5
    assert updated.account_id == "ACC-1234"
    assert payload.balance == 100.0


def test_3_user_service_orm_and_dump():
    db_user = MockDBUser(
        user_id=42,
        email="  Admin@Example.COM  ",
        hashed_password="argon2$secret$hash",
        is_active=True,
    )
    data = serialize_db_user(db_user)
    assert data["user_id"] == 42
    assert data["email"] == "admin@example.com"
    assert "hashed_password" not in data
    assert data["is_active"] is True

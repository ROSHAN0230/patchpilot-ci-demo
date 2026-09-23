"""
Test suite for UserProfile.
Verifies functionality and catches breaking changes under Pydantic v2.
"""
import pytest
from models import UserProfile, export_user_data

class MockDbUser:
    """Mock ORM instance."""
    id = 42
    username = "alice"
    email = "Alice.Admin@Example.COM"
    role = "admin"

def test_user_email_validator():
    """Verify validator normalizes email address to lowercase."""
    user = UserProfile(id=1, username="john_doe", email="John.Doe@Example.COM")
    assert user.email == "john.doe@example.com"

def test_user_from_orm_compatibility():
    """Verify loading from ORM instance via from_attributes / from_orm."""
    db_user = MockDbUser()
    # In Pydantic v1: UserProfile.from_orm(db_user)
    # In Pydantic v2: Requires from_attributes=True and raises if orm_mode was used
    user = UserProfile.from_orm(db_user)
    assert user.id == 42
    assert user.username == "alice"
    assert user.email == "alice.admin@example.com"

def test_user_export_method():
    """Verify data serialization to dictionary."""
    user = UserProfile(id=2, username="bob", email="bob@example.com")
    data = export_user_data(user)
    assert isinstance(data, dict)
    assert data["id"] == 2
    assert data["username"] == "bob"

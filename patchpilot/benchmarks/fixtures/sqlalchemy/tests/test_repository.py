import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import Base, Customer
from repository import CustomerRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_1_customer_creation_and_query(db_session):
    repo = CustomerRepository(db_session)
    cust = repo.add_customer("Alice Smith", "alice@example.com")
    assert cust.id is not None
    assert cust.name == "Alice Smith"

    fetched = repo.get_by_id(cust.id)
    assert fetched is not None
    assert fetched.email == "alice@example.com"


def test_2_customer_list_and_delete(db_session):
    repo = CustomerRepository(db_session)
    repo.add_customer("Bob Jones", "bob@example.com")
    repo.add_customer("Charlie Brown", "charlie@example.com")

    all_active = repo.get_all_active()
    assert len(all_active) == 2

    deleted_count = repo.delete_by_email("bob@example.com")
    assert deleted_count == 1

    remaining = repo.get_all_active()
    assert len(remaining) == 1
    assert remaining[0].email == "charlie@example.com"

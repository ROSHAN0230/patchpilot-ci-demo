import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, UserModel
from repository import UserRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    try:
        user1 = UserModel(id=1, username="alice", email="alice@example.com")
        user2 = UserModel(id=2, username="bob", email="bob@example.com")
        sess.add_all([user1, user2])
        sess.commit()
        yield sess
    finally:
        sess.close()


def test_get_by_id(session):
    repo = UserRepository(session)
    user = repo.get_by_id(1)
    assert user is not None
    assert user.username == "alice"
    assert user.email == "alice@example.com"


def test_get_all(session):
    repo = UserRepository(session)
    users = repo.get_all()
    assert len(users) == 2
    assert [u.username for u in users] == ["alice", "bob"]


def test_count_raw(session):
    repo = UserRepository(session)
    count = repo.count_raw()
    assert count == 2

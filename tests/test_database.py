import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.audit import AuditLog
from app.models.crm import Game, Membership, Order, User, Vendor

@pytest.fixture()
def db_session():
    """
    A clean database session fixture for ORM testing. 
    Unlike the workflow fixture, we start empty so we can strictly test inserts.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Vendor.__table__,
            User.__table__,
            Game.__table__,
            Membership.__table__,
            Order.__table__,
            AuditLog.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_create_and_read_vendor(db_session):
    # Act: Insert a new vendor
    new_vendor = Vendor(id="v_111", name="Database Test Corp", status="active", payout_balance=100)
    db_session.add(new_vendor)
    db_session.commit()

    # Assert: Query it back
    fetched_vendor = db_session.query(Vendor).filter(Vendor.id == "v_111").first()
    
    assert fetched_vendor is not None
    assert fetched_vendor.name == "Database Test Corp"
    assert fetched_vendor.payout_balance == 100


def test_update_record(db_session):
    # Arrange: Seed a user
    user = User(id="u_001", name="Bob Builder", email="bob@example.com")
    db_session.add(user)
    db_session.commit()

    # Act: Update the email
    user_to_update = db_session.query(User).filter(User.id == "u_001").first()
    user_to_update.email = "bob.new@example.com"
    db_session.commit()

    # Assert: Verify the update persisted
    updated_user = db_session.query(User).filter(User.id == "u_001").first()
    assert updated_user.email == "bob.new@example.com"


def test_foreign_key_relationships(db_session):
    # Arrange: Create a vendor, a game, and link them
    vendor = Vendor(id="v_222", name="Sports Co", status="active")
    game = Game(id="g_001", name="Tennis", vendor_id=vendor.id)

    db_session.add_all([vendor, game])
    db_session.commit()

    # Act: Query the game and check the vendor linkage
    fetched_game = db_session.query(Game).filter(Game.name == "Tennis").first()
    
    # Assert: Foreign key is correct
    assert fetched_game.vendor_id == "v_222"
    
    # If your models have SQLAlchemy `relationship` defined (e.g. game.vendor), 
    # you can also test the ORM mapping directly like this:
    # assert fetched_game.vendor.name == "Sports Co"


def test_primary_key_integrity_error(db_session):
    # Arrange: Insert first user
    user1 = User(id="u_conflict", name="Charlie", email="charlie@test.com")
    db_session.add(user1)
    db_session.commit()

    # Act & Assert: Attempt to insert a second user with the same Primary Key ID
    user2 = User(id="u_conflict", name="Duplicate Charlie", email="dup@test.com")
    db_session.add(user2)
    
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_delete_record(db_session):
    # Arrange: Create and commit an order
    order = Order(id="o_999", vendor_id="v_333", amount=500, status="pending")
    db_session.add(order)
    db_session.commit()

    # Act: Delete the order
    order_to_delete = db_session.query(Order).filter(Order.id == "o_999").first()
    db_session.delete(order_to_delete)
    db_session.commit()

    # Assert: Order no longer exists
    deleted_order = db_session.query(Order).filter(Order.id == "o_999").first()
    assert deleted_order is None
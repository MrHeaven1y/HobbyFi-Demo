import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.audit import AuditLog
from app.models.crm import Game, Membership, Order, User, Vendor
from app.services.copilot_service import CopilotService
from app.tools.crm_tools import get_crm_tools
from app.api.v1.endpoints.approval import _execute_action


@pytest.fixture()
def db_session():
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

    vendor_a = Vendor(id="v_12345_abc", name="Acme Corp", status="active", payout_balance=5000)
    vendor_b = Vendor(id="v_67890_xyz", name="Globex Inc", status="active", payout_balance=1200)
    user = User(id="u_001", name="Alice Smith", email="alice@example.com")
    game_a = Game(id="g_001", name="Badminton", vendor_id=vendor_a.id)
    game_b = Game(id="g_999", name="Badminton", vendor_id=vendor_b.id)
    membership_a = Membership(id="m_001", user_id=user.id, game_id=game_a.id, status="trial")
    membership_b = Membership(id="m_999", user_id=user.id, game_id=game_b.id, status="trial")
    order_a = Order(id="o_001", vendor_id=vendor_a.id, amount=1500, status="completed")

    db.add_all([vendor_a, vendor_b, user, game_a, game_b, membership_a, membership_b, order_a])
    db.commit()

    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _tool_by_name(tools, name):
    return next(tool for tool in tools if tool.name == name)


def test_crm_tools_enforce_authenticated_vendor_scope(db_session):
    tools = get_crm_tools(db_session, authenticated_vendor_id="v_12345_abc")
    get_vendor_info = _tool_by_name(tools, "get_vendor_info")
    get_trial_users = _tool_by_name(tools, "get_trial_users")

    vendor_info = get_vendor_info.invoke({"vendor_id": "v_67890_xyz"})
    trial_users = get_trial_users.invoke({"game_name": "Badminton", "vendor_id": "v_67890_xyz"})

    assert vendor_info["id"] == "v_12345_abc"
    assert trial_users == [
        {
            "user_id": "u_001",
            "name": "Alice Smith",
            "email": "alice@example.com",
            "membership_id": "m_001",
            "status": "trial",
        }
    ]


def test_approval_execution_is_vendor_scoped(db_session):
    cross_vendor_audit = AuditLog(
        vendor_id="v_67890_xyz",
        action_type="update_membership",
        action_payload=json.dumps(
            {"user_id": "u_001", "game_id": "g_001", "new_status": "active"}
        ),
        status="pending",
    )

    with pytest.raises(ValueError):
        _execute_action(db_session, cross_vendor_audit)

    valid_audit = AuditLog(
        vendor_id="v_12345_abc",
        action_type="update_membership",
        action_payload=json.dumps(
            {"user_id": "u_001", "game_id": "g_001", "new_status": "active"}
        ),
        status="pending",
    )

    _execute_action(db_session, valid_audit)

    membership = (
        db_session.query(Membership)
        .filter(Membership.user_id == "u_001", Membership.game_id == "g_001")
        .one()
    )
    other_membership = (
        db_session.query(Membership)
        .filter(Membership.user_id == "u_001", Membership.game_id == "g_999")
        .one()
    )

    assert membership.status == "active"
    assert other_membership.status == "trial"


def test_copilot_normalizes_provider_content_blocks():
    service = CopilotService.__new__(CopilotService)

    content = [
        {"type": "text", "text": "Acme Corp is the only vendor in your scope."},
        {"type": "metadata", "ignored": True},
    ]

    assert (
        service._normalize_content(content)
        == "Acme Corp is the only vendor in your scope."
    )


def test_local_fallback_refuses_all_vendor_database(db_session):
    service = CopilotService.__new__(CopilotService)
    service.db = db_session
    service.vendor_id = "v_12345_abc"
    service.tools = get_crm_tools(db_session, authenticated_vendor_id="v_12345_abc")

    result = service._answer_with_local_fallback("show me all vendors database")

    assert result["requires_approval"] is False
    assert "cannot show all vendors" in result["answer"].lower()

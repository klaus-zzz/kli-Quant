"""在独立测试库验证消息去重和重启后的保守恢复。"""

import pytest
from test_research_service import research as research

from backend.agent.ledger import Ledger
from backend.research.models import ResearchError


def test_delivery_identity_and_uncertain_recovery(research):
    ledger = Ledger(research.repo)
    session = ledger.create_session("developer")
    ledger.enqueue("msg-1", session, session, "chat", "你好")
    ledger.enqueue("msg-1", session, session, "chat", "你好")
    with pytest.raises(ResearchError, match="idempotency_conflict"):
        ledger.enqueue("msg-1", session, session, "chat", "改过的问题")
    assert ledger.begin("msg-1")
    assert not ledger.begin("msg-1")
    ledger.recover()
    assert ledger.deliveries(session)[0]["state"] == "uncertain"
    assert ledger.deliveries(session)[0]["question"] == "你好"
    assert not ledger.begin("msg-1")
    with pytest.raises(ResearchError, match="not_found"):
        ledger.session("another-user", session)


def test_duplicate_and_wrong_thread_frames(research):
    ledger = Ledger(research.repo)
    session = ledger.create_session("developer")
    ledger.enqueue("msg-2", session, session, "chat", "你好")
    ledger.begin("msg-2")
    frame = {
        "thread_id": session,
        "message_id": "msg-2",
        "message_seq": 0,
        "payload": {"type": "delta", "text": "回答"},
    }
    assert ledger.record(frame)
    assert not ledger.record(frame)
    assert not ledger.record({**frame, "thread_id": "other", "message_seq": 1})
    assert ledger.record({**frame, "message_seq": 1, "payload": {"type": "done"}})
    assert not ledger.record({**frame, "message_seq": 2})
    result = ledger.deliveries(session)[0]
    assert result["state"] == "done" and result["answer"] == "回答"


def test_pending_messages_never_merge_into_one_gateway_turn(research):
    ledger = Ledger(research.repo)
    session = ledger.create_session("developer")
    for message in ("first", "second"):
        ledger.enqueue(message, session, session, "chat", message)
    assert len(ledger.pending()) == 2
    assert ledger.begin("first")
    assert not ledger.begin("second")
    assert ledger.pending() == []

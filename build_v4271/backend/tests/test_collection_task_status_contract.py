from modules.core.db import CollectionTask


def test_collection_task_status_column_supports_verification_required_state():
    status_column = CollectionTask.__table__.c.status

    assert getattr(status_column.type, "length", 0) >= len("verification_required")


def test_executor_mentions_main_account_coordination_step_messages():
    from pathlib import Path

    text = Path("modules/apps/collection_center/executor_v2.py").read_text(encoding="utf-8")

    assert "waiting_for_main_account_session" in text
    assert "preparing_main_account_session" in text
    assert "switching_target_shop" in text
    assert "target_shop_ready" in text

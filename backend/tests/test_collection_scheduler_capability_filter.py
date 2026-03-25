from types import SimpleNamespace

from backend.services.collection_scheduler import build_scheduled_task_scope


def test_build_scheduled_task_scope_filters_domains_and_domain_subtypes():
    config = SimpleNamespace(
        data_domains=["orders", "services"],
        sub_domains={"services": ["agent", "ai_assistant"]},
    )
    account_info = {
        "account_id": "acc-1",
        "capabilities": {
            "orders": True,
            "services": False,
        },
    }

    filtered_domains, domain_subtypes, total_targets = build_scheduled_task_scope(
        config=config,
        account_info=account_info,
    )

    assert filtered_domains == ["orders"]
    assert domain_subtypes == {}
    assert total_targets == 1

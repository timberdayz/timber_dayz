from backend.services.event_listeners import EventListener
from backend.utils.events import DataIngestedEvent


class FakeDispatchService:
    def __init__(self):
        self.events = []
        self.sync_inline_called = False

    def enqueue_or_coalesce(self, event):
        self.events.append(event)
        return {"job_id": "job-1", "coalesced": False}


def test_data_ingested_event_carries_source_table_metadata():
    event = DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        sub_domain=None,
        granularity="daily",
        source_table_name="fact_shopee_orders_daily",
        row_count=10,
    )
    assert event.source_table_name == "fact_shopee_orders_daily"
    assert event.sub_domain is None


def test_listener_enqueues_but_does_not_sync_inline(monkeypatch):
    fake_dispatch_service = FakeDispatchService()
    monkeypatch.setattr(
        EventListener,
        "dispatch_service_factory",
        lambda: fake_dispatch_service,
    )

    sample_event = DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        sub_domain=None,
        granularity="daily",
        source_table_name="fact_shopee_orders_daily",
        row_count=10,
    )

    result = EventListener.handle_data_ingested(sample_event)

    assert result["job_id"] == "job-1"
    assert fake_dispatch_service.sync_inline_called is False
    assert fake_dispatch_service.events[0].source_table_name == "fact_shopee_orders_daily"

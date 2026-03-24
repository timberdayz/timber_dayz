import asyncio

from backend.services.cloud_b_class_sync_service import CloudBClassSyncService


class FakeRunRecorder:
    def __init__(self):
        self.created = []
        self.finished = []

    def create_run(self, total_tables: int):
        run_id = f"run-{len(self.created) + 1}"
        self.created.append((run_id, total_tables))
        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        succeeded_tables: int,
        failed_tables: int,
        error_summary: str | None = None,
    ):
        self.finished.append((run_id, status, succeeded_tables, failed_tables, error_summary))


def test_sync_all_tables_records_run_summary():
    recorder = FakeRunRecorder()
    service = CloudBClassSyncService(
        checkpoint_service=None,
        mirror_manager=None,
        source_batch_reader=lambda *args, **kwargs: [],
        remote_writer=lambda *args, **kwargs: {"success": True},
        table_inspector=lambda: ["fact_shopee_orders_daily", "fact_tiktok_orders_daily"],
        run_recorder=recorder,
        sync_table_handler=lambda table_name, batch_size=1000: {
            "status": "completed",
            "table_name": table_name,
            "written_rows": 0,
        },
    )

    result = asyncio.run(service.sync_all_tables(batch_size=100))

    assert result["status"] == "completed"
    assert recorder.created == [("run-1", 2)]
    assert recorder.finished == [("run-1", "completed", 2, 0, None)]


def test_sync_all_tables_records_partial_success_summary():
    recorder = FakeRunRecorder()

    def handler(table_name, batch_size=1000):
        if table_name == "fact_tiktok_orders_daily":
            return {"status": "failed", "table_name": table_name, "error": "boom"}
        return {"status": "completed", "table_name": table_name, "written_rows": 1}

    service = CloudBClassSyncService(
        checkpoint_service=None,
        mirror_manager=None,
        source_batch_reader=lambda *args, **kwargs: [],
        remote_writer=lambda *args, **kwargs: {"success": True},
        table_inspector=lambda: ["fact_shopee_orders_daily", "fact_tiktok_orders_daily"],
        run_recorder=recorder,
        sync_table_handler=handler,
    )

    result = asyncio.run(service.sync_all_tables(batch_size=100))

    assert result["status"] == "partial_success"
    assert recorder.finished == [("run-1", "partial_success", 1, 1, "1 tables failed")]

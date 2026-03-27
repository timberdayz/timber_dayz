import pytest


@pytest.mark.asyncio
@pytest.mark.pg_only
async def test_scan_endpoint_registers_files_without_triggering_auto_ingest(
    pg_async_client,
    monkeypatch,
):
    from modules.services.catalog_scanner import ScanResult

    scan_calls = []

    def fake_scan_and_register(base_dir):
        scan_calls.append(base_dir)
        return ScanResult(seen=3, registered=2, skipped=1, new_file_ids=[101, 102])

    monkeypatch.setattr(
        "modules.services.catalog_scanner.scan_and_register",
        fake_scan_and_register,
    )
    monkeypatch.setattr(
        "modules.core.path_manager.get_data_raw_dir",
        lambda: "data/raw",
    )
    response = await pg_async_client.post("/api/field-mapping/scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["new_file_ids"] == [101, 102]
    assert payload["data"]["auto_ingest"] == []
    assert scan_calls == ["data/raw"]

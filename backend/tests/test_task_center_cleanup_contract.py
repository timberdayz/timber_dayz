from pathlib import Path

from backend.services.progress_tracker import ProgressTracker


def test_data_sync_service_no_longer_imports_legacy_progress_tracker():
    source = Path("backend/services/data_sync_service.py").read_text(encoding="utf-8")

    assert "from backend.services.progress_tracker import progress_tracker" not in source
    assert "self.progress_tracker = progress_tracker" not in source


def test_legacy_progress_tracker_no_longer_uses_process_local_store():
    tracker = ProgressTracker()

    assert not hasattr(tracker, "_progress_store")

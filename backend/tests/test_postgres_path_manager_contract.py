import io
from contextlib import redirect_stdout

from backend.utils import postgres_path


def test_auto_configure_postgres_path_does_not_emit_misleading_failure_when_client_tools_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        postgres_path.PostgresPathManager,
        "ensure_postgres_in_path",
        classmethod(lambda cls: False),
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert postgres_path.auto_configure_postgres_path() is False

    output = buffer.getvalue()
    assert "database operations may fail" not in output
    assert "Please set POSTGRES_BIN_PATH" not in output
    assert "client tools" in output


def test_auto_configure_postgres_path_can_run_silently(monkeypatch):
    monkeypatch.setattr(
        postgres_path.PostgresPathManager,
        "ensure_postgres_in_path",
        classmethod(lambda cls: False),
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert postgres_path.auto_configure_postgres_path(emit_output=False) is False

    assert buffer.getvalue() == ""

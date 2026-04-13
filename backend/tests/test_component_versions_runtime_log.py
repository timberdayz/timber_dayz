from pathlib import Path

from backend.routers import component_versions


def test_write_runtime_log_persists_stdout_and_stderr(tmp_path: Path) -> None:
    runtime_log = tmp_path / "runtime.log"

    component_versions._write_subprocess_runtime_log(
        runtime_log,
        stdout="detail tab attempt 1\nselected_after_click=False\n",
        stderr="[PROGRESS] step_failed\n",
        returncode=1,
    )

    content = runtime_log.read_text(encoding="utf-8")

    assert "returncode=1" in content
    assert "STDOUT" in content
    assert "selected_after_click=False" in content
    assert "STDERR" in content
    assert "[PROGRESS] step_failed" in content

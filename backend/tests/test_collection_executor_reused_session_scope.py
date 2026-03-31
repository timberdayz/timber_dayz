from pathlib import Path


def test_execute_defines_reused_session_before_runtime_task_params_call():
    source = Path("modules/apps/collection_center/executor_v2.py").read_text(encoding="utf-8")

    reused_index = source.index("reused_session = False")
    build_params_index = source.index("params = _build_runtime_task_params(")

    assert reused_index < build_params_index

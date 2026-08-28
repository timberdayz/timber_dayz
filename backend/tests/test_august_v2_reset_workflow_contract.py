from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "reset-august-v2-start.yml"
)


def test_august_v2_reset_workflow_is_fixed_and_protected():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in source
    assert "environment:" in source
    assert "name: production" in source
    assert "RESET_2026_08_TO_V2" in source
    assert "dry-run" in source
    assert "mode:" in source
    assert "actor_user_id" in source
    assert "^[1-9][0-9]*$" in source
    assert "reset_args=(--apply" in source
    assert 'reset_august_v2_start.py "${reset_args[@]}"' in source
    assert "quiesce_monthly_input_writers" in source
    assert "restore_monthly_input_writers" in source
    assert "trap restore_monthly_input_writers EXIT" in source
    assert "--period" not in source
    assert "actions/upload-artifact" in source

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "profit-basis-v2-dry-run.yml"
)


def test_profit_basis_dry_run_workflow_is_manual_and_read_only():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in source
    assert "PRODUCTION_SSH_PRIVATE_KEY" in source
    assert "PRODUCTION_HOST" in source
    assert "PRODUCTION_PATH" in source
    assert "migrate_profit_basis_to_v2.py --dry-run" in source
    assert "--apply" not in source
    assert "--reopen-protected" not in source
    assert "docker exec xihong_erp_backend_api" in source
    assert "actions/upload-artifact" in source

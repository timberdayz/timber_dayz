from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_formal_collection_start_script_uses_strict_tunnel_check():
    script = PROJECT_ROOT / "scripts" / "start_collection_formal.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "check_local_run_env.py" in text
    assert "--profile collection" in text
    assert "--require-cloud-tunnel" in text
    assert "run.py" in text
    assert "--local" in text
    assert "Ensure-CloudSyncTunnel" in text
    assert "CLOUD_SYNC_SSH_HOST" in text
    assert "CLOUD_SYNC_SSH_KEY" in text
    assert "Start-Process" in text
    assert "Import-EnvFile" in text
    assert "BatchMode=yes" in text
    assert "TunnelOnly" in text
    assert 'Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_HOST" "127.0.0.1"' in text
    assert 'Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_PORT" "15435"' in text


def test_local_collection_start_script_keeps_development_preflight():
    script = PROJECT_ROOT / "scripts" / "start_local_collection_mode.ps1"
    text = script.read_text(encoding="utf-8")

    assert "--profile collection" in text
    assert "--require-cloud-tunnel" not in text


def test_collection_local_example_uses_remote_localhost_proxy_port():
    text = (PROJECT_ROOT / "env.collection.local.example").read_text(encoding="utf-8")

    assert "CLOUD_SYNC_REMOTE_DB_HOST=127.0.0.1" in text
    assert "CLOUD_SYNC_REMOTE_DB_PORT=15435" in text

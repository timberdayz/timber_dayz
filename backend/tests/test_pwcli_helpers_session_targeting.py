from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPERS = REPO_ROOT / "scripts" / "pwcli_helpers.ps1"
LAUNCHER = REPO_ROOT / "scripts" / "pwcli.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _save_helper_block() -> str:
    text = _read(HELPERS)
    return text.split("function Save-PwcliPlatformState", 1)[1].split("\nfunction ", 1)[0]


def test_launcher_propagates_exit_code():
    """pwcli.ps1 必须把 python 的退出码传给调用方，否则失败会被当成成功。"""
    text = _read(LAUNCHER)
    assert re.search(r"exit\s+\$LASTEXITCODE", text), "pwcli.ps1 缺少 exit $LASTEXITCODE"


def test_save_helper_accepts_work_tag():
    """保存函数必须能按账号定位会话，不能只依赖环境变量。"""
    block = _save_helper_block()
    assert "WorkTag" in block, "Save-PwcliPlatformState 缺少 -WorkTag 参数"
    assert '"$platformName-$WorkTag"' in block, "保存函数没有用 platform+WorkTag 拼 session 名"


def test_save_helper_throws_on_nonzero_exit():
    """保存失败必须抛错，让调用方拿到非 0 退出码。"""
    block = _save_helper_block()
    assert "$LASTEXITCODE" in block
    assert "throw" in block


def test_save_helper_rejects_unresolvable_session():
    """既没有 -WorkTag、又没有活动会话时必须报错，不能静默退回 session=default。"""
    block = _save_helper_block()
    assert "cannot locate the browser session" in block, (
        "定位不到会话时必须报错（否则会退回 pwcli state-save -> session=default -> 断点 A）"
    )
    assert "Get-PwcliActiveSession" in block, "必须复用既有 Get-PwcliActiveSession 解析活动会话"


def test_panel_save_command_passes_work_tag():
    """面板的保存命令必须带上 -WorkTag，否则 session 又会退回 default。"""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pwcli_inspection_panel import build_pwcli_action_command

    account = {
        "platform": "shopee",
        "account_id": "hongxikeji:main",
        "work_tag": "shopee-hongxikeji-main-inspect",
        "display_name": "hongxikeji:main",
    }
    command = build_pwcli_action_command("save", account, REPO_ROOT)
    joined = " ".join(command)
    assert "-WorkTag" in joined, "面板保存命令缺少 -WorkTag"
    assert "shopee-hongxikeji-main-inspect" in joined, "面板保存命令没有传具体 work_tag"

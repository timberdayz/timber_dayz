from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPERS = REPO_ROOT / "scripts" / "pwcli_helpers.ps1"
LAUNCHER = REPO_ROOT / "scripts" / "pwcli.ps1"
INVENTORY = REPO_ROOT / "scripts" / "pwcli_account_inventory.py"


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


def test_inspection_loop_passes_work_tag_on_every_platform_branch():
    """巡店循环的**三个**平台分支都必须传 -WorkTag。

    计划自称 Step 5b 是"最易漏的一步"：漏掉任何一条，
    该平台的 session 名就会退回 default -> 存错地方 -> 下次读不到。

    这里按**调用点**逐条锁定（不是只查函数签名）：
    巡店循环里恰好有 3 处 `Save-Pwcli*State -AccountId $account.account_id` 调用，
    且每一处都带 `-WorkTag $account.work_tag`。
    （函数**定义**形如 `Save-PwcliShopeeState {`，不带 -AccountId，天然不会被误计。）
    """
    text = _read(HELPERS)

    calls = re.findall(
        r"Save-Pwcli(Miaoshou|Shopee|Tiktok)State\s+-AccountId\s+\$account\.account_id(?P<rest>[^\r\n]*)",
        text,
    )
    assert len(calls) == 3, (
        f"应恰好有 3 处 Save-Pwcli*State 调用（巡店循环的三个平台分支），实际 {len(calls)} 处：{calls}"
    )
    for platform, rest in calls:
        assert "-WorkTag" in rest, f"{platform} 分支没有传 -WorkTag（实际：{rest.strip()!r}）"
        assert "$account.work_tag" in rest, (
            f"{platform} 分支传的 -WorkTag 不是 $account.work_tag（实际：{rest.strip()!r}）"
        )

    # 三个平台一个都不能少
    assert {platform for platform, _ in calls} == {"Miaoshou", "Shopee", "Tiktok"}


def test_platform_save_wrappers_forward_work_tag():
    """三个 Save-Pwcli{Platform}State 包装必须把 -WorkTag 透传给 Save-PwcliPlatformState。

    包装层漏传的话，即使巡店循环传了 work_tag，session 名仍然退回 default。
    """
    text = _read(HELPERS)
    for platform in ("miaoshou", "shopee", "tiktok"):
        pattern = (
            rf"function Save-Pwcli{platform.capitalize()}State\s*\{{[^}}]*"
            rf"Save-PwcliPlatformState\s+-Platform\s+{platform}\s+-AccountId\s+\$AccountId\s+-WorkTag\s+\$WorkTag"
        )
        assert re.search(pattern, text, re.IGNORECASE | re.DOTALL), (
            f"Save-Pwcli{platform.capitalize()}State 没有把 -WorkTag 透传给 Save-PwcliPlatformState"
        )


def _powershell_work_tag(platform: str, account_id: str) -> str:
    """在 PowerShell 里跑一次 Resolve-PwcliWorkTag，返回它算出来的 work tag。"""
    script = (
        f". '{HELPERS}'; "
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        f"Resolve-PwcliWorkTag -Platform '{platform}' -AccountId '{account_id}'"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = (result.stdout or "").strip()
    assert result.returncode == 0, f"PowerShell 执行失败：{result.stdout}\n{result.stderr}"
    return output


def test_open_helper_resolves_work_tag_from_account():
    """Open-PwcliPlatform 必须把账号拼进 work tag，不能默认用平台级的 "explore"。

    否则手工执行 `Open-PwcliShopee -AccountId X`（不带 -WorkTag）时，
    同平台的多个账号会共用 `shopee-explore` 这一个 session 名 ——
    后开的窗口会把先开的窗口杀掉（spec D9 / ③一账号一巡店窗口）。

    这里锁定的是**函数体**而不是字面量：只要 Open 走了 Resolve-PwcliWorkTag，
    推导规则怎么变都不会退化回平台级 session 名。
    """
    text = _read(HELPERS)
    block = text.split("function Open-PwcliPlatform", 1)[1].split("\nfunction ", 1)[0]
    assert "Resolve-PwcliWorkTag" in block, "Open-PwcliPlatform 没有按账号解析 work tag"
    assert "$resolvedWorkTag" in block, "Open-PwcliPlatform 没有用解析出来的 work tag 拼 session 名"


@pytest.mark.skipif(shutil.which("powershell") is None, reason="requires Windows PowerShell")
def test_powershell_and_python_derive_the_same_work_tag():
    """PowerShell 侧与 Python 侧的 work tag 规则必须完全一致。

    两侧各写一遍规则迟早会分叉；一旦分叉，同一个账号在「网页面板」和
    「手工命令」下会落到不同的 session 名与工作目录（spec D9）。
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pwcli_account_inventory import work_tag

    for platform, account_id in (
        ("shopee", "hongxikeji:main"),
        ("tiktok", "Tiktok 1店"),
        ("shopee", "虾皮巴西（东朗照明主体）"),
    ):
        assert _powershell_work_tag(platform, account_id) == work_tag(platform, account_id)


@pytest.mark.skipif(shutil.which("powershell") is None, reason="requires Windows PowerShell")
def test_powershell_derives_distinct_tags_for_chinese_accounts():
    """两个中文账号在 PowerShell 侧也必须得到不同的 work tag。

    这是 ③「一账号一巡店窗口」在手工命令路径上的前提 ——
    中文账号名不能塌成同一个 session 名。
    """
    first = _powershell_work_tag("shopee", "虾皮巴西（东朗照明主体）")
    second = _powershell_work_tag("shopee", "验证码测试账号")
    assert first != second, "两个中文账号推导出了同一个 work tag"
    assert first and second, "work tag 不能为空"


@pytest.mark.skipif(shutil.which("powershell") is None, reason="requires Windows PowerShell")
def test_explicit_work_tag_wins_over_account_derivation():
    """显式传入的 -WorkTag 必须优先于按账号推导。"""
    script = (
        f". '{HELPERS}'; "
        "Resolve-PwcliWorkTag -Platform 'shopee' -WorkTag 'fixed-tag' -AccountId 'hongxikeji:main'"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"PowerShell 执行失败：{result.stdout}\n{result.stderr}"
    assert (result.stdout or "").strip() == "fixed-tag"


def test_work_tag_cli_does_not_touch_database():
    """work-tag 子命令必须能在没有数据库的环境里跑（PowerShell 侧要靠它推导）。"""
    result = subprocess.run(
        [
            sys.executable,
            str(INVENTORY),
            "work-tag",
            "--platform",
            "shopee",
            "--account-id",
            "hongxikeji:main",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": "postgresql://invalid:invalid@127.0.0.1:1/none"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert (result.stdout or "").strip() == "shopee-hongxikeji-main-inspect"

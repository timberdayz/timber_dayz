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


def _helpers_text() -> str:
    return _read(HELPERS)


def test_launcher_propagates_exit_code():
    """pwcli.ps1 必须把 python 的退出码传给调用方，否则失败会被当成成功。"""
    text = _read(LAUNCHER)
    assert re.search(r"exit\s+\$LASTEXITCODE", text), "pwcli.ps1 缺少 exit $LASTEXITCODE"


def test_save_helpers_are_removed():
    """登录态只由浏览器 profile 承载：保存会话的 PowerShell 函数必须全部删掉。

    只要还留着 ``Save-Pwcli*State``，运维就还能走「打开 -> 保存」的老路径，
    而那条路径写的是 ``data/sessions`` 下的会话文件 —— 与 profile 单一载体冲突。
    """
    text = _helpers_text()

    assert "Save-Pwcli" not in text, "pwcli_helpers.ps1 仍保留 Save-Pwcli*State"
    assert "state-save" not in text, "pwcli_helpers.ps1 仍调用 pwcli state-save"


def test_panel_rejects_save_action():
    """面板不再支持「保存」动作（端点已删，命令构造也必须拒绝）。"""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pwcli_inspection_panel import build_pwcli_action_command

    account = {
        "platform": "shopee",
        "account_id": "hongxikeji:main",
        "work_tag": "shopee-hongxikeji-main-inspect",
        "display_name": "hongxikeji:main",
    }

    with pytest.raises(ValueError):
        build_pwcli_action_command("save", account, REPO_ROOT)


def test_panel_open_command_passes_work_tag():
    """面板的打开命令必须带上 -WorkTag，否则 session 会退回 default。"""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pwcli_inspection_panel import build_pwcli_action_command

    account = {
        "platform": "shopee",
        "account_id": "hongxikeji:main",
        "work_tag": "shopee-hongxikeji-main-inspect",
        "display_name": "hongxikeji:main",
    }

    joined = " ".join(build_pwcli_action_command("open", account, REPO_ROOT))

    assert "-WorkTag" in joined, "面板打开命令缺少 -WorkTag"
    assert "shopee-hongxikeji-main-inspect" in joined, "面板打开命令没有传具体 work_tag"


def test_panel_open_command_forwards_proxy_server():
    """账号代理必须一路传到 pwcli 命令行（代理服务器地址不带凭据）。"""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pwcli_inspection_panel import build_pwcli_action_command

    account = {
        "platform": "shopee",
        "account_id": "hongxikeji:main",
        "work_tag": "shopee-hongxikeji-main-inspect",
        "display_name": "hongxikeji:main",
    }

    joined = " ".join(
        build_pwcli_action_command(
            "open",
            account,
            REPO_ROOT,
            proxy_server="http://10.0.0.9:8080",
        )
    )

    assert "-ProxyServer" in joined, "面板打开命令缺少 -ProxyServer"
    assert "10.0.0.9:8080" in joined, "面板打开命令没有把代理地址传下去"


def test_open_helper_forwards_proxy_server_to_pwcli():
    """PowerShell 侧的 Open 函数必须把代理地址转成 pwcli 的 --proxy-server 参数。"""
    block = _helpers_text().split("function Open-PwcliPlatform", 1)[1].split("\nfunction ", 1)[0]

    assert "--proxy-server" in block, "Open-PwcliPlatform 没有把代理地址传给 pwcli open"
    assert "ProxyServer" in block, "Open-PwcliPlatform 缺少 -ProxyServer 参数"


def test_inspection_loop_no_longer_saves_state():
    """交互式巡店循环不得再调用 Save-*，改成「关掉浏览器即由 profile 保存」。"""
    text = _helpers_text()

    calls = re.findall(
        r"Save-Pwcli(Miaoshou|Shopee|Tiktok)State\s+-AccountId\s+\$account\.account_id",
        text,
    )
    assert not calls, f"巡店循环仍在调用保存函数: {calls}"
    assert "Press Enter to save" not in text, "巡店循环仍提示保存会话"
    assert "Read-Host" in text, "巡店循环必须仍然等待人工确认"


def test_inspection_loop_tells_operator_to_close_the_browser():
    """循环提示必须明确「关闭浏览器后登录态由 profile 保存」。"""
    text = _helpers_text()
    loop = text.split("function Start-PwcliDailyInspection", 1)[1]

    assert "close the browser" in loop.lower(), "巡店循环没有提示关闭浏览器"
    assert "profile" in loop.lower(), "巡店循环没有说明登录态由浏览器 profile 保存"


def test_open_helper_resolves_work_tag_from_account():
    """Open-PwcliPlatform 必须把账号拼进 work tag，不能默认用平台级的 "explore"。

    否则手工执行 `Open-PwcliShopee -AccountId X`（不带 -WorkTag）时，
    同平台的多个账号会共用 `shopee-explore` 这一个 session 名 ——
    后开的窗口会把先开的窗口杀掉（spec D9 / ③一账号一巡店窗口）。

    这里锁定的是**函数体**而不是字面量：只要 Open 走了 Resolve-PwcliWorkTag，
    推导规则怎么变都不会退化回平台级 session 名。
    """
    text = _helpers_text()
    block = text.split("function Open-PwcliPlatform", 1)[1].split("\nfunction ", 1)[0]
    assert "Resolve-PwcliWorkTag" in block, "Open-PwcliPlatform 没有按账号解析 work tag"
    assert "$resolvedWorkTag" in block, "Open-PwcliPlatform 没有用解析出来的 work tag 拼 session 名"


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

#!/usr/bin/env python3
"""云端同步隧道**看门狗**脚本的契约守护(纯源码, 不建连接)。

守护的底线
----------
1. **参数不漂移** —— 看门狗拉隧道的 ssh 参数必须与
   :func:`scripts/start_collection_formal.ps1` 的 ``Ensure-CloudSyncTunnel`` **完全一致**。
   两处各写一份参数 ⇒ 总有一处会过期 ⇒ 过期那处「连不上却不知道为什么」。
2. **幂等** —— 端口已通就**不许**再拉一条隧道(否则计划任务每跑一次多一条 ssh 进程)。
3. **不停容器** —— 看门狗只管隧道。它绝不能碰 backend / celery / frontend 容器,
   否则「检查隧道」会变成「打断采集」。
4. **不落明文口令** —— 隧道走 **key** 登录, 脚本里不许出现 ``sshpass`` 之类的东西。
5. **能自愈僵死进程** —— 端口被僵死 ssh 占着时, 新进程会因为
   ``ExitOnForwardFailure=yes`` 立刻退出 ⇒ 必须先清理再重连。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_PATH = PROJECT_ROOT / "scripts" / "watch_cloud_sync_tunnel.ps1"
FORMAL_PATH = PROJECT_ROOT / "scripts" / "start_collection_formal.ps1"

#: 两个脚本必须一致的 ssh 选项(防漂移清单)。
SHARED_SSH_OPTIONS = (
    "BatchMode=yes",
    "ExitOnForwardFailure=yes",
    "ServerAliveInterval=30",
    "ServerAliveCountMax=3",
    "StrictHostKeyChecking=accept-new",
)

#: 看门狗绝不许出现的东西(会打断采集 / 绕过 key 登录)。
FORBIDDEN_IN_WATCHDOG = (
    "sshpass",
    "docker compose",
    "docker-compose",
    "Stop-Container",
    "docker stop",
    "docker rm",
)


@pytest.fixture(scope="module")
def watchdog_source() -> str:
    assert WATCHDOG_PATH.exists(), "隧道看门狗脚本缺失: %s" % WATCHDOG_PATH
    return WATCHDOG_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def formal_source() -> str:
    assert FORMAL_PATH.exists(), "正式采集脚本缺失: %s" % FORMAL_PATH
    return FORMAL_PATH.read_text(encoding="utf-8")


def test_ssh_options_do_not_drift(watchdog_source: str, formal_source: str) -> None:
    missing_watchdog = [
        option for option in SHARED_SSH_OPTIONS if option not in watchdog_source
    ]
    assert not missing_watchdog, "看门狗缺少 ssh 选项: %s" % missing_watchdog
    missing_formal = [
        option for option in SHARED_SSH_OPTIONS if option not in formal_source
    ]
    assert not missing_formal, "正式采集脚本缺少 ssh 选项: %s" % missing_formal


def _forward_expression(source: str) -> str | None:
    """取出构造转发串的那一行(形如 ``本机端口:远端主机:远端端口``)。"""
    match = re.search(r"forward\s*=\s*(.+)", source)
    return match.group(1) if match else None


def test_forward_spec_matches(watchdog_source: str, formal_source: str) -> None:
    """转发必须是「本机端口:远端主机:远端端口」三段式, 两边都得是。"""
    for label, source in (("看门狗", watchdog_source), ("正式脚本", formal_source)):
        expression = _forward_expression(source)
        assert expression, "%s 里找不到 forward 的构造" % label
        lowered = expression.lower()
        assert lowered.count(":") >= 2, "%s 的 forward 不是三段式: %s" % (
            label,
            expression,
        )
        for token in ("port", "remote"):
            assert token in lowered, "%s 的 forward 少了 %s 段: %s" % (
                label,
                token,
                expression,
            )
        assert "host" in lowered, "%s 的 forward 少了主机段: %s" % (label, expression)


def test_watchdog_is_idempotent(watchdog_source: str) -> None:
    """必须先探测端口, 可达就退出 —— 不许无条件拉隧道。"""
    probe_at = watchdog_source.find("$reachable = Test-TcpPort")
    exit_at = watchdog_source.find("exit 0", probe_at)
    start_call_at = watchdog_source.find("Start-CloudSyncTunnel -Config $config")
    assert probe_at > 0, "看门狗必须先探测端口"
    assert exit_at > probe_at, "端口可达时必须直接退出(不拉新隧道)"
    assert start_call_at > exit_at, "拉隧道必须排在「可达即退出」之后"


def test_watchdog_does_not_touch_containers(watchdog_source: str) -> None:
    offenders = [
        token
        for token in FORBIDDEN_IN_WATCHDOG
        if token.lower() in watchdog_source.lower()
    ]
    assert not offenders, "看门狗只管隧道, 不许碰容器: %s" % offenders


def test_watchdog_does_not_embed_credentials(watchdog_source: str) -> None:
    assert "sshpass" not in watchdog_source, "隧道必须走 key 登录, 不许用口令"
    # 私钥路径只能来自环境变量, 不能写死。
    assert "CLOUD_SYNC_SSH_KEY" in watchdog_source
    assert (
        ".ssh/github_actions_deploy" not in watchdog_source
    ), "私钥路径必须来自 CLOUD_SYNC_SSH_KEY, 不许写死"


def test_watchdog_cleans_stale_tunnel_processes(watchdog_source: str) -> None:
    """端口被僵死 ssh 占着时必须先清理, 否则新进程起不来。"""
    assert "Remove-StaleTunnelProcesses" in watchdog_source
    assert "Stop-Process" in watchdog_source, "必须真的会终止僵死进程"
    assert (
        "ExitOnForwardFailure=yes" in watchdog_source
    ), "ExitOnForwardFailure 是「必须先清理」的原因, 不许被改掉"


def test_watchdog_writes_a_trace_log(watchdog_source: str) -> None:
    """每次执行都要留一行痕迹(什么时候断的、断了多久)。"""
    assert "Write-WatchdogLog" in watchdog_source
    assert "cloud-sync-tunnel-watchdog.log" in watchdog_source


def test_watchdog_supports_scheduled_task(watchdog_source: str) -> None:
    assert "InstallScheduledTask" in watchdog_source
    assert "UninstallScheduledTask" in watchdog_source
    assert "schtasks" in watchdog_source, "计划任务用 schtasks 注册(不需管理员改组策略)"


def test_watchdog_task_action_never_flashes_a_window(watchdog_source: str) -> None:
    """看门狗每 2 分钟跑一次 —— 它**绝不能**往用户脸上弹控制台窗口。

    2026-11-12 事故：任务是 ``powershell.exe -NoProfile ...`` 直接跑的,
    Windows Terminal 是本机默认终端宿主 ⇒ 每次触发都弹一个可见终端窗口,
    每 2 分钟闪一次, 用户完全无法判断这是自家任务还是被入侵。

    修法是让任务动作走 ``conhost.exe --headless``, 它跑完全相同的命令行
    但不创建任何窗口(实测 0 个可见窗口)。

    注意: ``-WindowStyle Hidden`` **不够** —— 窗口是终端宿主创建的,
    不是 PowerShell 创建的, 加了它照样闪。
    """
    install_body = watchdog_source[
        watchdog_source.find("function Install-WatchdogScheduledTask") :
        watchdog_source.find("function Remove-WatchdogScheduledTask")
    ]
    assert install_body, "找不到 Install-WatchdogScheduledTask 函数"

    assert "conhost.exe" in install_body, (
        "计划任务动作必须走 conhost.exe --headless, 否则每 2 分钟弹一次窗口"
    )
    assert "--headless" in install_body, "conhost 必须带 --headless 才是无窗口运行"

    # 反向守护: 任务命令**本身**不许退回直接跑 powershell.exe 的旧式动作。
    # 只看真正拼出来的命令行, 不看注释(注释里可以解释为什么不用它)。
    command_lines = [
        line
        for line in install_body.splitlines()
        if "taskCommand" in line and "=" in line
    ]
    assert command_lines, "找不到 taskCommand 的构造"
    for line in command_lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "--headless" in stripped, (
            "taskCommand 必须带 --headless: %s" % stripped
        )
        assert "-WindowStyle" not in stripped, (
            "-WindowStyle Hidden 挡不住终端宿主弹窗, 别用它冒充无窗口方案: %s" % stripped
        )


def test_watchdog_loads_env_files(watchdog_source: str) -> None:
    """配置必须来自 env 文件, 与正式采集脚本同样的加载顺序。"""
    for env_file in (".env", ".env.local", ".env.collection.local"):
        assert env_file in watchdog_source, "看门狗必须加载 %s" % env_file

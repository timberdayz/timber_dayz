#!/usr/bin/env python3
"""SSH 访问契约的守护（**纯源码**，不建任何连接、不读私钥）。

为什么需要这份契约
------------------
2026-11-13 实测事故：agent 用 ``root@134.175.222.171`` 加本机两把钥匙试连，
两次 ``Permission denied`` ⇒ 误判「本机没有生产 SSH 私钥」，
并据此写下「部署类核验无法登机」的结论，一路影响到后续多轮判断。

真相是：隧道与生产运维走的是 ``deploy@`` + ``~/.ssh/github_actions_deploy``，
这把钥匙**就在本机**且隧道当时正在跑；而 ``root@`` 的私钥**只在 GitHub Actions
Secret 里**，本机刻意不持有 —— 那是**设计**（部署自动化），不是"环境缺东西"。

⇒ 守护的底线（每条都对应上面那个误判）：

1. **账号 ↔ 钥匙 ↔ 用途**只写在 ``docs/guides/SSH_ACCESS.md`` 一份文档里（律 1）。
2. 文档里的默认值必须与**脚本里的默认值一致** —— 两处各写一份就会漂移，
   漂移那处就是下一个「连不上却不知道为什么」。
3. 脚本里不许出现 ``root@``：root 是**流水线**的身份，不是交互式身份。
4. 隧道走 **key 登录**，不许出现口令（``sshpass``）。
5. 本机必须**有**那把隧道钥匙 —— 缺了要早失败，不要等运行时才发现。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = PROJECT_ROOT / "docs" / "guides" / "SSH_ACCESS.md"
WATCHDOG_PATH = PROJECT_ROOT / "scripts" / "watch_cloud_sync_tunnel.ps1"
FORMAL_PATH = PROJECT_ROOT / "scripts" / "start_collection_formal.ps1"

#: 隧道配置的两个真源脚本：看门狗与采集启动脚本，参数必须一致。
TUNNEL_SCRIPTS = (WATCHDOG_PATH, FORMAL_PATH)

#: 文档里必须出现的「机器可读配置块」条目 —— 值必须与脚本默认值一致。
DOCUMENTED_ENV_KEYS = (
    "CLOUD_SYNC_SSH_HOST",
    "CLOUD_SYNC_SSH_USER",
    "CLOUD_SYNC_TUNNEL_HOST",
    "CLOUD_SYNC_TUNNEL_PORT",
    "CLOUD_SYNC_REMOTE_DB_HOST",
    "CLOUD_SYNC_REMOTE_DB_PORT",
)

#: 交互式（人 / agent 可直接用）登录生产机时唯一允许的账号。
INTERACTIVE_ACCOUNT = "deploy@134.175.222.171"

#: 隧道用的私钥文件名（路径本身随机器不同，文件名是稳定契约）。
TUNNEL_KEY_NAME = "github_actions_deploy"

#: 绝不许出现在脚本里的东西。
FORBIDDEN_IN_SCRIPTS = ("root@", "sshpass")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _script_env_defaults(path: Path) -> dict[str, str]:
    """从 PowerShell 脚本里解析 ``Get-EnvOrDefault "NAME" "value"`` 的默认值。"""
    text = _read(path)
    pattern = re.compile(r'Get-EnvOrDefault\s+"([A-Z0-9_]+)"\s+"([^"]*)"')
    return {name: value for name, value in pattern.findall(text)}


def _doc_env_block() -> dict[str, str]:
    """解析文档里的机器可读配置块（``CLOUD_SYNC_XXX=value`` 形式的行）。"""
    text = _read(DOC_PATH)
    pattern = re.compile(r"^(CLOUD_SYNC_[A-Z0-9_]+)=([^\s`]+)\s*$", re.MULTILINE)
    return {name: value for name, value in pattern.findall(text)}


def test_ssh_access_doc_exists() -> None:
    """SSOT 文档必须在 —— 没有它，账号/钥匙/用途就会散落在各处各自漂移。"""
    if not DOC_PATH.exists():
        raise AssertionError(f"缺少 SSH 访问真源文档：{DOC_PATH}")
    assert DOC_PATH.exists()


def test_doc_declares_the_interactive_account() -> None:
    """文档必须写明**交互式**登录生产机的账号 —— 避免再用 root@ 试连。"""
    text = _read(DOC_PATH)
    assert INTERACTIVE_ACCOUNT in text, f"文档没有写明交互式账号 {INTERACTIVE_ACCOUNT}"


def test_doc_declares_the_tunnel_key() -> None:
    """文档必须写明隧道用的那把钥匙的文件名。"""
    text = _read(DOC_PATH)
    assert TUNNEL_KEY_NAME in text, f"文档没有写明隧道私钥 {TUNNEL_KEY_NAME}"


def test_doc_separates_root_account_from_interactive_use() -> None:
    """``root@`` 必须被写成「只属于流水线」，否则又会被当成交互式账号去试。"""
    text = _read(DOC_PATH)
    assert "root@" in text, "文档必须显式提到 root@，说明它属于哪条通道"
    assert "GitHub Actions" in text, "root@ 的归属必须指向 GitHub Actions 流水线"


def test_doc_documents_the_github_ssh_endpoint() -> None:
    """GitHub 的 HTTPS 不可达，代码通道只能走 SSH-443 —— 文档必须写明。"""
    text = _read(DOC_PATH)
    assert "ssh.github.com:443" in text, "文档没有写明 GitHub 的 SSH-443 端点"


def test_doc_lists_every_tunnel_env_key() -> None:
    """文档的配置块必须覆盖全部隧道配置项 —— 少一条就等于留了个未写明的默认值。"""
    block = _doc_env_block()
    missing = [key for key in DOCUMENTED_ENV_KEYS if key not in block]
    assert not missing, f"文档配置块缺少：{missing}"


def test_doc_values_match_script_defaults() -> None:
    """文档 ↔ 脚本不许漂移（律 1：真源只能一个，写在纸上）。"""
    block = _doc_env_block()
    for script in TUNNEL_SCRIPTS:
        defaults = _script_env_defaults(script)
        for key in DOCUMENTED_ENV_KEYS:
            assert key in defaults, f"{script.name} 里没有 {key} 的默认值"
            message = f"{key}: 脚本={defaults[key]} 文档={block[key]}"
            assert block[key] == defaults[key], message


def test_both_tunnel_scripts_share_the_same_defaults() -> None:
    """看门狗与采集启动脚本必须一致 —— 否则「一个跑一个跳」。"""
    watchdog = _script_env_defaults(WATCHDOG_PATH)
    formal = _script_env_defaults(FORMAL_PATH)
    for key in DOCUMENTED_ENV_KEYS:
        message = f"{key}: 看门狗={watchdog.get(key)} 采集={formal.get(key)}"
        assert watchdog.get(key) == formal.get(key), message


def test_scripts_never_use_root_account() -> None:
    """root 是流水线的身份；脚本里把它当登录目标就是越权。

    ⚠️ 判定的是**登录目标**（``root@<host>``），不是"文本里提到过 root"——
    脚本注释里可以、也应该解释清楚 root 属于哪条通道。
    """
    pattern = re.compile(r"root@[A-Za-z0-9.]")
    for script in TUNNEL_SCRIPTS:
        text = _read(script)
        assert not pattern.search(text), f"{script.name} 里把 root 当成了登录目标"


def test_scripts_never_use_password_auth() -> None:
    """隧道必须走 key 登录 —— 口令既不安全也会把口令写进脚本。"""
    for script in TUNNEL_SCRIPTS:
        text = _read(script)
        assert "sshpass" not in text, f"{script.name} 里出现了 sshpass"


def test_local_machine_must_hold_the_tunnel_key() -> None:
    """本机必须**有**那把隧道钥匙 —— 缺了要早失败，别等运行时才发现。

    ⚠️ 这是**工作站**断言：CI runner 上本来就没有这把钥匙 ⇒ CI 跳过。
       守护的对象是"开发/采集机上不该缺"，不是"CI 上也该有"。
    """
    if os.getenv("CI", "").lower() in {"1", "true", "yes"}:
        pytest.skip("CI runner 本来就没有采集机私钥，这个断言只对工作站成立")
    key_path = Path.home() / ".ssh" / TUNNEL_KEY_NAME
    assert key_path.exists(), f"本机缺少隧道私钥：{key_path}"


def test_docs_map_lists_the_ssh_access_doc() -> None:
    """入口文档必须能指向这份真源 —— 否则 agent 根本找不到它。"""
    agents_md = _read(PROJECT_ROOT / "AGENTS.md")
    assert "SSH_ACCESS.md" in agents_md, "AGENTS.md 的文档地图里没有 SSH_ACCESS.md"

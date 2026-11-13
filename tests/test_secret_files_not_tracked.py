"""密钥文件**不再被跟踪** + 密钥门禁**真的拦得住**的守护（2026-11-13，批次 C2）。

事故背景
--------
公开仓库（GitHub ``timberdayz/timber_dayz`` = **PUBLIC**）里长期跟踪着：

* ``.env.production.passwords.txt`` —— 生产密钥备份（5 个密钥）；
* ``.env.cleaned`` —— 部署临时产物，里面带着 ``ACCOUNT_ENCRYPTION_KEY``；
* ``accounts.enc`` —— 加密的**店铺账号档案**（15 个 Amazon / Shopee / TikTok
  店铺账号，带密码、邮箱密码、手机号、代理配置）。

⇒ **密文与解密它的密钥同时公开** ⇒ 实测可以用公开仓库里的
   ``.env.cleaned`` 直接解开 ``accounts.enc``（见 STATUS.md 的取证记录）。

而仓库**自带**的密钥门禁 ``scripts/check_precommit_secrets.py`` 当时的
``is_blocked()`` 只拦「文件名**恰好**是 ``.env``」与「后缀是 ``.key`` / ``.enc``」
⇒ 上面三个文件**全部绕过**（``.txt`` 后缀、名字又不恰好是 ``.env``）。
**这道门禁本该在初始提交时就拦住它，实际没有。**

本文件锁四件事
--------------
1. 这些文件**不在** git 的跟踪清单里（取消跟踪不能回退）；
2. 门禁 ``is_blocked()`` 对它们**一律判拦**；
3. 门禁**不误伤**正常文件（模板、样例、文档、脚本）——
   门禁太宽 ⇒ 大家习惯性 ``--no-verify`` ⇒ 门禁等于没有；
4. ``.gitignore`` 真的把它们挡在仓库外。

⚠️ 历史里的副本**撤不掉**（``git filter-repo`` 会作废全部已发布 tag）
⇒ 「取消跟踪」只止血，**轮换仍是必须** —— 见 STATUS.md 的待拍板清单。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_precommit_secrets import is_blocked  # noqa: E402


#: 曾经被公开跟踪、如今**不许再被跟踪**的文件。
MUST_NOT_BE_TRACKED = (
    ".env.production.passwords.txt",
    ".env.cleaned",
    "accounts.enc",
    "frontend/.env.development",
)

#: 这些是**模板/样例/无密钥的运行期配置** —— 门禁必须放行。
MUST_BE_ALLOWED = (
    ".env.example",
    ".env.template",
    "env.template",
    "env.production.example",
    "config/production.example.env",
    # 限流器运行期配置（纯 ASCII、只有一个开关、无口令）
    ".env.limiter",
    # 文档与脚本名字里带 password/secret 是正常的 —— 不能一刀切
    "docs/deployment/PASSWORD_AND_REGISTRY_CHECK.md",
    "scripts/reset_passwords.py",
    "scripts/check_passwords_and_registry.py",
)


def _git(*args: str) -> str:
    """跑 git 并按 **utf-8** 解码。

    ⚠️ 必须显式指定编码：仓库里有中文文件名，Windows 默认的 gbk 解码会抛
       ``UnicodeDecodeError``（本文件第一次写时就踩到了）。
    """
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout


def _tracked_files() -> set[str]:
    return set(_git("ls-files").splitlines())


# ---------------------------------------------------------------------------
# 1. 不许再被跟踪
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative_path", MUST_NOT_BE_TRACKED)
def test_secret_file_is_not_tracked_by_git(relative_path: str) -> None:
    """这些文件**不许**出现在 git 的跟踪清单里。"""
    tracked = _tracked_files()
    assert (
        relative_path not in tracked
    ), f"{relative_path} 又被跟踪了 —— 它含密钥或账号密文，公开仓库里不可出现"


def test_no_tracked_file_matches_the_secret_gate() -> None:
    """**被跟踪**的文件里，不许有任何��个会被密钥门禁拦下的。

    ⚠️ 这是「全仓一次扫」的守护 —— 比逐个断言更强：
    以后谁再提交一个 ``.env.something`` 或 ``xxx.passwords.txt``，
    这条就会红。
    """
    offenders = sorted(
        path for path in _tracked_files() if is_blocked(PROJECT_ROOT / path)
    )
    assert not offenders, f"被跟踪文件里有会被密钥门禁拦下的：{offenders}"


# ---------------------------------------------------------------------------
# 2. 门禁拦得住
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative_path", MUST_NOT_BE_TRACKED)
def test_secret_gate_blocks_the_known_leaking_files(relative_path: str) -> None:
    """门禁必须对这几个文件**判拦** —— 这正是当年漏掉的那几条。"""
    assert is_blocked(PROJECT_ROOT / relative_path) is True


@pytest.mark.parametrize(
    "file_name",
    [
        ".env",
        ".env.local",
        ".env.production",
        ".env.cleaned",
        ".env.production.passwords.txt",
        ".env.limiter_backup",
        "my_passwords.txt",
        "secrets.json",
        "db_credentials.yaml",
        "accounts.enc",
        "secure_account_key.key",
        "server.pem",
    ],
)
def test_secret_gate_blocks_sensitive_name_patterns(file_name: str) -> None:
    """按**规则**拦，不是逐个文件名补 —— 新名字也拦得住。"""
    assert is_blocked(PROJECT_ROOT / file_name) is True


# ---------------------------------------------------------------------------
# 3. 门禁不误伤
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative_path", MUST_BE_ALLOWED)
def test_secret_gate_allows_templates_and_harmless_files(relative_path: str) -> None:
    """模板、样例、文档、脚本必须**放行**。

    ⚠️ 门禁太宽比没有门禁更糟：大家会开始习惯性 ``--no-verify``，
       于是门禁彻底失效 —— 所以这条必须钉死。
    """
    assert is_blocked(PROJECT_ROOT / relative_path) is False


# ---------------------------------------------------------------------------
# 4. .gitignore 真的挡住了
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative_path", MUST_NOT_BE_TRACKED)
def test_gitignore_blocks_the_secret_files(relative_path: str) -> None:
    """``.gitignore`` 必须让这些文件进不来（取消跟踪后它们还在本地）。"""
    result = subprocess.run(
        ["git", "check-ignore", "-q", relative_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, f"{relative_path} 没有被 .gitignore 挡住"


def test_gitignore_still_allows_env_limiter() -> None:
    """``.env.limiter`` 是限流器的运行期配置 ⇒ 必须**继续**入库。"""
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env.limiter"],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    assert (
        result.returncode != 0
    ), ".env.limiter 被 .gitignore 挡住了 —— 限流器会读不到它"


# ---------------------------------------------------------------------------
# 5. 镜像构建上下文也不许带这些文件
# ---------------------------------------------------------------------------


def _dockerignore_excludes(relative_path: str) -> bool:
    """按 ``.dockerignore`` 的规则判断这个文件**会不会进镜像**。

    ⚠️ 自己实现匹配，而不是断言文本 —— 断言"文件里有某一行"
       只锁住了写法，锁不住**行为**。

    支持的规则形态（Docker 语义）：
    * ``*``  —— 任意字符（不跨 ``/``）；
    * ``**`` —— 跨目录；
    * ``?``  —— 单个字符；
    * 末尾 ``/`` —— 只匹配目录；
    * ``!`` 前缀 —— 否定（后出现的规则覆盖先出现的）。
    """
    import re

    lines = [
        line.strip()
        for line in (PROJECT_ROOT / ".dockerignore")
        .read_text(encoding="utf-8", errors="ignore")
        .splitlines()
    ]

    excluded = False
    for raw in lines:
        if not raw or raw.startswith("#"):
            continue
        negated = raw.startswith("!")
        pattern = raw[1:] if negated else raw
        pattern = pattern.rstrip("/")
        if not pattern:
            continue

        regex = ""
        index = 0
        while index < len(pattern):
            char = pattern[index]
            if char == "*":
                if pattern[index : index + 2] == "**":
                    regex += ".*"
                    index += 2
                    continue
                regex += "[^/]*"
            elif char == "?":
                regex += "[^/]"
            else:
                regex += re.escape(char)
            index += 1

        if re.fullmatch(regex, relative_path):
            excluded = not negated

    return excluded


@pytest.mark.parametrize("relative_path", MUST_NOT_BE_TRACKED)
def test_dockerignore_blocks_the_secret_files(relative_path: str) -> None:
    """镜像构建上下文也不许带这些文件。

    ⚠️ 镜像层是**可被 pull 下来解开**的 —— 密钥进了镜像等于发布到了镜像仓库。
    Dockerfile.backend 用的是 ``COPY . .`` ⇒ 只靠 ``.dockerignore`` 挡。
    """
    assert (
        _dockerignore_excludes(relative_path) is True
    ), f"{relative_path} 会被打进镜像 —— 密钥进了镜像层就等于公开了"


def test_dockerignore_excludes_env_family_but_keeps_templates() -> None:
    """``.env`` 家族进镜像，但**模板**要留（模板是给人看的，不是密钥）。"""
    assert _dockerignore_excludes(".env.cleaned") is True
    assert _dockerignore_excludes(".env.production.passwords.txt") is True
    assert _dockerignore_excludes(".env.example") is False
    assert _dockerignore_excludes(".env.template") is False

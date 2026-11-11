#!/usr/bin/env python3
"""PowerShell **env 文件读取**的编码契约守护(纯源码, 不执行脚本)。

为什么要有这个守护
------------------
2026-11-11 在采集机上实测踩到的坑:

Windows PowerShell 5.1 读**无 BOM** 的文件时, 默认按**系统 ANSI 代码页**解码
(中文机器上是 GBK)。而 ``.env`` 系列文件里**有中文注释块** ⇒
GBK 解码把那些行解坏 ⇒ 解析中断 ⇒ **中文注释之后的每一个变量都被静默丢弃**。

实测证据(采集机 ``.env.collection.local``)::

    不带 -Encoding  => 只导入 12 个变量, SHOP_IDENTITY_* 三个全丢
    带 -Encoding UTF8 => 全部导入(2026-12-01 / 0 / 1 都在)

丢变量的后果不是"少配一个开关"这么轻: 采集机的 compose 插值**优先取进程环境变量**
⇒ 变量没进进程环境 ⇒ 容器拿到的就是空值 ⇒ **看起来配了、其实没生效**。

守护的底线
----------
1. **读 env 文件必须显式指定编码** —— 且必须是 ``UTF8``(这些文件是无 BOM 的 UTF-8);
2. **凡是文件里有非 ASCII 字节**, 就必须有这条约束(纯 ASCII 文件没有 GBK 陷阱,
   但统一写上更省心, 也避免以后有人加中文注释时重新踩坑);
3. 两处 ``Import-EnvFile`` 必须**同步** —— 它们本来就互相引用("kept in sync"),
   一个改了另一个不改 ⇒ 行为分叉。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 会读 env 文件的脚本(两个都要有 Import-EnvFile)。
ENV_READER_SCRIPTS = (
    PROJECT_ROOT / "scripts" / "start_collection_formal.ps1",
    PROJECT_ROOT / "scripts" / "watch_cloud_sync_tunnel.ps1",
)

#: 匹配 Import-EnvFile 整个函数体(到下一个顶层 function/结束为止)。
_FUNCTION_RE = re.compile(
    r"function\s+Import-EnvFile\s*\{(?P<body>.*?)\n\}",
    re.DOTALL,
)

#: 匹配函数体里的 Get-Content 调用。
_GET_CONTENT_RE = re.compile(r"Get-Content\b[^\n]*")


def _function_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _FUNCTION_RE.search(text)
    assert match, "%s 里找不到 Import-EnvFile" % path.name
    return match.group("body")


@pytest.mark.parametrize("script_path", ENV_READER_SCRIPTS, ids=lambda p: p.name)
def test_import_env_file_reads_with_explicit_utf8(script_path: Path) -> None:
    """读 env 文件必须显式 ``-Encoding UTF8``。"""
    body = _function_body(script_path)
    calls = _GET_CONTENT_RE.findall(body)
    assert calls, "%s 的 Import-EnvFile 里没有 Get-Content" % script_path.name
    for call in calls:
        msg = "Import-EnvFile 读文件没指定编码: %s (当前 %r)" % (
            script_path.name,
            call.strip(),
        )
        assert "-Encoding" in call, msg
        msg = "Import-EnvFile 必须用 UTF8: %s (当前 %r)" % (
            script_path.name,
            call.strip(),
        )
        assert "UTF8" in call.upper(), msg


@pytest.mark.parametrize("script_path", ENV_READER_SCRIPTS, ids=lambda p: p.name)
def test_script_files_are_bomless_utf8(script_path: Path) -> None:
    """这些 .ps1 必须是**无 BOM 的 UTF-8** —— ``-Encoding UTF8`` 才对得上。"""
    raw = script_path.read_bytes()
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    msg = "%s 不该带 BOM(PS 5.1 带 BOM 会走 UTF-8 分支, 与无 BOM 文件行为不一致)" % (
        script_path.name,
    )
    assert not has_bom, msg
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        pytest.fail("%s 不是合法 UTF-8: %s" % (script_path.name, exc))


@pytest.mark.parametrize("script_path", ENV_READER_SCRIPTS, ids=lambda p: p.name)
def test_env_reader_uses_literal_path(script_path: Path) -> None:
    """用 ``-LiteralPath`` —— 路径含 ``[`` / ``]`` 时 ``-Path`` 会被当成通配符。"""
    body = _function_body(script_path)
    calls = _GET_CONTENT_RE.findall(body)
    for call in calls:
        assert (
            "-LiteralPath" in call
        ), "%s 的 Import-EnvFile 应用 -LiteralPath(当前 %r)" % (
            script_path.name,
            call.strip(),
        )


def test_both_env_readers_stay_in_sync() -> None:
    """两个脚本的 Import-EnvFile 必须**同步** —— 它们本来就互相引用。"""
    bodies = {
        script_path.name: _function_body(script_path)
        for script_path in ENV_READER_SCRIPTS
    }
    get_content_calls = {
        name: sorted(_GET_CONTENT_RE.findall(body)) for name, body in bodies.items()
    }
    values = list(get_content_calls.values())
    msg = "两个 Import-EnvFile 的 Get-Content 写法不一致: %s" % get_content_calls
    assert values[0] == values[1], msg

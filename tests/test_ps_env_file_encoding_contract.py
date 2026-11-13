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

第四条底线(2026-11-13 补)：**.ps1 脚本本身必须无 BOM**。
------------------------------------------------------------------
2026-11-13 实测踩到：v7.26.0 发版提交给 ``watch_cloud_sync_tunnel.ps1``
补了 UTF-8 BOM, 理由写的是"仓库既有用例全带 BOM" —— **与事实相反**：
本仓库 27 个受跟踪的 ``.ps1`` 里 26 个无 BOM, 只有它一个带。
而 2026-11-11 的方案明写的是「仓库 .ps1 **全部无 BOM**, 看门狗脚本
**刻意保持纯 ASCII**」⇒ 那一版把约定写反了。

**为什么"无 BOM + 纯 ASCII"才是安全写法**(而不是"加 BOM"):
PS 5.1 读脚本文件时, 带 BOM 才按 UTF-8 解码, 不带 BOM 就按**系统 ANSI
代码页**(中文机器 = GBK)解码 ⇒ 脚本里的非 ASCII 字节(哪怕只是一个 ⚠️)
会被误解码 ⇒ 轻则注释乱码, 重则破坏语法。
⇒ 与其给脚本加 BOM(那会让整个仓库 27 个 .ps1 出现两种约定),
不如让**看门狗脚本回到纯 ASCII** —— 这正是 2026-11-11 方案的原话。

本文件是这条约定的**唯一真源**, 任何改动都必须让下面两条守护重新变绿。
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

#: 看门狗脚本 —— 它由计划任务每 2 分钟拉起, 跑在**采集机**上(GBK 代码页)。
#:
#: 它必须**纯 ASCII**: PS 5.1 读**无 BOM** 脚本时按系统 ANSI 代码页解码,
#: 非 ASCII 字节会被误解码(轻则注释乱码, 重则破坏语法)。
#: ⇒ 约定是「无 BOM + 纯 ASCII」, 而不是给脚本补 BOM。
WATCHDOG_PATH = PROJECT_ROOT / "scripts" / "watch_cloud_sync_tunnel.ps1"

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


def test_watchdog_script_is_pure_ascii() -> None:
    """看门狗脚本必须**纯 ASCII**(注释与输出都是英文)。

    为什么这条比"补 BOM"更根本:
    PS 5.1 读**无 BOM** 脚本时按系统 ANSI 代码页解码(采集机是 GBK)⇒ 脚本里的
    非 ASCII 字节(哪怕只是一个 ⚠️)会被误解码, 轻则注释乱码、重则破坏语法。
    ⇒ 约定是「无 BOM + 纯 ASCII」——而不是给脚本补 BOM 让它走 UTF-8 分支。

    ⚠️ 2026-11-13 实测: v7.25.0 那批给它加了一个 ⚠️(SSH 访问真源文档的引用),
    v7.26.0 那批用"补 BOM"去兜 ⇒ 双重违约(既非纯 ASCII, 又破了无 BOM 约定),
    而 CI 的根契约清单里**没有本文件** ⇒ 两批都没被门禁拦住。
    """
    raw = WATCHDOG_PATH.read_bytes()
    offenders = sorted({byte for byte in raw if byte > 0x7F})
    msg = "看门狗脚本必须保持纯 ASCII(PS 5.1 按 GBK 解码无 BOM 脚本, 非 ASCII 字节会误解码); 发现高位字节: %s" % (
        [hex(byte) for byte in offenders],
    )
    assert not offenders, msg


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

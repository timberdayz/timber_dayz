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

第四条底线(2026-11-13 补)：**.ps1 的编码规则按「形态」分, 不是一句话**。
------------------------------------------------------------------
同一个 ``.ps1`` 在两个环境里有**两种合法形态**, 编码要求相反:

* **仓库形态**(开发机 / CI / GitHub):**不带 BOM**。
* **采集机形态**(本机, ``output/local_adaptations.py`` 管理的 30 项):
  在远端内容上**加 UTF-8 BOM**。

2026-11-13 两批实测把这条规则写反过两次, 值得完整记下来:

· v7.25.0(e2103f46)给看门狗 ``watch_cloud_sync_tunnel.ps1`` 加了一个 ⚠️
  ⇒ 该脚本不再是纯 ASCII;
· v7.26.0(05a359a1)给它补了 UTF-8 BOM 并**写进了仓库** —— 那是把采集机
  专属形态泄漏进仓库; 而仓库当时的 27 个受跟踪 .ps1 全部**不带** BOM;
· 之后(341441d6)把看门狗改成纯 ASCII + 无 BOM —— **这一版是对的**, 本文件保留它。

⚠️ 同一批里出现过"仓库 27 个 .ps1 里 26 个无 BOM"的统计, **与事实相反**:
实测 HEAD 里 27 个 .ps1 **全部无 BOM**。照那个统计去给中文脚本去 BOM,
会把乱码从注释扩散到代码。

**真实规则(以 PS 5.1 的实际行为为准, 已在本采集机实测)**:

1. **含非 ASCII 字节的 .ps1 ⇒ 在采集机上必须带 UTF-8 BOM**。
   PS 5.1 读脚本文件: 带 BOM ⇒ 按 UTF-8 解码; 不带 BOM ⇒ 按**系统 ANSI
   代码页**解码。采集机是 zh-CN / **936(GBK)** ⇒ 无 BOM 的中文脚本会被
   误解码: 实测 ``start_collection_formal.ps1`` 去掉 BOM 后, 注释
   「逐个停, 不能用一条 docker stop 带多个容器」变成乱码「閫愪釜鍋滐紝...」;
   而 CP936 解码器还会**吞掉某些多字节序列后面的换行** ⇒ 注释行与下一行合并
   ⇒ 语句被注释掉 ⇒ 脚本死在解析器(现场见 ``output/local_adaptations.py``)。
2. **纯 ASCII 的 .ps1 ⇒ 无 BOM 也安全**(任何代码页解出同一结果)。
3. **看门狗 ``watch_cloud_sync_tunnel.ps1`` 必须纯 ASCII 且无 BOM** ——
   它由计划任务每 2 分钟拉起(``\\XihongCloudSyncTunnelWatchdog``),
   跑在采集机(GBK 代码页)上, 且是 v7.25.0 那次事故的源头。

⚠️ **"给中文 .ps1 去 BOM" 不是修法** —— 那只会把乱码从注释扩散到代码。

本文件是这条约定的**唯一真源**, 任何改动都必须让下面几条守护重新变绿。
"""

from __future__ import annotations

import re
import subprocess
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


def _skip_worktree_paths() -> set:
    """本地适配文件集合（git 标记了 ``skip-worktree`` 的那些路径）。

    为什么需要区分「本地适配」：同一个 ``.ps1`` 在两个环境里有**两种合法形态**，
    编码规则相反：

    * **仓库形态**（开发机 / CI / GitHub）：**不带 BOM**；
    * **采集机形态**（本机，``output/local_adaptations.py`` 管理的 30 项）：
      在远端内容上**加 UTF-8 BOM**，否则 PS 5.1 按 936/GBK 解码会吞换行、
      让脚本死在解析器。

    ⇒ 守护必须按形态分别断言，不能一句话套两处。
    CI 上没有 skip-worktree 标记 ⇒ 集合为空 ⇒ 全部按仓库形态检查。
    """
    result = subprocess.run(
        ["git", "ls-files", "-v"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        return set()
    paths = set()
    for line in result.stdout.splitlines():
        flag, _, path = line.partition(" ")
        if flag == "S":
            # git 用正斜杠; Windows 上 Path 的 str() 是反斜杠 ⇒ 统一成正斜杠再比。
            paths.add(path.strip().replace("\\", "/"))
    return paths


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
def test_env_reader_scripts_follow_their_form_encoding(script_path: Path) -> None:
    """按**形态**断言编码：仓库形态无 BOM；采集机形态（含非 ASCII）带 BOM。

    为什么不是"一律无 BOM"或"一律带 BOM"：PS 5.1 读脚本文件时，
    带 BOM 才按 UTF-8 解码；不带 BOM 就按**系统 ANSI 代码页**解码 ——
    采集机是 zh-CN / **936(GBK)**，于是中文注释乱码，且 GBK 误解码存在
    吞掉行尾反斜杠、破坏脚本语法的路径（仓库自带
    ``output/local_adaptations.py`` 记录了实测到的解析失败现场）。

    ⇒ 规则按形态分：仓库形态不带 BOM，采集机形态含中文就带 BOM。
    """
    raw = script_path.read_bytes()
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    has_non_ascii = any(byte > 0x7F for byte in (raw[3:] if has_bom else raw))
    relative = script_path.relative_to(PROJECT_ROOT).as_posix()
    locally_adapted = relative in _skip_worktree_paths()
    if locally_adapted:
        if has_non_ascii:
            assert has_bom, (
                "%s 是采集机本地适配文件且含非 ASCII 字节, 却没有 UTF-8 BOM —— "
                "PS 5.1 会按 936/GBK 解码, 乱码甚至让脚本死在解析器" % script_path.name
            )
    else:
        assert not has_bom, (
            "%s 是仓库形态, 不该带 BOM(采集机需要的 BOM 由本地适配提供)"
            % script_path.name
        )
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
    assert not raw.startswith(
        b"\xef\xbb\xbf"
    ), "看门狗脚本不该带 BOM —— 纯 ASCII + 无 BOM 在任何代码页下都解出同一结果"


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


# ---------------------------------------------------------------------------
# 仓库级防线: 任何含非 ASCII 的 .ps1 都必须带 UTF-8 BOM
# ---------------------------------------------------------------------------

#: 扫描仓库 .ps1 时跳过的目录(依赖目录 / 运行期产物)。
_PS1_SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "logs",
    "node_modules",
    "output",
    "temp",
    "venv",
}


def _iter_repo_ps1():
    """仓库内全部 ``.ps1``(跳过依赖目录与运行期产物)。"""
    found = []
    for path in sorted(PROJECT_ROOT.rglob("*.ps1")):
        relative = path.relative_to(PROJECT_ROOT)
        if set(relative.parts) & _PS1_SKIP_DIRS:
            continue
        found.append(relative)
    return found


def test_repo_form_ps1_have_no_bom() -> None:
    """仓库形态：非本地适配的 ``.ps1`` 一律**不带 BOM**。

    仓库形态不带 BOM ⇒ 开发机 / CI / GitHub 上的文件与远端一致；
    采集机需要的 BOM 由**本地适配**提供（``output/local_adaptations.py``）。

    ⇒ 仓库里出现 BOM = 把采集机专属形态泄漏进了仓库
    （v7.26.0 的 ``05a359a1`` 就干过一次：给看门狗补 BOM 并写进了仓库）。
    """
    adapted = _skip_worktree_paths()
    offenders = []
    for relative in _iter_repo_ps1():
        if relative.as_posix() in adapted:
            continue
        raw = (PROJECT_ROOT / relative).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            offenders.append(relative.as_posix())
    assert not offenders, (
        "仓库形态的 .ps1 不该带 BOM(采集机要的 BOM 属本地适配, 不入库): %s" % offenders
    )


def test_locally_adapted_ps1_with_non_ascii_keep_utf8_bom() -> None:
    """采集机形态：本地适配且含非 ASCII 的 ``.ps1`` **必须带 UTF-8 BOM**。

    这是采集机实测过的解析失败防线（现场记录在
    ``output/local_adaptations.py`` 的说明里）：PS 5.1 对无 BOM 的 ``.ps1``
    按 936/GBK 解码，CP936 解码器会吞掉某些多字节序列后面的换行 ⇒
    注释行与下一行合并 ⇒ 语句被注释掉 ⇒ 脚本死在解析器。

    CI 上没有 skip-worktree 标记 ⇒ 本条在 CI 上空跑（绿）；
    在采集机本地跑 pytest 就能抓到"适配被弄丢"。
    """
    adapted = _skip_worktree_paths()
    offenders = []
    for relative in _iter_repo_ps1():
        if relative.as_posix() not in adapted:
            continue
        raw = (PROJECT_ROOT / relative).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            continue
        if any(byte > 0x7F for byte in raw):
            offenders.append(relative.as_posix())
    assert not offenders, (
        "这些本地适配的 .ps1 含非 ASCII 却没有 UTF-8 BOM —— 采集机(936/GBK)上"
        "PS 5.1 会误解码, 甚至让脚本死在解析器: %s" % offenders
    )

"""仓库形态 ``.ps1`` 的卫生守护（2026-11-14）。

锁住三件事
----------

1. **仓库形态的 ``.ps1`` 不得硬编码凭据。**
   仓库是**公开**的（见 ``docs/guides/ENV_FILE_CONTRACT.md``），
   脚本里写死的密码等于公开密码。
   凭据一律运行时解析：``.env`` / 环境变量 / 显式参数。

2. **``sync_templates_to_cloud.ps1`` 必须纯 ASCII 且无 BOM。**
   文件无 BOM + 工作站 ANSI 代码页为 GBK 时，PowerShell 5.1 会把 UTF-8
   字节按 GBK 解码，中文字节可能破坏引号配对 ⇒ **假语法错误**
   （实测：该脚本在 GBK 代码页下静态解析报 2 处 "缺少右 }"，而按 UTF-8
   读取后解析完全正常）。ASCII 字节在任何代码页下解码一致。

3. **仓库形态 ``.ps1`` 一律无 BOM。**
   BOM 属采集机本地适配形态，不入库。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"

#: 本次改造过的模板同步脚本（凭据来源 + ASCII 形态都要守住）。
SYNC_TEMPLATES_SCRIPT = SCRIPTS_DIR / "sync_templates_to_cloud.ps1"

#: 形如 ``PASSWORD = "xxx"`` 的**非空**字面量。
#: 排除空串与变量引用（``$FOO`` / ``${FOO}``）。
HARDCODED_CREDENTIAL_PATTERN = re.compile(
    r"""(?i)\b(password|passwd|pwd|secret|token)\b\s*=\s*["']([^"'$]{3,})["']"""
)

#: 仓库形态的 .ps1 脚本清单（排除备份目录与本机适配脚本）。
_LOCAL_ONLY_DIRS = {"backups", "temp", "logs", "node_modules", ".git"}


def _repo_ps1_files() -> List[Path]:
    if not SCRIPTS_DIR.is_dir():
        return []
    files: List[Path] = []
    for path in sorted(SCRIPTS_DIR.rglob("*.ps1")):
        relative_parts = set(path.relative_to(REPO_ROOT).parts)
        if relative_parts & _LOCAL_ONLY_DIRS:
            continue
        files.append(path)
    return files


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _has_utf8_bom(data: bytes) -> bool:
    return data[:3] == b"\xef\xbb\xbf"


# ---------------------------------------------------------------------------
# 1. 硬编码凭据
# ---------------------------------------------------------------------------
def test_repo_ps1_scripts_contain_no_hardcoded_credentials():
    """``scripts/`` 下的 .ps1 不得出现非空凭据字面量。"""
    offenders = []
    for path in _repo_ps1_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in HARDCODED_CREDENTIAL_PATTERN.finditer(text):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)[:60]}")
    assert not offenders, "仓库 .ps1 脚本出现硬编码凭据（仓库是公开的）: " + "; ".join(
        offenders
    )


def test_sync_templates_script_resolves_credentials_from_env():
    """模板同步脚本必须从 ``.env`` / 环境变量取密码，而不是写死。"""
    text = SYNC_TEMPLATES_SCRIPT.read_text(encoding="utf-8")
    assert "Resolve-LocalDatabaseSettings" in text, "缺少运行时凭据解析函数"
    assert "DATABASE_URL" in text, "未从 DATABASE_URL 解析连接信息"
    assert "PGPASSWORD" in text, "未保留 PGPASSWORD 回退"
    assert not HARDCODED_CREDENTIAL_PATTERN.search(text), "仍存在凭据字面量"


# ---------------------------------------------------------------------------
# 2. ASCII 形态（sync_templates_to_cloud.ps1）
# ---------------------------------------------------------------------------
def test_sync_templates_script_is_pure_ascii_without_bom():
    """纯 ASCII + 无 BOM ⇒ 在任意 ANSI 代码页下都能正确解析。"""
    data = _read_bytes(SYNC_TEMPLATES_SCRIPT)
    assert not _has_utf8_bom(data), "仓库形态 .ps1 不得带 UTF-8 BOM"
    non_ascii = [byte for byte in data if byte > 127]
    assert not non_ascii, (
        "sync_templates_to_cloud.ps1 含非 ASCII 字节 "
        f"({len(non_ascii)} 个): 无 BOM + GBK 代码页下会被误解码并破坏语法"
    )


def test_sync_templates_script_parses_under_ansi_code_page():
    """在 GBK(936) 代码页下静态解析必须通过（与执行同条件）。"""
    import subprocess

    script = (
        "$e = $null; "
        "$null = [System.Management.Automation.Language.Parser]::ParseFile("
        "'"
        + str(SYNC_TEMPLATES_SCRIPT).replace("'", "''")
        + "', [ref]$null, [ref]$e); "
        "if ($e -and $e.Count -gt 0) { $e | ForEach-Object { $_.Message }; exit 1 }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        "sync_templates_to_cloud.ps1 在 ANSI 代码页下解析失败: "
        + (completed.stdout or "")
        + (completed.stderr or "")
    )


# ---------------------------------------------------------------------------
# 3. 仓库形态一律无 BOM
# ---------------------------------------------------------------------------
def test_repo_ps1_scripts_have_no_utf8_bom():
    """BOM 属采集机本地适配形态，不入库。"""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _repo_ps1_files()
        if _has_utf8_bom(_read_bytes(path))
    ]
    assert not offenders, "仓库形态 .ps1 不得带 UTF-8 BOM: " + "; ".join(offenders)

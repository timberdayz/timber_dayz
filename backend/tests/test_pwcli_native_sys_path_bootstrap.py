from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_probe(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    probe = REPO_ROOT / "modules" / "utils" / "pwcli_native.py"
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, "-c", code, str(probe), *args],
            cwd=tmp,  # 关键：CWD 不在仓库根，否则仓库根会通过 CWD 混进 sys.path
            capture_output=True,
            text=True,
            # 子进程按 UTF-8 输出（pwcli_native 会把 stdout 重配为 UTF-8），
            # 不能用 Windows 本地代码页（cp936）解码，否则会 UnicodeDecodeError。
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )


def test_direct_script_launch_can_import_modules_package():
    """直接以脚本方式启动时，必须能 import 到 `modules.*`。

    这是生产故障的精确复现：`python modules/utils/pwcli_native.py ... --account-id X`
    时 `sys.path[0]` 是 `modules/utils`，不含仓库根 →
    `modules/utils/pwcli_native.py:320` 的延迟导入
    `from modules.utils.sessions.session_manager import SessionManager`
    抛 `ModuleNotFoundError: No module named 'modules'`。

    探针把 CWD 放在**临时目录**（不在仓库根），
    否则 `python -m pytest` 的 CWD 兜底会让这条断言今天就通过（已实测）。
    """
    code = (
        "import runpy, sys\n"
        "runpy.run_path(sys.argv[1], run_name='pwcli_probe')\n"
        "from modules.utils.sessions.session_manager import SessionManager\n"
        "print('SESSION_MANAGER_IMPORT_OK')\n"
    )
    result = _run_probe(code)
    assert result.returncode == 0, (
        "直接调用入口无法 import modules.*：\n" + (result.stderr or "")
    )
    assert "SESSION_MANAGER_IMPORT_OK" in result.stdout


def test_pwcli_native_bootstraps_repo_root_into_sys_path():
    """仓库根必须由模块**自己**放进 sys.path，而不是靠 CWD 兜底。

    判据不能写成 `repo_root in sys.path`：`python -m pytest` 会把 CWD（= 仓库根）
    放进 `sys.path`，那条断言今天就通过，守不住任何东西（已实测）。
    """
    code = (
        "import runpy, sys\n"
        "runpy.run_path(sys.argv[1], run_name='pwcli_probe')\n"
        "print('REPO_ROOT_IN_PATH=' + str(sys.argv[2] in [p.rstrip('/\\\\') for p in sys.path]))\n"
    )
    result = _run_probe(code, str(REPO_ROOT))
    assert "REPO_ROOT_IN_PATH=True" in result.stdout, (
        "pwcli_native 没有自己把仓库根放进 sys.path：\n"
        + result.stdout + (result.stderr or "")
    )


def test_direct_script_launch_does_not_fail_on_import():
    """直接以脚本方式启动时，不得出现 ModuleNotFoundError。"""
    probe = REPO_ROOT / "modules" / "utils" / "pwcli_native.py"
    result = subprocess.run(
        [sys.executable, str(probe), "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert "ModuleNotFoundError" not in (result.stderr or ""), result.stderr

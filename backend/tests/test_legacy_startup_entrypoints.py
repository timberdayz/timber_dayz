"""旧版启动入口（``build_v4271`` 快照）的委托契约。

背景
----
``build_v4271/`` 是仓库早期留下的一份**完整仓库快照**目录，里面的 ``run.py`` /
``local_run.py`` 带有 ``_delegate_to_latest_entrypoint_if_needed``：当自己不是
最新版本时，把启动委托给仓库根目录的同名脚本。

该快照目录已在 commit ``bce2551d``（"feat：321321"）随其它快照文件一并从仓库里
删除（``git ls-files build_v4271`` 现在返回空），仓库根的 ``run.py`` / ``local_run.py``
也不包含该委托函数（见下方两条断言）。

所以这里不再针对**已下线**的快照目录写运行时用例，改为钉死两条仍然成立的事实：

1. 旧快照目录不再属于仓库；
2. 仓库根启动脚本不是「旧快照入口」，不得再带委托逻辑。

⚠️ 这里只做**源码文本**断言，不导入根脚本：``run.py`` 在 import 时会调用
``load_project_env()``（把 .env 灌进进程环境），跑测试时不能有这种副作用。
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SNAPSHOT_DIR = PROJECT_ROOT / "build_v4271"
LEGACY_DELEGATE_HELPER = "_delegate_to_latest_entrypoint_if_needed"


def test_legacy_build_snapshot_directory_is_not_part_of_the_repo():
    """旧快照目录已从仓库删除（commit bce2551d），不得再被当成启动入口来源。"""
    assert not LEGACY_SNAPSHOT_DIR.exists()
    assert not (LEGACY_SNAPSHOT_DIR / "run.py").exists()
    assert not (LEGACY_SNAPSHOT_DIR / "local_run.py").exists()


def test_root_run_py_is_not_a_legacy_snapshot_entrypoint():
    """仓库根 ``run.py`` 是当前启动入口，不得带旧快照的委托逻辑。"""
    source = (PROJECT_ROOT / "run.py").read_text(encoding="utf-8")

    assert LEGACY_DELEGATE_HELPER not in source


def test_root_local_run_py_is_not_a_legacy_snapshot_entrypoint():
    """仓库根 ``local_run.py`` 同理：旧快照委托逻辑已随快照目录一起下线。"""
    source = (PROJECT_ROOT / "local_run.py").read_text(encoding="utf-8")

    assert LEGACY_DELEGATE_HELPER not in source

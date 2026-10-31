import os
import re
from pathlib import Path

from scripts.verify_remote_deploy_contracts import verify_remote_deploy_contracts

DEPLOY_SCRIPT_PATH = Path("scripts/deploy_remote_production.sh")
DOCKERFILE_BACKEND_PATH = Path("Dockerfile.backend")

# 部署脚本里内联 Python 的写法：python3 -c '<换行>代码<换行>'
INLINE_PYTHON_PATTERN = re.compile(r"python3 -c '\n(.*?)\n'", re.DOTALL)


def test_remote_deploy_contracts_require_no_build_and_image_overrides():
    assert verify_remote_deploy_contracts() is True


def test_deploy_script_rebuilds_view_definitions():
    """视图**定义**变更必须显式重建。

    数据刷新流程与 dashboard bootstrap 都会跳过「已存在的普通视图」
    （recreate_views=False），生产又关掉了启动自愈
    （AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP=false）——
    少了这一步，改过的 sql/ 资产部署完也不会生效。
    """
    source = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "python3 /app/scripts/rebuild_views.py" in source
    assert "api.clearance_ranking_module" in source
    # 目标清单可覆盖 ⇒ 以后有新视图资产变更不用改脚本
    assert "DEPLOY_REBUILD_VIEW_TARGETS" in source
    # 重建后必须再确认视图确实存在：rebuild_views.py 对「目标不在库里」
    # 会跳过并返回 0 —— 那是静默成功，部署不能当成成功。
    assert "-e REBUILD_VERIFY_TARGETS" in source


def test_view_rebuild_runs_before_application_layer_starts():
    """重建必须早于应用层启动，否则旧定义会先上线一轮。"""
    source = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    rebuild_index = source.index("python3 /app/scripts/rebuild_views.py")
    app_start_index = source.index(
        "up -d --no-build --no-deps backend-api celery-worker celery-beat"
    )
    assert rebuild_index < app_start_index


def test_backend_image_contains_view_rebuild_script():
    """重建脚本必须在后端镜像里（容器内执行）。"""
    dockerfile = DOCKERFILE_BACKEND_PATH.read_text(encoding="utf-8")

    assert "COPY scripts/rebuild_views.py /app/scripts/rebuild_views.py" in dockerfile


def test_inline_python_blocks_in_deploy_script_compile():
    """部署脚本里的内联 Python 必须能编译。

    这些代码只在生产容器里执行，本地不会跑到 ⇒ 语法错误（比如漏 import）
    只会在发版那一刻炸。在这里提前挑出来。
    """
    source = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    blocks = INLINE_PYTHON_PATTERN.findall(source)
    assert blocks, "deploy script should contain inline python blocks"

    for block in blocks:
        compile(block, "<deploy-inline-python>", "exec")


def test_inline_python_using_asyncio_imports_it():
    """用了 asyncio.run 的内联块必须 import asyncio。

    漏 import 编译期查不出来，只在运行时抛 NameError —— 而那时已经在生产发版了。
    """
    source = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    blocks = INLINE_PYTHON_PATTERN.findall(source)
    assert blocks

    for block in blocks:
        if "asyncio.run" in block:
            assert (
                "import asyncio" in block
            ), "内联 Python 用了 asyncio.run 却没 import asyncio"


def test_deploy_script_rebuilds_both_inventory_layers():
    """库龄层与状态层都要在部署时重建。

    状态层 `mart.inventory_state` 是「距上次进货天数」的**唯一来源**，
    它是表不是视图 —— SQL 资产重建只会 CREATE TABLE IF NOT EXISTS，灌不进数据。
    部署时少了这一步 → 空表 → 滞销榜恒 0 行（§3.9.11）。
    """
    source = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    assert (
        "python3 /app/scripts/rebuild_inventory_age_from_snapshots.py --full-rebuild"
        in source
    )
    assert (
        "python3 /app/scripts/rebuild_inventory_state_from_snapshots.py --full-rebuild"
        in source
    )


def test_backend_image_contains_inventory_rebuild_scripts():
    """两个重建脚本都必须在后端镜像里（部署时在容器内执行）。"""
    dockerfile = DOCKERFILE_BACKEND_PATH.read_text(encoding="utf-8")

    assert (
        "COPY scripts/rebuild_inventory_age_from_snapshots.py "
        "/app/scripts/rebuild_inventory_age_from_snapshots.py" in dockerfile
    )
    assert (
        "COPY scripts/rebuild_inventory_state_from_snapshots.py "
        "/app/scripts/rebuild_inventory_state_from_snapshots.py" in dockerfile
    )


def test_inventory_state_rebuild_script_dry_run_lists_targets():
    """新脚本必须能真正跑起来（--dry-run 只打印目标，不连库）。

    脚本只在生产容器里执行 ⇒ 本地跑不通的语法/导入错误只会在发版那一刻炸。
    """
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/rebuild_inventory_state_from_snapshots.py",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert "semantic.fact_inventory_snapshot" in result.stdout
    assert "mart.inventory_state" in result.stdout

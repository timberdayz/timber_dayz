import os
import re
from pathlib import Path

from scripts.verify_remote_deploy_contracts import verify_remote_deploy_contracts

DEPLOY_SCRIPT_PATH = Path("scripts/deploy_remote_production.sh")
DOCKERFILE_BACKEND_PATH = Path("Dockerfile.backend")
COMPOSE_PROD_PATH = Path("docker-compose.prod.yml")
COMPOSE_CLOUD_PATH = Path("docker-compose.cloud.yml")

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
    assert "api.business_overview_inventory_backlog_module" in source
    # 目标清单可覆盖 ⇒ 以后有新视图资产变更不用改脚本
    assert "DEPLOY_REBUILD_VIEW_TARGETS" in source
    # 重建后必须再确认视图确实存在：rebuild_views.py 对「目标不在库里」
    # 会跳过并返回 0 —— 那是静默成功，部署不能当成成功。
    assert "-e REBUILD_VERIFY_TARGETS" in source


def test_deploy_script_rebuilds_every_semantic_atomic_view():
    """部署时必须重建**全部**语义层原子层视图。

    背景：改了 ``sql/`` 里的视图定义，光部署**不会生效** ——
    数据刷新流程与 dashboard bootstrap 都跳过「已存在的普通视图」
    （``recreate_views=False``），生产又关掉了启动自愈。
    所以部署脚本的重建清单漏一个 = **这次发布对它完全白改**。

    商品/服务两条链路曾因此长期停在旧口径：占位键没拆开、
    满意度列读崩也没修好，而发布记录上却写着「已上线」。
    """
    from backend.services.data_pipeline.refresh_registry import (
        SEMANTIC_ATOMIC_VIEW_TARGETS,
    )

    source = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")
    match = re.search(r'DEFAULT_REBUILD_VIEW_TARGETS="([^"]*)"', source)
    assert match, "部署脚本缺少 DEFAULT_REBUILD_VIEW_TARGETS 定义"

    listed = set(match.group(1).split())
    missing = sorted(set(SEMANTIC_ATOMIC_VIEW_TARGETS) - listed)
    assert not missing, (
        f"语义层原子层视图 {missing} 不在部署重建清单里 ⇒ "
        "改了它们的 sql/ 资产也不会在生产生效"
    )


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


def _postgres_c_params() -> dict:
    """取 compose 里 postgres 容器实际生效的 ``-c key=value`` 参数。

    注意：这些参数写在 ``command:`` 里而不是 postgresql.conf ——
    命令行 ``-c`` 的优先级**高于** postgresql.conf，
    所以改配置文件不会生效，必须改这里。
    """
    import yaml

    data = yaml.safe_load(COMPOSE_PROD_PATH.read_text(encoding="utf-8"))
    command = data["services"]["postgres"]["command"]
    params = {}
    for item in command:
        if isinstance(item, str) and "=" in item and not item.startswith("-"):
            key, _, value = item.partition("=")
            params[key] = value
    return params


def test_production_postgres_memory_budget_is_bounded():
    """生产 PG 的内存参数必须收口，不能退回过高的默认值。

    背景：宿主机只有 7.4 GiB，openclaw 常驻 2.8 GiB，且当时 swap 为 0。
    ``work_mem × max_connections`` 的理论峰值曾是 32MB × 100 = 3.2 GiB，
    而 PG 容器上限只有 1.5 GiB ⇒ PG 已被 OOMKill 过
    （连接被重置 → nginx 记 502 → 页面打不开）。

    2026-11-05 收口后：8MB × 80 = 640 MiB，实测 PG 常驻 716 MiB → 356 MiB。
    """
    params = _postgres_c_params()

    assert params.get("work_mem") == "8MB"
    assert params.get("shared_buffers") == "256MB"
    assert params.get("effective_cache_size") == "2GB"
    assert params.get("max_connections") == "80"
    # 长查询超时不能被顺带关掉
    assert params.get("statement_timeout") == "120s"


def test_production_postgres_memory_peak_stays_under_container_limit():
    """理论峰值必须留在 PG 容器内存上限以内。

    上限来自 docker-compose.cloud.yml 的 limits（1.5 GiB）。
    """
    params = _postgres_c_params()
    work_mem_mb = int(re.match(r"(\d+)MB", params["work_mem"]).group(1))
    max_connections = int(params["max_connections"])
    peak_mb = work_mem_mb * max_connections

    assert peak_mb <= 1024, (
        f"work_mem({work_mem_mb}MB) × max_connections({max_connections}) "
        f"= {peak_mb}MB，超过 PG 容器 1.5GiB 上限的安全线 ⇒ 会被 OOMKill"
    )


def _memory_to_mb(value) -> int:
    """把 compose 的 memory 写法（``1.5G`` / ``512M`` / 字节数）统一成 MiB。"""
    text = str(value).strip()
    if text.endswith("G"):
        return int(float(text[:-1]) * 1024)
    if text.endswith("M"):
        return int(float(text[:-1]))
    if text.endswith("K"):
        return int(float(text[:-1]) / 1024)
    return int(int(text) / (1024 * 1024))


def test_cloud_postgres_memory_limit_not_raised_above_host_capacity():
    """PG 容器的内存上限不能被调高到超过宿主机能给的量。

    宿主机 7.4 GiB，openclaw 常驻 2.8 GiB 且不可停 ⇒ PG 实际可用余量有限。
    把 PG 上限抬到 4 GiB 只会让它在峰值时被 OOMKill，而不会多拿到内存。
    """
    import yaml

    data = yaml.safe_load(COMPOSE_CLOUD_PATH.read_text(encoding="utf-8"))
    limit = data["services"]["postgres"]["deploy"]["resources"]["limits"]["memory"]
    limit_mb = _memory_to_mb(limit)

    assert (
        limit_mb <= 2048
    ), f"PG 容器内存上限 {limit} 超过宿主机实际能给量（openclaw 占 2.8 GiB）"

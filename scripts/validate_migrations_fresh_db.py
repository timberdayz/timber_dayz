#!/usr/bin/env python3
"""
临时库迁移门禁脚本：在全新临时 Postgres 上执行 fail-closed current-schema migration。

用途：发布前在本地复现「从零跑全量迁移」的门禁，不触碰开发库或现有 compose 的 Postgres 卷。
用法：python scripts/validate_migrations_fresh_db.py [--port 5433]
可选参数：--port PORT  临时 Postgres 映射到本机的端口，默认 5433（避免与开发库 5432 冲突）
"""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

# 门禁脚本既可能被当成 `python scripts/validate_migrations_fresh_db.py` 运行
# (此时 sys.path[0] 是 scripts/), 也可能被 `python -m scripts.validate_...` 运行
# (此时 sys.path[0] 是仓库根) ⇒ 两种都要能 import 到同目录模块。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.bootstrap_fresh_environment import (  # noqa: E402
    PRECHECK_TARGET_REVISION,
    run_two_phase_bootstrap,
)
from scripts.bootstrap_seed_manifest import (  # noqa: E402
    build_gate_rows,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5433
DEFAULT_DOCKER_RUN_TIMEOUT_SECONDS = 180
PG_USER = "migration_test_user"
PG_PASSWORD = "migration_test_pass"
PG_DB = "migration_test_db"
IMAGE = "postgres:15"
# 固定容器名：脚本被强杀时残留的容器会保留这个名字（而不是变成一堆
# Docker 随机名），下一次运行启动前先清一次，既不会撞 name conflict，
# 也不会让孤儿容器长期占着磁盘。
TEMP_CONTAINER_NAME = "xihong_freshdb_migration_gate"

#: 第一段迁移的目标节点 —— 20261116 的**前一个**节点。
#:
#: ⚠ 取值来自 ``scripts/bootstrap_fresh_environment.py``（那里是**唯一实现**，
#: 真实新环境的引导入口与本门禁共用同一段两段式流程）；本模块通过上面的 import
#: **再导出**它，保持 ``validate_migrations_fresh_db.PRECHECK_TARGET_REVISION``
#: 这个既有入口不变（守护用例直接读这个名字）。
#:
#: 为什么要在中间停一次
#: ----------------------
#: ``20261116_add_tiktok_export_store_name_aliases`` 是**数据修复型**迁移:
#: 它给 6 个已存在的 TikTok 店铺账号补「导出店名」别名, 动手前做 fail-closed
#: 前置检查(账号存在 / 区域相符 / 已启用 / 是经营店 / 别名键没被别人认领)。
#:
#: 全新空库上 ``core.shop_accounts`` 里没有这些账号 ⇒ 前置检查必然失败
#: ⇒ 整条链在 20261116 中止 ⇒ 本门禁永远跑不通。
#:
#: 所以门禁在跑到 20261116 之前先停一下, 注入**最小前置数据**
#: (见 ``scripts/migration_gate_seed_data.py``), 让那个前置检查**有意义**,
#: 然后继续跑到 head。
#:
#: ⚠ **不采用**「改 20261116 让它在空库上 no-op」这条路:
#: 已执行过的迁移不可改; 而且那样会把「全新部署的环境里 TikTok 导出别名不存在」
#: 这个**真实部署缺陷**悄悄掩掉。

DATA_SYNC_CRITICAL_COLUMNS: dict[str, set[str]] = {
    "core.data_quarantine": {"catalog_file_id"},
    "core.staging_orders": {"file_id"},
    "core.staging_product_metrics": {"file_id"},
    "core.staging_inventory": {"file_id"},
}


def safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode("gbk", errors="ignore").decode("gbk"), flush=True)
        except Exception:
            print(msg.encode("ascii", errors="ignore").decode("ascii"), flush=True)


def run(
    cmd: list, cwd: Path = None, env: dict = None, timeout: int = 120
) -> tuple[int, str]:
    """Run command, return (returncode, combined_output)."""
    cwd = cwd or PROJECT_ROOT
    env = env or os.environ
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            env={**os.environ, **env} if isinstance(env, dict) else env,
            capture_output=True,
            text=True,
            # 子进程输出是 UTF-8（迁移日志里有中文）。Windows 上 ``text=True``
            # 默认按 GBK 解码，会抛 UnicodeDecodeError 并**把真正的迁移错误吞掉**
            # —— 迁移失败时只看到一段乱码，什么原因都看不到。
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return (r.returncode, out)
    except subprocess.TimeoutExpired:
        return (-1, "Command timed out")
    except FileNotFoundError:
        return (-1, f"Command not found: {cmd[0]}")


def find_missing_data_sync_critical_columns(conn_inspector) -> list[str]:
    missing_columns: list[str] = []

    for qualified_table, required_columns in DATA_SYNC_CRITICAL_COLUMNS.items():
        schema_name, table_name = qualified_table.split(".", 1)
        try:
            actual_columns = {
                column["name"]
                for column in conn_inspector.get_columns(table_name, schema=schema_name)
            }
        except Exception:
            continue
        for column_name in sorted(required_columns - actual_columns):
            missing_columns.append(f"{qualified_table}.{column_name}")

    return sorted(missing_columns)


def verify_data_sync_critical_columns(database_url: str) -> list[str]:
    engine = create_engine(database_url)
    try:
        conn_inspector = inspect(engine)
        return find_missing_data_sync_critical_columns(conn_inspector)
    finally:
        engine.dispose()


def verify_orm_schema_consistency(
    database_url: str,
    *,
    run_command=run,
) -> str:
    code, output = run_command(
        ["python", "scripts/verify_schema_consistency.py", "--ignore-schema"],
        env={"DATABASE_URL": database_url},
        timeout=120,
    )
    return "" if code == 0 else output


def build_temp_postgres_run_command(port: int) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        TEMP_CONTAINER_NAME,
        "-e",
        f"POSTGRES_USER={PG_USER}",
        "-e",
        f"POSTGRES_PASSWORD={PG_PASSWORD}",
        "-e",
        f"POSTGRES_DB={PG_DB}",
        "-p",
        f"{port}:5432",
        IMAGE,
    ]


def remove_leftover_temp_container(run_command=run) -> bool:
    """清掉上一次运行被中断留下的同名容器（含匿名卷）。

    没有这一步的话：脚本被强杀 → 容器残留 → 下次 `docker run` 直接报
    name conflict，门禁从此再也跑不起来。
    """
    code, _ = run_command(["docker", "rm", "-f", "-v", TEMP_CONTAINER_NAME], timeout=30)
    return code == 0


def _connect_once(database_url: str) -> Exception | None:
    """按脚本真正要用的方式连一次目标库。

    成功返回 ``None``，失败返回**异常对象**（调用方用它说明失败根因）。
    """
    engine = None
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return None
    except Exception as exc:  # noqa: BLE001 —— 连不上就是没就绪，异常类型不重要
        return exc
    finally:
        if engine is not None:
            engine.dispose()


def probe_postgres_ready(database_url: str) -> bool:
    """按**脚本真正要用的方式**探一次：TCP 连上目标库并执行 ``SELECT 1``。

    为什么不能用容器内的 ``pg_isready``
    ------------------------------------
    postgres 镜像首次启动时，entrypoint 会先起一个**只监听 unix socket** 的临时
    server 跑 initdb 与初始化脚本；这个临时 server 期间**根本不监听 TCP**。
    而容器内的 ``pg_isready`` 默认走 socket ⇒ 它会对临时 server 返回
    "accepting connections" ⇒ 门禁以为就绪 ⇒ 随后脚本按 TCP 连上**真** server 时，
    它还在启动过程中 ⇒ ``FATAL: the database system is starting up``。

    实测（2026-11-10）：CI run ``42842488697`` 的 ``fresh-db-drill`` 就这样随机红，
    重跑即绿 ⇒ 是**就绪判据的竞态**，不是迁移链本身的问题。

    实测（2026-11-11，本机 postgres:15-alpine 全新容器、同钟口径高频轮询 4 次）：
    socket 探针报「accepting connections」的时刻分别比 TCP 探针早
    **0.51 / 0.49 / 0.50 / 0.52 秒** ⇒ 存在一个**稳定复现的假就绪窗口**：
    这半秒里 socket 探针说「好了」，而真实 TCP 连接尚未可用
    （此时连上去只会拿到 ``FATAL: the database system is starting up``）。
    CI runner 上磁盘更慢、竞争更重 ⇒ 窗口更宽 ⇒ 表现为「随机红、重跑即绿」。

    改成直接按业务要用的方式连一次：临时 server 根本不监听 TCP ⇒ 判据与真实
    可用性一致，不存在"探针说好了、其实没好"的窗口。
    """
    return _connect_once(database_url) is None


def wait_for_postgres_ready(
    database_url: str,
    *,
    attempts: int = 60,
    delay: float = 1.0,
) -> tuple[bool, str]:
    """等临时 Postgres **真正可用**（见 :func:`probe_postgres_ready`）。

    返回 ``(是否就绪, 最后一次失败原因)`` —— 失败原因会原样打进日志，
    便于区分「还没起来」「驱动缺失」「账号密码不对」三类根因。
    """
    last_error = "unknown error"
    for index in range(attempts):
        error = _connect_once(database_url)
        if error is None:
            return True, ""
        last_error = f"{type(error).__name__}: {error}".strip()
        if index + 1 < attempts:
            time.sleep(delay)
    return False, last_error


def start_temp_postgres_container(
    port: int,
    *,
    run_command=run,
    docker_run_timeout: int = DEFAULT_DOCKER_RUN_TIMEOUT_SECONDS,
) -> str:
    code, out = run_command(
        build_temp_postgres_run_command(port),
        timeout=docker_run_timeout,
    )
    if code != 0:
        raise RuntimeError(
            out.strip() or "failed to start temporary postgres container"
        )
    container_id = (out.strip().split("\n")[0] or "").strip()
    if not container_id:
        raise RuntimeError("failed to resolve temporary postgres container id")
    return container_id


def is_docker_bind_error(message: str) -> bool:
    normalized = str(message or "").lower()
    return (
        "bind for 0.0.0.0" in normalized and "port is already allocated" in normalized
    )


def choose_temp_postgres_port(preferred_port: int) -> int:
    if preferred_port > 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("0.0.0.0", preferred_port))
                return preferred_port
            except OSError:
                pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as fallback:
        fallback.bind(("0.0.0.0", 0))
        return int(fallback.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="临时库迁移门禁：在全新临时 Postgres 上跑 current-schema migration"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"临时 Postgres 端口（默认 {DEFAULT_PORT}）",
    )
    args = parser.parse_args()
    port = choose_temp_postgres_port(args.port)
    if port != args.port:
        safe_print(f"[WARN] 端口 {args.port} 已被占用，改用临时端口 {port}")

    safe_print(f"[INFO] 启动临时 Postgres 容器（端口 {port}）...")
    # 先清上一次被中断留下的同名容器，避免 name conflict
    if not remove_leftover_temp_container():
        safe_print("[WARN] 清理同名残留容器失败（可能不存在），继续启动")
    try:
        # 容器 id 不再需要：就绪判据改成「按脚本真正要用的方式连一次」（TCP），
        # 不再往容器里 exec pg_isready；收尾清理按固定容器名做。
        start_temp_postgres_container(port)
    except RuntimeError as exc:
        if is_docker_bind_error(str(exc)):
            fallback_port = choose_temp_postgres_port(0)
            safe_print(
                f"[WARN] 端口 {port} Docker 绑定失败，改用临时端口 {fallback_port}"
            )
            port = fallback_port
            try:
                start_temp_postgres_container(port)
            except RuntimeError as retry_exc:
                safe_print("[FAIL] 启动临时 Postgres 失败")
                safe_print(str(retry_exc))
                return 1
        else:
            safe_print("[FAIL] 启动临时 Postgres 失败")
            safe_print(str(exc))
            return 1

    try:
        database_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@127.0.0.1:{port}/{PG_DB}"
        safe_print("[INFO] 等待 Postgres 就绪...")
        # 就绪判据 = **按脚本真正要用的方式连一次**（TCP + 目标库 + 目标账号），
        # 不是容器内 pg_isready（它走 socket，会命中 initdb 期间的临时 server
        # ⇒ 提前放行 ⇒ 随后 TCP 连接撞上 "the database system is starting up"）。
        # 见 probe_postgres_ready() 的说明。
        ready, last_error = wait_for_postgres_ready(database_url)
        if not ready:
            safe_print("[FAIL] Postgres 就绪超时（TCP 连不上目标库）")
            safe_print(f"[FAIL] 最后一次失败原因: {last_error}")
            return 1
        safe_print("[OK] Postgres 就绪")

        # ── 两段式引导（共享实现，见 scripts/bootstrap_fresh_environment.py）──
        # 第一段: 跑到 20261116 的前一个节点 → 注入最小前置数据 → 第二段: 跑到 head
        # ⚠ 本门禁用**占位值** profile；真实新环境必须走
        #   scripts/bootstrap_fresh_environment.py --manifest <清单.json>
        main_row, shop_rows = build_gate_rows()
        try:
            summary = run_two_phase_bootstrap(
                database_url,
                main_row=main_row,
                shop_rows=shop_rows,
                project_root=PROJECT_ROOT,
                log=safe_print,
            )
        except Exception as exc:  # noqa: BLE001 —— 失败必须说清楚是哪一步
            safe_print("[FAIL] 两段式迁移失败")
            safe_print(str(exc))
            return 1
        safe_print(
            "[OK] 两段式迁移完成（引导账号 {n} 个，本次新增 {inserted} 行）".format(
                n=summary["shop_accounts"], inserted=summary["inserted"]
            )
        )
        missing_columns = verify_data_sync_critical_columns(database_url)
        if missing_columns:
            safe_print("[FAIL] 迁移后数据同步关键列缺失")
            for missing_column in missing_columns:
                safe_print(f"  - {missing_column}")
            return 1
        safe_print("[OK] 数据同步关键列校验通过")
        schema_consistency_error = verify_orm_schema_consistency(database_url)
        if schema_consistency_error:
            safe_print("[FAIL] 迁移后的 ORM Schema 一致性校验失败")
            safe_print(
                schema_consistency_error[-3000:]
                if len(schema_consistency_error) > 3000
                else schema_consistency_error
            )
            return 1
        safe_print("[OK] 迁移后的 ORM Schema 一致性校验通过")
        return 0
    finally:
        safe_print("[INFO] 停止并删除临时容器...")
        # 按名字删（容器 id 可能已经因 --rm 失效），并带上 -v：
        # postgres:15 会建匿名卷，不删的话每次运行都漏一个卷（实测 17 个悬空卷）
        run(["docker", "rm", "-f", "-v", TEMP_CONTAINER_NAME], timeout=30)
        safe_print("[OK] 临时容器已移除")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""云端同步链路完整性巡检的定时任务。

作用: 定时巡检**云端**那一侧的三件事, 把结论写进 ``ops.pipeline_run_log`` /
``ops.pipeline_step_log``(既有监控台账, **不需要新增表、不需要迁移**):

1. **云端数据还新鲜吗** —— 用 ``max(ingest_timestamp)`` 判定, 同步链断一天就能发现;
2. **行内身份还能不能认出来** —— 算「能唯一归属到主数据账号」的收敛率;
3. **候选池有没有缺平台** —— 缺平台 ⇒ 那条链的身份从一开始就解析不出来。

为什么必须是**云端**连接
----------------------
采集机本地跑的是「采集链」新鲜度(:mod:`source_freshness_service`),
它回答的是「我采到的数据有多旧」。它**回答不了**「云端还有没有在收数据」——
2026-11-07 事故里, 采集机一切正常, 是云端停在 11-06 再也没动过。

所以这个任务用 ``CLOUD_DATABASE_URL`` 连云端。
没配这个环境变量时**跳过**(不报错)—— 云端不可达不该把定时任务打挂。

容器里的 ``127.0.0.1`` 是**容器自己**
---------------------------------
采集机上的 ``CLOUD_DATABASE_URL`` 指向 ``127.0.0.1:15433`` —— 那是**宿主机**上
的 SSH 隧道。原样透传进容器必然 ``Connection refused``(容器里的回环地址是容器自己)。

所以主机名重写只有**一个入口**: :func:`normalize_cloud_database_url`。
compose 只负责把环境变量**传进容器**, 重写一律在代码里做, 这样就不会出现
「原样透传 127.0.0.1」把连接直接打死的坑。

⚠️ **但回环地址在两种运行环境里含义相反**
------------------------------------
采集机上有两种进程:

* **容器里**(``celery-worker`` / ``celery-beat``): ``127.0.0.1`` 是容器自己
  ⇒ 必须换成宿主可达地址;
* **宿主进程**(``scripts\\start_collection_formal.ps1`` 拉起的云端同步 worker):
  ``127.0.0.1`` 就是宿主自己 ⇒ **原样就是对的**, 换成
  ``host.docker.internal`` 反而连不上(那个名字只在容器里有意义)。

⇒ 所以重写**只在容器里做**(判据见 :func:`_running_in_container`), 宿主进程原样保留。
"""

import logging
import os
from typing import Any, Dict, NamedTuple, Optional
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.celery_app import celery_app
from backend.models.database import get_async_database_url
from backend.services.data_pipeline.cloud_sync_integrity_service import (
    ALIGNMENT_EFFECTIVE_DATE_ENV,
    run_cloud_sync_integrity_check,
)
from backend.utils.async_task_runner import run_async_task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 云端连接串的主机名规整(全仓唯一入口)
# ---------------------------------------------------------------------------

#: 回环地址 —— 在容器里指的是**容器自己**, 连不到宿主上的 SSH 隧道。
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: 隧道默认落点: Docker Desktop 提供的宿主机别名。
DEFAULT_TUNNEL_HOST = "host.docker.internal"
DEFAULT_TUNNEL_PORT = 15433

#: 只有这些字面量算「显式关掉隧道」; 未设置 / 空串 => 视为「没关」。
_TUNNEL_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})


class CloudDatabaseUrlResolution(NamedTuple):
    """云端连接串的规整结果。

    ``rewritten`` 为 ``False`` 表示**没有**做主机名重写 —— 调用方必须把它透出到
    返回结果里, 否则运维会以为「容器里已经能连到云端了」, 而实际上连接串里的
    ``127.0.0.1`` 指的是容器自己, 巡检必然连不上。
    """

    url: str
    rewritten: bool
    original_host: str
    effective_host: str
    effective_port: Optional[int]
    reason: str

    def to_summary_dict(self) -> Dict[str, Any]:
        """给任务返回结果用的**脱敏**摘要(绝不含用户名 / 口令)。"""
        return {
            "rewritten": self.rewritten,
            "original_host": self.original_host,
            "effective_host": self.effective_host,
            "effective_port": self.effective_port,
            "reason": self.reason,
        }


def _coerce_port(value: Any) -> Optional[int]:
    """把端口规整成正整数; 非法值返回 ``None``。"""
    if isinstance(value, bool):  # bool 是 int 的子类, 这里明确排除
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        port = int(text)
    except ValueError:
        return None
    return port if port > 0 else None


def _replace_netloc(parsed, host: str, port: int) -> str:
    """替换连接串里的 host / port, **其余部分原样保留**。

    用户名 / 口令按**字面量**搬运(``p%40ss`` 不会被解码、也不会丢),
    驱动前缀(``postgresql+asyncpg``)、库名、查询参数同样原样保留。
    """
    userinfo, _, _hostport = parsed.netloc.rpartition("@")
    host_part = f"[{host}]" if ":" in host else host
    new_hostport = f"{host_part}:{port}"
    netloc = f"{userinfo}@{new_hostport}" if userinfo else new_hostport
    return urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


def normalize_cloud_database_url(
    database_url: str,
    *,
    tunnel_enabled: bool,
    tunnel_host: str = DEFAULT_TUNNEL_HOST,
    tunnel_port: Any = DEFAULT_TUNNEL_PORT,
    in_container: bool = True,
) -> CloudDatabaseUrlResolution:
    """把云端连接串的 host 规整成**容器里真正可达**的地址(纯函数)。

    规则
    ----
    * host 是回环地址(``127.0.0.1`` / ``localhost`` / ``::1``)
      **且当前跑在容器里** ⇒ host 换成 ``tunnel_host``, port 换成 ``tunnel_port``;
    * **不在容器里** ⇒ **原样保留**: 采集机的云端同步 worker 跑在**宿主进程**
      (``scripts\\start_collection_formal.ps1`` 拉起的后端进程), 那里 ``127.0.0.1``
      就是宿主自己 ⇒ 重写反而连不上(``host.docker.internal`` 在宿主上不解析);
    * host 不是回环 ⇒ **原样保留**(幂等: 已经是 ``host.docker.internal``
      或真实域名就一个字都不动);
    * 隧道被**显式关掉** ⇒ **不改**, 但 ``rewritten`` 会是 ``False``,
      调用方必须把它透出, 别让运维以为已经修好了;
    * 用户名 / 口令 / 库名 / 参数 / 驱动前缀**原样保留**。

    Args:
        database_url: 原始云端连接串(``postgresql://`` 或 ``postgresql+asyncpg://``)。
        tunnel_enabled: 隧道是否开启。
        tunnel_host: 隧道落点主机名。
        tunnel_port: 隧道落点端口。
        in_container: 当前进程是否跑在容器里。默认 ``True`` —— 本函数的契约
            就是「规整成**容器里**真正可达的地址」；宿主进程由调用方显式传
            ``False``(见 :func:`_resolve_cloud_database_url_from_env`)。

    Returns:
        :class:`CloudDatabaseUrlResolution`。
    """
    raw = (database_url or "").strip()
    if not raw:
        return CloudDatabaseUrlResolution("", False, "", "", None, "empty_url")

    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        # 畸形连接串(端口越界 / IPv6 括号不配对等): 原样交给上层报错。
        return CloudDatabaseUrlResolution(raw, False, "", "", None, "unparsable_url")

    original_host = hostname or ""
    if not original_host:
        return CloudDatabaseUrlResolution(raw, False, "", "", port, "missing_host")

    if original_host.lower() not in _LOOPBACK_HOSTS:
        # 已经是真实域名 / 容器主机名 ⇒ 原样保留(幂等)。
        return CloudDatabaseUrlResolution(
            raw, False, original_host, original_host, port, "not_loopback_host"
        )

    if not tunnel_enabled:
        return CloudDatabaseUrlResolution(
            raw, False, original_host, original_host, port, "tunnel_disabled"
        )

    if not in_container:
        # 不在容器里 ⇒ 回环地址指向的就是宿主自己 ⇒ **原样保留**。
        # 采集机的云端同步 worker 跑在宿主进程, 那里 127.0.0.1 就是对的。
        return CloudDatabaseUrlResolution(
            raw, False, original_host, original_host, port, "not_in_container"
        )

    target_host = str(tunnel_host or "").strip()
    if not target_host:
        return CloudDatabaseUrlResolution(
            raw, False, original_host, original_host, port, "tunnel_host_missing"
        )

    target_port = _coerce_port(tunnel_port)
    if target_port is None:
        return CloudDatabaseUrlResolution(
            raw, False, original_host, original_host, port, "tunnel_port_invalid"
        )

    return CloudDatabaseUrlResolution(
        _replace_netloc(parsed, target_host, target_port),
        True,
        original_host,
        target_host,
        target_port,
        "rewritten_to_tunnel",
    )


def _tunnel_enabled_from_env(raw: Optional[str]) -> bool:
    """``CLOUD_SYNC_TUNNEL_ENABLED`` 只有**显式**为假时才关掉隧道重写。"""
    if raw is None:
        return True
    return raw.strip().lower() not in _TUNNEL_DISABLED_VALUES


def _running_in_container() -> bool:
    """当前进程是否跑在**容器**里。

    为什么必须判这个
    --------------
    采集机上有**两种**运行环境, 对回环地址的解读**相反**:

    * **容器里**(``celery-worker`` / ``celery-beat``): ``127.0.0.1`` 是**容器自己**
      ⇒ 必须换成宿主可达地址(``host.docker.internal``);
    * **宿主进程**(``scripts\\start_collection_formal.ps1`` 拉起的云端同步 worker):
      ``127.0.0.1`` 就是**宿主自己** ⇒ 原样就是对的, 换成 ``host.docker.internal``
      反而**连不上**(该名字只在容器里有意义)。

    ⇒ 不判容器就会把其中一边弄坏。判据用**文件系统事实**而不是环境变量,
    因为 compose 会给两个 service 都塞同样的默认值, 环境变量区分不了。
    """
    if os.path.exists("/.dockerenv"):
        return True
    if os.path.exists("/run/.containerenv"):
        return True
    if (os.getenv("KUBERNETES_SERVICE_HOST") or "").strip():
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
    except OSError:
        return False
    return any(marker in content for marker in ("docker", "containerd", "kubepods"))


def _resolve_cloud_database_url_from_env() -> CloudDatabaseUrlResolution:
    """按当前环境变量规整云端连接串。"""
    return normalize_cloud_database_url(
        (os.getenv("CLOUD_DATABASE_URL") or "").strip(),
        tunnel_enabled=_tunnel_enabled_from_env(os.getenv("CLOUD_SYNC_TUNNEL_ENABLED")),
        tunnel_host=(os.getenv("CLOUD_SYNC_TUNNEL_HOST") or "").strip()
        or DEFAULT_TUNNEL_HOST,
        tunnel_port=(os.getenv("CLOUD_SYNC_TUNNEL_PORT") or "").strip()
        or DEFAULT_TUNNEL_PORT,
        in_container=_running_in_container(),
    )


async def _run_check() -> Dict[str, Any]:
    cloud_database_url = (os.getenv("CLOUD_DATABASE_URL") or "").strip()
    if not cloud_database_url:
        return {
            "status": "skipped",
            "reason": "CLOUD_DATABASE_URL is not configured",
        }

    # 容器里的 127.0.0.1 是容器自己 —— 连库前先把主机名规整成真正可达的地址。
    resolution = _resolve_cloud_database_url_from_env()
    if resolution.rewritten:
        logger.info(
            "[CloudSyncIntegrity] 云端连接串主机名已重写: %s -> %s:%s(走宿主隧道)",
            resolution.original_host,
            resolution.effective_host,
            resolution.effective_port,
        )
    elif resolution.original_host.lower() in _LOOPBACK_HOSTS:
        logger.warning(
            "[CloudSyncIntegrity] 云端连接串**未**重写(host=%s, reason=%s): "
            "回环地址在当前运行环境里指向的就是它自己; "
            "若本进程跑在容器里, 需要 CLOUD_SYNC_TUNNEL_HOST 指向宿主可达地址",
            resolution.original_host,
            resolution.reason,
        )

    engine = create_async_engine(get_async_database_url(resolution.url))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    try:
        report = await run_cloud_sync_integrity_check(db, trigger_source="scheduler")
        summary = report.to_summary()
        summary["status"] = "success" if report.is_success else "partial_failed"
        summary["error_message"] = report.to_error_message()
        # 让运维看得见「主机名到底有没有被重写」(脱敏: 不含用户名 / 口令)。
        summary["cloud_database_url_resolution"] = resolution.to_summary_dict()
        return summary
    finally:
        await db.close()
        await engine.dispose()


@celery_app.task(
    name="backend.tasks.cloud_sync_integrity_tasks.check_cloud_sync_integrity"
)
def check_cloud_sync_integrity() -> Dict[str, Any]:
    """巡检云端同步链路的完整性(陈旧 / 收敛率 / 候选池平台)。"""
    try:
        # 用全仓唯一的异步出口: 它保证在本事件循环**存活期间**真正关闭连接池。
        # 直接 asyncio.run(...) 会让 asyncpg 的连接绑定到一个随即死掉的循环上,
        # 之后连 close 都关不掉 —— 生产实测 80/80 连接槽位就是这样被打满的。
        summary = run_async_task(_run_check)
    except Exception as exc:  # noqa: BLE001
        logger.error("[CloudSyncIntegrity] 巡检执行失败: %s", exc, exc_info=True)
        raise

    if summary.get("status") == "skipped":
        logger.info("[CloudSyncIntegrity] 未配置云端连接, 跳过巡检")
        return summary

    if summary.get("status") == "partial_failed":
        logger.warning(
            "[CloudSyncIntegrity] 云端同步链路异常: 陈旧链 %s 条, 收敛率异常 %s 条, "
            "候选池缺平台 %s 个, 语义层可解析性异常 %s 个月",
            summary.get("stale_chains"),
            summary.get("low_convergence_chains"),
            summary.get("missing_candidate_platforms"),
            summary.get("degraded_semantic_months"),
        )
    else:
        logger.info(
            "[CloudSyncIntegrity] 巡检通过: %s 条链全部新鲜, 收敛率正常, 候选池平台齐全, "
            "语义层 %s 个月份可解析(其中 %s 个月属已知历史遗留)",
            summary.get("checked_chains"),
            summary.get("semantic_months_checked"),
            summary.get("semantic_known_legacy_months"),
        )

    if summary.get("semantic_months_checked") and not summary.get(
        "alignment_effective_date"
    ):
        logger.warning(
            "[CloudSyncIntegrity] 未配置 %s —— 语义层 unknown 全部按「已知历史遗留」处理, "
            "不会报警；请在批次 2 登记信息对齐生效后配置该环境变量",
            ALIGNMENT_EFFECTIVE_DATE_ENV,
        )
    return summary

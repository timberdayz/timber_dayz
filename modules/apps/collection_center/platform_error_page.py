"""平台「错误页 / 404 页 / 登录页」判据 —— 全采集链路的**唯一实现**。

为什么必须识别它
----------------
采集器登录后打开的第一个页面**可能是错误页**（会话失效、店铺被封、
链接过期时平台会跳到 ``/404?cnsc_shop_id=...``）。
这个 URL **照样带着 ``cnsc_shop_id`` 参数** —— 而那个参数是**上一家店**的
（持久 profile 会把上次会话停着的页面恢复出来）。

2026-11-07 实测事故：``https://seller.shopee.cn/404?cnsc_shop_id=1391124228``
被当成一次正常探测 ⇒ 那个编号被另一个账号占着 ⇒ 记成 ``conflict_detected``
⇒ 业务概览页弹出「采集期探测到 1 次店铺身份异常」。

错误页上的编号**不是探测结果** ⇒ 拿它做绑定判定 = **制造假冲突**。
正确做法：判成「探测失败」（status='failed'），不参与绑定判定、
也不计入身份异常告警。

这个模块为什么单独成文件
------------------------
2026-11-29 之前，这个判据住在 ``executor_v2.py`` 里。但
``runtime_session.py``（导航实现的唯一归属）也需要它，而
``executor_v2`` 依赖 ``runtime_session`` ⇒ 直接 import 会形成循环依赖。

所以判据下沉到本模块，``executor_v2`` 保留同名别名向后兼容，
``runtime_session`` 直接引用本模块。

**口径纪律**：本模块的判据必须与迁移
``current_migrations/versions/20261129_reclassify_error_page_shop_discoveries.py``
的 SQL 判据**逐条一致**（由 ``backend/tests/data_pipeline/
test_error_page_discovery_reclassification_migration.py`` 守护）。
"""

from __future__ import annotations

from urllib.parse import urlparse


#: 平台「错误页 / 404 页」的 URL 路径特征（path 的**最后一段**）。
ERROR_PAGE_PATH_SEGMENTS: frozenset[str] = frozenset(
    {
        "404",
        "404.html",
        "404.htm",
        "404error",
        "error",
        "error.html",
        "error.htm",
        "errorpage",
        "notfound",
        "not-found",
        "not_found",
        "signin",
        "login",
    }
)


def is_platform_error_page(current_url: str) -> bool:
    """这个 URL 是不是平台的**错误页 / 404 页 / 登录页**。

    只看 path 的**最后一段**（文件名）—— 避免把
    ``/datacenter/error_report`` 这类正常业务路径误判成错误页。

    登录页也算：页面上同样没有店铺身份信息，
    2026-04 的 3 条历史 ``failed`` 记录命中的就是登录页。
    """
    parsed = urlparse(str(current_url or ""))
    path = (parsed.path or "").strip().lower()
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    last_segment = segments[-1]
    if last_segment in ERROR_PAGE_PATH_SEGMENTS:
        return True
    normalized = last_segment.replace("-", "").replace("_", "").replace(".", "")
    if normalized.startswith("404") or normalized.startswith("error"):
        return True
    return False

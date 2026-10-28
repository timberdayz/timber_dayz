"""数据同步缓存键构造 (SSOT)

为什么
----
同一份「模板状态」在系统里被两处分别缓存, 但两把尺子的构成不一样:

* ``backend/services/data_sync_service.py::_readiness_cache_key``
  —— 含 ``last_modified``, 文件内容变了缓存会失效
* ``backend/domains/data_platform/routers/data_sync.py::_build_template_status_cache_key``
  —— **不含** ``last_modified``, 文件在磁盘上换了内容仍会读到旧结论

两把尺子量同一个东西, 必然出现「治理面板说没问题、就绪判定说有漂移」
这类互相矛盾的口径。

本模块提供**唯一**的键构造函数, 两处共用。

键里必须包含
------------
* 文件标识(id / file_name / file_path)
* 文件状态与**修改时间** —— 文件内容或状态变了, 缓存自然失效
* 模板标识与**版本号** —— 模板升级, 缓存自然失效
* 模板表头行(header_row)
* 表头行口径(``use_template_header_row``) —— 严格按模板表头行读与不按它读,
  读出来的列不一样, 结论也不一样
"""

from __future__ import annotations

from typing import Any, Optional


def build_template_status_cache_key(
    catalog_file: Any,
    template: Any = None,
    *,
    use_template_header_row: Optional[bool] = None,
) -> tuple:
    """构造「模板状态」缓存键。

    Args:
        catalog_file: ``catalog_files`` 记录(ORM 对象或同构对象)
        template: 参与判定的模板(可为 None)
        use_template_header_row: 是否严格按模板表头行读取文件;
            ``None`` 表示该调用点不区分口径(例如文件列表行级展示)
    """
    return (
        getattr(catalog_file, "id", None),
        getattr(catalog_file, "file_name", None),
        getattr(catalog_file, "file_path", None),
        getattr(catalog_file, "status", None),
        getattr(catalog_file, "last_modified", None),
        getattr(template, "id", None),
        getattr(template, "version", None),
        getattr(template, "header_row", None),
        use_template_header_row,
    )

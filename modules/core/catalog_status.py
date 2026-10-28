#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``catalog_files.status`` 状态枚举 (Single Source of Truth)

为什么
----
``catalog_files.status`` 的取值定义曾经散落在四个地方:

1. 历史迁移脚本里的字面量
2. 后端代码里的字面量(``catalog_scanner`` / ``data_sync_service`` /
   ``scheduled_tasks`` / ``ingestion_worker`` ...)
3. 前端状态筛选下拉框里的选项
4. 数据库 —— **完全没有约束**

于是「什么是合法状态」没有唯一答案: 前端能选出一个后端写不出、
数据库也不拦的值。DB 侧只有主键与 ``storage_layer`` 两条约束,
``status`` 可以是任意字符串。

本模块给出唯一的状态集合, 供三处共用:

* Python 代码判断取值是否合法
* ORM 模型生成 ``ck_catalog_files_status`` CHECK 约束
* 迁移脚本把同一套取值写进数据库

状态语义
--------
===========================  ===================================================
``pending``                  已登记, 等待同步(自动入库的默认入口状态)
``processing``               同步进行中(并发保护标记)
``validated``                已通过校验, 尚未入库
``ingested``                 已成功入库
``partial_success``          部分数据入库成功, 部分被隔离或失败
``quarantined``              数据被隔离(质量不达标)
``failed``                   同步失败
``needs_shop``               店铺归属待人工指派
``source_missing``           源文件在磁盘上缺失
``template_update_required`` 模板待更新 —— 文件表头与生效模板不匹配
===========================  ===================================================
"""

from typing import Dict, Optional, Tuple

# ── 状态常量 ──────────────────────────────────────────────────────────
CATALOG_FILE_STATUS_PENDING = "pending"
CATALOG_FILE_STATUS_PROCESSING = "processing"
CATALOG_FILE_STATUS_VALIDATED = "validated"
CATALOG_FILE_STATUS_INGESTED = "ingested"
CATALOG_FILE_STATUS_PARTIAL_SUCCESS = "partial_success"
CATALOG_FILE_STATUS_QUARANTINED = "quarantined"
CATALOG_FILE_STATUS_FAILED = "failed"
CATALOG_FILE_STATUS_NEEDS_SHOP = "needs_shop"
CATALOG_FILE_STATUS_SOURCE_MISSING = "source_missing"
CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED = "template_update_required"


# ── 合法状态集合 (SSOT) ──────────────────────────────────────────────
CATALOG_FILE_STATUSES: Tuple[str, ...] = (
    CATALOG_FILE_STATUS_PENDING,
    CATALOG_FILE_STATUS_PROCESSING,
    CATALOG_FILE_STATUS_VALIDATED,
    CATALOG_FILE_STATUS_INGESTED,
    CATALOG_FILE_STATUS_PARTIAL_SUCCESS,
    CATALOG_FILE_STATUS_QUARANTINED,
    CATALOG_FILE_STATUS_FAILED,
    CATALOG_FILE_STATUS_NEEDS_SHOP,
    CATALOG_FILE_STATUS_SOURCE_MISSING,
    CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED,
)

CATALOG_FILE_STATUS_SET = frozenset(CATALOG_FILE_STATUSES)


# ── 中文标签(接口/面板展示用) ────────────────────────────────────────
CATALOG_FILE_STATUS_LABELS: Dict[str, str] = {
    CATALOG_FILE_STATUS_PENDING: "待同步",
    CATALOG_FILE_STATUS_PROCESSING: "处理中",
    CATALOG_FILE_STATUS_VALIDATED: "已校验",
    CATALOG_FILE_STATUS_INGESTED: "已同步",
    CATALOG_FILE_STATUS_PARTIAL_SUCCESS: "部分成功",
    CATALOG_FILE_STATUS_QUARANTINED: "隔离",
    CATALOG_FILE_STATUS_FAILED: "失败",
    CATALOG_FILE_STATUS_NEEDS_SHOP: "需要指派店铺",
    CATALOG_FILE_STATUS_SOURCE_MISSING: "源文件缺失",
    CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED: "模板待确认",
}


# ── 状态分组(判断文件是否还需要被处理) ────────────────────────────────
# 「未完成」= 还需要自动入库流程去处理
CATALOG_FILE_STATUS_ACTIVE: Tuple[str, ...] = (
    CATALOG_FILE_STATUS_PENDING,
    CATALOG_FILE_STATUS_PROCESSING,
    CATALOG_FILE_STATUS_VALIDATED,
    CATALOG_FILE_STATUS_FAILED,
    CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED,
)

# 「已入库」= 数据已经落库, 不需要再跑一遍
CATALOG_FILE_STATUS_INGESTED_SET = frozenset(
    {
        CATALOG_FILE_STATUS_INGESTED,
        CATALOG_FILE_STATUS_PARTIAL_SUCCESS,
        CATALOG_FILE_STATUS_QUARANTINED,
    }
)


def is_valid_catalog_file_status(value: Optional[str]) -> bool:
    """判断是否为合法的 ``catalog_files.status`` 取值。"""
    if not value:
        return False
    return str(value).strip().lower() in CATALOG_FILE_STATUS_SET


def catalog_file_status_label(value: Optional[str]) -> str:
    """取状态的中文标签; 未知取值原样返回。"""
    if not value:
        return ""
    key = str(value).strip().lower()
    return CATALOG_FILE_STATUS_LABELS.get(key, str(value))

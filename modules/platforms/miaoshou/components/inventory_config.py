"""
Miaoshou ERP inventory (仓库清单) component config

Centralizes base URL, deep-link paths and key selectors used by
navigation/export. Mirrors the orders_config / purchase_config convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List, Tuple

BASE_URL: Final[str] = "https://erp.91miaoshou.com"
WAREHOUSE_CHECKLIST_PATH: Final[str] = "/warehouse/checklist"

OPEN_EXPORT_MENU_SELECTORS: Final[Tuple[str, ...]] = (
    'button:has-text("导入/导出商品")',
    '[role="button"]:has-text("导入/导出商品")',
    '.operate-side .jx-dropdown button.jx-button.is-plain:has-text("导入/导出商品")',
    'button.jx-button.is-plain:has-text("导入/导出商品")',
    'button.jx-button:has-text("导入/导出商品")',
    '.pro-button:has-text("导入/导出商品")',
    '[aria-haspopup="menu"]:has-text("导入/导出商品")',
    'button:has-text("导出")',
)

MENU_EXPORT_SEARCHED_SELECTORS: Final[Tuple[str, ...]] = (
    ".J_warehouseChecklistExportSearch",
    '[role="menuitem"]:has-text("导出搜索的商品")',
    "text=导出搜索的商品",
)

GROUP_TITLES: Final[Tuple[str, ...]] = ("商品信息", "其他信息")
GROUP_CHECK_ALL_TEXT: Final[str] = "全选"

EXPORT_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    "button:has-text(导出)",
    "[role='button']:has-text(导出)",
    ".jx-dialog__body .pro-button:has-text(导出)",
    "button.jx-button.jx-button--primary:has-text(导出)",
    "button.pro-button:has-text(导出)",
)

POPUP_CLOSE_SELECTORS: Final[Tuple[str, ...]] = (
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-notification .anticon-close",
    ".ant-message-notice-close",
    ".ant-popover .ant-popover-close",
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    "button:has-text(我知道了)",
    "button:has-text(知道了)",
    "button:has-text(关闭)",
    "button:has-text(确认)",
    "button:has-text(确定)",
    "button:has-text(取消)",
    "button:has-text(OK)",
)

CLOSE_POLL_MAX_ROUNDS: Final[int] = 20
CLOSE_POLL_INTERVAL_MS: Final[int] = 300

PROGRESS_TEXTS: Final[Tuple[str, ...]] = (
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "导出成功",
    "Generating",
    "Processing",
)

DATA_TYPE_DIR: Final[str] = "inventory"

# ── 仓库范围下拉框（jx-select）防护参数 ──────────────────────────────
# 取证来源（2026-10-23 复核，证据已落在本仓库，无需再等 pwcli 环境）：
#   1. `logs/backend-local.out.log`（2026-10-23 11:56:35 真实失败 call log）：
#      `get_by_label(re.compile("仓库"))` 解析到
#      `<input role="combobox" aria-expanded="false" aria-haspopup="listbox"
#        aria-controls="jx-id-1399-15" class="jx-select__input is-small">`
#      → 触发器就是 jx-select 内部的 input，遮挡它的是
#      `<div class="jx-select__selected-item jx-select__placeholder is-transparent">`。
#   2. `output/playwright/work/miaoshou/finance-inventory-recording/inventory-02*.md|.png`
#      （2026-09-13 真实页面取证）：空态显示「请选择」placeholder；全选态折叠为
#      `仓库: [菲律宾3店-时尚箱包 ×] + 4` → 「+ N」折叠标签确实存在。
#   3. `modules/platforms/miaoshou/archive/export.py:368`（历史跑通过的实战写法）：
#      用 `.jx-select__wrapper` 点开 jx-select 下拉。
#
# ⚠️ 改版风险：层 A 依赖 jx-select 的 DOM 结构（.jx-select / .jx-select__wrapper /
#    .jx-select__selected-item / .jx-tag），妙手前端改版会失效。
#    妙手前端改版或仓库筛选控件换实现时，需要重新取证校正（《规范》§1 要求注明）。
WAREHOUSE_SCOPE_TRIGGER_TIMEOUT_MS: Final[int] = 3000
WAREHOUSE_SCOPE_OPEN_MAX_ATTEMPTS: Final[int] = 2
WAREHOUSE_SCOPE_RETRY_BACKOFF_SECONDS: Final[float] = 0.5
# 容器外壳候选（按证据强度排序，逐个尝试，第一个可用即用）：
#   1. `.jx-select__wrapper` —— 归档 export.py 实战验证过能点开下拉
#   2. `.jx-select`（精确 class token）—— 最外层外壳
#   3. 宽松 `contains(@class,'jx-select')` —— 防改版兜底
# ⚠️ 不要用 `contains(@class,'jx-select')` 单独定位：它同时匹配
#    `jx-select__input` / `jx-select__content` / `jx-select__wrapper`，
#    `[1]` 取最近祖先会落到内层容器上，点击位置仍在 input 区域 → 仍被遮挡。
WAREHOUSE_SCOPE_WRAPPER_XPATH: Final[str] = (
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
    "' jx-select__wrapper ')][1]"
)
WAREHOUSE_SCOPE_CONTAINER_XPATH: Final[str] = (
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
    "' jx-select ')][1]"
)
WAREHOUSE_SCOPE_CONTAINER_XPATH_LOOSE: Final[str] = (
    "xpath=ancestor::*[contains(@class,'jx-select')][1]"
)
# 浮层定位候选（依据 archive/export.py:386-399 的实战写法 + call log 的
# `aria-haspopup="listbox"` / `aria-controls` 线索）：
WAREHOUSE_SCOPE_OVERLAY_SELECTORS: Final[Tuple[str, ...]] = (
    ".jx-select-dropdown:visible",
    ".jx-select__dropdown:visible",
    ".jx-popper:visible",
)
# 浮层头部「全选」复选框（archive/export.py:396-399 实战写法）：
# `.jx-select-dropdown__header .jx-checkbox` → `.jx-checkbox__input`
WAREHOUSE_SCOPE_FULL_SELECT_HEADER_SELECTOR: Final[str] = (
    ".jx-select-dropdown__header .jx-checkbox"
)
WAREHOUSE_SCOPE_CHECKBOX_INPUT_SELECTOR: Final[str] = ".jx-checkbox__input"


@dataclass(frozen=True)
class InventorySelectors:
    base_url: str = BASE_URL
    checklist_path: str = WAREHOUSE_CHECKLIST_PATH
    open_export_menu: Tuple[str, ...] = OPEN_EXPORT_MENU_SELECTORS
    menu_export_searched: Tuple[str, ...] = MENU_EXPORT_SEARCHED_SELECTORS
    group_titles: Tuple[str, ...] = GROUP_TITLES
    group_check_all_text: str = GROUP_CHECK_ALL_TEXT
    export_buttons: Tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    popup_close_buttons: Tuple[str, ...] = POPUP_CLOSE_SELECTORS
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: Tuple[str, ...] = PROGRESS_TEXTS
    data_type_dir: str = DATA_TYPE_DIR
    warehouse_scope_trigger_timeout_ms: int = WAREHOUSE_SCOPE_TRIGGER_TIMEOUT_MS
    warehouse_scope_open_max_attempts: int = WAREHOUSE_SCOPE_OPEN_MAX_ATTEMPTS
    warehouse_scope_retry_backoff_seconds: float = WAREHOUSE_SCOPE_RETRY_BACKOFF_SECONDS
    warehouse_scope_container_xpath: str = WAREHOUSE_SCOPE_CONTAINER_XPATH
    warehouse_scope_wrapper_xpath: str = WAREHOUSE_SCOPE_WRAPPER_XPATH
    warehouse_scope_container_xpath_loose: str = WAREHOUSE_SCOPE_CONTAINER_XPATH_LOOSE
    warehouse_scope_overlay_selectors: Tuple[str, ...] = (
        WAREHOUSE_SCOPE_OVERLAY_SELECTORS
    )
    warehouse_scope_full_select_header_selector: str = (
        WAREHOUSE_SCOPE_FULL_SELECT_HEADER_SELECTOR
    )
    warehouse_scope_checkbox_input_selector: str = (
        WAREHOUSE_SCOPE_CHECKBOX_INPUT_SELECTOR
    )

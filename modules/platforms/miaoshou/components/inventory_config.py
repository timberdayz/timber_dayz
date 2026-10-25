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
# 取证来源（按证据强度排序，2026-10-23 更新）：
#   1. ⭐ **2026-10-23 人工登录 + CDP 探针实测**（最强证据，直接读真实 DOM）：
#      `scripts/probe_miaoshou_warehouse_scope.py --cdp <port>`，
#      配套 pwcli 录制产物见 `output/playwright/work/miaoshou/inventory_scope/`。
#      结论见下方常量区注释。
#   2. `logs/backend-local.out.log`（2026-10-23 11:56:35 真实失败 call log）：
#      `get_by_label(re.compile("仓库"))` 解析到
#      `<input role="combobox" aria-expanded="false" aria-haspopup="listbox"
#        aria-controls="jx-id-1399-15" class="jx-select__input is-small">`
#      → 触发器就是 jx-select 内部的 input，遮挡它的是
#      `<div class="jx-select__selected-item jx-select__placeholder is-transparent">`。
#   3. `output/playwright/work/miaoshou/finance-inventory-recording/inventory-02*.md|.png`
#      （2026-09-13 真实页面取证）：空态显示「请选择」placeholder；全选态折叠为
#      `仓库: [菲律宾3店-时尚箱包 ×] + 4` → 「+ N」折叠标签确实存在。
#   4. `modules/platforms/miaoshou/archive/export.py:368`（历史跑通过的实战写法）：
#      用 `.jx-select__wrapper` 点开 jx-select 下拉。
#
# ⚠️ 改版风险：层 A 依赖 jx-select 的 DOM 结构（.jx-select / .jx-select__wrapper /
#    .jx-select__selected-item / .jx-tag），妙手前端改版会失效。
#    妙手前端改版或仓库筛选控件换实现时，需要重新取证校正（《规范》§1 要求注明）。
#    ⚠️ 但**仓库筛选是可选筛选项，「不选 = 全选」**（2026-10-23 实测：
#    空态与全选态的 SKU 总数 1113 / 56 页 / 表格内容完全一致），
#    所以即使这层结构整体失效，也只应降级告警，**不应让整个采集任务失败**。
WAREHOUSE_SCOPE_TRIGGER_TIMEOUT_MS: Final[int] = 3000
WAREHOUSE_SCOPE_OPEN_MAX_ATTEMPTS: Final[int] = 2
WAREHOUSE_SCOPE_RETRY_BACKOFF_SECONDS: Final[float] = 0.5

# ── 2026-10-23 真实页面取证（CDP 探针，仓库清单页）────────────────────
#   仓库筛选字段的**稳定锚点**：`[data-field='warehouseIds']`
#   （与订单域 `[data-field='appOrderStatus']` 同款，不再依赖 class / 文案）
WAREHOUSE_SCOPE_FIELD_SELECTOR: Final[str] = "[data-field='warehouseIds']"
#   浮层真实结构（实测）：
#     div.jx-select-dropdown.is-multiple.pro-select-popper
#       ├── div.jx-select-dropdown__header          ← 「全选」复选框在这里
#       └── div.jx-scrollbar > ul.jx-select-dropdown__list[role=listbox]
#   ⚠️ `aria-controls` 指向的是**内层 ul**，ul 里**没有** header 的复选框，
#      所以浮层根必须取 `.jx-select-dropdown`（外层 div）而不是 listbox。
WAREHOUSE_SCOPE_DROPDOWN_SELECTOR: Final[str] = ".jx-select-dropdown"
#   已全选判据：仓库 select 的 `modelvaluegroup` 属性 = 选中的仓库 ID 列表
#   （实测全选态为 "684506,563787,563786,381635,299699"，空态为空串）
WAREHOUSE_SCOPE_SELECTED_VALUE_ATTR: Final[str] = "modelvaluegroup"
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
# ⚠️ 顺序很重要：`.jx-select-dropdown` 必须排在 listbox **之前**，
#    因为只有它包含 header 的「全选」复选框。
WAREHOUSE_SCOPE_OVERLAY_SELECTORS: Final[Tuple[str, ...]] = (
    ".jx-select-dropdown:visible",
    ".jx-select__dropdown:visible",
    ".jx-popper:visible",
)
# 浮层头部「全选」复选框（实测：div.jx-select-dropdown__header >
#   label.jx-checkbox.jx-checkbox--small.is-checked.pro-checkbox >
#   span.jx-checkbox__label「全选」+ input.jx-checkbox__original）
WAREHOUSE_SCOPE_FULL_SELECT_HEADER_SELECTOR: Final[str] = (
    ".jx-select-dropdown__header .jx-checkbox"
)
# 真实 input 的 class 是 `jx-checkbox__original`（**不是**归档脚本里的
# `jx-checkbox__input` —— 妙手改版过，2026-10-23 实测确认）
WAREHOUSE_SCOPE_CHECKBOX_INPUT_SELECTOR: Final[str] = ".jx-checkbox__original"


# ── B1 增量采集：仓库清单「更新时间维度 + 自定义区间」筛选 ─────────────
# 取证来源：2026-10-25 真实页面取证（CDP 探针）。
#
# ⚠️ 妙手这里有**三处静默失败**：维度没切、「确定」没点、搜索没刷新，
#    页面都照常显示、不报错，只会安静地给你错数据。
#    → 每一步都必须断言落地证据（见 inventory_date_filter.py）。
#
# 筛选器面板：点开「更新时间 / 创建时间」下拉后出现的面板
INVENTORY_DATE_FILTER_PANEL_SELECTOR: Final[str] = ".jx-picker-panel"
# 维度下拉（面板内的 jx-select）：它的 modelvaluegroup = 维度键
INVENTORY_DATE_FILTER_DIMENSION_SELECT_SELECTOR: Final[str] = (
    ".jx-picker-panel .jx-select"
)
# 维度键：妙手只有两项 —— 创建时间 gmtCreate / 更新时间 gmtModified
# ⚠️ 维度选错是静默失败：同一区间按更新时间 147 个 SKU，按创建时间只有 3 个
INVENTORY_DATE_FILTER_DIMENSION_MODIFIED: Final[str] = "gmtModified"
INVENTORY_DATE_FILTER_DIMENSION_CREATE: Final[str] = "gmtCreate"
INVENTORY_DATE_FILTER_DIMENSION_MODIFIED_LABEL: Final[str] = "更新时间"
INVENTORY_DATE_FILTER_DIMENSION_CREATE_LABEL: Final[str] = "创建时间"
# 维度下拉里的选项
INVENTORY_DATE_FILTER_DIMENSION_OPTION_SELECTOR: Final[str] = (
    ".jx-picker-panel .jx-select-dropdown li"
)
# 区间输入框（datetimerange 的两个 range input）
INVENTORY_DATE_FILTER_RANGE_INPUT_SELECTOR: Final[str] = (
    ".jx-picker-panel input.jx-range-input"
)
# 「确定」= link-btn + is-plain；「清空」= link-btn + is-text
# ⚠️ **必须用完整 class 区分**，只匹配 is-plain 会误点「清空」，把区间清成空
INVENTORY_DATE_FILTER_CONFIRM_SELECTOR: Final[str] = (
    "button.jx-picker-panel__link-btn.is-plain"
)
INVENTORY_DATE_FILTER_CLEAR_SELECTOR: Final[str] = (
    "button.jx-picker-panel__link-btn.is-text"
)
# 已应用筛选值的读取口：modelvaluegroup 属性
# ⚠️ 与仓库筛选同一个属性名，但读的是**不同节点**：
#    维度下拉上的是维度键（gmtModified…），筛选器根上的是已应用的区间
INVENTORY_DATE_FILTER_VALUE_ATTR: Final[str] = "modelvaluegroup"
# 筛选器根节点的候选（按证据强度排序，第一个取得到就用）
INVENTORY_DATE_FILTER_ROOT_SELECTORS: Final[Tuple[str, ...]] = (
    "[data-field='gmtModified']",
    "[data-field='gmtCreate']",
    ".jx-picker-panel",
)
# 结果计数文本（断言「搜索确实刷新了」）
INVENTORY_DATE_FILTER_SKU_TOTAL_TEXT: Final[str] = "SKU总数"

# ── 真实页面结构（2026-10-26 失败现场 + 页面截图取证）─────────────────
#
# ⚠️ 上一版把筛选器当成「picker 面板 + 维度 select + 确定/清空按钮」，
#    真实页面**根本没有那个面板**：
#    - 时间维度是筛选栏里的**内联下拉**，触发器直接显示「创建时间」/「更新时间」
#    - 下拉浮层里就两项：「创建时间」「更新时间」
#    - 日期区间是**内联的两个输入框**（占位文字「开始时间」「结束时间」）
#    - 填完**直接点「搜索」**，页面没有「确定」「清空」按钮
#    → 上一版的 `.jx-picker-panel` 系列选择器全部落空，
#      实测报「仓库清单日期筛选面板打不开」，采集在设置筛选这步就断了。
#
# 新策略：**以「可见文案」和「placeholder」为锚**，不赌 class 名。
# class 是 jx-ui 的实现细节、随版本变；「创建时间 / 更新时间 / 开始时间 / 结束时间」
# 是业务语义，稳定。用文案定位还能顺带拿到**人能读的落地证据**。
#
# 浮层里定位维度选项的容器候选（限定在浮层内找，避免点到别处的同名文字）
INVENTORY_DATE_FILTER_DROPDOWN_CONTAINER_SELECTORS: Final[Tuple[str, ...]] = (
    ".jx-select-dropdown",
    ".jx-dropdown-menu",
    ".ant-select-dropdown",
    "[role='listbox']",
)
# 日期区间输入框：按 placeholder 认
INVENTORY_DATE_FILTER_RANGE_START_PLACEHOLDERS: Final[Tuple[str, ...]] = (
    "开始时间",
    "开始日期",
    "开始",
)
INVENTORY_DATE_FILTER_RANGE_END_PLACEHOLDERS: Final[Tuple[str, ...]] = (
    "结束时间",
    "结束日期",
    "结束",
)
# 区间输入框的 class 兜底（真实页面没有 picker-panel，这几个是历史候选）
INVENTORY_DATE_FILTER_RANGE_INPUT_SELECTOR: Final[str] = (
    "input.jx-range-input, input[placeholder*='开始'], input[placeholder*='结束']"
)
# 维度下拉触发器：找到「创建时间 / 更新时间」文字后，向上找可点击的祖先
INVENTORY_DATE_FILTER_TRIGGER_ANCESTOR_XPATHS: Final[Tuple[str, ...]] = (
    "xpath=ancestor::*[contains(@class,'select')][1]",
    "xpath=ancestor::*[contains(@class,'picker')][1]",
    "xpath=..",
)


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
    warehouse_scope_field_selector: str = WAREHOUSE_SCOPE_FIELD_SELECTOR
    warehouse_scope_dropdown_selector: str = WAREHOUSE_SCOPE_DROPDOWN_SELECTOR
    warehouse_scope_selected_value_attr: str = WAREHOUSE_SCOPE_SELECTED_VALUE_ATTR
    warehouse_scope_overlay_selectors: Tuple[str, ...] = (
        WAREHOUSE_SCOPE_OVERLAY_SELECTORS
    )
    warehouse_scope_full_select_header_selector: str = (
        WAREHOUSE_SCOPE_FULL_SELECT_HEADER_SELECTOR
    )
    warehouse_scope_checkbox_input_selector: str = (
        WAREHOUSE_SCOPE_CHECKBOX_INPUT_SELECTOR
    )
    # ── B1 增量采集筛选器 ──
    inventory_date_filter_panel_selector: str = INVENTORY_DATE_FILTER_PANEL_SELECTOR
    inventory_date_filter_dimension_select_selector: str = (
        INVENTORY_DATE_FILTER_DIMENSION_SELECT_SELECTOR
    )
    inventory_date_filter_dimension_modified: str = (
        INVENTORY_DATE_FILTER_DIMENSION_MODIFIED
    )
    inventory_date_filter_dimension_create: str = INVENTORY_DATE_FILTER_DIMENSION_CREATE
    inventory_date_filter_dimension_modified_label: str = (
        INVENTORY_DATE_FILTER_DIMENSION_MODIFIED_LABEL
    )
    inventory_date_filter_dimension_create_label: str = (
        INVENTORY_DATE_FILTER_DIMENSION_CREATE_LABEL
    )
    inventory_date_filter_dimension_option_selector: str = (
        INVENTORY_DATE_FILTER_DIMENSION_OPTION_SELECTOR
    )
    inventory_date_filter_range_input_selector: str = (
        INVENTORY_DATE_FILTER_RANGE_INPUT_SELECTOR
    )
    inventory_date_filter_confirm_selector: str = INVENTORY_DATE_FILTER_CONFIRM_SELECTOR
    inventory_date_filter_clear_selector: str = INVENTORY_DATE_FILTER_CLEAR_SELECTOR
    inventory_date_filter_value_attr: str = INVENTORY_DATE_FILTER_VALUE_ATTR
    inventory_date_filter_root_selectors: Tuple[str, ...] = (
        INVENTORY_DATE_FILTER_ROOT_SELECTORS
    )
    inventory_date_filter_sku_total_text: str = INVENTORY_DATE_FILTER_SKU_TOTAL_TEXT
    # 真实页面结构（2026-10-26 失败现场取证）：文案/placeholder 驱动
    inventory_date_filter_dropdown_container_selectors: Tuple[str, ...] = (
        INVENTORY_DATE_FILTER_DROPDOWN_CONTAINER_SELECTORS
    )
    inventory_date_filter_range_start_placeholders: Tuple[str, ...] = (
        INVENTORY_DATE_FILTER_RANGE_START_PLACEHOLDERS
    )
    inventory_date_filter_range_end_placeholders: Tuple[str, ...] = (
        INVENTORY_DATE_FILTER_RANGE_END_PLACEHOLDERS
    )
    inventory_date_filter_trigger_ancestor_xpaths: Tuple[str, ...] = (
        INVENTORY_DATE_FILTER_TRIGGER_ANCESTOR_XPATHS
    )

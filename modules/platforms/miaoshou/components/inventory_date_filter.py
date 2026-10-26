"""妙手仓库清单「更新时间维度 + 自定义区间」筛选组件（B1）。

真实页面结构（2026-10-26 失败现场 + 页面截图取证）
------------------------------------------------
上一版把筛选器当成「picker 面板 + 维度 select + 确定/清空按钮」，
真实页面**根本没有那个面板**：

    [仓库: 全选] [商品SKU] [双击补录…]
    [是否有预占库存] [可用库存]
    [创建时间 ▾] [🕐 开始时间 ____ - 结束时间 ____] [🔍 搜索] [重置]
                 └─ 下拉展开后只有两项：创建时间 / 更新时间

- 时间维度是**筛选栏里的内联下拉**，触发器上直接显示当前维度名
- 下拉浮层里就两项：「创建时间」「更新时间」
- 日期区间是**内联的两个输入框**（占位文字「开始时间」「结束时间」）
- 填完**直接点「搜索」**，页面**没有「确定」「清空」按钮**

→ 上一版的 ``.jx-picker-panel`` 系列选择器全部落空。实测（任务 7b302e24）
  报「仓库清单日期筛选面板打不开」，采集在「设置更新时间维度与采集区间」
  这步就断了，**搜索和导出根本没开始**。

新策略
------
1. **以可见文案 / placeholder 为锚**，不赌 class 名
   （class 是 jx-ui 的实现细节、随版本变；「创建时间 / 更新时间 / 开始时间 /
   结束时间」是业务语义，稳定）
2. **定位必须限定范围** ← 2026-10-26 第二次失败（任务 5526faf9）补的
   结果表格的**表头里也有「创建时间」「更新时间」两列**（可排序），
   和下拉浮层里的选项**同名** → 全页 ``get_by_text("更新时间")`` 的第一个
   命中是**表头**，点下去变成「按更新时间排序」，维度根本没切。
   所以：触发器用维度键（``modelvaluegroup`` 里有 ``gmtCreate/gmtModified``）认，
   选项只在**可见的下拉浮层容器内**找，读当前维度**只从触发器读**。
   （详见 ``inventory_dimension_mixin.py``）
3. **幂等**：已经是「更新时间」就不碰下拉
   （用户可能已经手动选过 —— 重复点反而会把状态点乱）
4. **顺序无关**：浮层已经开着就别再点触发器（再点一下反而把它关了）
5. **「确定」可选**：页面没有就不点，**不算失败**
6. **证据用可见文本**：触发器文案变成「更新时间」本身就是人能读的落地证据

三处静默失败仍然必须挡住（页面照常显示、不报错，只会安静地给错数据）
--------------------------------------------------------------------
| # | 失败 | 后果 |
|---|---|---|
| 1 | **维度没切**（默认「创建时间」） | 同区间按更新时间 147 个 SKU，按创建时间只有 3 个 |
| 2 | **区间没落进去** | 筛选范围不是目标区间，导出的数据是错的 |
| 3 | **搜索没刷新** | 拿到的还是上一次的结果 |

→ 每一步都必须拿到**落地证据**，拿不到就当失败。
宁可失败，也不能拿错数据还显示成功。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_dimension_mixin import (
    DIMENSION_CREATE,
    DIMENSION_MODIFIED,
    InventoryDimensionMixin,
)


@dataclass(frozen=True)
class InventoryDateFilterEvidence:
    """一次筛选落地后可断言的证据。"""

    dimension: str
    """筛选栏上当前显示的维度文案，必须是「更新时间」"""

    applied_range: str
    """已应用区间的可读原文（输入框回填值或筛选器属性）"""

    start: str
    end: str

    @property
    def dimension_is_modified(self) -> bool:
        return self.dimension == DIMENSION_MODIFIED


class MiaoshouInventoryDateFilter(InventoryDimensionMixin):
    """把仓库清单的筛选器设成「更新时间维度 + 自定义区间」。"""

    platform = "miaoshou"
    component_type = "inventory_date_filter"
    data_domain = "inventory"

    def __init__(
        self, ctx: ExecutionContext, selectors: InventorySelectors | None = None
    ) -> None:
        self.ctx = ctx
        self.sel = selectors or InventorySelectors()

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
    @staticmethod
    async def _settle(page: Any, ms: int = 150) -> None:
        try:
            await page.wait_for_timeout(ms)
        except Exception:
            pass

    @staticmethod
    async def _first_visible(locator: Any) -> Optional[Any]:
        """取第一个**可见**的节点（找不到返回 None）。"""
        try:
            count = await locator.count()
        except Exception:
            return None
        for index in range(min(count, 12)):
            node = locator.nth(index)
            try:
                if await node.is_visible():
                    return node
            except Exception:
                continue
        return None

    async def _visible_nodes(self, page: Any, label: str) -> list[Any]:
        """页面上可见的、文本命中 label 的节点。

        ⚠️ **只用于页面上独一份的文案**（比如「SKU总数」）。
        「创建时间 / 更新时间」**不能用它** —— 表格表头里也有一模一样的两列，
        全页搜索会命中表头，点下去变成「按更新时间排序」，维度根本没切
        （2026-10-26 任务 5526faf9 的真实失败原因）。
        """
        for exact in (True, False):
            try:
                locator = page.get_by_text(label, exact=exact)
                count = await locator.count()
            except Exception:
                continue
            nodes: list[Any] = []
            for index in range(min(count, 12)):
                node = locator.nth(index)
                try:
                    if await node.is_visible():
                        nodes.append(node)
                except Exception:
                    continue
            if nodes:
                return nodes
        return []

    # ------------------------------------------------------------------
    # 维度下拉：定位（**必须限定范围**）
    # ------------------------------------------------------------------

    @staticmethod
    async def _read_attr(locator: Any, name: str) -> str:
        try:
            value = await locator.get_attribute(name)
        except Exception:
            return ""
        return str(value or "").strip()

    @staticmethod
    def _contains_time(applied: str, value: str) -> bool:
        """已应用区间里是否含目标时刻。

        只比对**日期部分**：妙手回填的文本格式（``2026-10-01 00:00:00`` /
        ``2026-10-01`` / 带逗号的千分位）实测不固定，比日期稳。
        """
        normalized = " ".join((applied or "").split())
        if not normalized:
            return False
        date_part = value.split(" ")[0]
        return bool(value and value in normalized) or bool(
            date_part and date_part in normalized
        )

    # ------------------------------------------------------------------
    # 取值
    # ------------------------------------------------------------------
    async def read_sku_total(self, page: Any) -> Optional[int]:
        """读页面上的「SKU总数」。读不到返回 None（**不等于 0**）。

        ⚠️ 数字必须**紧跟在「SKU总数」后面**取。
        页面同一块区域里还有「库存总数 / 库存总价值 / …」，全文取第一个数字
        会取错（真实页面实测曾读到 0）。
        """
        pattern = re.compile(self.sel.inventory_date_filter_sku_total_pattern)
        try:
            element = page.get_by_text(
                self.sel.inventory_date_filter_sku_total_text, exact=False
            ).first
        except Exception:
            return None
        for candidate in (element, element.locator("xpath=..")):
            try:
                text = (await candidate.text_content()) or ""
            except Exception:
                continue
            match = pattern.search(text)
            if not match:
                continue
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                continue
        return None

    async def _close_dropdown(self, page: Any) -> None:
        """把可能开着的维度浮层收起来。

        顺序无关的关键：浮层开着时，页面上「更新时间」既可能是触发器、
        也可能是浮层里的选项，分不清就收起来再读。
        """
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await self._settle(page)

    # ------------------------------------------------------------------
    # 各步骤
    # ------------------------------------------------------------------

    async def _first_visible_by_placeholder(
        self, page: Any, placeholders: tuple[str, ...]
    ) -> Optional[Any]:
        for text in placeholders:
            try:
                locator = page.locator(f"input[placeholder*='{text}']")
            except Exception:
                continue
            node = await self._first_visible(locator)
            if node is not None:
                return node
        return None

    async def _find_range_inputs(self, page: Any) -> tuple[Any, Any]:
        """找「开始时间 / 结束时间」两个输入框。"""
        start = await self._first_visible_by_placeholder(
            page, self.sel.inventory_date_filter_range_start_placeholders
        )
        end = await self._first_visible_by_placeholder(
            page, self.sel.inventory_date_filter_range_end_placeholders
        )
        if start is not None and end is not None:
            return start, end
        try:
            inputs = page.locator(self.sel.inventory_date_filter_range_input_selector)
            count = await inputs.count()
        except Exception:
            count = 0
        if count >= 2:
            return inputs.nth(0), inputs.nth(1)
        raise RuntimeError("找不到日期区间输入框（开始时间 / 结束时间）")

    @staticmethod
    async def _read_input_value(node: Any) -> str:
        """读输入框当前值。

        ``input_value()`` 无参、``get_attribute("value")`` 有参 —— 两者签名不同，
        混用会双双失败、读到空值（进而把「区间没落进去」误判成「没生效」）。
        """
        try:
            value = await node.input_value()
            if value:
                return str(value).strip()
        except Exception:
            pass
        try:
            value = await node.get_attribute("value")
            if value:
                return str(value).strip()
        except Exception:
            pass
        return ""

    async def _fill_one(self, node: Any, value: str, date_part: str) -> str:
        """填一个输入框，并校验回填值。

        妙手的输入框可能只接受到日期（``2026-10-01``），
        所以带时间的写法失败时自动降级到日期写法。
        """
        for candidate in (value, date_part):
            try:
                await node.click(timeout=1500)
            except Exception:
                pass
            try:
                await node.press("Control+A")
            except Exception:
                pass
            try:
                await node.fill(candidate, timeout=1500)
            except Exception:
                continue
            actual = await self._read_input_value(node)
            if actual and date_part in actual:
                return actual
        return await self._read_input_value(node)

    async def _fill_range(self, page: Any, *, start: str, end: str) -> tuple[str, str]:
        # 先把维度浮层收起来 —— 它正好盖在日期区间输入框上方，不收会点不到
        await self._close_dropdown(page)
        start_input, end_input = await self._find_range_inputs(page)
        start_value = await self._fill_one(start_input, start, start.split(" ")[0])
        end_value = await self._fill_one(end_input, end, end.split(" ")[0])
        return start_value, end_value

    async def _click_confirm_if_present(self, page: Any) -> bool:
        """点「确定」—— **页面没有这个按钮也不算失败**。

        真实页面填完区间直接点「搜索」，没有「确定/清空」。
        老版本组件把「确定」当成必经步骤，所以页面结构一变就整段失败。
        ⚠️ 必须要求**可见** —— 页面上有些隐藏面板里也放着同 class 的按钮。
        """
        try:
            confirm = page.locator(self.sel.inventory_date_filter_confirm_selector)
            count = await confirm.count()
        except Exception:
            return False
        for index in range(min(count, 4)):
            node = confirm.nth(index)
            try:
                if not await node.is_visible():
                    continue
                await node.click(timeout=1500)
                return True
            except Exception:
                continue
        return False

    async def _date_panel_visible(self, page: Any) -> bool:
        """日期选择面板（点开区间输入框后弹出）现在开着没有。"""
        try:
            locator = page.locator(self.sel.inventory_date_filter_date_panel_selector)
            if await locator.count() == 0:
                return False
            return bool(await locator.first.is_visible())
        except Exception:
            return False

    async def _close_date_panel(self, page: Any) -> bool:
        """把日期选择面板收起来 —— **必须收**，否则它挡着「搜索」按钮。

        实测（2026-10-26）：点开区间输入框会弹出 ``.jx-picker-panel``，
        面板开着时点「搜索」会一直被
        ``… .jx-picker-panel__sidebar … intercepts pointer events`` 拦到超时。

        顺序：先试「确定」（有确定按钮说明草稿有效，点它才算提交），
        确定不可用（``is-disabled``）就按 Escape 收起来 ——
        **区间到底有没有生效另有判据**（见 spec §8.14）。
        """
        if not await self._date_panel_visible(page):
            return True
        try:
            confirm = page.locator(self.sel.inventory_date_filter_confirm_selector)
            count = await confirm.count()
        except Exception:
            count = 0
        for index in range(min(count, 4)):
            node = confirm.nth(index)
            try:
                if not await node.is_visible():
                    continue
                if await node.is_disabled():
                    continue
                await node.click(timeout=1500)
                await self._settle(page)
                break
            except Exception:
                continue
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await self._settle(page)
        return not await self._date_panel_visible(page)

    async def _read_applied_range(self, page: Any) -> str:
        """读筛选器上已应用的区间（老路：``modelvaluegroup`` 属性）。"""
        for selector in self.sel.inventory_date_filter_root_selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="attached", timeout=1000)
                value = await self._read_attr(
                    locator, self.sel.inventory_date_filter_value_attr
                )
                if value:
                    return value
            except Exception:
                continue
        return ""

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    async def probe_state(self, page: Any) -> dict[str, Any]:
        """**只读**探测筛选器当前状态（给取证探针用）。

        用的是**组件自己的定位逻辑** → 探针的结论就是组件的结论，
        不会出现「探针能找到、组件找不到」这种两边不一致的情况。

        全程只读：不点下拉、不填区间、不点搜索、不点导出。
        """
        start_input = await self._first_visible_by_placeholder(
            page, self.sel.inventory_date_filter_range_start_placeholders
        )
        end_input = await self._first_visible_by_placeholder(
            page, self.sel.inventory_date_filter_range_end_placeholders
        )
        try:
            confirm = page.locator(self.sel.inventory_date_filter_confirm_selector)
            has_confirm = False
            count = await confirm.count()
            for index in range(min(count, 4)):
                if await confirm.nth(index).is_visible():
                    has_confirm = True
                    break
        except Exception:
            has_confirm = False
        return {
            "dimension": await self.read_current_dimension(page),
            "has_start_input": start_input is not None,
            "has_end_input": end_input is not None,
            "has_confirm_button": has_confirm,
            "sku_total": await self.read_sku_total(page),
            "applied_range_attr": await self._read_applied_range(page),
        }

    async def assert_search_refreshed(
        self,
        page: Any,
        *,
        total_before: Optional[int],
        logger: Any = None,
    ) -> None:
        """搜索后断言结果集确实刷新了（读筛选后的总数并判定）。"""
        total_after = await self.read_sku_total(page)
        assert_search_results_refreshed(
            total_before=total_before, total_after=total_after, logger=logger
        )

    async def apply_incremental_range(
        self, page: Any, *, start: str, end: str
    ) -> InventoryDateFilterEvidence:
        """把筛选器设成「更新时间 + [start, end]」，并交出落地证据。

        ``start`` / ``end`` 用 ``YYYY-MM-DD HH:MM:SS`` 文本。
        """
        dimension = await self._switch_to_modified_dimension(page)
        start_value, end_value = await self._fill_range(page, start=start, end=end)
        # 填完必须把日期面板收起来 —— 它会挡住「搜索」按钮
        if not await self._close_date_panel(page):
            raise RuntimeError(
                "日期选择面板没收起来：它会挡住「搜索」按钮，采集会卡在点搜索上"
            )
        await self._click_confirm_if_present(page)

        applied = await self._read_applied_range(page)
        # 两条证据路径：输入框回填值（真实页面）/ 筛选器属性（老路径）
        by_inputs = self._contains_time(start_value, start) and self._contains_time(
            end_value, end
        )
        by_attribute = self._contains_time(applied, start) and self._contains_time(
            applied, end
        )
        if not (by_inputs or by_attribute):
            raise RuntimeError(
                f"区间未生效：期望含 {start} / {end}，"
                f"输入框读到 {start_value!r} / {end_value!r}，筛选器读到 {applied!r}"
            )

        return InventoryDateFilterEvidence(
            dimension=dimension,
            applied_range=applied or f"{start_value},{end_value}",
            start=start,
            end=end,
        )


# 增量区间在执行配置里的键名（两个平铺的字符串键）
# ⚠️ 必须与 backend/services/collection_contracts.py 的常量一致：
#    任务的 date_range 契约是 Dict[str, str]，塞嵌套 dict 会让任务接口 500。
INCREMENTAL_RANGE_START_KEY = "inventory_incremental_range_start"
INCREMENTAL_RANGE_END_KEY = "inventory_incremental_range_end"


def read_incremental_range(config: Any) -> Optional[tuple[str, str]]:
    """从执行配置里读增量区间；没配就是全量采集（返回 None）。

    约定：``config["inventory_incremental_range_start"]`` 与
    ``config["inventory_incremental_range_end"]`` 两个字符串键。
    """
    if not isinstance(config, dict):
        return None
    start = str(config.get(INCREMENTAL_RANGE_START_KEY) or "").strip()
    end = str(config.get(INCREMENTAL_RANGE_END_KEY) or "").strip()
    if not start or not end:
        return None
    return start, end


def assert_search_results_refreshed(
    *,
    total_before: Optional[int],
    total_after: Optional[int],
    logger: Any = None,
) -> None:
    """断言搜索确实刷新了结果集。

    - ``total_after`` 必须 **> 0**：0 = 筛选把范围清空了，或筛选根本没生效
    - ``total_after`` 不得 **> ``total_before``：筛选后不可能更多
    - 两者**相等**只记警告、不报错：增量窗口可能覆盖了全量数据（例如首采长窗口），
      此时相等是合法的。真正能抓住「维度切错 / 区间没生效」的是
      维度文案与区间回填值那两条证据，不是这里的计数差。
    """
    if total_after is None:
        raise RuntimeError("读不到「SKU总数」：搜索结果没有刷新")
    if total_after <= 0:
        raise RuntimeError(
            f"「SKU总数」为 {total_after}：筛选把范围清空了，或筛选根本没生效"
        )
    if total_before is not None and total_after > total_before:
        raise RuntimeError(
            f"「SKU总数」筛选后反而变多（{total_before} → {total_after}）：筛选没生效"
        )
    if total_before is not None and total_after == total_before:
        message = (
            f"「SKU总数」筛选前后都是 {total_after}："
            "增量窗口可能覆盖了全量数据，请确认窗口区间"
        )
        if logger is not None:
            try:
                logger.warning(message)
            except Exception:
                pass

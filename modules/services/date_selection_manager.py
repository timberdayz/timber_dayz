from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass
class DateSelectionResult:
    success: bool
    message: str = ""


class DateSelectionManager:
    """
    统一的日期选择与校验管理器（可复用到 流量/商品/订单/财务 等子类型）。

    策略（Shopee 初版）：
    - 配方优先：优先使用 RecipeExecutor 在页面上复刻用户录制的日期选择步骤；
    - 快捷项回退：如配方失效，尝试点击“过去7/30”等快捷项；
    - 严格校验：优先读取 UI 毫秒时间戳进行比对（右开区间），失败则回退文本关键字校验；

    目前上下文 context 支持："traffic"（流量表现），后续可扩展 "products"、"orders"、"finance"。
    """

    OPTION_TEXT = {
        "yesterday": "昨天",
        "last7": "过去7天",
        "last30": "过去30天",
    }
    QUICK_LABEL = {
        "last7": "过去7",
        "last30": "过去30",
    }

    def __init__(self, playwright=None, logger_ref=None) -> None:
        self.playwright = playwright
        self._logger = logger_ref or logger

    # --- Public API -------------------------------------------------------
    def select_and_verify(
        self,
        *,
        page,
        preset: Optional[str],
        start_date: str,
        end_date: str,
        context: str = "traffic",
    ) -> bool:
        """
        执行“选择日期 + 校验生效”的完整流程。

        Args:
            page: Playwright Page
            preset: "yesterday"/"last7"/"last30"（None 表示不变更）
            start_date, end_date: 期望的日期范围（YYYY-MM-DD）
            context: 数据子类型上下文（"traffic" | "products" | ...）
        Returns:
            bool: 是否生效
        """
        if not preset:
            return True  # 不修改时间，跳过

        option_text = self.OPTION_TEXT.get(preset)
        quick_label = self.QUICK_LABEL.get(preset)

        recipe_ok = False
        try:
            recipe_ok = self._try_recipe(page, option_text, context)
        except Exception as e:
            self._logger.debug(f"日期配方执行异常: {e}")

        if not recipe_ok and quick_label:
            try:
                self._quick_set(page, quick_label)
            except Exception as e:
                self._logger.debug(f"快捷项设置失败: {e}")

        # 严格校验，若失败再给一次快捷项机会
        ok = self._verify(page, start_date, end_date, option_text, context)
        if ok:
            return True

        if quick_label:
            try:
                self._quick_set(page, quick_label)
            except Exception:
                pass
            ok = self._verify(page, start_date, end_date, option_text, context)
            if ok:
                return True

        self._logger.warning("时间选择未生效：请稍后重试或检查页面结构")
        return False

    # --- Internals --------------------------------------------------------
    def _try_recipe(self, page, option_text: Optional[str], context: str) -> bool:
        if not option_text:
            return False
        try:
            from modules.services.recipe_executor import RecipeExecutor
            rexe = RecipeExecutor()
            if context == "traffic":
                self._logger.info(f"执行日期选择配方(traffic): {option_text}")
                return bool(rexe.execute_traffic_date_recipe(page, option_text))
            elif context == "order":
                self._logger.info(f"执行日期选择配方(order): {option_text}")
                return bool(rexe.execute_order_date_recipe(page, option_text))
            elif context == "finance":
                self._logger.info(f"执行日期选择配方(finance): {option_text}")
                return bool(rexe.execute_finance_date_recipe(page, option_text))
            else:
                # 默认走通用日期配方（商品等其他类型）
                self._logger.info(f"执行日期选择配方(generic): {option_text}")
                return bool(rexe.execute_date_picker_recipe(page, target_option=option_text))
        except Exception as e:
            self._logger.debug(f"配方异常: {e}")
            return False

    def _quick_set(self, page, quick_label: str) -> None:
        # 复用已有的 helper 以避免选择器重复维护
        from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
        helper = ShopeePlaywrightExporter(self.playwright)
        helper._set_quick_timerange(page, quick_label)

    def _verify(self, page, start_date: str, end_date: str, option_text: Optional[str], context: str) -> bool:
        try:
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            helper = ShopeePlaywrightExporter(self.playwright)
            if context == "traffic":
                ok = helper._verify_traffic_time_selection(page, start_date, end_date, option_text or "")
                return bool(ok)
            else:
                # 通用校验：读取 UI 毫秒时间戳并与入参比较
                try:
                    start_ms, end_ms = helper._read_week_from_ui(page)
                except Exception:
                    start_ms, end_ms = None, None
                if start_ms and end_ms:
                    from datetime import datetime as dt, timezone, timedelta
                    tz = timezone(timedelta(hours=8))
                    s = dt.fromtimestamp(start_ms / 1000, tz).date().isoformat()
                    e = (dt.fromtimestamp(end_ms / 1000, tz) - timedelta(days=1)).date().isoformat()
                    if s == start_date and e == end_date:
                        self._logger.info("时间范围校验通过(UI, generic)")
                        return True
                # 退化关键字：尽量放行（不同子类型文案可能不同，后续按模块专项优化）
                text = (helper._read_time_display(page) or {}).get("value") or ""
                if option_text and option_text in text:
                    return True
                return False
        except Exception as e:
            self._logger.debug(f"校验异常: {e}")
            return False


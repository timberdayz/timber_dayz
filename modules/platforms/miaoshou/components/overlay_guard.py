from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Set

# 配置来源：优先使用 *_config.py 中的列表与策略，以便后续只改配置即可生效
from .warehouse_config import WarehouseSelectors
from .products_config import ProductsSelectors


@dataclass
class OverlayGuard:
    """Miaoshou 专用：观察-关闭弹窗 的轻量守护组件。

    - 选择器、轮询轮次/间隔均来自 *_config.py，可热更新
    - 顶层 + 所有 frame 并行尝试
    - 支持 ESC 兜底
    """

    def _collect_selectors(self) -> List[str]:
        ws = WarehouseSelectors()
        try:
            ps = ProductsSelectors()
        except Exception:
            ps = None
        sels: Set[str] = set(getattr(ws, "popup_close_buttons", []))
        if ps:
            sels.update(getattr(ps, "popup_close_buttons", []))
        return list(sels)

    def _poll_strategy(self) -> tuple[int, int]:
        ws = WarehouseSelectors()
        rounds = int(getattr(ws, "close_poll_max_rounds", 20))
        interval = int(getattr(ws, "close_poll_interval_ms", 300))
        return rounds, interval

    async def run(self, page: Any, *, label: Optional[str] = None) -> int:
        """执行一次观察-关闭流程，返回估计关闭的次数。

        Args:
            page: Playwright Page 实例
            label: 可选的日志标签
        Returns:
            int: 估计被关闭的弹窗点击次数
        """
        sels = self._collect_selectors()
        rounds, interval = self._poll_strategy()
        closed_count = 0
        try:
            if label:
                print(label)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            for _ in range(rounds):
                closed = False
                for s in sels:
                    try:
                        el = page.locator(s).first
                        if await el.count() > 0 and await el.is_visible():
                            await el.click(timeout=800)
                            closed = True
                            closed_count += 1
                    except Exception:
                        pass
                try:
                    for fr in page.frames:
                        for s in sels:
                            try:
                                el2 = fr.locator(s).first
                                if await el2.count() > 0 and await el2.is_visible():
                                    await el2.click(timeout=800)
                                    closed = True
                                    closed_count += 1
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    await page.wait_for_timeout(interval)
                except Exception:
                    pass
        except Exception:
            pass
        return closed_count


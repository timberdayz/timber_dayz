from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
import re

from modules.components.base import ExecutionContext


@dataclass
class ShopSelectResult:
    success: bool
    region: Optional[str] = None
    shop_name: Optional[str] = None
    shop_code: Optional[str] = None
    message: str = ""


class TiktokShopSelector:
    """Discover and select TikTok shop (region -> shop).

    Notes:
    - TikTok 常见为“按区域切换店铺”，UI 会展示地区(MY/PH/SG 等)；截图中店铺代码位于店铺名下方。
    - 本组件以极保守方式实现：
      1) 尝试从 homepage 读取 DOM 文本，解析可用区域以及店铺代码
      2) 发现失败时，回退为提示用户输入（不阻断主流程）
    - 仅在 run() 中执行 UI/网络操作；导入期无副作用
    """

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self.logger = getattr(ctx, "logger", None)

    def _log(self, level: str, msg: str) -> None:
        try:
            if self.logger and hasattr(self.logger, level):
                getattr(self.logger, level)(f"[TiktokShopSelector] {msg}")
        except Exception:
            pass

    def _extract_regions(self, html: str) -> List[str]:
        # 常见区域代码
        candidates = ["MY", "PH", "SG", "TH", "VN", "ID", "TW", "CN"]
        found: List[str] = []
        # 先匹配括号内代码，例如 “(MY)”
        for m in re.findall(r"\(([A-Z]{2})\)", html):
            if m in candidates and m not in found:
                found.append(m)
        # 兜底：如果 UI 未显示括号，直接查找代码词
        for c in candidates:
            if c in html and c not in found:
                found.append(c)
        return found

    def _extract_shop_name(self, html: str) -> Optional[str]:
        # 粗略从标题/头像旁文本抓取，优先中文/英文名样式
        # 这里采用简单启发：抓取 “主账号” 上方/附近的粗体名称不可靠，退化为从 ctx.account
        acc = self.ctx.account or {}
        return (
            acc.get("menu_display_name")
            or acc.get("display_shop_name")
            or acc.get("store_name")
            or acc.get("label")
            or acc.get("username")
        )

    def _extract_shop_code(self, html: str) -> Optional[str]:
        # 匹配 “店铺代码: XXXXXXX” 或 “Shop code: XXXXXXX”
        m = re.search(r"店铺代码\s*[:：]\s*([A-Z0-9]+)", html)
        if not m:
            m = re.search(r"Shop\s*code\s*[:：]\s*([A-Z0-9]+)", html, re.I)
        return m.group(1) if m else None

    async def run(self, page: Any) -> ShopSelectResult:
        try:
            # 0) 可用区域候选：优先使用账号配置，其次默认仅列出 MY/PH/SG
            acc = self.ctx.account or {}
            allowed: List[str] = []
            try:
                cfg_allowed = acc.get("allowed_regions") or []
                if isinstance(cfg_allowed, list):
                    allowed = [str(x).upper() for x in cfg_allowed if str(x).strip()]
            except Exception:
                pass
            if not allowed:
                allowed = ["MY", "PH", "SG"]

            # 1) 逐区域探测 homepage，并尝试读取"店铺代码"
            candidates: list[tuple[str, Optional[str], Optional[str]]] = []  # (region, shop_name, shop_code)
            for r in allowed:
                url = f"https://seller.tiktokshopglobalselling.com/homepage?shop_region={r}"
                nav_ok = False
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    nav_ok = True
                except Exception:
                    try:
                        await page.goto(url, wait_until="load", timeout=25000)
                        nav_ok = True
                    except Exception:
                        nav_ok = False
                if nav_ok:
                    try:
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass

                # 读取店铺名/代码（即使导航失败也不隐藏该区域）
                shop_name = self._extract_shop_name("") or "unknown_shop"
                shop_code = None
                if nav_ok:
                    try:
                        loc = page.locator("div.text-p4-regular.text-neutral-text4.mb-4.px-24.break-all")
                        texts = []
                        try:
                            texts = await loc.all_inner_texts() or []
                        except Exception:
                            try:
                                texts = [await loc.inner_text(timeout=1000)]
                            except Exception:
                                texts = []
                        for t in texts:
                            m = re.search(r"店铺代码\s*[:：]\s*([A-Z0-9]+)", t)
                            if not m:
                                m = re.search(r"Shop\s*code\s*[:：]\s*([A-Z0-9]+)", t, re.I)
                            if m:
                                shop_code = m.group(1)
                                break
                        if not shop_code:
                            html = await page.content()
                            shop_code = self._extract_shop_code(html)
                    except Exception:
                        pass

                candidates.append((r, shop_name, shop_code))

            # 2) 菜单显示（仅列出探测到的候选）
            if not candidates:
                ans = input("[SHOP] 未自动发现有效区域，请输入区域代码(MY/PH/SG...)，回车跳过: ").strip().upper()
                if not ans:
                    return ShopSelectResult(success=False, message="no region selected")
                picked_region = ans
                shop_name = self._extract_shop_name("") or "unknown_shop"
                shop_code = None
            else:
                print("\n[SHOP] 可用区域/店铺：")
                for idx, (r, sname, scode) in enumerate(candidates, 1):
                    extra = f"（店铺代码: {scode}）" if scode else ""
                    print(f"  {idx}. {sname} - {r} {extra}")
                ans = input("请选择序号（或直接输入区域代码，回车默认第1项）: ").strip().upper()
                if not ans:
                    picked_region, shop_name, shop_code = candidates[0]
                elif ans.isdigit() and 1 <= int(ans) <= len(candidates):
                    picked_region, shop_name, shop_code = candidates[int(ans) - 1]
                else:
                    picked_region = ans
                    first = candidates[0]
                    shop_name = first[1]
                    shop_code = None

            # 3) 回写到上下文，供落盘与导航使用
            self.ctx.config = self.ctx.config or {}
            self.ctx.config["shop_region"] = picked_region
            if shop_code:
                self.ctx.config["shop_id"] = shop_code
            # 店铺目录命名：与 Shopee 对齐，采用 “account_label_region” 形式（均为小写/slug时处理）
            try:
                acc = self.ctx.account or {}
                account_label = acc.get("label") or acc.get("store_name") or acc.get("username") or "unknown"
            except Exception:
                account_label = "unknown"
            shop_name_norm = f"{account_label}_{picked_region.lower()}"
            self.ctx.config["shop_name"] = shop_name_norm

            self._log("info", f"selected region={picked_region}, shop_name={self.ctx.config.get('shop_name')}, shop_id={self.ctx.config.get('shop_id')}")
            return ShopSelectResult(success=True, region=picked_region, shop_name=self.ctx.config.get("shop_name"), shop_code=shop_code, message="ok")
        except Exception as e:
            self._log("error", f"failed: {e}")
            return ShopSelectResult(success=False, message=str(e))


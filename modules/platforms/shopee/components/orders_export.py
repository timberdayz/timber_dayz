from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportResult, ExportMode, build_standard_output_root
from modules.platforms.shopee.components.orders_config import OrdersSelectors
from modules.utils.path_sanitizer import build_output_path, build_filename


class ShopeeOrdersExport(ExportComponent):
    """Shopee 订单表现（Orders）导出组件

    - 只依赖 orders_config 中的 URL/选择器
    - 统一落盘到 temp/outputs/shopee/<账号>/<店铺>/orders/<粒度>/
    - 优先 UI 导出（点击->等待->下载），后续可扩展 API 备选
    """

    # Component metadata
    platform = "shopee"
    component_type = "export"
    data_domain = "orders"

    def __init__(self, ctx: ExecutionContext, selectors: Optional[OrdersSelectors] = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or OrdersSelectors()

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            account = self.ctx.account
            cfg = self.ctx.config or {}
            # 店铺命名优先级：菜单显示名 > 账号里显式的display/menu字段 > store_name > 配置里的shop_name
            shop_name = (
                account.get("menu_display_name")
                or account.get("menu_name")
                or account.get("selected_shop_name")
                or account.get("display_shop_name")
                or account.get("display_name")
                or account.get("store_name")
                or cfg.get("shop_name")
                or "unknown_shop"
            )
            # 账号标签仍保持 label 优先，回退到 store_name/username，避免路径大范围变化
            account_label = account.get("label") or account.get("store_name") or account.get("username", "unknown")

            # 1) 确认页面加载完成（探针）
            for probe in self.sel.data_ready_probes:
                try:
                    if await page.locator(probe).first.is_visible():
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(500)

            # 1.1) 统一日期设置（可选）：若上游注入了 date_preset，则执行"配方优先->快捷项回退->严格校验"
            try:
                preset = cfg.get("date_preset")
                if preset:
                    from modules.services.date_selection_manager import DateSelectionManager
                    mgr = DateSelectionManager()
                    ok = await mgr.select_and_verify(
                        page=page,
                        preset=preset,
                        start_date=str(cfg.get("start_date", "")),
                        end_date=str(cfg.get("end_date", "")),
                        context="orders",
                    )
                    if not ok and self.logger:
                        self.logger.warning("[ShopeeOrdersExport] 日期设置未生效，将继续尝试导出")
            except Exception:
                pass

            # 2) 点击导出
            clicked = False
            for btn in self.sel.export_buttons:
                try:
                    loc = page.locator(btn)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        if self.logger:
                            self.logger.info(f"[ShopeeOrdersExport] 点击导出按钮: {btn}")
                        await loc.first.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                return ExportResult(False, None, "未找到导出按钮")

            await page.wait_for_timeout(1000)

            # 3) 等待"下载"按钮就绪并点击，捕获下载（支持30s重试机制）
            download = None
            download_button_used = None

            # 第一次尝试：短超时快速检测
            for btn in self.sel.download_buttons:
                try:
                    loc = page.locator(btn)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        try:
                            async with page.expect_download(timeout=5000) as dl_info:
                                await loc.first.click()
                            download = dl_info.value
                            download_button_used = btn
                            if self.logger:
                                self.logger.info(f"[ShopeeOrdersExport] 立即下载成功")
                            break
                        except Exception:
                            if self.logger:
                                self.logger.info(f"[ShopeeOrdersExport] 未检测到立即下载，尝试重试机制")

                            # 30s后重试一次导出按钮
                            await page.wait_for_timeout(30000)
                            try:
                                # 重新点击导出按钮
                                for export_btn in self.sel.export_buttons:
                                    try:
                                        export_loc = page.locator(export_btn)
                                        if await export_loc.count() > 0 and await export_loc.first.is_visible():
                                            await export_loc.first.click()
                                            if self.logger:
                                                self.logger.info(f"[ShopeeOrdersExport] 30s后重试点击导出按钮")
                                            await page.wait_for_timeout(1000)
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass

                            # 第二次尝试：正常超时
                            try:
                                async with page.expect_download(timeout=30000) as dl_info:
                                    await loc.first.click()
                                download = dl_info.value
                                download_button_used = btn
                                break
                            except Exception:
                                continue
                except Exception:
                    continue

            if download:
                # 4) 保存文件到标准目录（使用统一路径构建）
                gran = cfg.get("granularity") or "manual"
                start_date = cfg.get("start_date")
                end_date = cfg.get("end_date")

                out_root = build_standard_output_root(self.ctx, data_type="orders", granularity=gran)
                out_root.mkdir(parents=True, exist_ok=True)

                tmp_name = download.suggested_filename or "orders.xlsx"
                tmp_path = out_root / tmp_name
                await download.save_as(str(tmp_path))

                # 统一命名（使用统一文件命名函数）
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = build_filename(
                    ts=ts,
                    account_label=account_label,
                    shop_name=shop_name,
                    data_type="orders",
                    granularity=gran,
                    start_date=start_date,
                    end_date=end_date,
                    suffix=".xlsx"
                )
                target = out_root / filename
                try:
                    tmp_path.rename(target)
                except Exception:
                    import shutil
                    shutil.copy2(tmp_path, target)
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

                if self.logger:
                    self.logger.success(f"[OK] Export complete: {target}")
                print(f"\n[OK] Export complete: {target}")
                return ExportResult(True, str(target), "Download complete (UI)")
            else:
                return ExportResult(False, None, "未捕获到下载事件或未找到下载按钮")

        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeOrdersExport] 失败: {e}")
            return ExportResult(False, None, str(e))

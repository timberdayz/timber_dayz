"""
Flow Orchestrator
=================

目标
- 以“账号”为单位，将“自动登录 + 自动采集(orders/products/analytics/finance)”编排为可复用流程。
- 严格遵守登录入口 login_url 规范；自动采集阶段只在确认“已在后台且账号健康”的前提下执行。
- 统一回放录制脚本的入口，支持 Playwright Inspector。

设计
- Orchestrator 接受 platform/account/data_type 三元组；
- 基于 recording_registry 选择“稳定版/最新”的脚本组合；
- 运行时注入会话管理/设备指纹/健康检查；
- 全链路日志、错误兜底，不破坏现有代码。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional

from modules.utils.logger import get_logger
from modules.utils.recording_registry import (
    RecordingType,
    ensure_index,
    plan_flow,
)
from modules.utils.account_health_checker import AccountHealthChecker
from modules.utils.platform_adapters import get_platform_adapter

logger = get_logger(__name__)


class FlowOrchestrator:
    def __init__(self, platform: str):
        self.platform = platform.lower()
        self.adapter = get_platform_adapter(self.platform)

    def plan(self, account_name: str, data_type: RecordingType):
        ensure_index(self.platform)
        login, collect = plan_flow(self.platform, account_name, data_type)
        return login, collect

    def run(self, playwright_context_factory, account: Dict, data_type: RecordingType,
            shop_id: Optional[str] = None, use_deep_link: bool = True, **kwargs) -> bool:
        """执行“自动登录 + 自动采集(data_type)”组合。

        Args:
            playwright_context_factory: 一个回调，返回 (browser, context, page)，由现有系统提供
            account: 账号配置
            data_type: RecordingType
        Returns:
            bool: 是否成功
        """
        account_name = account.get("name") or account.get("username")

        # 如果使用深链接模式，只需要登录脚本
        if use_deep_link and shop_id:
            login_path, _ = self.plan(account_name, data_type)
            if not login_path:
                logger.error("未找到登录录制脚本，请先完成自动登录录制")
                return False

            logger.info(f"[ACTION] 深链接模式: 登录 -> 直达 {data_type.value} 页面 (店铺: {shop_id})")
        else:
            # 传统模式：需要登录+采集脚本
            login_path, collect_path = self.plan(account_name, data_type)
            if not login_path:
                logger.error("未找到登录录制脚本，请先完成自动登录录制")
                return False
            if not collect_path:
                logger.error("未找到采集录制脚本，请先完成该类型的数据采集录制")
                return False

            logger.info(f"[ACTION] 传统模式: 登录= {login_path} -> 采集= {collect_path}")

        browser, context, page = playwright_context_factory()
        try:
            # 1) 执行登录脚本
            self._run_script(login_path, page, account)

            # 2) 登录后健康检查
            checker = AccountHealthChecker(self.platform)
            status, msg, _ = checker.check_account_health(page, account)
            if not checker.handle_unhealthy_account(status, msg, account, page):
                logger.error("登录后账号健康校验未通过，停止采集")
                return False

            # 3) 深链接直达或传统采集
            if use_deep_link and shop_id:
                return self._execute_deep_link_collection(page, account, data_type, shop_id, **kwargs)
            else:
                # 传统模式：回放采集脚本
                self._run_script(collect_path, page, account)
                logger.success("[OK] 传统流程执行完成")
                return True
        except Exception as e:
            logger.error(f"[FAIL] 流程执行异常: {e}")
            return False
        finally:
            # 注意：由上层统一关闭 context / browser
            pass

    def _execute_deep_link_collection(self, page, account: Dict, data_type: RecordingType,
                                    shop_id: str, **kwargs) -> bool:
        """执行深链接直达采集"""
        try:
            # 1) 构造深链接并导航
            deep_link = self.adapter.build_deep_link(data_type, shop_id, **kwargs)
            logger.info(f"[LINK] 导航到深链接: {deep_link}")

            page.goto(deep_link, wait_until="domcontentloaded", timeout=60000)

            # 等待页面稳定
            time.sleep(3)

            # 2) 验证店铺访问权限
            has_access, access_msg = self.adapter.validate_shop_access(page, shop_id)
            if not has_access:
                logger.error(f"[FAIL] 店铺访问验证失败: {access_msg}")
                return False

            logger.success(f"[OK] 店铺访问验证通过: {access_msg}")

            # 3) 等待页面关键元素加载
            selectors = self.adapter.get_page_selectors(data_type)

            # 等待数据表格或主要内容加载
            if "data_table" in selectors:
                try:
                    page.wait_for_selector(selectors["data_table"], timeout=20000)
                    logger.info("[OK] 数据表格已加载")
                except:
                    logger.warning("[WARN] 数据表格加载超时，但继续执行")

            # 4) 尝试直接导出（优先）或点击导出按钮（兜底）
            return self._perform_data_export(page, data_type, shop_id, **kwargs)

        except Exception as e:
            logger.error(f"[FAIL] 深链接采集执行失败: {e}")
            return False

    def _perform_data_export(self, page, data_type: RecordingType, shop_id: str, **kwargs) -> bool:
        """执行数据导出"""
        try:
            # 方案A：直接调用导出API（推荐）
            try:
                export_config = self.adapter.get_export_config(data_type, shop_id, **kwargs)
                logger.info(f"[START] 尝试直接API导出: {export_config.endpoint}")

                response = page.request.get(
                    export_config.endpoint,
                    params=export_config.params,
                    headers=export_config.headers,
                    timeout=export_config.timeout
                )

                if response.ok:
                    # 保存导出文件
                    output_path = self._generate_output_path(data_type, shop_id, export_config.file_extension)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(response.body())

                    logger.success(f"[OK] API导出成功: {output_path}")
                    return True
                else:
                    logger.warning(f"[WARN] API导出失败 (状态码: {response.status})，尝试点击导出")

            except Exception as api_error:
                logger.warning(f"[WARN] API导出异常: {api_error}，尝试点击导出")

            # 方案B：点击导出按钮（兜底）
            return self._click_export_button(page, data_type, shop_id)

        except Exception as e:
            logger.error(f"[FAIL] 数据导出失败: {e}")
            return False

    def _click_export_button(self, page, data_type: RecordingType, shop_id: str) -> bool:
        """点击导出按钮进行下载"""
        try:
            selectors = self.adapter.get_page_selectors(data_type)
            export_button = selectors.get("export_button")

            if not export_button:
                logger.error("[FAIL] 未配置导出按钮选择器")
                return False

            # 等待导出按钮出现
            try:
                page.wait_for_selector(export_button, timeout=10000)
            except:
                logger.error(f"[FAIL] 导出按钮未找到: {export_button}")
                return False

            # 监听下载事件
            with page.expect_download(timeout=60000) as download_info:
                page.click(export_button)
                logger.info("[MOUSE] 已点击导出按钮，等待下载...")

            download = download_info.value

            # 保存下载文件
            file_extension = download.suggested_filename.split('.')[-1] if '.' in download.suggested_filename else 'unknown'
            output_path = self._generate_output_path(data_type, shop_id, file_extension)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            download.save_as(str(output_path))
            logger.success(f"[OK] 点击导出成功: {output_path}")
            return True

        except Exception as e:
            logger.error(f"[FAIL] 点击导出失败: {e}")
            return False

    def _generate_output_path(self, data_type: RecordingType, shop_id: str, file_extension: str) -> Path:
        """生成输出文件路径"""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{data_type.value}_{shop_id}.{file_extension}"

        output_dir = Path("temp/outputs") / self.platform / shop_id / data_type.value
        return output_dir / filename

    def _run_script(self, script_path: str, page, account: Dict):
        """简单的脚本执行加载器：以模块方式 import 并调用 run(page, account)。
        录制模板需要暴露 def run(page, account): -> None
        """
        script_file = Path(script_path)
        if not script_file.exists():
            raise FileNotFoundError(script_path)

        import importlib.util
        spec = importlib.util.spec_from_file_location("_rec_module", str(script_file))
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        if hasattr(module, "run"):
            logger.info(f"[START] 回放脚本: {script_file.name}")
            module.run(page, account)
        else:
            raise AttributeError(f"录制脚本缺少 run(page, account) 入口: {script_file}")


__all__ = ["FlowOrchestrator", "RecordingType"]


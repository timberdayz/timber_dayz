"""
数据采集中心核心功能处理器

迁移原系统中的核心数据采集功能，包括：
- 录制向导功能
- 数据采集功能
- 智能登录功能
- 验证码处理功能
"""

import time
import asyncio
import subprocess
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# 可选依赖导入
try:
    import psutil
except ImportError:
    psutil = None

from modules.core.logger import get_logger

logger = get_logger(__name__)


def _auto_register_downloaded_files(downloaded_files: List[str]) -> Dict[str, Any]:
    """
    自动注册下载的文件到 catalog_files 表
    
    Phase 0 - 数据采集器自动注册功能：
    - 在数据采集器下载文件后自动调用
    - 只注册新下载的文件，不扫描整个目录
    - 注册失败不影响采集流程
    
    Args:
        downloaded_files: 下载的文件路径列表
        
    Returns:
        Dict: 注册结果统计
    """
    if not downloaded_files:
        return {"registered": 0, "skipped": 0, "failed": 0, "file_ids": []}
    
    try:
        from modules.services.catalog_scanner import register_single_file
        
        registered_count = 0
        skipped_count = 0
        failed_count = 0
        file_ids = []
        
        for file_path in downloaded_files:
            try:
                file_id = register_single_file(file_path)
                if file_id:
                    registered_count += 1
                    file_ids.append(file_id)
                    logger.info(f"[AutoRegister] 文件已注册: {file_path} (ID: {file_id})")
                else:
                    skipped_count += 1
                    logger.debug(f"[AutoRegister] 文件已存在或跳过: {file_path}")
            except Exception as e:
                failed_count += 1
                logger.warning(f"[AutoRegister] 注册文件失败 {file_path}: {e}", exc_info=True)
                # 注册失败不影响采集流程，继续处理下一个文件
        
        result = {
            "registered": registered_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "file_ids": file_ids
        }
        
        if registered_count > 0:
            logger.info(f"[AutoRegister] 自动注册完成: 成功{registered_count}个, 跳过{skipped_count}个, 失败{failed_count}个")
            print(f"[OK] 文件自动注册完成: 成功{registered_count}个文件")
        
        return result
        
    except Exception as e:
        logger.error(f"[AutoRegister] 自动注册功能异常: {e}", exc_info=True)
        # 自动注册失败不影响采集流程
        return {"registered": 0, "skipped": 0, "failed": len(downloaded_files), "file_ids": [], "error": str(e)}


class RecordingWizardHandler:
    """录制向导处理器 - 迁移自原系统 run_recording_wizard"""

    def __init__(self):
        self.supported_platforms = ['妙手ERP', 'Shopee', 'Amazon', 'miaoshou', 'miaoshou_erp']
        self.recording_types = [
            ("login", "[LOCK] 登录流程录制", "录制账号登录、验证码处理等认证流程"),
            ("login_auto", "[BOT] 自动登录流程修正", "系统自动完成验证码输入和登录，无需手动操作"),
            ("collection", "[DATA] 数据采集录制", "自动登录后直接到登录后的网页，录制数据采集操作"),
            ("complete", "[RETRY] 完整流程录制", "录制从登录到数据采集的完整流程")
        ]

    def run_recording_wizard(self):
        """运行录制向导（兼容旧版交互）。
        默认走旧版完整流程（平台->账号->录制类型->数据类型->模板->执行）。
        """
        try:
            self.run_legacy_recording_flow()
        except Exception as e:
            logger.error(f"录制向导失败: {e}")
            print(f"[FAIL] 录制向导失败: {e}")

    def run_legacy_recording_flow(self, dtype_key: Optional[str] = None, preset_type: Optional[str] = None) -> None:
        """旧版录制流程：
        - 选择平台 -> 选择账号（要求 enabled 且配置 login_url）
        - 选择录制类型（登录/自动登录修正/数据采集/完整流程）或使用外部预设 preset_type
        - 选择数据类型（当需要时；登录-only 可省略）或使用外部预设 dtype_key
        - 生成录制模板 -> 执行对应录制/回放流程
        """
        accounts = self._load_accounts()
        if not accounts:
            print("[FAIL] 未找到任何账号，请先在 local_accounts.py 或加密配置中添加账号")
            return

        # 平台与账号
        plat, plat_accounts = self._select_platform(accounts)
        if not plat or not plat_accounts:
            return
        account = self._select_account(plat_accounts, plat)
        if not account:
            return

        # 录制类型
        rec_type = preset_type or self._select_recording_type()
        if not rec_type:
            return

        # 数据类型（仅当需要）
        dt_key = dtype_key
        if not dt_key and rec_type in ("data_collection", "collection", "complete", "full_process"):
            dt_key = self._select_data_type(plat)
            if not dt_key:
                return

        # 模板并执行
        template = self._create_recording_template(account, plat, rec_type, dt_key)
        if not template:
            return
        self._execute_recording(account, plat, rec_type, dt_key, template)

    def _load_accounts(self) -> List[Dict]:
        """从数据库加载账号配置（v4.7.0）"""
        try:
            from backend.services.account_loader_service import get_account_loader_service
            from backend.models.database import SessionLocal
            
            db = SessionLocal()
            try:
                account_loader = get_account_loader_service()
                accounts = account_loader.load_all_accounts(db)
                
                if not accounts:
                    logger.warning("数据库中没有启用的账号")
                    print("[WARN] 数据库中没有启用的账号")
                    return []
                
                logger.info(f"从数据库加载了 {len(accounts)} 个账号")
                print(f"[OK] 从数据库加载了 {len(accounts)} 个账号")
                return accounts
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"从数据库加载账号失败: {e}")
            print(f"[ERROR] 从数据库加载账号失败: {e}")
            return []

    def _select_platform(self, accounts: List[Dict]) -> tuple:
        """选择平台"""
        # 按平台分组
        platforms = {}
        for account in accounts:
            platform = account.get('platform', 'unknown')
            if platform not in platforms:
                platforms[platform] = []
            platforms[platform].append(account)

        print(f"\n[PHONE] 第一步：选择平台 (共发现 {len(platforms)} 个平台)")
        print("-" * 40)
        platform_list = list(platforms.keys())
        for i, platform in enumerate(platform_list, 1):
            enabled_count = len([acc for acc in platforms[platform] if acc.get('enabled', True)])
            total_count = len(platforms[platform])
            print(f"  {i}. {platform} ({enabled_count}/{total_count} 启用)")

        platform_choice = input("请选择平台序号: ").strip()
        try:
            platform_idx = int(platform_choice) - 1
            if not (0 <= platform_idx < len(platform_list)):
                print("[FAIL] 无效序号")
                return None, None
        except ValueError:
            print("[FAIL] 无效输入")
            return None, None

        selected_platform = platform_list[platform_idx]
        return selected_platform, platforms[selected_platform]

    def _select_account(self, platform_accounts: List[Dict], platform: str) -> Optional[Dict]:
        """选择账号"""
        # 仅显示“启用且已配置 login_url”的账号（统一登录网址规范）
        enabled_accounts = [acc for acc in platform_accounts if acc.get('enabled', True) and acc.get('login_url')]

        if not enabled_accounts:
            print(f"[FAIL] {platform} 平台没有启用且已配置 login_url 的账号")
            print("[TIP] 提示：请在 local_accounts.py 中设置 'enabled': True 且补充 'login_url'")
            return None

        print(f"\n[USER] 第二步：选择 {platform} 账号 (共 {len(enabled_accounts)} 个启用账号)")
        print("-" * 40)
        for i, acc in enumerate(enabled_accounts, 1):
            label = acc.get('store_name') or acc.get('username') or acc.get('account_id') or f"账号{i}"
            login_url = acc.get('login_url', 'N/A')
            notes = acc.get('notes', '')
            print(f"  {i}. {label} [OK]")
            print(f"     登录URL: {login_url}")
            if notes:
                print(f"     备注: {notes}")

        account_choice = input("请选择账号序号: ").strip()
        try:
            account_idx = int(account_choice) - 1
            if not (0 <= account_idx < len(enabled_accounts)):
                print("[FAIL] 无效序号")
                return None
        except ValueError:
            print("[FAIL] 无效输入")
            return None

        selected_account = enabled_accounts[account_idx]

        if not selected_account.get('login_url'):
            print("[FAIL] 该账号未配置login_url，请先补充配置")
            return None

        return selected_account

    def _select_recording_type(self):
        """选择录制类型"""
        print(f"\n[TARGET] 第三步：选择录制类型")
        print("-" * 40)

        for i, (key, title, desc) in enumerate(self.recording_types, 1):
            print(f"  {i}. {title}")
            print(f"     {desc}")

        type_choice = input("请选择录制类型序号: ").strip()
        try:
            type_idx = int(type_choice) - 1
            if not (0 <= type_idx < len(self.recording_types)):
                print("[FAIL] 无效序号")
                return None
        except ValueError:
            print("[FAIL] 无效输入")
            return None

        return self.recording_types[type_idx][0]

    def _select_data_type(self, platform: str):
        """选择数据类型（统一为五大数据类型：orders/products/analytics/finance/services）。"""
        print(f"\n[FOLDER] 第四步：选择数据类型")
        print("-" * 40)

        # 统一五大数据类型，跨 TikTok / Shopee / 妙手ERP
        data_types = [
            ("orders", "订单数据采集"),
            ("products", "商品数据采集"),
            ("analytics", "客流/流量数据采集"),
            ("finance", "财务数据采集"),
            ("services", "服务数据采集（客服/聊天）"),
        ]

        for i, (_, label) in enumerate(data_types, 1):
            print(f"  {i}. {label}")

        dt_choice = input("请选择数据类型序号: ").strip()
        try:
            dt_idx = int(dt_choice) - 1
            if not (0 <= dt_idx < len(data_types)):
                print("[FAIL] 无效序号")
                return None
        except ValueError:
            print("[FAIL] 无效输入")
            return None

        return data_types[dt_idx][0]

    def _create_recording_template(self, account: Dict, platform: str,
                                 recording_type: str, data_type_key: Optional[str]) -> Optional[Path]:
        """创建录制模板"""
        try:
            from modules.utils.template_generator import create_platform_recording_template

            # 生成录制模板文件
            if platform in ["妙手ERP", "miaoshou", "miaoshou_erp"]:
                template_path = self._create_miaoshou_template(account)
            else:
                template_path = create_platform_recording_template(account, platform, recording_type, data_type_key)

            if template_path:
                print(f"[OK] 录制模板已生成: {template_path}")
                return template_path
            else:
                print("[FAIL] 录制模板生成失败")
                return None

        except Exception as e:
            logger.error(f"创建录制模板失败: {e}")
            print(f"[FAIL] 创建录制模板失败: {e}")
            return None

    def _create_miaoshou_template(self, account: Dict) -> Path:
        """创建妙手ERP模板"""
        # 创建模板目录
        template_dir = Path("temp/recordings/miaoshou")
        template_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        account_name = account.get('store_name', account.get('username', 'unknown'))
        safe_name = "".join(c for c in account_name if c.isalnum() or c in '._-')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_login_auto_{timestamp}.py"

        template_path = template_dir / filename

        # 生成模板内容
        content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
妙手ERP自动登录模板
账号: {account.get('store_name', 'unknown')}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

from playwright.sync_api import sync_playwright
import time

def main():
    """主函数"""
    account_config = {{
        'username': '{account.get('username', '')}',
        'password': '{account.get('password', '')}',
        'login_url': '{account.get('login_url', '')}',
        'store_name': '{account.get('store_name', 'unknown')}'
    }}

    print("[START] 启动妙手ERP自动登录...")

    with sync_playwright() as p:
        # v4.7.0: 使用环境感知配置
        from modules.apps.collection_center.browser_config_helper import get_browser_launch_args, get_browser_context_args
        
        launch_args = get_browser_launch_args()
        browser = p.chromium.launch(**launch_args)
        
        context_args = get_browser_context_args()
        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            # 访问登录页面
            page.goto(account_config['login_url'])
            page.wait_for_load_state("networkidle")

            # TODO: 在这里添加自动登录逻辑
            print("[TIP] 请在此处添加具体的登录代码")

            # 暂停以供手动操作
            page.pause()

        finally:
            browser.close()

if __name__ == "__main__":
    main()
'''

        template_path.write_text(content, encoding='utf-8')
        return template_path

    def _execute_recording(self, account: Dict, platform: str, recording_type: str,
                          data_type_key: Optional[str], template_path: Path):
        """执行录制"""
        # 添加资源清理前的等待
        import gc

        # 清理之前的资源
        gc.collect()
        time.sleep(1)  # 短暂等待确保资源释放

        playwright_instance = None
        browser = None
        context = None
        page = None

        try:
            from playwright.sync_api import sync_playwright

            login_url = account['login_url']
            account_label = account.get('store_name') or account.get('username') or "未知账号"
            # 兼容别名：data_collection -> collection
            rt_key = "collection" if recording_type == "data_collection" else recording_type
            recording_title = next(title for key, title, _ in self.recording_types if key == rt_key)

            print(f"\n[START] 启动 {recording_title}")
            print("=" * 60)
            print(f"[LIST] 账号: {account_label} ({platform})")
            print(f"[LINK] 入口: {login_url}")
            print(f"[DIR] 模板: {template_path}")
            if data_type_key:
                print(f"[DATA] 数据类型: {data_type_key}")
            print("=" * 60)

            # 提供录制指导
            self._show_recording_guidance(recording_type)

            # 根据录制类型选择不同的处理方式
            if recording_type == "login":
                # [LOCK] 登录流程录制 - 使用Playwright录制工具
                self._execute_playwright_recording(login_url, template_path, "登录流程", account_label, platform)
            elif recording_type == "login_auto":
                # [BOT] 自动登录流程修正 - 执行真正的自动化登录
                print("[BOT] 启动自动登录流程修正...")
                print("[TIP] 这将执行真正的自动化登录，您可以观察整个过程")
                input("按 Enter 继续...")

                # 执行自动登录
                self._execute_auto_login_test(account, platform, login_url)
            elif recording_type == "data_collection" or recording_type == "collection":
                # [DATA] 数据采集录制 - 先自动登录，再录制采集（Inspector + HAR）
                self._execute_data_collection_recording(account, platform, login_url, data_type_key)
            elif recording_type == "full_process" or recording_type == "complete":
                # [RETRY] 完整流程录制 - 登录 + 采集（Inspector + HAR）
                self._execute_full_process_recording(account, platform, login_url, data_type_key)
            else:
                print(f"[WARN] 未知的录制类型: {recording_type}")

            return  # 直接返回，不需要执行其他录制逻辑

        except Exception as e:
            logger.error(f"执行录制失败: {e}")
            print(f"[FAIL] 执行录制失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 简单的资源清理
            import gc
            gc.collect()
            print("[OK] 录制会话结束")

    def _execute_auto_login_test(self, account: Dict, platform: str, login_url: str):
        """
        执行自动登录测试（恢复可用性）：
        - Shopee：沿用旧版 Shopee 自动登录处理器。
        - TikTok：使用同步组件化登录（避免 asyncio 事件循环冲突）。
        """
        try:
            print(f"[START] 开始自动登录测试: {account.get('store_name', '未知账号')}")
            print(f"[WEB] 平台: {platform}")
            print(f"[LINK] 登录URL: {login_url}")

            plat = (platform or '').strip().lower()
            tiktok_aliases = {
                'tiktok','tiktok_shop','tiktokshop','tiktokshopglobalselling',
                'tiktok global shop','tiktokglobalshop','tiktok shop'
            }

            if plat in tiktok_aliases:
                # 使用同步组件化登录，避免 asyncio.run 冲突
                from playwright.sync_api import sync_playwright
                from modules.utils.persistent_browser_manager import PersistentBrowserManager
                from modules.components.base import ExecutionContext
                from modules.platforms.tiktok.components.login import TiktokLogin
                from modules.core.logger import get_logger

                print("[BOT] 启动 TikTok 组件化自动登录（同步）...")
                with sync_playwright() as p:
                    pb = PersistentBrowserManager(p)
                    account_id = (
                        account.get('store_name') or account.get('username') or
                        str(account.get('account_id') or 'account')
                    )
                    ctx = pb.get_or_create_persistent_context('tiktok', str(account_id), account)
                    page = ctx.new_page()

                    if not login_url:
                        print("[FAIL] 账号缺少 login_url，请在 local_accounts.py 补充后再试")
                        return
                    try:
                        page.goto(login_url, wait_until='domcontentloaded', timeout=45000)
                    except Exception:
                        page.goto(login_url, wait_until='load', timeout=60000)

                    exec_ctx = ExecutionContext(platform='tiktok', account=account, logger=get_logger(__name__))
                    comp = TiktokLogin(exec_ctx)
                    try:
                        res = comp.run(page)
                        success = bool(getattr(res, 'success', False))
                    except Exception as _e:
                        success = False
                        print(f"[WARN] TikTok 登录组件运行异常: {_e}")

                    if success:
                        print("\n[OK] 自动登录成功（TikTok）")
                        try:
                            pb.save_context_state(ctx, 'tiktok', str(account_id))
                        except Exception:
                            pass
                        input("按回车键关闭浏览器并返回...")
                    else:
                        print("\n[FAIL] 自动登录失败（TikTok）")
                        input("按回车键返回...")

                    try:
                        pb.close_context('tiktok', str(account_id))
                    except Exception:
                        pass
                return

            if plat == 'shopee':
                from modules.utils.shopee_login_handler import ShopeeLoginHandler
                from playwright.sync_api import sync_playwright

                print("[LOCK] 启动Shopee自动登录流程...")
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=False,
                        args=[
                            '--no-sandbox',
                            '--disable-web-security',
                            '--disable-features=VizDisplayCompositor',
                            '--disable-blink-features=AutomationControlled'
                        ]
                    )
                    login_handler = ShopeeLoginHandler(browser)
                    result = login_handler.login_to_shopee(account)

                    if result:
                        print("[OK] 自动登录成功！")
                        print("[LIST] 登录过程中的关键步骤:\n   1. 页面加载完成\n   2. 输入用户名密码\n   3. 处理验证码（如需要）\n   4. 登录成功验证")
                        input("\n[PAUSE] 登录成功！请观察页面状态，按回车键继续...")
                    else:
                        print("[FAIL] 自动登录失败")
                        print("[TIP] 可能的原因:\n   1. 账号信息不正确\n   2. 验证码处理失败\n   3. 网络连接问题\n   4. 页面结构发生变化")
                        input("\n[PAUSE] 登录失败，请观察页面状态，按回车键继续...")

                    try:
                        browser.close()
                    except Exception:
                        pass
                return


            if plat in {'妙手erp','miaoshou','miaoshou_erp','miaoshou erp','erp'}:
                from playwright.sync_api import sync_playwright
                from modules.utils.persistent_browser_manager import PersistentBrowserManager
                from modules.components.base import ExecutionContext
                from modules.platforms.miaoshou.components.login import MiaoshouLogin
                from modules.core.logger import get_logger

                print("[BOT] 启动 妙手ERP 组件化自动登录（同步）...")
                with sync_playwright() as p:
                    pb = PersistentBrowserManager(p)
                    account_id = (
                        account.get('store_name') or account.get('username') or
                        str(account.get('account_id') or 'account')
                    )
                    ctx = pb.get_or_create_persistent_context('miaoshou', str(account_id), account)
                    page = ctx.new_page()

                    if not login_url:
                        print("[FAIL] 账号缺少 login_url，请在 local_accounts.py 补充后再试")
                        return
                    try:
                        page.goto(login_url, wait_until='domcontentloaded', timeout=45000)
                    except Exception:
                        page.goto(login_url, wait_until='load', timeout=60000)

                    exec_ctx = ExecutionContext(platform='miaoshou', account=account, logger=get_logger(__name__))
                    comp = MiaoshouLogin(exec_ctx)
                    try:
                        res = comp.run(page)
                        success = bool(getattr(res, 'success', False))
                    except Exception as _e:
                        success = False
                        print(f"[WARN] 妙手ERP 登录组件运行异常: {_e}")

                    if success:
                        print("\n[OK] 自动登录成功（妙手ERP）")
                        try:
                            pb.save_context_state(ctx, 'miaoshou', str(account_id))
                        except Exception:
                            pass
                        input("按回车键关闭浏览器并返回...")
                    else:
                        print("\n[FAIL] 自动登录失败（妙手ERP）")
                        input("按回车键返回...")

                    try:
                        pb.close_context('miaoshou', str(account_id))
                    except Exception:
                        pass
                return

            print(f"[WARN] 暂不支持 {platform} 平台的自动登录测试")
            print("[LIST] 支持的平台: Shopee, TikTok, 妙手ERP（已通过组件化登录实现）")

        except Exception as e:
            logger.error(f"自动登录测试失败: {e}")
            print(f"[FAIL] 自动登录测试失败: {e}")
            import traceback
            traceback.print_exc()

    def _create_manual_recording_template(self, login_url: str, template_path, flow_type: str):
        """创建手动录制模板"""
        try:
            template_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
手动录制脚本 - {flow_type}
URL: {login_url}
生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}

使用说明:
1. 运行此脚本会打开浏览器
2. 手动完成您需要录制的操作
3. 在操作完成后按回车继续
4. 将您的操作转换为Playwright代码添加到TODO部分
"""

import asyncio
from playwright.async_api import async_playwright

async def run(playwright):
    # 启动浏览器
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={{"width": 1920, "height": 1080}},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await context.new_page()

    try:
        # 访问目标页面
        print(f"[WEB] 正在访问: {login_url}")
        await page.goto("{login_url}")

        # 等待页面加载
        await page.wait_for_load_state('networkidle')

        # TODO: 在这里添加您的操作代码
        # 常用操作示例:
        # await page.fill('input[name="username"]', "your_username")
        # await page.fill('input[name="password"]', "your_password")
        # await page.click('button[type="submit"]')
        # await page.wait_for_url("**/dashboard**")  # 等待跳转

        # 交互式等待用户完成操作
        print("\\n[LIST] 请在浏览器中完成您的操作...")
        print("[TIP] 完成后请回到这里按回车继续")
        input("按回车键结束录制...")

    except Exception as e:
        print(f"[FAIL] 录制过程中出错: {{e}}")
    finally:
        # 关闭浏览器
        await browser.close()
        print("[OK] 录制会话结束")

async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == "__main__":
    print("[ACTION] 手动录制模式启动")
    print("=" * 50)
    asyncio.run(main())
'''

            # 保存模板文件
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(template_content)

            print(f"[OK] 手动录制模板已创建: {template_path}")
            print("\n[LIST] 模板生成完成！")
            print("[TIP] 接下来请使用Playwright Inspector进行录制操作")

        except Exception as e:
            print(f"[FAIL] 创建手动录制模板失败: {e}")

    def _cleanup_old_recordings(self, platform: str, account_id: str, recording_type: str):
        """清理旧的录制文件，确保每个账号+类型只保留最新一个"""
        try:
            recordings_dir = Path("temp/recordings")
            platform_dir = recordings_dir / platform.lower()
            if not platform_dir.exists():
                return

            # 查找相同账号和录制类型的旧文件
            pattern = f"*{account_id}*{recording_type}*.py"
            old_files = list(platform_dir.glob(pattern))

            if old_files:
                print(f"[CLEAN] 清理旧录制文件: {len(old_files)} 个")
                for old_file in old_files:
                    # 移动到backups目录而不是直接删除
                    backup_dir = Path("temp/backups/recordings")
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    backup_path = backup_dir / old_file.name
                    old_file.rename(backup_path)
                    print(f"   [PKG] {old_file.name} -> backups/")
        except Exception as e:
            print(f"[WARN] 清理旧文件时出错: {e}")

    def _execute_playwright_recording(self, login_url: str, template_path, flow_type: str, account_label: str = "未知账号", platform_name: str = "未知平台"):
        """执行Playwright Inspector录制 - 使用真正的录制工具"""
        try:
            import re
            import sys
            import subprocess
            from pathlib import Path

            # 提取账号ID用于清理旧文件
            account_id = re.search(r'account_(\w+)', str(template_path))
            if account_id:
                account_id = account_id.group(1)
                # 清理旧的录制文件
                recording_type = "login" if "login" in str(template_path) else "collection"
                self._cleanup_old_recordings(platform_name.lower(), account_id, recording_type)

            # 检查Playwright是否可用
            try:
                result = subprocess.run([sys.executable, "-m", "playwright", "--version"],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    print("[FAIL] Playwright未正确安装")
                    print("[TIP] 请运行以下命令安装:")
                    print("   pip install playwright")
                    print("   python -m playwright install")
                    return False
                else:
                    playwright_version = result.stdout.strip()
                    print(f"[OK] Playwright版本: {playwright_version}")
            except Exception as e:
                print(f"[FAIL] Playwright检查失败: {e}")
                return False

            print(f"\n[START] 启动{flow_type}录制工具")
            print("=" * 50)
            print(f"[LINK] 登录URL: {login_url}")
            print(f"[DIR] 输出文件: {template_path}")
            print("=" * 50)

            # 使用原始路径，确保路径正确
            safe_template_path = Path(template_path)
            # 确保父目录存在
            safe_template_path.parent.mkdir(parents=True, exist_ok=True)

            print("\n[TIP] Playwright Inspector 录制工具说明:")
            print("   [ACTION] 即将启动专业的Playwright录制界面")
            print("   [NOTE] 您的所有操作都会被自动转换为Python代码")
            print("   [RETRY] 录制完成后代码会自动保存到文件")
            print("   [STOP] 录制界面关闭后返回系统")

            input("\n按 Enter 键启动 Playwright Inspector 录制工具...")

            print("[WAIT] 正在启动 Playwright Inspector...")

            # 检测Playwright环境问题，提供替代方案
            try:
                # 确保输出目录存在
                safe_template_path.parent.mkdir(parents=True, exist_ok=True)

                # 先测试Playwright是否能正常启动
                print("[SEARCH] 检测Playwright环境...")
                test_cmd = [sys.executable, "-m", "playwright", "--version"]
                test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)

                if test_result.returncode != 0:
                    raise Exception("Playwright未正确安装")

                print(f"[OK] {test_result.stdout.strip()}")

                # 尝试启动codegen
                print("[START] 尝试启动Playwright Inspector...")
                cmd = [
                    sys.executable, "-m", "playwright", "codegen",
                    "--target", "python",
                    "--output", str(safe_template_path),
                    "--browser", "chromium",
                    login_url
                ]

                print(f"[TOOL] 启动命令: {' '.join(cmd)}")
                print("[ACTION] Playwright Inspector 录制工具启动中...")
                print("[LIST] 使用说明:")
                print("   1. 即将打开浏览器窗口和Inspector界面")
                print("   2. 在浏览器中进行您的操作（登录、填表、点击等）")
                print("   3. 代码会实时生成在Inspector界面中")
                print("   4. 录制完成后直接关闭Inspector界面")
                print(f"   5. 代码将自动保存到: {safe_template_path}")
                print()
                print("[WAIT] 启动录制工具...")

                # 使用subprocess.run，这是正确的方法
                result = subprocess.run(cmd, cwd=str(Path.cwd()))

                print("[LIST] 录制界面已关闭")

                # 检查是否成功生成录制文件
                if safe_template_path.exists():
                    print(f"[OK] 录制成功！代码已自动保存到: {safe_template_path}")
                    # 显示生成的代码预览
                    with open(safe_template_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content.strip():
                            print("\n[NOTE] 录制代码预览:")
                            print("-" * 50)
                            print(content[:500] + "..." if len(content) > 500 else content)
                            print("-" * 50)
                            return True
                        else:
                            print("[WARN] 录制文件为空，可能没有录制任何操作")
                else:
                    print("[WARN] 录制文件未生成，可能用户取消了录制")

                return result.returncode == 0

            except Exception as e:
                print(f"[WARN] Playwright自动录制暂时不可用: {e}")
                print("\n[TOOLS] 使用手动录制模式")
                print("=" * 50)
                return self._manual_recording_mode(account_label, login_url, safe_template_path, flow_type)

            # 录制完成后的处理在try块中已完成
            return True

        except Exception as e:
            print(f"[FAIL] 录制功能初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            print("[OK] 录制会话结束")

    def _manual_recording_mode(self, account_label, login_url, template_path, flow_type):
        """手动录制模式 - 当Playwright Inspector无法启动时使用"""

        print("[TARGET] 手动录制模式")
        print("[LIST] 当前系统检测到Playwright Inspector无法正常启动")
        print("[TIP] 我们将指导您手动创建录制脚本")
        print()

        # 生成基础模板代码
        template_code = self._generate_recording_template(account_label, login_url, flow_type)

        print("[NOTE] 基础模板代码已生成:")
        print("=" * 60)
        print(template_code)
        print("=" * 60)
        print()

        print("[TOOLS] 手动录制指导:")
        if "login" in flow_type.lower():
            print("   1. 打开浏览器，访问登录页面:")
            print(f"      {login_url}")
            print("   2. 打开浏览器开发者工具 (F12)")
            print("   3. 在控制台中记录以下操作的元素选择器:")
            print("      - 用户名输入框")
            print("      - 密码输入框")
            print("      - 验证码输入框 (如有)")
            print("      - 登录按钮")
            print("   4. 根据上面的模板，手动编写Playwright代码")
            print("   5. 完成后将代码粘贴到下面")

        print()
        print("[NOTE] 请粘贴您的录制代码 (输入空行结束):")

        # 收集用户输入的代码
        code_lines = []
        while True:
            try:
                line = input()
                if line.strip() == "":
                    break
                code_lines.append(line)
            except (EOFError, KeyboardInterrupt):
                break

        if code_lines:
            user_code = "\n".join(code_lines)

            # 显示代码预览
            print("\n[LIST] 代码预览:")
            print("-" * 40)
            print(user_code)
            print("-" * 40)

            # 确认保存
            confirm = input("\n[OK] 确认保存此代码? (y/n): ").lower()
            if confirm in ['y', 'yes', '确认', '是']:
                try:
                    with open(template_path, 'w', encoding='utf-8') as f:
                        f.write(user_code)
                    print(f"[OK] 代码已保存到: {template_path}")
                    return True
                except Exception as e:
                    print(f"[FAIL] 保存失败: {e}")
                    return False
            else:
                print("[WARN] 录制取消")
                return False
        else:
            print("[WARN] 未输入任何代码，录制取消")
            return False

    def _generate_recording_template(self, account_label, login_url, flow_type):
        """生成录制模板代码"""

        from datetime import datetime

        template = f'''"""
{account_label} - {flow_type}录制脚本
自动生成于: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # 访问登录页面
    page.goto("{login_url}")

    # 等待页面加载
    page.wait_for_load_state("networkidle")

    # TODO: 在这里添加您的录制操作
    # 示例:
    # page.fill("input[name='username']", "your_username")
    # page.fill("input[name='password']", "your_password")
    # page.click("button[type='submit']")

    # 等待登录完成
    # page.wait_for_url("**/dashboard") # 根据实际登录后的URL调整

    print("录制操作完成")

    # 关闭浏览器
    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
'''
        return template

    def _show_recording_guidance(self, recording_type: str):
        """显示录制指导"""
        if recording_type == "login":
            print("[TARGET] 录制指导 - 登录流程录制：")
            print("  1. 页面加载完成后，填写用户名和密码")
            print("  2. 处理验证码（如有）")
            print("  3. 点击登录按钮")
            print("  4. 等待登录成功，到达主页面")
            print("  5. 完成后关闭录制界面")

        elif recording_type == "login_auto":
            print("[TARGET] 录制指导 - 自动登录流程修正：")
            print("  1. 系统将自动填写用户名和密码")
            print("  2. 系统将自动处理验证码（如需要）")
            print("  3. 系统将自动完成登录流程")
            print("  4. 观察自动登录过程，发现问题点")
            print("  5. 完成后关闭录制界面")

        elif recording_type == "collection":
            print("[TARGET] 录制指导 - 数据采集流程：")
            print("  1. 系统将自动完成登录，直接进入登录后的页面")
            print("  2. 导航到相关数据页面")
            print("  3. 设置筛选条件（日期范围等）")
            print("  4. 执行数据查询/导出操作")
            print("  5. 完成后关闭录制界面")

        elif recording_type == "complete":
            print("[TARGET] 录制指导 - 完整流程：")
            print("  1. 完成登录流程")
            print("  2. 导航到数据采集页面")
            print("  3. 执行数据采集操作")
            print("  4. 完成后关闭录制界面")

    def _execute_auto_login_recording(self, page, account: Dict, platform: str, login_url: str):
        """执行自动登录录制"""
        print("[BOT] 开始自动登录流程修正...")
        page.goto(login_url)

        # 等待页面加载
        page.wait_for_load_state("networkidle")

        try:
            if platform == "Shopee":
                self._perform_shopee_auto_login(page, account)
            elif platform in ["妙手ERP", "miaoshou", "miaoshou_erp"]:
                self._perform_miaoshou_auto_login(page, account)
            else:
                print("[TIP] 通用自动登录功能开发中")
                page.pause()

        except Exception as e:
            print(f"[WARN] 自动登录过程中出现错误: {e}")
            print("[TIP] 请手动完成登录流程")

        # 自动登录完成，等待用户确认结果
        print("\n[TARGET] 自动登录流程修正完成！")
        print("[LOOK] 请观察浏览器中的登录结果")
        input("按 Enter 结束测试...")

    def _perform_shopee_auto_login(self, page, account: Dict):
        """执行Shopee自动登录"""
        try:
            print("[START] 开始智能Shopee登录流程...")

            # 执行基础登录操作
            success = self._execute_shopee_basic_login(page, account)
            if not success:
                print("[FAIL] 基础登录操作失败")
                return

            # 启动Shopee专用验证码处理器
            print("[LOCK] 启动Shopee专用验证码处理器...")

            start_time = time.time()

            try:
                from modules.utils.shopee_verification_handler import ShopeeVerificationHandler

                verification_handler = ShopeeVerificationHandler(page, account)
                verification_success = verification_handler.handle_shopee_verification()

                processing_time = time.time() - start_time

                if verification_success:
                    print(f"[DONE] Shopee登录验证码处理完成，登录成功！")
                    print(f"[DATA] 处理统计: 耗时 {processing_time:.1f}秒, 状态: login_success")

                    # 等待页面跳转
                    print("[WAIT] 等待页面跳转到Shopee卖家后台...")
                    time.sleep(5)

                    current_url = page.url
                    if 'seller.shopee' in current_url and 'signin' not in current_url:
                        print("[OK] 已成功进入Shopee卖家后台！")
                    else:
                        print("[WARN] 登录可能成功，但页面跳转异常")
                        print(f"当前URL: {current_url}")
                else:
                    print("[FAIL] 验证码处理失败")

            except ImportError:
                print("[WARN] Shopee验证码处理器模块导入失败，使用备用方案")
                # 导入旧的智能录制向导作为备用
                from modules.utils.enhanced_recording_wizard import EnhancedRecordingWizard
                wizard = EnhancedRecordingWizard()
                login_success = wizard._perform_shopee_login(page,
                                                          account.get('username', ''),
                                                          account.get('password', ''),
                                                          account)
                if login_success:
                    print("[DONE] 备用登录方案成功！")
                else:
                    print("[FAIL] 备用登录方案失败")

        except Exception as e:
            print(f"[FAIL] Shopee自动登录失败: {e}")
            raise

    def _execute_shopee_basic_login(self, page, account: Dict) -> bool:
        """执行Shopee基础登录操作"""
        try:
            username = account.get('username', '')
            password = account.get('password', '')

            if not username or not password:
                print("[FAIL] 用户名或密码未配置")
                return False

            # 智能填写用户名
            username_selectors = [
                'input[type="text"]',
                'input[name="username"]',
                'input[name="user"]',
                'input[name="email"]',
                'input[placeholder*="用户名"]',
                'input[placeholder*="手机号"]',
                'input[placeholder*="邮箱"]'
            ]

            username_filled = False
            for selector in username_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, username)
                        print(f"[OK] 找到用户名输入框: {selector}")
                        username_filled = True
                        break
                except:
                    continue

            if not username_filled:
                print("[FAIL] 未找到用户名输入框")
                return False

            # 智能填写密码
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[name="pwd"]',
                'input[placeholder*="密码"]'
            ]

            password_filled = False
            for selector in password_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, password)
                        print(f"[OK] 找到密码输入框: {selector}")
                        password_filled = True
                        break
                except:
                    continue

            if not password_filled:
                print("[FAIL] 未找到密码输入框")
                return False

            # 智能点击登录按钮
            login_selectors = [
                'button:has-text("登入")',
                'button:has-text("登录")',
                'button:has-text("Login")',
                'button[type="submit"]',
                'input[type="submit"]',
                '.login-btn'
            ]

            login_clicked = False
            for selector in login_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector)
                        print(f"[OK] 找到登录按钮: {selector}")
                        login_clicked = True
                        break
                except:
                    continue

            if not login_clicked:
                print("[FAIL] 未找到登录按钮")
                return False

            print("[OK] 基础登录操作完成，等待验证码处理...")
            return True

        except Exception as e:
            print(f"[FAIL] 基础登录操作失败: {e}")
            return False

    def _perform_miaoshou_auto_login(self, page, account: Dict):
        """执行妙手ERP自动登录"""
        try:
            # 自动填写登录信息
            username = account.get('username', '')
            password = account.get('password', '')

            # 查找并填写用户名
            username_selectors = [
                'input[name="username"]',
                'input[name="user"]',
                'input[name="email"]',
                'input[name="phone"]',
                'input[type="text"]',
                'input[placeholder*="用户名"]',
                'input[placeholder*="手机号"]',
                'input[placeholder*="邮箱"]'
            ]

            for selector in username_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, username)
                        print(f"[OK] 用户名已填写: {username}")
                        break
                except:
                    continue

            # 查找并填写密码
            password_selectors = [
                'input[name="password"]',
                'input[name="pwd"]',
                'input[type="password"]',
                'input[placeholder*="密码"]'
            ]

            for selector in password_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, password)
                        print("[OK] 密码已填写")
                        break
                except:
                    continue

            # 查找并点击登录按钮
            login_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("登录")',
                'button:has-text("登入")',
                'button:has-text("Login")',
                '.login-btn',
                '#login',
                '.submit-btn'
            ]

            for selector in login_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector)
                        print("[OK] 登录按钮已点击")
                        break
                except:
                    continue

            # 等待登录结果
            print("[WAIT] 等待登录完成...")
            time.sleep(5)

            # 检查验证码
            captcha_selectors = [
                'input[name="captcha"]',
                'input[placeholder*="验证码"]',
                'input[placeholder*="captcha"]'
            ]

            need_captcha = False
            for selector in captcha_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        need_captcha = True
                        break
                except:
                    continue

            if need_captcha:
                print("[PHONE] 检测到验证码，启动智能处理...")
                # 这里可以调用智能验证码处理
                try:
                    from modules.collectors.miaoshou_smart_login import MiaoshouSmartLogin
                    smart_login = MiaoshouSmartLogin()
                    # 调用验证码处理逻辑（需要适配）
                    print("[TIP] 验证码处理功能需要异步适配")
                except Exception as e:
                    print(f"[WARN] 智能验证码处理失败: {e}")

                print("请手动处理验证码，然后继续...")
                page.pause()
            else:
                print("[OK] 未检测到验证码需求")

        except Exception as e:
            print(f"[FAIL] 妙手ERP自动登录失败: {e}")
            raise

    def _execute_collection_recording(self, playwright, page, account: Dict, platform: str, login_url: str, data_type_key: Optional[str] = None):
        """
        执行数据采集录制（带登录成功检测 + Inspector + HAR）：
        - 如未登录：执行对应平台的自动登录（TikTok 走组件化登录；Shopee/妙手走各自实现）
        - 登录成功后：在新窗口启动 Inspector 与 HAR 捕获，指导录制登录后的采集操作
        """
        from modules.utils.har_capture_utils import run_har_capture
        plat = (platform or '').strip().lower()
        account_label = account.get('store_name') or account.get('username') or str(account.get('account_id') or 'account')

        print("[DATA] 开始自动登录/校验登录，准备数据采集录制...")
        # 导航到登录入口（更稳健的加载策略）
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[WARN] 首次导航异常，继续尝试: {e}")
            try:
                page.goto(login_url, wait_until="load", timeout=60000)
            except Exception as e2:
                print(f"[WARN] 备用导航也异常（忽略，继续尝试登录检测）: {e2}")
        # 尝试等待网络空闲，但不因超时中断
        try:
            page.wait_for_load_state("networkidle", timeout=45000)
        except Exception:
            pass

        def _is_tiktok_logged_in() -> bool:
            try:
                url = page.url or ""
                if ("tiktokshopglobalselling.com" in url or "tiktokglobalshop.com" in url) and ("/homepage" in url or "seller." in url) and ("account/login" not in url):
                    return True
            except Exception:
                return False
            return False

        # 平台化登录/检测
        try:
            if plat == "shopee":
                self._perform_shopee_auto_login(page, account)
            elif plat in ["妙手erp", "miaoshou", "miaoshou_erp", "miaoshou erp"]:
                self._perform_miaoshou_auto_login(page, account)
            elif plat.startswith("tiktok"):
                # TikTok：如未登录则执行组件化自动登录
                if not _is_tiktok_logged_in():
                    from modules.platforms.tiktok.components.login import TiktokLogin
                    from modules.components.base import ExecutionContext
                    from modules.core.logger import get_logger
                    exec_ctx = ExecutionContext(platform='tiktok', account=account, logger=get_logger(__name__))
                    comp = TiktokLogin(exec_ctx)
                    try:
                        res = comp.run(page)
                        ok = bool(getattr(res, 'success', False))
                    except Exception as e:
                        ok = False
                        print(f"[WARN] TikTok 登录组件异常: {e}")
                    if not ok:
                        print("[FAIL] TikTok 自动登录失败，请手动完成后继续")
                # 最后再判定一次
                if not _is_tiktok_logged_in():
                    print("[WARN] 仍未检测到 TikTok 后台页面，您可以手动导航到后台首页后再开始录制")
            else:
                print("[TIP] 通用平台：请确保已登录并到达后台页面")
        except Exception as e:
            print(f"[WARN] 自动登录/检测过程异常（可忽略，手动继续）: {e}")

        # 启动 HAR 捕获 + Inspector（在新的录制窗口中进行，复用当前 storage state）
        dt_key = (data_type_key or "collection").lower()
        har_path = run_har_capture(
            playwright,
            page,
            platform_key=plat or "platform",
            account_id=str(account_label),
            account_label=str(account_label),
            platform_display=platform or plat,
            data_type_key=dt_key,
        )
        print(f"[FILES] HAR 已保存: {har_path}")

    def _execute_complete_recording(self, page, account: Dict, platform: str, login_url: str):
        """执行完整流程录制"""
        print("[RETRY] 开始完整流程录制（登录 + 数据采集）...")
        page.goto(login_url)
        page.pause()  # 让用户录制完整流程

    def _execute_login_recording(self, page, account: Dict, platform: str, login_url: str):
        """执行登录录制"""
        print("[LOCK] 开始登录流程录制...")
        page.goto(login_url)
        page.pause()  # 让用户手动录制登录流程


    def _execute_data_collection_recording(self, account: Dict, platform: str, login_url: str, data_type_key: Optional[str] = None):
        """
        启动“对应账号”的持久化上下文 -> 自动登录/校验登录成功 -> 打开 Inspector + 启动 HAR 捕获，录制登录后数据采集流程。
        """
        from playwright.sync_api import sync_playwright
        from modules.utils.persistent_browser_manager import PersistentBrowserManager
        from modules.utils.har_capture_utils import run_har_capture
        plat = (platform or '').strip().lower()
        account_label = account.get('store_name') or account.get('username') or str(account.get('account_id') or 'account')
        with sync_playwright() as p:
            pb = PersistentBrowserManager(p)
            account_id = str(account_label)
            ctx = pb.get_or_create_persistent_context(plat, account_id, account)
            page = ctx.new_page()
            # 内部将完成：导航、登录检测/自动登录、停留在后台首页
            self._execute_collection_recording(p, page, account, platform, login_url, data_type_key)
            # 保存并关闭上下文（必须在 Playwright 关闭之前）
            try:
                pb.save_context_state(ctx, plat, account_id)
            except Exception:
                pass
            try:
                pb.close_context(plat, account_id)
            except Exception:
                pass

    def _execute_full_process_recording(self, account: Dict, platform: str, login_url: str, data_type_key: Optional[str] = None):
        """
        启动“对应账号”的持久化上下文 -> 打开 Inspector，录制“登录+采集”的完整流程。
        复用 _execute_complete_recording(page, ...)。
        """
        from playwright.sync_api import sync_playwright
        from modules.utils.persistent_browser_manager import PersistentBrowserManager
        plat = (platform or '').strip().lower()
        account_label = account.get('store_name') or account.get('username') or str(account.get('account_id') or 'account')
        with sync_playwright() as p:
            pb = PersistentBrowserManager(p)
            account_id = str(account_label)
            ctx = pb.get_or_create_persistent_context(plat, account_id, account)
            page = ctx.new_page()
            # 完整流程交由页面内 pause 完成
            self._execute_complete_recording(page, account, platform, login_url)
            # 结束后保存并关闭（在 Playwright 关闭之前）
            try:
                pb.save_context_state(ctx, plat, account_id)
            except Exception:
                pass
            try:
                pb.close_context(plat, account_id)
            except Exception:
                pass

class DataCollectionHandler:
    """数据采集处理器 - 迁移自原系统 run_data_collection"""

    def __init__(self):
        # v4.7.0: 已迁移到数据库账号管理，不再使用AccountManager
        pass

    def run_data_collection(self):
        """运行数据采集 - 完全迁移自原系统"""
        try:
            print("\n[START] 数据采集中心")
            print("=" * 60)

            # 自动同步多地区代理配置
            try:
                from modules.utils.multi_region_router import MultiRegionRouter
                router = MultiRegionRouter()
                router.save_config()  # 保存当前配置
                print("[OK] 多地区代理配置已同步")
            except Exception as e:
                print(f"[WARN] 多地区配置同步失败: {e}")

            # 加载账号
            account_list, source = self._load_accounts_for_run()
            enabled_accounts = [acc for acc in account_list if acc.get('enabled', True)]
            if not enabled_accounts:
                print("[FAIL] 没有启用的账号，无法进行数据采集")
                print("请先添加并启用账号")
                return

            print(f"\n[START] 数据采集配置 (共 {len(enabled_accounts)} 个启用账号，来源: {source})")
            print("=" * 60)

            # 第一步：选择采集账号
            selected_accounts = self._select_collection_accounts(enabled_accounts)
            if not selected_accounts:
                return

            # 第二步：选择日期范围
            date_range = self._select_date_range()
            if not date_range:
                return

            print(f"\n[TARGET] 开始数据采集")
            print("=" * 60)
            print(f"[DATA] 采集账号: {len(selected_accounts)} 个")
            print(f"[DATE] 日期范围: {date_range['description']}")
            print("=" * 60)

            success_count = 0
            failed_count = 0

            for i, account in enumerate(selected_accounts, 1):
                platform = account.get('platform', 'unknown')
                store_name = account.get('store_name', account.get('username', 'unknown'))
                print(f"\n[{i}/{len(selected_accounts)}] 采集: {platform} - {store_name}")
                print(f"   [DATE] 日期: {date_range['start_date']} 至 {date_range['end_date']}")

                try:
                    if platform in ["妙手ERP", "miaoshou", "miaoshou_erp"]:
                        result = self._collect_miaoshou_data_with_date_range(account, date_range)
                    elif platform == "Shopee":
                        result = self._collect_shopee_data_with_date_range(account, date_range)
                    elif platform == "Amazon":
                        result = self._collect_amazon_data_with_date_range(account, date_range)
                    elif platform in ["TikTok", "tiktok", "tiktok_shop"]:
                        result = self._collect_tiktok_data_with_date_range(account, date_range)
                    else:
                        print(f"[WARN]  平台 {platform} 暂未支持")
                        continue

                    if result['success']:
                        print(f"[OK] 采集成功")
                        success_count += 1
                    else:
                        print(f"[FAIL] 采集失败: {result.get('error', '未知错误')}")
                        failed_count += 1

                except Exception as e:
                    print(f"[FAIL] 采集异常: {e}")
                    failed_count += 1

                # 账号间延迟
                if i < len(selected_accounts):
                    time.sleep(2)

            print(f"\n[DATA] 采集完成")
            print("=" * 30)
            print(f"[OK] 成功: {success_count} 个")
            print(f"[FAIL] 失败: {failed_count} 个")
            if success_count + failed_count > 0:
                success_rate = success_count/(success_count+failed_count)*100
                print(f"[CHART] 成功率: {success_rate:.1f}%")
            print("=" * 30)

        except Exception as e:
            logger.error(f"数据采集异常: {e}")
            print(f"[FAIL] 数据采集异常: {e}")

    def _load_accounts_for_run(self):
        """从数据库加载账号（v4.7.0）"""
        try:
            from backend.services.account_loader_service import get_account_loader_service
            from backend.models.database import SessionLocal
            
            db = SessionLocal()
            try:
                account_loader = get_account_loader_service()
                accounts = account_loader.load_all_accounts(db)
                
                if not accounts:
                    logger.warning("数据库中没有启用的账号")
                    return [], "数据库（无账号）"
                
                logger.info(f"从数据库加载了 {len(accounts)} 个账号")
                return accounts, "数据库"
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"从数据库加载账号失败: {e}")
            return [], "错误"

    def _select_collection_accounts(self, enabled_accounts):
        """选择要采集的账号"""
        print("\n[PHONE] 第一步：选择采集账号")
        print("-" * 40)
        print("  1. [LIST] 全部账号采集")
        print("  2. [TARGET] 单个账号采集")
        print("  3. [TAG] 按平台采集")
        print("  4. [FAIL] 返回上级菜单")

        choice = input("\n请选择采集方式 (1-4): ").strip()

        if choice == "1":
            # 全部账号
            print(f"[OK] 已选择全部 {len(enabled_accounts)} 个账号")
            return enabled_accounts

        elif choice == "2":
            # 单个账号选择
            print(f"\n[USER] 选择单个账号 (共 {len(enabled_accounts)} 个启用账号)")
            print("-" * 40)
            for i, acc in enumerate(enabled_accounts, 1):
                platform = acc.get('platform', 'unknown')
                store_name = acc.get('store_name', acc.get('username', 'unknown'))
                print(f"  {i}. {platform} - {store_name}")

            account_choice = input("\n请选择账号序号: ").strip()
            try:
                account_idx = int(account_choice) - 1
                if 0 <= account_idx < len(enabled_accounts):
                    selected_account = enabled_accounts[account_idx]
                    print(f"[OK] 已选择账号: {selected_account.get('store_name', 'unknown')}")
                    return [selected_account]
                else:
                    print("[FAIL] 无效序号")
                    return None
            except ValueError:
                print("[FAIL] 无效输入")
                return None

        elif choice == "3":
            # 按平台选择
            platforms = {}
            for acc in enabled_accounts:
                platform = acc.get('platform', 'unknown')
                if platform not in platforms:
                    platforms[platform] = []
                platforms[platform].append(acc)

            print(f"\n[TAG] 选择平台 (共 {len(platforms)} 个平台)")
            print("-" * 40)
            platform_list = list(platforms.keys())
            for i, platform in enumerate(platform_list, 1):
                count = len(platforms[platform])
                print(f"  {i}. {platform} ({count} 个账号)")

            platform_choice = input("\n请选择平台序号: ").strip()
            try:
                platform_idx = int(platform_choice) - 1
                if 0 <= platform_idx < len(platform_list):
                    selected_platform = platform_list[platform_idx]
                    selected_accounts = platforms[selected_platform]
                    print(f"[OK] 已选择平台: {selected_platform} ({len(selected_accounts)} 个账号)")
                    return selected_accounts
                else:
                    print("[FAIL] 无效序号")
                    return None
            except ValueError:
                print("[FAIL] 无效输入")
                return None

        elif choice == "4":
            return None
        else:
            print("[FAIL] 无效选择")
            return None

    def _select_date_range(self):
        """选择日期范围"""
        print("\n[DATE] 第二步：选择日期范围")
        print("-" * 40)
        print("  1. [DATE] 今天")
        print("  2. [DATE] 昨天")
        print("  3. [DATE] 最近3天")
        print("  4. [DATE] 最近7天")
        print("  5. [DATE] 最近30天")
        print("  6. [DATE] 本月")
        print("  7. [DATE] 上月")
        print("  8. [DATE] 自定义日期范围")

        choice = input("\n请选择日期范围 (1-8): ").strip()

        today = datetime.now().date()

        if choice == "1":
            return {
                'start_date': today,
                'end_date': today,
                'description': '今天'
            }
        elif choice == "2":
            yesterday = today - timedelta(days=1)
            return {
                'start_date': yesterday,
                'end_date': yesterday,
                'description': '昨天'
            }
        elif choice == "3":
            start_date = today - timedelta(days=2)
            return {
                'start_date': start_date,
                'end_date': today,
                'description': '最近3天'
            }
        elif choice == "4":
            start_date = today - timedelta(days=6)
            return {
                'start_date': start_date,
                'end_date': today,
                'description': '最近7天'
            }
        elif choice == "5":
            start_date = today - timedelta(days=29)
            return {
                'start_date': start_date,
                'end_date': today,
                'description': '最近30天'
            }
        elif choice == "6":
            start_date = today.replace(day=1)
            return {
                'start_date': start_date,
                'end_date': today,
                'description': '本月'
            }
        elif choice == "7":
            # 上月
            if today.month == 1:
                last_month = today.replace(year=today.year-1, month=12, day=1)
            else:
                last_month = today.replace(month=today.month-1, day=1)

            # 上月最后一天
            if today.month == 1:
                last_month_end = today.replace(year=today.year-1, month=12, day=31)
            else:
                import calendar
                last_day = calendar.monthrange(today.year, today.month-1)[1]
                last_month_end = today.replace(month=today.month-1, day=last_day)

            return {
                'start_date': last_month,
                'end_date': last_month_end,
                'description': '上月'
            }
        elif choice == "8":
            # 自定义日期范围
            try:
                start_str = input("请输入开始日期 (格式: YYYY-MM-DD): ").strip()
                end_str = input("请输入结束日期 (格式: YYYY-MM-DD): ").strip()

                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

                if start_date > end_date:
                    print("[FAIL] 开始日期不能晚于结束日期")
                    return None

                return {
                    'start_date': start_date,
                    'end_date': end_date,
                    'description': f'自定义 ({start_str} 至 {end_str})'
                }
            except ValueError:
                print("[FAIL] 日期格式错误")
                return None
        else:
            print("[FAIL] 无效选择")
            return None

    def _collect_miaoshou_data_with_date_range(self, account: Dict, date_range: Dict) -> Dict:
        """采集妙手ERP数据 - 使用新的三模块架构"""
        try:
            print(f"[START] 开始妙手ERP数据采集: {account.get('store_name', 'unknown')}")

            # 强制要求login_url，符合规范
            if not account.get('login_url'):
                return {
                    "success": False,
                    "error": "账号未配置login_url，按照规范禁止硬编码或猜测URL",
                    "platform": "妙手ERP",
                    "account_id": account.get("account_id", "")
                }

            # 使用新的三模块架构
            import asyncio
            from playwright.sync_api import sync_playwright
            from modules.utils.login_orchestrator import LoginOrchestrator
            from modules.utils.step_runner import StepRunner
            from modules.utils.data_processing_pipeline import DataProcessingPipeline

            collection_result = {
                "success": False,
                "platform": "妙手ERP",
                "account_id": account.get("account_id", ""),
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "downloaded_files": [],
                "error": None,
                "data_type": "sales",
                "date_range": {
                    "start_date": date_range['start_date'].strftime('%Y-%m-%d'),
                    "end_date": date_range['end_date'].strftime('%Y-%m-%d')
                }
            }

            # 执行异步登录流程
            async def run_collection():
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=100)

                    try:
                        # 模块1: 智能登录页面模块
                        login_orchestrator = LoginOrchestrator(browser)
                        login_success, login_error, page = await login_orchestrator.orchestrate_login(account)

                        if not login_success:
                            collection_result["error"] = f"登录失败: {login_error}"
                            return collection_result

                        print("[OK] 智能登录完成")

                        # 模块2: 智能采集数据模块
                        step_runner = StepRunner(browser)
                        step_result = step_runner.execute_recorded_steps(
                            platform="miaoshou",
                            account=account,
                            page=page,
                            date_range=collection_result["date_range"],
                            step_type="collection"
                        )

                        if step_result["success"]:
                            collection_result["downloaded_files"] = step_result["downloaded_files"]
                            collection_result["success"] = True
                            print("[OK] 智能采集完成")
                        else:
                            collection_result["error"] = f"采集失败: {step_result.get('error', '未知错误')}"
                            return collection_result

                    finally:
                        # 清理资源
                        login_orchestrator.close()
                        browser.close()

                return collection_result

            # 运行异步采集
            collection_result = asyncio.run(run_collection())

            # 模块3: 智能数据处理模块
            if collection_result["success"] and collection_result["downloaded_files"]:
                data_pipeline = DataProcessingPipeline()
                processing_result = data_pipeline.process_collection_result(collection_result, account)

                # 合并处理结果
                collection_result["processing_result"] = processing_result
                print("[OK] 智能数据处理完成")
                
                # Phase 0: 自动注册下载的文件到 catalog_files 表
                if collection_result["downloaded_files"]:
                    register_result = _auto_register_downloaded_files(collection_result["downloaded_files"])
                    collection_result["auto_register_result"] = register_result

            collection_result["end_time"] = datetime.now().isoformat()
            return collection_result

        except Exception as e:
            logger.error(f"妙手ERP数据采集失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "platform": "妙手ERP",
                "account_id": account.get("account_id", ""),
                "end_time": datetime.now().isoformat()
            }

    def _collect_shopee_data_with_date_range(self, account: Dict, date_range: Dict) -> Dict:
        """采集Shopee数据 - 使用新的三模块架构"""
        try:
            print(f"[START] 开始Shopee数据采集: {account.get('store_name', 'unknown')}")

            # 强制要求login_url，符合规范
            if not account.get('login_url'):
                return {
                    "success": False,
                    "error": "账号未配置login_url，按照规范禁止硬编码或猜测URL",
                    "platform": "Shopee",
                    "account_id": account.get("account_id", "")
                }

            # 使用新的三模块架构
            import asyncio
            from playwright.sync_api import sync_playwright
            from modules.utils.login_orchestrator import LoginOrchestrator
            from modules.utils.step_runner import StepRunner
            from modules.utils.data_processing_pipeline import DataProcessingPipeline

            collection_result = {
                "success": False,
                "platform": "Shopee",
                "account_id": account.get("account_id", ""),
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "downloaded_files": [],
                "error": None,
                "data_type": "sales",
                "date_range": {
                    "start_date": date_range['start_date'].strftime('%Y-%m-%d'),
                    "end_date": date_range['end_date'].strftime('%Y-%m-%d')
                }
            }

            # 执行异步登录流程
            async def run_collection():
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=100)

                    try:
                        # 模块1: 智能登录页面模块
                        login_orchestrator = LoginOrchestrator(browser)
                        login_success, login_error, page = await login_orchestrator.orchestrate_login(account)

                        if not login_success:
                            collection_result["error"] = f"登录失败: {login_error}"
                            return collection_result

                        print("[OK] 智能登录完成")

                        # 模块2: 智能采集数据模块
                        step_runner = StepRunner(browser)
                        step_result = step_runner.execute_recorded_steps(
                            platform="shopee",
                            account=account,
                            page=page,
                            date_range=collection_result["date_range"],
                            step_type="collection"
                        )

                        if step_result["success"]:
                            collection_result["downloaded_files"] = step_result["downloaded_files"]
                            collection_result["success"] = True
                            print("[OK] 智能采集完成")
                        else:
                            collection_result["error"] = f"采集失败: {step_result.get('error', '未知错误')}"
                            return collection_result

                    finally:
                        # 清理资源
                        login_orchestrator.close()
                        browser.close()

                return collection_result

            # 运行异步采集
            collection_result = asyncio.run(run_collection())

            # 模块3: 智能数据处理模块
            if collection_result["success"] and collection_result["downloaded_files"]:
                data_pipeline = DataProcessingPipeline()
                processing_result = data_pipeline.process_collection_result(collection_result, account)

                # 合并处理结果
                collection_result["processing_result"] = processing_result
                print("[OK] 智能数据处理完成")
                
                # Phase 0: 自动注册下载的文件到 catalog_files 表
                if collection_result["downloaded_files"]:
                    register_result = _auto_register_downloaded_files(collection_result["downloaded_files"])
                    collection_result["auto_register_result"] = register_result

            collection_result["end_time"] = datetime.now().isoformat()
            return collection_result

        except Exception as e:
            logger.error(f"Shopee数据采集失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "platform": "Shopee",
                "account_id": account.get("account_id", ""),
                "end_time": datetime.now().isoformat()
            }

    def _collect_amazon_data_with_date_range(self, account: Dict, date_range: Dict) -> Dict:
        """采集Amazon数据 - 预留接口"""
        try:
            print("[RETRY] 启动Amazon数据采集...")

            # 强制要求login_url，符合规范
            if not account.get('login_url'):
                return {
                    "success": False,
                    "error": "账号未配置login_url，按照规范禁止硬编码或猜测URL",
                    "platform": "Amazon",
                    "account_id": account.get("account_id", "")
                }

            # Amazon采集功能开发中，暂时返回占位结果
            print("[TIP] Amazon采集功能开发中")

            return {
                'success': True,
                'message': 'Amazon采集功能开发中',
                'platform': 'Amazon',
                'account_id': account.get('account_id', ''),
                'start_time': datetime.now().isoformat(),
                'end_time': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Amazon数据采集失败: {e}")
            return {'success': False, 'error': str(e)}

    def _collect_tiktok_data_with_date_range(self, account: Dict, date_range: Dict) -> Dict:
        """采集TikTok数据 - 使用新的三模块架构"""
        try:
            print(f"[START] 开始TikTok数据采集: {account.get('store_name', 'unknown')}")

            # 强制要求login_url，符合规范
            if not account.get('login_url'):
                return {
                    "success": False,
                    "error": "账号未配置login_url，按照规范禁止硬编码或猜测URL",
                    "platform": "TikTok",
                    "account_id": account.get("account_id", "")
                }

            # 使用新的三模块架构
            import asyncio
            from playwright.sync_api import sync_playwright
            from modules.utils.login_orchestrator import LoginOrchestrator
            from modules.utils.step_runner import StepRunner
            from modules.utils.data_processing_pipeline import DataProcessingPipeline

            collection_result = {
                "success": False,
                "platform": "TikTok",
                "account_id": account.get("account_id", ""),
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "downloaded_files": [],
                "error": None,
                "data_type": "sales",
                "date_range": {
                    "start_date": date_range['start_date'].strftime('%Y-%m-%d'),
                    "end_date": date_range['end_date'].strftime('%Y-%m-%d')
                }
            }

            # 执行异步登录流程
            async def run_collection():
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=100)

                    try:
                        # 模块1: 智能登录页面模块
                        login_orchestrator = LoginOrchestrator(browser)
                        login_success, login_error, page = await login_orchestrator.orchestrate_login(account)

                        if not login_success:
                            collection_result["error"] = f"登录失败: {login_error}"
                            return collection_result

                        print("[OK] 智能登录完成")

                        # 模块2: 智能采集数据模块
                        step_runner = StepRunner(browser)
                        step_result = step_runner.execute_recorded_steps(
                            platform="tiktok",
                            account=account,
                            page=page,
                            date_range=collection_result["date_range"],
                            step_type="collection"
                        )

                        if step_result["success"]:
                            collection_result["downloaded_files"] = step_result["downloaded_files"]
                            collection_result["success"] = True
                            print("[OK] 智能采集完成")
                        else:
                            collection_result["error"] = f"采集失败: {step_result.get('error', '未知错误')}"
                            return collection_result

                    finally:
                        # 清理资源
                        login_orchestrator.close()
                        browser.close()

                return collection_result

            # 运行异步采集
            collection_result = asyncio.run(run_collection())

            # 模块3: 智能数据处理模块
            if collection_result["success"] and collection_result["downloaded_files"]:
                data_pipeline = DataProcessingPipeline()
                processing_result = data_pipeline.process_collection_result(collection_result, account)

                # 合并处理结果
                collection_result["processing_result"] = processing_result
                print("[OK] 智能数据处理完成")
                
                # Phase 0: 自动注册下载的文件到 catalog_files 表
                if collection_result["downloaded_files"]:
                    register_result = _auto_register_downloaded_files(collection_result["downloaded_files"])
                    collection_result["auto_register_result"] = register_result

            collection_result["end_time"] = datetime.now().isoformat()
            return collection_result

        except Exception as e:
            logger.error(f"TikTok数据采集失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "platform": "TikTok",
                "account_id": account.get("account_id", ""),
                "end_time": datetime.now().isoformat()
            }


class ShopeeCollectionHandler:
    """Shopee专属采集处理器"""

    def __init__(self):
        # v4.7.0: 已迁移到数据库账号管理，不再使用AccountManager
        pass

    def run_shopee_collection_only(self):
        """运行Shopee多账号专属采集"""
        try:
            print("\n[SHOP] Shopee多账号专属采集")
            print("=" * 60)
            print("[LIST] 功能: 专门针对Shopee平台的优化采集")
            print("[NEW] 特性: 多账号并行、智能错误恢复、实时监控")
            print("=" * 60)

            # 加载Shopee账号
            account_list, source = self._load_accounts_for_run()
            shopee_accounts = [acc for acc in account_list
                             if acc.get('platform') == 'Shopee' and acc.get('enabled', True)]

            if not shopee_accounts:
                print("[FAIL] 没有启用的Shopee账号")
                print("[TIP] 请先在账号管理中添加Shopee账号")
                return

            print(f"[DATA] 发现 {len(shopee_accounts)} 个启用的Shopee账号")

            # 选择采集账号
            selected_accounts = self._select_shopee_accounts(shopee_accounts)
            if not selected_accounts:
                return

            # 选择采集模式
            collection_mode = self._select_collection_mode()
            if not collection_mode:
                return

            # 执行采集
            self._execute_shopee_collection(selected_accounts, collection_mode)

        except Exception as e:
            logger.error(f"Shopee专属采集失败: {e}")
            print(f"[FAIL] Shopee专属采集失败: {e}")

    def _load_accounts_for_run(self):
        """从数据库加载账号（v4.7.0）"""
        try:
            from backend.services.account_loader_service import get_account_loader_service
            from backend.models.database import SessionLocal
            
            db = SessionLocal()
            try:
                account_loader = get_account_loader_service()
                accounts = account_loader.load_all_accounts(db)
                
                if not accounts:
                    logger.warning("数据库中没有启用的账号")
                    return [], "数据库（无账号）"
                
                logger.info(f"从数据库加载了 {len(accounts)} 个账号")
                return accounts, "数据库"
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"从数据库加载账号失败: {e}")
            return [], "错误"

    def _select_shopee_accounts(self, shopee_accounts):
        """选择Shopee账号"""
        print("\n[PHONE] 选择采集账号")
        print("-" * 40)
        print("  1. [LIST] 全部Shopee账号")
        print("  2. [TARGET] 选择特定账号")
        print("  3. [FAIL] 返回")

        choice = input("\n请选择 (1-3): ").strip()

        if choice == "1":
            print(f"[OK] 已选择全部 {len(shopee_accounts)} 个Shopee账号")
            return shopee_accounts
        elif choice == "2":
            print(f"\n[TARGET] 选择特定账号 (共 {len(shopee_accounts)} 个)")
            print("-" * 40)
            for i, acc in enumerate(shopee_accounts, 1):
                store_name = acc.get('store_name', acc.get('username', 'unknown'))
                print(f"  {i}. {store_name}")

            selected_indices = input("\n请输入账号序号 (多个用逗号分隔): ").strip()
            try:
                indices = [int(x.strip()) - 1 for x in selected_indices.split(',')]
                selected_accounts = []
                for idx in indices:
                    if 0 <= idx < len(shopee_accounts):
                        selected_accounts.append(shopee_accounts[idx])

                if selected_accounts:
                    print(f"[OK] 已选择 {len(selected_accounts)} 个账号")
                    return selected_accounts
                else:
                    print("[FAIL] 无效选择")
                    return None
            except ValueError:
                print("[FAIL] 输入格式错误")
                return None
        elif choice == "3":
            return None
        else:
            print("[FAIL] 无效选择")
            return None

    def _select_collection_mode(self):
        """选择采集模式"""
        print("\n[GEAR] 选择采集模式")
        print("-" * 40)
        print("  1. [START] 快速采集 (基础数据)")
        print("  2. [DATA] 完整采集 (所有数据)")
        print("  3. [TARGET] 自定义采集 (选择数据类型)")
        print("  4. [BOT] 自动登录模式 (新功能)")
        print("  5. [FAIL] 返回")

        choice = input("\n请选择采集模式 (1-5): ").strip()

        if choice == "1":
            return {
                'type': 'quick',
                'name': '快速采集',
                'data_types': ['orders', 'basic_analytics']
            }
        elif choice == "2":
            return {
                'type': 'complete',
                'name': '完整采集',
                'data_types': ['orders', 'products', 'analytics', 'financial']
            }
        elif choice == "3":
            return self._select_custom_data_types()
        elif choice == "4":
            return {
                'type': 'auto_login',
                'name': '自动登录模式',
                'description': '专家级自动登录系统，自动打开登录页面并完成登录'
            }
        elif choice == "5":
            return None
        else:
            print("[FAIL] 无效选择")
            return None

    def _select_custom_data_types(self):
        """选择自定义数据类型"""
        print("\n[TARGET] 选择数据类型 (多选)")
        print("-" * 40)
        data_types = [
            ('orders', '订单数据'),
            ('products', '商品数据'),
            ('analytics', '分析数据'),
            ('financial', '财务数据'),
            ('performance', '绩效数据'),
            ('inventory', '库存数据')
        ]

        for i, (key, name) in enumerate(data_types, 1):
            print(f"  {i}. {name}")

        selected_indices = input("\n请输入数据类型序号 (多个用逗号分隔): ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in selected_indices.split(',')]
            selected_types = []
            selected_names = []

            for idx in indices:
                if 0 <= idx < len(data_types):
                    selected_types.append(data_types[idx][0])
                    selected_names.append(data_types[idx][1])

            if selected_types:
                print(f"[OK] 已选择: {', '.join(selected_names)}")
                return {
                    'type': 'custom',
                    'name': '自定义采集',
                    'data_types': selected_types
                }
            else:
                print("[FAIL] 无效选择")
                return None
        except ValueError:
            print("[FAIL] 输入格式错误")
            return None

    def _execute_shopee_collection(self, selected_accounts, collection_mode):
        """执行Shopee采集"""
        print(f"\n[START] 开始 {collection_mode['name']}")
        print("=" * 60)
        print(f"[DATA] 采集账号: {len(selected_accounts)} 个")

        # 处理自动登录模式
        if collection_mode['type'] == 'auto_login':
            print(f"[BOT] 模式: 专家级自动登录系统")
            print(f"[NEW] 功能: 自动打开登录页面 -> 自动登录 -> 进入卖家端后台")
        else:
            print(f"[LIST] 数据类型: {', '.join(collection_mode['data_types'])}")

        print("=" * 60)

        success_count = 0
        failed_count = 0

        for i, account in enumerate(selected_accounts, 1):
            store_name = account.get('store_name', account.get('username', 'unknown'))
            print(f"\n[{i}/{len(selected_accounts)}] 处理: {store_name}")

            try:
                # 处理自动登录模式
                if collection_mode['type'] == 'auto_login':
                    result = self._execute_auto_login(account)
                else:
                    # 调用Shopee工作流管理器
                    from modules.collectors.shopee_workflow_manager import ShopeeWorkflowManager

                    workflow = ShopeeWorkflowManager(account)
                    result = workflow.execute_collection(collection_mode)

                if result.get('success', False):
                    print(f"[OK] 处理成功")
                    success_count += 1
                else:
                    print(f"[FAIL] 处理失败: {result.get('error', '未知错误')}")
                    failed_count += 1

            except Exception as e:
                print(f"[FAIL] 采集异常: {e}")
                failed_count += 1

            # 账号间延迟
            if i < len(selected_accounts):
                print("[WAIT] 等待2秒后继续下一个账号...")
                time.sleep(2)

        print(f"\n[DATA] Shopee采集完成")
        print("=" * 30)
        print(f"[OK] 成功: {success_count} 个")
        print(f"[FAIL] 失败: {failed_count} 个")
        if success_count + failed_count > 0:
            success_rate = success_count/(success_count+failed_count)*100
            print(f"[CHART] 成功率: {success_rate:.1f}%")
        print("=" * 30)

    def _execute_auto_login(self, account):
        """执行自动登录"""
        try:
            print("[BOT] 启动自动登录...")

            # 转换账号格式为自动登录模块要求的格式
            auto_login_account = {
                'account_id': account.get('account_id', account.get('store_name', 'Unknown')),
                'username': account.get('username', ''),
                'password': account.get('password', ''),
                'login_url': account.get('login_url', ''),
                'email': account.get('E-mail', account.get('email', '')),
                'email_password': account.get('Email password', account.get('email_password', '')),
            }

            # 验证必要字段
            if not auto_login_account['username'] or not auto_login_account['password']:
                return {
                    'success': False,
                    'error': '缺少用户名或密码'
                }

            if not auto_login_account['login_url']:
                return {
                    'success': False,
                    'error': '缺少登录URL'
                }

            # 导入并执行自动登录
            try:
                from modules.automation.shopee_seller_auto_login import auto_login_single_shopee_account

                print(f"   账号: {auto_login_account['account_id']}")
                print(f"   URL: {auto_login_account['login_url']}")

                start_time = time.time()
                result = auto_login_single_shopee_account(auto_login_account, headless=False)
                end_time = time.time()

                if result.success:
                    print(f"   登录成功! 耗时: {end_time - start_time:.1f}s")
                    print(f"   最终URL: {result.final_url}")
                    return {'success': True, 'login_time': end_time - start_time}
                else:
                    print(f"   登录失败: {result.error_message}")
                    return {'success': False, 'error': result.error_message}

            except ImportError as e:
                return {
                    'success': False,
                    'error': f'自动登录模块导入失败: {e}'
                }

        except Exception as e:
            logger.error(f"自动登录执行失败: {e}")
            return {
                'success': False,
                'error': f'自动登录执行失败: {e}'
            }


class CollectionStatsHandler:
    """采集统计处理器"""

    def __init__(self):
        self.stats_file = Path("data/collection_stats.json")

    def show_collection_stats(self):
        """显示采集统计"""
        try:
            print("\n[DATA] 数据采集统计")
            print("=" * 60)

            if not self.stats_file.exists():
                print("[LIST] 暂无采集统计数据")
                print("[TIP] 请先运行数据采集任务")
                return

            import json
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)

            # 显示总体统计
            total_runs = stats.get('total_runs', 0)
            successful_runs = stats.get('successful_runs', 0)
            failed_runs = stats.get('failed_runs', 0)

            print(f"[123] 总运行次数: {total_runs}")
            print(f"[OK] 成功次数: {successful_runs}")
            print(f"[FAIL] 失败次数: {failed_runs}")

            if total_runs > 0:
                success_rate = (successful_runs / total_runs) * 100
                print(f"[CHART] 总体成功率: {success_rate:.1f}%")

            # 显示平台统计
            platform_stats = stats.get('platform_stats', {})
            if platform_stats:
                print(f"\n[PHONE] 平台统计:")
                print("-" * 30)
                for platform, data in platform_stats.items():
                    runs = data.get('runs', 0)
                    success = data.get('success', 0)
                    rate = (success / runs * 100) if runs > 0 else 0
                    print(f"  {platform}: {success}/{runs} ({rate:.1f}%)")

            # 显示最近记录
            recent_logs = stats.get('recent_logs', [])
            if recent_logs:
                print(f"\n[LIST] 最近运行记录:")
                print("-" * 30)
                for log in recent_logs[-5:]:  # 显示最近5条
                    timestamp = log.get('timestamp', 'unknown')
                    platform = log.get('platform', 'unknown')
                    status = log.get('status', 'unknown')
                    status_icon = "[OK]" if status == "success" else "[FAIL]"
                    print(f"  {timestamp} | {platform} | {status_icon} {status}")

            print("=" * 60)

        except Exception as e:
            logger.error(f"显示采集统计失败: {e}")
            print(f"[FAIL] 显示采集统计失败: {e}")

    def clear_collection_stats(self):
        """清空采集统计"""
        try:
            if self.stats_file.exists():
                self.stats_file.unlink()
                print("[OK] 采集统计已清空")
            else:
                print("[LIST] 没有采集统计数据需要清空")
        except Exception as e:
            logger.error(f"清空采集统计失败: {e}")
            print(f"[FAIL] 清空采集统计失败: {e}")


class CollectionConfigHandler:
    """采集配置处理器"""

    def __init__(self):
        self.config_file = Path("config/collection_config.yaml")

    def show_collection_config(self):
        """显示采集器配置"""
        print("\n[GEAR] 采集器配置")
        print("=" * 40)

        print("\n[TOOL] Shopee采集器")
        print("   [LIST] 支持平台: Shopee")
        print("   [NEW] 功能特性: 多账号并行, 智能错误恢复, 实时监控")
        print("   [DATA] 数据类型: 订单, 商品, 分析, 财务")
        print("   [RETRY] 采集频率: 可配置")
        print("   [TIME] 超时设置: 30秒/页面")

        print("\n[TOOL] Amazon采集器")
        print("   [LIST] 支持平台: Amazon")
        print("   [NEW] 功能特性: 多店铺支持, 数据标准化, 自动重试")
        print("   [DATA] 数据类型: 订单, 库存, 绩效, 财务")
        print("   [RETRY] 采集频率: 可配置")
        print("   [TIME] 超时设置: 45秒/页面")

        print("\n[TOOL] 妙手ERP采集器")
        print("   [LIST] 支持平台: 妙手ERP")
        print("   [NEW] 功能特性: 智能登录, 数据同步, 状态监控")
        print("   [DATA] 数据类型: 销售, 运营, 财务")
        print("   [RETRY] 采集频率: 可配置")
        print("   [TIME] 超时设置: 60秒/页面")

        print("\n[TIP] 配置说明:")
        print("   [DIR] 配置文件: config/collection_config.yaml")
        print("   [TOOL] 支持自定义: 超时时间, 重试次数, 并发数")
        print("   [DATA] 支持监控: 采集进度, 错误日志, 性能指标")

    def edit_collection_config(self):
        """编辑采集配置"""
        print("\n[GEAR] 编辑采集配置")
        print("-" * 40)
        print("[TIP] 配置编辑功能开发中")
        print("[DIR] 请直接编辑: config/collection_config.yaml")
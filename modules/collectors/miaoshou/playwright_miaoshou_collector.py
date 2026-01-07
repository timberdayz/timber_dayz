#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
妙手ERP Playwright采集器
使用Playwright实现妙手ERP数据采集
"""

import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.collectors.base.playwright_collector import PlaywrightCollector

# 导入VPN加速器
try:
    from modules.utils.vpn_china_accelerator import vpn_accelerator
    VPN_ACCELERATOR_AVAILABLE = True
except ImportError:
    VPN_ACCELERATOR_AVAILABLE = False
    print("⚠️  VPN加速器不可用，将使用默认网络配置")

logger = logging.getLogger(__name__)

class MiaoshouPlaywrightCollector(PlaywrightCollector):
    """妙手ERP Playwright采集器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化妙手ERP采集器
        
        Args:
            config: 配置信息
        """
        super().__init__(config)
        
        # 按项目规范：禁止硬编码URL，所有跳转严格以账号配置的login_url为唯一入口
        self.login_url = None
        self.dashboard_url = None
        self.order_url = None
        
        # VPN加速器集成
        self.vpn_accelerator = vpn_accelerator if VPN_ACCELERATOR_AVAILABLE else None
        
        # 多地区路由器集成（支持VPN绕过）
        try:
            from modules.utils.multi_region_router import MultiRegionRouter
            self.multi_region_router = MultiRegionRouter()
            self.MULTI_REGION_AVAILABLE = True
        except ImportError:
            self.multi_region_router = None
            self.MULTI_REGION_AVAILABLE = False
            print("⚠️  多地区路由器不可用，将使用默认网络配置")
        if self.vpn_accelerator and self.vpn_accelerator.is_vpn_environment:
            print("🌐 检测到VPN环境，启用中国网站访问优化")
        
                    # 元素选择器（需要根据实际页面结构调整）
        self.selectors = {
            # 登录页面
            "username_input": "input[name='username'], input[type='text']",
            "password_input": "input[name='password'], input[type='password']",
            "login_button": "button[type='submit'], .login-btn, #login-btn",
            
            # 导航菜单
            "order_menu": "a[href*='order'], .order-menu, #order-menu",
            
            # 日期选择 - 针对妙手ERP优化
            "date_picker": ".date-picker, input[type='date'], .ant-calendar-picker",
            "start_date": "input[placeholder*='开始'], input[placeholder*='start'], input[value*='00:00:00']",
            "end_date": "input[placeholder*='结束'], input[placeholder*='end'], input[value*='23:59:59']",
            
            # 下载按钮 - 增加更多可能的选择器
            "download_button": "button:has-text('下载'), button:has-text('导出'), .download-btn, .export-btn, #download-btn",
            "export_button": "button:has-text('导出'), button:has-text('导出数据'), .export-btn, #export-btn",
            "export_data_button": "button:has-text('导出数据'), [title*='导出'], [aria-label*='导出']",
            
            # 其他元素
            "search_button": "button:has-text('搜索'), button:has-text('查询'), .search-btn",
            "table_container": ".table-container, .ant-table",
            # 导出菜单项
            "export_all_menuitem": "li[role='menuitem']:has-text('导出全部订单'), .ant-dropdown-menu-title-content:has-text('导出全部订单'), .el-dropdown-menu__item:has-text('导出全部订单')",
        }
        
    def close_known_modals(self) -> None:
        """尝试关闭常见的功能更新/公告等弹窗"""
        try:
            if not self.page:
                return
            candidates = [
                "button[aria-label='关闭此对话框']",
                "button:has-text('关闭此对话框')",
                ".ant-modal-close",
                ".el-message-box__close",
                "button:has-text('我知道了')",
                "button:has-text('知道了')",
                "button:has-text('关闭')",
            ]
            for sel in candidates:
                try:
                    if self.page.query_selector(sel):
                        self.page.click(sel)
                        time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass
        
    def login(self, username: str, password: str, login_url: str = None) -> bool:
        """
        登录妙手ERP，自动识别重定向到登录页并自动登录
        """
        try:
            # 强制要求login_url由账号配置提供，禁止猜测或硬编码
            if not login_url:
                logger.error("❌ 未提供login_url，按照规范禁止硬编码或猜测URL")
                self.take_screenshot("missing_login_url")
                return False
            # 1. 访问login_url，等待页面主要元素出现
            self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            import time
            time.sleep(2)
            # 2. 判断是否在登录页（根据输入框或按钮）
            is_login_page = False
            try:
                if self.page.query_selector("input[placeholder='手机号/子账号/邮箱']") or \
                   self.page.query_selector("input[placeholder='手机号/子账号/邮箱/邮箱']") or \
                   self.page.query_selector("input[placeholder*='账号']"):
                    is_login_page = True
            except Exception:
                pass
            if is_login_page:
                logger.info("🔐 检测到登录页，自动填充账号密码并登录")
                try:
                    self.page.fill("input[placeholder='手机号/子账号/邮箱']", username)
                    self.page.fill("input[placeholder='密码']", password)
                    self.page.click("button:has-text('立即登录')")
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"❌ 填写账号或点击登录失败: {e}")
                    self.take_screenshot("login_fill_error")
                    return False
                # 可加弹窗关闭逻辑
            # 3. 判断是否已登录
            time.sleep(2)
            if "login" not in self.page.url:
                logger.info("✅ 登录成功或已在业务页面")
                self.take_screenshot("login_success")
                return True
            else:
                logger.error("❌ 登录失败，仍在登录页面")
                self.take_screenshot("login_failed")
                return False
        except Exception as e:
            logger.error(f"❌ 登录过程出错: {e}")
            self.take_screenshot("login_exception")
            return False
    
    def navigate_to_order_page(self, account: dict = None) -> bool:
        """
        导航到订单页面，基于login_url域名跳转
        """
        try:
            logger.info("📋 导航到订单页面...")
            # 直接用login_url作为唯一入口（禁止使用冗余order_url字段）
            if not account or not account.get("login_url"):
                logger.error("❌ 账号未配置login_url，无法导航到业务页面")
                self.take_screenshot("missing_login_url_for_order")
                return False
            order_url = account["login_url"]
            logger.info(f"📋 导航到订单页面: {order_url}")
            if not self.navigate_to(order_url):
                self.take_screenshot("navigate_order_failed")
                return False
            import time
            time.sleep(2)
            self.take_screenshot("order_page")
            logger.info("✅ 成功导航到订单页面")
            return True
        except Exception as e:
            logger.error(f"❌ 导航到订单页面失败: {e}")
            return False
    
    def set_date_range_popup(self, start_date: str, end_date: str) -> bool:
        """
        适配弹窗型日期控件的自动化选择
        """
        try:
            logger.info(f"📅 弹窗控件-设置日期范围: {start_date} 到 {end_date}")
            self.take_screenshot("before_set_date_range_popup")

            # 1. 点击日期输入框，弹出日历
            if not self.click_element("input[placeholder*='日期'], .ant-picker-input, .el-date-editor"):
                logger.error("❌ 无法点击日期输入框")
                self.take_screenshot("click_date_input_failed")
                return False
            import time
            time.sleep(1)

            # 2. 直接输入日期（如支持），否则点选日历
            filled = False
            if self.fill_input("input[placeholder*='开始']", start_date) and self.fill_input("input[placeholder*='结束']", end_date):
                logger.info("✅ 直接填充日期成功")
                filled = True
            else:
                logger.warning("⚠️ 直接填充失败，尝试点选日历")
                # 这里可根据实际HTML结构补充点击日历的逻辑
                # 例如：self.page.click("td[title='2025-08-01']")
                # 可用Inspector录制后补充

            # 3. 如有“确定”按钮，点击
            if self.click_element("button:has-text('确定'), .ant-picker-ok button, .el-picker-panel__footer .el-button--default"):
                logger.info("🖱️ 点击日期弹窗的确定按钮")
            time.sleep(1)

            # 4. 点击搜索
            if self.click_element(self.selectors["search_button"]):
                logger.info("🔍 点击搜索按钮")
            self.take_screenshot("after_set_date_range_popup")
            return filled
        except Exception as e:
            logger.error(f"❌ 弹窗日期控件设置失败: {e}")
            self.take_screenshot("set_date_range_popup_error")
            return False

    def set_date_range(self, start_date: str, end_date: str) -> bool:
        """
        设置日期范围，针对妙手ERP的日期时间选择器优化
        """
        try:
            logger.info(f"📅 设置日期范围: {start_date} 到 {end_date}")
            print(f"🔍 开始查找页面上的日期输入框...")
            self.take_screenshot("before_set_date_range")
            
            import time
            
            # 妙手ERP特定的日期选择器策略
            # 根据图片分析，页面上有两个日期输入框，显示格式类似 "2025-07-16 00:00:00"
            date_input_selectors = [
                "input[placeholder*='下单时间']",
                "input[placeholder*='开始']", 
                "input[placeholder*='结束']",
                "input[value*='2025']",  # 包含年份的输入框
                ".ant-picker-input input",
                ".el-date-editor input",
                "input[type='text']",  # 通用文本输入框
            ]
            
            # 查找所有可能的日期输入框
            date_inputs = []
            for selector in date_input_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        if element.is_visible():
                            value = element.get_attribute('value') or element.input_value() or ''
                            if '2025' in value or '2024' in value:  # 包含年份的输入框
                                date_inputs.append(element)
                                print(f"🎯 找到日期输入框: {selector}, 当前值: {value}")
                except Exception:
                    continue
            
            if len(date_inputs) < 2:
                print("⚠️ 未找到足够的日期输入框，尝试通用策略")
                return self.set_date_range_fallback(start_date, end_date)
            
            # 设置开始日期（第一个输入框）
            start_success = False
            try:
                start_input = date_inputs[0]
                print(f"📅 设置开始日期到第一个输入框: {start_date}")
                
                # 清空并输入新日期
                start_input.click()
                time.sleep(0.5)
                start_input.fill('')  # 清空
                time.sleep(0.3)
                # 输入完整的日期时间格式
                start_datetime = f"{start_date} 00:00:00"
                start_input.fill(start_datetime)
                time.sleep(0.5)
                
                # 验证输入是否成功
                new_value = start_input.input_value()
                if start_date in new_value:
                    print(f"✅ 开始日期设置成功: {new_value}")
                    start_success = True
                else:
                    print(f"⚠️ 开始日期设置可能失败，当前值: {new_value}")
                    
            except Exception as e:
                print(f"❌ 设置开始日期失败: {e}")
            
            # 设置结束日期（第二个输入框）
            end_success = False
            try:
                end_input = date_inputs[1]
                print(f"📅 设置结束日期到第二个输入框: {end_date}")
                
                # 清空并输入新日期
                end_input.click()
                time.sleep(0.5)
                end_input.fill('')  # 清空
                time.sleep(0.3)
                # 输入完整的日期时间格式
                end_datetime = f"{end_date} 23:59:59"
                end_input.fill(end_datetime)
                time.sleep(0.5)
                
                # 验证输入是否成功
                new_value = end_input.input_value()
                if end_date in new_value:
                    print(f"✅ 结束日期设置成功: {new_value}")
                    end_success = True
                else:
                    print(f"⚠️ 结束日期设置可能失败，当前值: {new_value}")
                    
            except Exception as e:
                print(f"❌ 设置结束日期失败: {e}")
            
            # 点击页面其他地方以确保输入生效
            try:
                self.page.click('body')
                time.sleep(0.5)
            except Exception:
                pass
            
            # 点击搜索按钮（如果存在）
            search_clicked = False
            search_selectors = [
                "button:has-text('搜索')",
                "button:has-text('查询')", 
                "button:has-text('筛选')",
                ".search-btn",
                "[class*='search'] button",
                "button[type='submit']"
            ]
            
            for selector in search_selectors:
                try:
                    if self.page.query_selector(selector):
                        self.page.click(selector)
                        print(f"🔍 点击搜索按钮: {selector}")
                        search_clicked = True
                        time.sleep(2)  # 等待搜索结果加载
                        break
                except Exception:
                    continue
            
            if not search_clicked:
                print("⚠️ 未找到搜索按钮，可能需要手动触发查询")
            
            self.take_screenshot("after_set_date_range")
            
            success = start_success and end_success
            if success:
                print("✅ 日期范围设置完成")
            else:
                print("⚠️ 日期范围设置可能不完整")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ 设置日期范围失败: {e}")
            print(f"❌ 设置日期范围失败: {e}")
            self.take_screenshot("date_setting_error")
            return False
    
    def set_date_range_fallback(self, start_date: str, end_date: str) -> bool:
        """
        备用日期设置策略
        """
        try:
            print("🔄 使用备用日期设置策略...")
            # 尝试通用的日期选择器
            general_selectors = [
                "input[placeholder*='开始']",
                "input[placeholder*='结束']", 
                "input[type='date']",
                ".ant-picker-input",
                ".el-date-editor__inner"
            ]
            
            for selector in general_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    if len(elements) >= 2:
                        # 设置第一个为开始日期，第二个为结束日期
                        elements[0].fill(start_date)
                        elements[1].fill(end_date)
                        print(f"✅ 备用策略设置日期成功: {selector}")
                        return True
                except Exception:
                    continue
                    
            return False
            
        except Exception as e:
            print(f"❌ 备用日期设置策略失败: {e}")
            return False

    def switch_to_tab(self, tab_name: str) -> bool:
        """
        支持多种Tab/菜单selector，通过Tab名自动切换页面
        """
        selectors = [
            f"//span[contains(text(), '{tab_name}')]",  # XPath
            f"button:has-text('{tab_name}')",
            f".ant-tabs-tab:has-text('{tab_name}')",
            f".el-tabs__item:has-text('{tab_name}')",
            f".menu-item:has-text('{tab_name}')",
        ]
        for selector in selectors:
            if self.click_element(selector):
                logger.info(f"🖱️ 切换到Tab: {tab_name}")
                import time
                time.sleep(1)
                return True
        logger.error(f"❌ 未找到Tab: {tab_name}")
        return False

    def download_data(self, download_dir: str = "downloads/miaoshou") -> Optional[str]:
        """
        下载数据文件，增强多种按钮识别和日志
        
        Args:
            download_dir: 下载目录
            
        Returns:
            str: 下载文件路径，失败返回None
        """
        try:
            logger.info("📥 开始下载数据...")
            print("📥 开始查找导出按钮...")
            download_path = Path(download_dir)
            download_path.mkdir(parents=True, exist_ok=True)
            self.take_screenshot("before_download")
            
            import time
            
            # 增强的下载按钮选择器，基于妙手ERP界面分析
            download_selectors = [
                # 根据图片分析，可能的导出按钮位置
                "button:has-text('导出数据')",
                "button:has-text('导出')", 
                "button:has-text('下载')",
                "[title*='导出']",
                "[aria-label*='导出']",
                ".export-btn",
                ".download-btn",
                "button[class*='export']",
                "button[class*='download']",
                # 可能在右上角的按钮
                ".ant-btn:has-text('导出')",
                ".el-button:has-text('导出')",
                # 通用按钮选择器
                "button[type='button']:has-text('导出')",
                "a:has-text('导出')",
            ]
            
            # 首先查找所有可能的导出按钮
            found_buttons = []
            for selector in download_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        if element.is_visible():
                            text = element.inner_text().strip()
                            print(f"🎯 找到可能的导出按钮: {text} ({selector})")
                            found_buttons.append((element, selector, text))
                except Exception:
                    continue
            
            if not found_buttons:
                print("⚠️ 未找到导出按钮，尝试查找页面上所有可点击元素...")
                # 查找所有包含"导出"文本的可点击元素
                try:
                    all_buttons = self.page.query_selector_all('button, a, [role="button"], [onclick], [class*="btn"]')
                    for btn in all_buttons:
                        if btn.is_visible():
                            text = btn.inner_text().strip()
                            if '导出' in text or '下载' in text or 'export' in text.lower():
                                print(f"🔍 发现包含导出关键词的元素: {text}")
                                found_buttons.append((btn, "通用选择器", text))
                except Exception as e:
                    print(f"⚠️ 查找通用按钮失败: {e}")
            
            if not found_buttons:
                print("❌ 未找到任何导出按钮")
                self.take_screenshot("no_export_button_found")
                return None
            
            # 尝试点击找到的导出按钮
            download_clicked = False
            for element, selector, text in found_buttons:
                try:
                    print(f"🖱️ 尝试点击导出按钮: {text}")
                    element.click()
                    download_clicked = True
                    logger.info(f"🖱️ 成功点击导出按钮: {text} ({selector})")
                    time.sleep(1)  # 等待可能的下拉菜单出现
                    break
                except Exception as e:
                    print(f"⚠️ 点击按钮失败: {text}, 错误: {e}")
                    continue
            
            if not download_clicked:
                print("❌ 所有导出按钮点击都失败了")
                self.take_screenshot("download_button_click_failed")
                return None
            # 查找并点击导出菜单项（如果有下拉菜单的话）
            print("🔍 查找导出菜单项...")
            export_menu_selectors = [
                "li[role='menuitem']:has-text('导出全部订单')",
                "li[role='menuitem']:has-text('导出全部')", 
                "li:has-text('导出全部订单')",
                "li:has-text('导出全部')",
                "text=导出全部订单",
                "text=导出全部",
                ".ant-dropdown-menu-item:has-text('导出')",
                ".el-dropdown-menu__item:has-text('导出')",
                "[role='menuitem']:has-text('导出')",
            ]
            
            menu_found = False
            for menu_selector in export_menu_selectors:
                try:
                    if self.page and self.page.query_selector(menu_selector):
                        menu_element = self.page.query_selector(menu_selector)
                        if menu_element and menu_element.is_visible():
                            menu_text = menu_element.inner_text().strip()
                            print(f"🎯 找到导出菜单项: {menu_text}")
                            
                            # 监听下载事件并点击菜单项
                            try:
                                with self.page.expect_download(timeout=120000) as download_info:
                                    print(f"🖱️ 点击导出菜单项: {menu_text}")
                                    menu_element.click()
                                    
                                download = download_info.value
                                suggested = download.suggested_filename
                                filename = suggested or f"miaoshou_data_{int(time.time())}.xlsx"
                                target_path = Path(download_dir) / filename
                                
                                download.save_as(str(target_path))
                                print(f"✅ 文件下载完成: {filename}")
                                logger.info(f"✅ 文件下载完成并保存: {target_path}")
                                self.take_screenshot("download_success")
                                return str(target_path)
                                
                            except Exception as download_error:
                                print(f"⚠️ 下载过程出错: {download_error}")
                                # 继续尝试其他菜单项
                                continue
                            
                            menu_found = True
                            break
                            
                except Exception as e:
                    print(f"⚠️ 检查菜单项失败: {menu_selector}, {e}")
                    continue
            
            if not menu_found:
                print("⚠️ 未找到导出菜单项，可能导出按钮直接触发下载")
                # 尝试直接监听下载事件
                try:
                    print("🔄 等待可能的直接下载...")
                    with self.page.expect_download(timeout=30000) as download_info:
                        # 等待下载开始
                        pass
                    
                    download = download_info.value
                    suggested = download.suggested_filename
                    filename = suggested or f"miaoshou_data_{int(time.time())}.xlsx"
                    target_path = Path(download_dir) / filename
                    
                    download.save_as(str(target_path))
                    print(f"✅ 直接下载完成: {filename}")
                    logger.info(f"✅ 直接下载完成并保存: {target_path}")
                    self.take_screenshot("direct_download_success")
                    return str(target_path)
                    
                except Exception as e:
                    print(f"⚠️ 直接下载也失败了: {e}")
            
            print("❌ 所有下载尝试都失败了")
            self.take_screenshot("all_download_attempts_failed")
            return None
        except Exception as e:
            logger.error(f"❌ 下载过程出错: {e}")
            self.take_screenshot("download_exception")
            return None
    
    def collect_data(self, account: Dict[str, Any], start_date: str = None, end_date: str = None, data_type: str = "sales") -> Dict[str, Any]:
        """
        执行完整的数据采集流程，支持自定义日期范围
        
        Args:
            account: 账号信息
            start_date: 开始日期 (YYYY-MM-DD)，可选
            end_date: 结束日期 (YYYY-MM-DD)，可选
            
        Returns:
            Dict: 采集结果
        """
        start_time = time.time()
        
        # 处理日期范围：如果为空或None，设置默认30天范围
        if not start_date or not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            print(f"📅 使用默认日期范围: {start_date} 到 {end_date}")
            logger.info(f"📅 使用默认日期范围: {start_date} 到 {end_date}")
        else:
            print(f"📅 使用指定日期范围: {start_date} 到 {end_date}")
            logger.info(f"📅 使用指定日期范围: {start_date} 到 {end_date}")
        
        result = {
            "success": False,
            "account_id": account.get("account_id", ""),
            "platform": "妙手ERP",
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration": 0,
            "error": None,
            "downloaded_files": [],
            "screenshots": [],
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
        }
        
        try:
            print(f"🚀 开始妙手ERP数据采集: {account.get('username', '')}")
            logger.info(f"🚀 开始妙手ERP数据采集: {account.get('username', '')}")
            
            # 根据账号与数据类型设置下载目录
            account_key = f"{str(account.get('platform','')).lower()}_{str(account.get('username','')).lower()}".replace('@','_')
            base_download_dir = Path("downloads") / "miaoshou" / account_key / data_type
            base_download_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 设置下载目录: {base_download_dir}")
            logger.info(f"📁 设置下载目录: {base_download_dir}")
            
            # 启动浏览器（集成VPN优化）
            print("🌐 步骤1: 启动浏览器...")
            logger.info("🌐 步骤1: 启动浏览器...")
            self.downloads_path = base_download_dir
            
            # 优先使用多地区路由器的VPN绕过功能
            login_url = account.get('login_url', 'https://erp.91miaoshou.com')
            if self.MULTI_REGION_AVAILABLE and self.multi_region_router:
                print("🚀 应用多地区路由器配置...")
                # 获取妙手ERP平台的代理配置
                proxy_config = self.multi_region_router.get_playwright_proxy_config("miaoshou_erp")
                if proxy_config:
                    print("✅ 已获取妙手ERP专用代理配置（VPN绕过）")
                    # 将代理配置合并到浏览器配置中
                    if 'proxy' not in self.browser_config:
                        self.browser_config['proxy'] = {}
                    self.browser_config['proxy'].update(proxy_config)
                else:
                    print("📡 使用直连模式访问妙手ERP")
            elif self.vpn_accelerator and self.vpn_accelerator.is_vpn_environment:
                print("🚀 应用VPN环境优化配置...")
                self.vpn_accelerator.optimize_china_access()
                
                # 获取妙手ERP网站的优化配置
                china_config = self.vpn_accelerator.get_playwright_config(login_url)
                if china_config:
                    print("✅ 已获取中国网站访问优化配置")
                    # 将优化配置合并到浏览器配置中
                    self.browser_config.update(china_config)
            
            if not self.start_browser():
                print("❌ 步骤1失败: 浏览器启动失败")
                logger.error("❌ 步骤1失败: 浏览器启动失败")
                result["error"] = "浏览器启动失败"
                return result
            print("✅ 步骤1成功: 浏览器已启动")
            logger.info("✅ 步骤1成功: 浏览器已启动")
            
            # 登录
            print("🔐 步骤2: 执行登录...")
            logger.info("🔐 步骤2: 执行登录...")
            username = account.get("username", "")
            password = account.get("password", "")
            login_url = account.get("login_url")
            
            if not self.login(username, password, login_url):
                print("❌ 步骤2失败: 登录失败或未配置login_url")
                logger.error("❌ 步骤2失败: 登录失败或未配置login_url")
                result["error"] = "登录失败或未配置login_url"
                return result
            print("✅ 步骤2成功: 登录完成")
            logger.info("✅ 步骤2成功: 登录完成")
            
            # 导航到订单页面（传递account参数）
            print("📋 步骤3: 导航到订单页面...")
            logger.info("📋 步骤3: 导航到订单页面...")
            if not self.navigate_to_order_page(account=account):
                print("❌ 步骤3失败: 导航到订单页面失败")
                logger.error("❌ 步骤3失败: 导航到订单页面失败")
                result["error"] = "导航到订单页面失败"
                return result
            print("✅ 步骤3成功: 已导航到订单页面")
            logger.info("✅ 步骤3成功: 已导航到订单页面")
            
            # 关闭可能的弹窗
            print("🚫 步骤4: 关闭弹窗...")
            logger.info("🚫 步骤4: 关闭弹窗...")
            self.close_known_modals()
            print("✅ 步骤4完成: 弹窗处理完成")
            logger.info("✅ 步骤4完成: 弹窗处理完成")
            
            # 可选：切换到"利润明细"等必要Tab
            print("📊 步骤5: 切换到利润明细标签...")
            logger.info("📊 步骤5: 切换到利润明细标签...")
            if self.switch_to_tab("利润明细"):
                print("✅ 步骤5成功: 已切换到利润明细标签")
                logger.info("✅ 步骤5成功: 已切换到利润明细标签")
            else:
                print("⚠️ 步骤5警告: 未找到利润明细标签，可能页面结构不同")
                logger.warning("⚠️ 步骤5警告: 未找到利润明细标签，可能页面结构不同")
            
            # 设置日期范围
            print(f"📅 步骤6: 设置日期范围 ({start_date} 到 {end_date})...")
            logger.info(f"📅 步骤6: 设置日期范围 ({start_date} 到 {end_date})...")
            if self.set_date_range(start_date, end_date):
                print("✅ 步骤6成功: 日期范围设置完成")
                logger.info("✅ 步骤6成功: 日期范围设置完成")
            else:
                print("⚠️ 步骤6警告: 日期范围设置可能失败，继续尝试下载")
                logger.warning("⚠️ 步骤6警告: 日期范围设置可能失败，继续尝试下载")
            
            # 下载数据
            print("📥 步骤7: 下载数据...")
            logger.info("📥 步骤7: 下载数据...")
            downloaded_file = self.download_data(download_dir=str(base_download_dir))
            if downloaded_file:
                print(f"✅ 步骤7成功: 数据下载完成，文件: {downloaded_file}")
                logger.info(f"✅ 步骤7成功: 数据下载完成，文件: {downloaded_file}")
                result["downloaded_files"].append(downloaded_file)
                result["success"] = True
                print("🎉 数据采集完成")
                logger.info("🎉 数据采集完成")
            else:
                print("❌ 步骤7失败: 数据下载失败")
                logger.error("❌ 步骤7失败: 数据下载失败")
                result["error"] = "数据下载失败"
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"❌ 数据采集异常: {e}")
            
        finally:
            # 记录结束时间和耗时
            end_time = time.time()
            result["end_time"] = datetime.now().isoformat()
            result["duration"] = end_time - start_time
            
            # 关闭浏览器
            self.close_browser()
            
            logger.info(f"📊 采集结果: {'成功' if result['success'] else '失败'}")
            logger.info(f"⏱️ 耗时: {result['duration']:.2f}秒")
            
            return result

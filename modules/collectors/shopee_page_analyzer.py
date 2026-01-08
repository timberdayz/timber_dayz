#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee商家端页面分析器
专门用于分析Shopee商家端页面的结构、数据下载选项和功能菜单
"""

import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
from playwright.sync_api import Page, Locator
from dataclasses import dataclass, asdict

from ..utils.page_analysis_tool import PageAnalysisTool, PageAnalysisResult

logger = logging.getLogger(__name__)

@dataclass
class ShopeeDataSection:
    """Shopee数据区域信息"""
    name: str
    url: str
    description: str
    data_types: List[str]
    export_options: List[str]
    access_level: str  # basic, advanced, premium

@dataclass
class ShopeeMenuStructure:
    """Shopee菜单结构"""
    main_menu: str
    sub_menus: List[str]
    url_pattern: str
    data_available: bool

@dataclass
class ShopeeAnalysisResult:
    """Shopee分析结果"""
    account_id: str
    store_name: str
    analysis_time: str
    current_page: str
    available_sections: List[ShopeeDataSection]
    menu_structure: List[ShopeeMenuStructure]
    download_capabilities: List[Dict[str, Any]]
    data_access_level: str
    recommended_collection_strategy: Dict[str, Any]

class ShopeePageAnalyzer:
    """Shopee商家端页面分析器"""
    
    def __init__(self, page: Page, account_config: Dict[str, Any]):
        """
        初始化Shopee页面分析器
        
        Args:
            page: Playwright页面对象
            account_config: 账号配置信息
        """
        self.page = page
        self.account_config = account_config
        self.account_id = account_config.get('account_id', '')
        self.store_name = account_config.get('store_name', '')
        
        # 创建通用页面分析工具
        self.analysis_tool = PageAnalysisTool(page, "shopee")
        
        # Shopee特定的页面配置
        self.shopee_pages = {
            "dashboard": {
                "url": "https://seller.shopee.cn/",
                "name": "仪表板",
                "data_types": ["概览数据", "实时指标", "趋势图表"],
                "export_options": ["截图", "数据导出"]
            },
            "analytics": {
                "url": "https://seller.shopee.cn/analytics",
                "name": "数据分析",
                "data_types": ["流量分析", "销售分析", "用户画像"],
                "export_options": ["Excel", "CSV", "PDF"]
            },
            "orders": {
                "url": "https://seller.shopee.cn/orders",
                "name": "订单管理",
                "data_types": ["订单列表", "订单详情", "订单统计"],
                "export_options": ["Excel", "CSV"]
            },
            "products": {
                "url": "https://seller.shopee.cn/products",
                "name": "商品管理",
                "data_types": ["商品列表", "库存信息", "价格信息"],
                "export_options": ["Excel", "CSV"]
            },
            "finance": {
                "url": "https://seller.shopee.cn/finance",
                "name": "财务管理",
                "data_types": ["收入统计", "支出记录", "财务报表"],
                "export_options": ["Excel", "PDF"]
            },
            "marketing": {
                "url": "https://seller.shopee.cn/marketing",
                "name": "营销工具",
                "data_types": ["活动数据", "推广效果", "ROI分析"],
                "export_options": ["Excel", "CSV"]
            }
        }
        
        logger.info(f"[SEARCH] 初始化Shopee页面分析器: {self.store_name}")
    
    def analyze_shopee_platform(self) -> ShopeeAnalysisResult:
        """
        分析Shopee平台整体结构
        
        Returns:
            ShopeeAnalysisResult: Shopee分析结果
        """
        try:
            logger.info(f"[SEARCH] 开始分析Shopee平台: {self.store_name}")
            
            # 分析当前页面
            current_page_analysis = self.analysis_tool.analyze_current_page()
            
            # 分析可访问的数据区域
            available_sections = self._analyze_available_sections()
            
            # 分析菜单结构
            menu_structure = self._analyze_menu_structure()
            
            # 分析下载能力
            download_capabilities = self._analyze_download_capabilities()
            
            # 确定数据访问级别
            data_access_level = self._determine_data_access_level()
            
            # 生成推荐采集策略
            collection_strategy = self._generate_collection_strategy(
                available_sections, download_capabilities, data_access_level
            )
            
            result = ShopeeAnalysisResult(
                account_id=self.account_id,
                store_name=self.store_name,
                analysis_time=datetime.now().isoformat(),
                current_page=self.page.url,
                available_sections=available_sections,
                menu_structure=menu_structure,
                download_capabilities=download_capabilities,
                data_access_level=data_access_level,
                recommended_collection_strategy=collection_strategy
            )
            
            logger.info(f"[OK] Shopee平台分析完成: {len(available_sections)} 个可用区域")
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] Shopee平台分析失败: {e}")
            raise
    
    def analyze_shopee_platform_logged_in(self) -> ShopeeAnalysisResult:
        """
        分析Shopee平台整体结构 - 仅在已登录状态下执行
        
        Returns:
            ShopeeAnalysisResult: Shopee分析结果
        """
        try:
            logger.info(f"[SEARCH] 开始分析已登录的Shopee平台: {self.store_name}")
            
            # 检查当前是否在登录页面
            current_url = self.page.url
            if any(keyword in current_url.lower() for keyword in ['login', 'signin', 'auth']):
                logger.warning(f"[WARN] 当前在登录页面，跳过页面跳转分析: {current_url}")
                # 如果在登录页面，先跳转到仪表板
                try:
                    dashboard_url = "https://seller.shopee.cn/"
                    self.page.goto(dashboard_url, timeout=30000)
                    time.sleep(3)
                    logger.info(f"[OK] 已跳转到仪表板: {dashboard_url}")
                except Exception as e:
                    logger.warning(f"[WARN] 跳转到仪表板失败: {e}")
            
            # 分析当前页面
            current_page_analysis = self.analysis_tool.analyze_current_page()
            
            # 仅分析当前页面的菜单结构，不跳转到其他页面
            menu_structure = self._analyze_current_page_menu()
            
            # 基于菜单结构推断可用区域，而不是实际访问
            available_sections = self._infer_available_sections_from_menu(menu_structure)
            
            # 分析当前页面的下载能力
            download_capabilities = self._analyze_current_page_downloads()
            
            # 确定数据访问级别
            data_access_level = "basic"  # 保守估计
            
            # 生成推荐采集策略
            collection_strategy = self._generate_safe_collection_strategy(
                available_sections, download_capabilities, data_access_level
            )
            
            result = ShopeeAnalysisResult(
                account_id=self.account_id,
                store_name=self.store_name,
                analysis_time=datetime.now().isoformat(),
                current_page=self.page.url,
                available_sections=available_sections,
                menu_structure=menu_structure,
                download_capabilities=download_capabilities,
                data_access_level=data_access_level,
                recommended_collection_strategy=collection_strategy
            )
            
            logger.info(f"[OK] 已登录Shopee平台分析完成: {len(available_sections)} 个推断区域")
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 已登录Shopee平台分析失败: {e}")
            # 返回基础的分析结果而不是抛出异常
            return ShopeeAnalysisResult(
                account_id=self.account_id,
                store_name=self.store_name,
                analysis_time=datetime.now().isoformat(),
                current_page=self.page.url,
                available_sections=[],
                menu_structure=[],
                download_capabilities=[],
                data_access_level="unknown",
                recommended_collection_strategy={"error": str(e)}
            )
    
    def _analyze_available_sections(self) -> List[ShopeeDataSection]:
        """分析可访问的数据区域"""
        sections = []
        
        try:
            # 检查各个数据页面是否可访问
            for page_key, page_info in self.shopee_pages.items():
                try:
                    # 尝试访问页面
                    self.page.goto(page_info["url"], timeout=10000)
                    time.sleep(2)
                    
                    # 检查页面是否可访问（不是错误页面）
                    if self._is_page_accessible():
                        section = ShopeeDataSection(
                            name=page_info["name"],
                            url=page_info["url"],
                            description=f"Shopee {page_info['name']}页面",
                            data_types=page_info["data_types"],
                            export_options=page_info["export_options"],
                            access_level=self._determine_section_access_level(page_key)
                        )
                        sections.append(section)
                        logger.info(f"[OK] 发现可访问区域: {page_info['name']}")
                    else:
                        logger.warning(f"[WARN] 页面不可访问: {page_info['name']}")
                        
                except Exception as e:
                    logger.warning(f"[WARN] 检查页面失败 {page_info['name']}: {e}")
                    continue
            
            return sections
            
        except Exception as e:
            logger.error(f"[FAIL] 分析可访问区域失败: {e}")
            return []
    
    def _is_page_accessible(self) -> bool:
        """检查页面是否可访问"""
        try:
            # 检查是否有错误信息
            error_selectors = [
                "div:has-text('错误')",
                "div:has-text('Error')",
                "div:has-text('404')",
                "div:has-text('403')",
                "div:has-text('访问被拒绝')",
                "div:has-text('Access Denied')"
            ]
            
            for selector in error_selectors:
                if self.page.locator(selector).count() > 0:
                    return False
            
            # 检查是否有主要内容
            content_selectors = [
                "main", ".main-content", ".content", ".container",
                "[class*='dashboard']", "[class*='analytics']"
            ]
            
            for selector in content_selectors:
                if self.page.locator(selector).count() > 0:
                    return True
            
            return True  # 默认认为可访问
            
        except Exception:
            return False
    
    def _determine_section_access_level(self, page_key: str) -> str:
        """确定区域访问级别"""
        # 根据页面类型和内容判断访问级别
        if page_key in ["dashboard", "analytics"]:
            return "basic"
        elif page_key in ["orders", "products"]:
            return "advanced"
        elif page_key in ["finance", "marketing"]:
            return "premium"
        else:
            return "basic"
    
    def _analyze_menu_structure(self) -> List[ShopeeMenuStructure]:
        """分析菜单结构"""
        menu_structures = []
        
        try:
            # 查找主导航菜单
            main_menu_selectors = [
                "nav", "[class*='nav']", "[class*='menu']",
                "[role='navigation']", ".sidebar", ".menu-container"
            ]
            
            for selector in main_menu_selectors:
                try:
                    menu_elements = self.page.locator(selector)
                    count = menu_elements.count()
                    
                    for i in range(count):
                        menu_element = menu_elements.nth(i)
                        if menu_element.is_visible():
                            # 提取主菜单项
                            main_menu_items = self._extract_main_menu_items(menu_element)
                            
                            for main_item in main_menu_items:
                                # 提取子菜单
                                sub_menus = self._extract_sub_menus(main_item)
                                
                                menu_structure = ShopeeMenuStructure(
                                    main_menu=main_item.get("text", ""),
                                    sub_menus=sub_menus,
                                    url_pattern=main_item.get("url", ""),
                                    data_available=self._check_menu_data_availability(main_item)
                                )
                                menu_structures.append(menu_structure)
                                
                except Exception:
                    continue
            
            return menu_structures
            
        except Exception as e:
            logger.error(f"[FAIL] 分析菜单结构失败: {e}")
            return []
    
    def _extract_main_menu_items(self, menu_element: Locator) -> List[Dict[str, str]]:
        """提取主菜单项"""
        items = []
        
        try:
            # 查找主菜单项
            item_selectors = [
                "a", "button", "[class*='item']", "[class*='link']",
                "[class*='menu-item']", "[class*='nav-item']"
            ]
            
            for selector in item_selectors:
                try:
                    elements = menu_element.locator(selector)
                    count = elements.count()
                    
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            item = {
                                "text": element.inner_text().strip(),
                                "url": element.get_attribute("href") or "",
                                "selector": selector
                            }
                            if item["text"] and len(item["text"]) < 50:
                                items.append(item)
                                
                except Exception:
                    continue
            
            return items
            
        except Exception:
            return []
    
    def _extract_sub_menus(self, main_item: Dict[str, str]) -> List[str]:
        """提取子菜单"""
        sub_menus = []
        
        try:
            # 这里需要根据实际页面结构来实现
            # 暂时返回空列表，后续可以根据具体页面结构完善
            return sub_menus
            
        except Exception:
            return []
    
    def _check_menu_data_availability(self, menu_item: Dict[str, str]) -> bool:
        """检查菜单项是否有数据"""
        try:
            # 根据菜单项文本判断是否有数据
            text = menu_item.get("text", "").lower()
            data_keywords = ["数据", "分析", "报表", "统计", "订单", "商品", "财务"]
            
            for keyword in data_keywords:
                if keyword in text:
                    return True
            
            return False
            
        except Exception:
            return False
    
    def _analyze_download_capabilities(self) -> List[Dict[str, Any]]:
        """分析下载能力"""
        capabilities = []
        
        try:
            # 使用通用分析工具分析下载选项
            page_analysis = self.analysis_tool.analyze_current_page()
            
            for download_option in page_analysis.download_options:
                capability = {
                    "name": download_option.name,
                    "selector": download_option.selector,
                    "file_types": download_option.file_types,
                    "date_ranges": download_option.date_ranges,
                    "data_types": download_option.data_types,
                    "is_available": download_option.is_available,
                    "platform_specific": self._analyze_platform_specific_features(download_option)
                }
                capabilities.append(capability)
            
            return capabilities
            
        except Exception as e:
            logger.error(f"[FAIL] 分析下载能力失败: {e}")
            return []
    
    def _analyze_platform_specific_features(self, download_option) -> Dict[str, Any]:
        """分析平台特定功能"""
        features = {}
        
        try:
            # 分析Shopee特定的下载功能
            text = download_option.name.lower()
            
            # 检查是否有时间范围选择
            if any(keyword in text for keyword in ["日期", "时间", "范围", "date", "time", "range"]):
                features["has_date_range"] = True
            
            # 检查是否有数据筛选
            if any(keyword in text for keyword in ["筛选", "过滤", "filter", "select"]):
                features["has_data_filter"] = True
            
            # 检查是否有批量下载
            if any(keyword in text for keyword in ["批量", "全部", "batch", "all"]):
                features["has_batch_download"] = True
            
            # 检查是否有实时数据
            if any(keyword in text for keyword in ["实时", "实时", "realtime", "live"]):
                features["has_realtime_data"] = True
            
            return features
            
        except Exception:
            return {}
    
    def _determine_data_access_level(self) -> str:
        """确定数据访问级别"""
        try:
            # 检查当前页面的功能来判断访问级别
            current_url = self.page.url
            
            # 检查是否有高级功能
            advanced_features = [
                "analytics", "finance", "marketing", "advanced"
            ]
            
            for feature in advanced_features:
                if feature in current_url:
                    return "premium"
            
            # 检查是否有基础功能
            basic_features = [
                "dashboard", "orders", "products"
            ]
            
            for feature in basic_features:
                if feature in current_url:
                    return "advanced"
            
            return "basic"
            
        except Exception:
            return "basic"
    
    def _generate_collection_strategy(self, sections: List[ShopeeDataSection], 
                                    capabilities: List[Dict[str, Any]], 
                                    access_level: str) -> Dict[str, Any]:
        """生成采集策略"""
        strategy = {
            "recommended_sections": [],
            "download_priorities": [],
            "collection_frequency": {},
            "data_retention": {},
            "error_handling": {}
        }
        
        try:
            # 推荐数据区域
            for section in sections:
                if section.access_level in ["basic", "advanced"]:
                    strategy["recommended_sections"].append({
                        "name": section.name,
                        "url": section.url,
                        "priority": "high" if section.access_level == "basic" else "medium",
                        "data_types": section.data_types
                    })
            
            # 下载优先级
            for capability in capabilities:
                if capability["is_available"]:
                    priority = "high" if len(capability["file_types"]) > 1 else "medium"
                    strategy["download_priorities"].append({
                        "name": capability["name"],
                        "priority": priority,
                        "file_types": capability["file_types"]
                    })
            
            # 采集频率建议
            strategy["collection_frequency"] = {
                "dashboard": "hourly",      # 仪表板数据每小时
                "analytics": "daily",       # 分析数据每天
                "orders": "real-time",      # 订单数据实时
                "products": "daily",        # 商品数据每天
                "finance": "daily",         # 财务数据每天
                "marketing": "weekly"       # 营销数据每周
            }
            
            # 数据保留策略
            strategy["data_retention"] = {
                "real_time_data": "7_days",
                "daily_data": "30_days",
                "weekly_data": "90_days",
                "monthly_data": "365_days"
            }
            
            # 错误处理策略
            strategy["error_handling"] = {
                "retry_times": 3,
                "retry_delay": 5,
                "fallback_strategy": "manual_collection",
                "notification_enabled": True
            }
            
            return strategy
            
        except Exception as e:
            logger.error(f"[FAIL] 生成采集策略失败: {e}")
            return strategy
    
    def save_analysis_result(self, result: ShopeeAnalysisResult, 
                           output_dir: str = "temp/analysis/shopee") -> str:
        """
        保存分析结果
        
        Args:
            result: 分析结果
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件路径
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_store_name = self.store_name.replace(" ", "_").replace("/", "_")
            filename = f"shopee_analysis_{safe_store_name}_{timestamp}.json"
            file_path = output_path / filename
            
            # 转换为字典并保存
            result_dict = asdict(result)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[SAVE] Shopee分析结果已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"[FAIL] 保存Shopee分析结果失败: {e}")
            raise
    
    def generate_shopee_report(self, result: ShopeeAnalysisResult) -> str:
        """
        生成Shopee分析报告
        
        Args:
            result: 分析结果
            
        Returns:
            str: 报告内容
        """
        try:
            report = []
            report.append("=" * 80)
            report.append(f"[*] SHOPEE商家端平台分析报告")
            report.append("=" * 80)
            report.append(f"[DATE] 分析时间: {result.analysis_time}")
            report.append(f"[STORE] 店铺名称: {result.store_name}")
            report.append(f"[ID] 账号ID: {result.account_id}")
            report.append(f"[WEB] 当前页面: {result.current_page}")
            report.append(f"[DATA] 数据访问级别: {result.data_access_level}")
            report.append("")
            
            # 可访问的数据区域
            report.append("[FOLDER] 可访问的数据区域:")
            if result.available_sections:
                for i, section in enumerate(result.available_sections, 1):
                    report.append(f"  {i}. {section.name}")
                    report.append(f"     URL: {section.url}")
                    report.append(f"     数据类型: {', '.join(section.data_types)}")
                    report.append(f"     导出选项: {', '.join(section.export_options)}")
                    report.append(f"     访问级别: {section.access_level}")
                    report.append("")
            else:
                report.append("  [FAIL] 未发现可访问的数据区域")
                report.append("")
            
            # 菜单结构
            report.append("[COMPASS] 菜单结构:")
            if result.menu_structure:
                for i, menu in enumerate(result.menu_structure, 1):
                    report.append(f"  {i}. {menu.main_menu}")
                    if menu.sub_menus:
                        for sub_menu in menu.sub_menus:
                            report.append(f"     - {sub_menu}")
                    report.append(f"     数据可用: {'[OK]' if menu.data_available else '[FAIL]'}")
                    report.append("")
            else:
                report.append("  [FAIL] 未发现菜单结构")
                report.append("")
            
            # 下载能力
            report.append("[RECV] 下载能力:")
            if result.download_capabilities:
                for i, capability in enumerate(result.download_capabilities, 1):
                    report.append(f"  {i}. {capability['name']}")
                    report.append(f"     文件类型: {', '.join(capability['file_types']) if capability['file_types'] else '未知'}")
                    report.append(f"     可用状态: {'[OK]' if capability['is_available'] else '[FAIL]'}")
                    report.append("")
            else:
                report.append("  [FAIL] 未发现下载能力")
                report.append("")
            
            # 推荐采集策略
            report.append("[TARGET] 推荐采集策略:")
            strategy = result.recommended_collection_strategy
            
            report.append("  推荐数据区域:")
            for section in strategy.get("recommended_sections", []):
                report.append(f"    - {section['name']} (优先级: {section['priority']})")
            
            report.append("  采集频率:")
            for section, frequency in strategy.get("collection_frequency", {}).items():
                report.append(f"    - {section}: {frequency}")
            
            report.append("  数据保留:")
            for data_type, retention in strategy.get("data_retention", {}).items():
                report.append(f"    - {data_type}: {retention}")
            
            report.append("")
            report.append("=" * 80)
            report.append("[LIST] 分析完成")
            report.append("=" * 80)
            
            return "\n".join(report)
            
        except Exception as e:
            logger.error(f"[FAIL] 生成Shopee报告失败: {e}")
            return f"生成报告失败: {e}"


    def _analyze_current_page_menu(self) -> List[ShopeeMenuStructure]:
        """分析当前页面的菜单结构，不跳转到其他页面"""
        menu_structures = []
        
        try:
            # 查找主导航菜单
            main_menu_selectors = [
                "nav", "[class*='nav']", "[class*='menu']",
                "[role='navigation']", ".sidebar", ".menu-container",
                "[class*='sidebar']", "[class*='navigation']"
            ]
            
            for selector in main_menu_selectors:
                try:
                    menu_elements = self.page.locator(selector)
                    count = menu_elements.count()
                    
                    for i in range(min(count, 3)):  # 限制检查数量
                        menu_element = menu_elements.nth(i)
                        if menu_element.is_visible():
                            # 提取菜单项文本，不点击
                            menu_items = self._extract_menu_items_safe(menu_element)
                            
                            for item in menu_items:
                                menu_structure = ShopeeMenuStructure(
                                    main_menu=item.get("text", ""),
                                    sub_menus=item.get("sub_menus", []),
                                    url_pattern=item.get("href", ""),
                                    data_available=True  # 假设有数据可用
                                )
                                menu_structures.append(menu_structure)
                            
                            if menu_structures:
                                break  # 找到菜单就停止
                                
                except Exception as e:
                    logger.debug(f"检查菜单元素失败: {e}")
                    continue
                    
                if menu_structures:
                    break  # 找到菜单就停止检查其他选择器
            
            logger.info(f"[OK] 分析当前页面菜单: {len(menu_structures)} 个菜单项")
            return menu_structures
            
        except Exception as e:
            logger.warning(f"[WARN] 分析菜单结构失败: {e}")
            return []
    
    def _extract_menu_items_safe(self, menu_element: Locator) -> List[Dict[str, Any]]:
        """安全提取菜单项，不触发点击"""
        items = []
        
        try:
            # 查找菜单项
            item_selectors = ["a", "li", "[class*='menu-item']", "[class*='nav-item']"]
            
            for selector in item_selectors:
                try:
                    menu_items = menu_element.locator(selector)
                    count = min(menu_items.count(), 10)  # 限制数量
                    
                    for i in range(count):
                        item = menu_items.nth(i)
                        if item.is_visible():
                            text = item.inner_text().strip()[:50]  # 限制长度
                            href = ""
                            
                            try:
                                href = item.get_attribute("href") or ""
                            except:
                                pass
                            
                            if text and len(text) > 1:
                                items.append({
                                    "text": text,
                                    "href": href,
                                    "sub_menus": []  # 简化处理
                                })
                                
                        if len(items) >= 10:  # 限制总数量
                            break
                            
                except Exception:
                    continue
                    
                if items:
                    break  # 找到菜单项就停止
            
            return items[:10]  # 最多返回10个
            
        except Exception as e:
            logger.debug(f"提取菜单项失败: {e}")
            return []
    
    def _infer_available_sections_from_menu(self, menu_structure: List[ShopeeMenuStructure]) -> List[ShopeeDataSection]:
        """基于菜单结构推断可用的数据区域，不实际访问"""
        sections = []
        
        try:
            # 菜单项到数据区域的映射
            menu_mapping = {
                "dashboard": ["仪表板", "概览", "总览", "首页"],
                "analytics": ["数据", "分析", "统计", "报告"],
                "orders": ["订单", "交易", "销售"],
                "products": ["商品", "产品", "货品", "库存"],
                "finance": ["财务", "收入", "资金", "账单"],
                "marketing": ["营销", "推广", "广告", "活动"]
            }
            
            # 遍历菜单结构，匹配已知的数据区域
            for menu_item in menu_structure:
                menu_text = menu_item.main_menu.lower()
                
                for section_key, keywords in menu_mapping.items():
                    if any(keyword in menu_text for keyword in keywords):
                        page_info = self.shopee_pages.get(section_key, {})
                        if page_info:
                            section = ShopeeDataSection(
                                name=page_info.get("name", section_key),
                                url=page_info.get("url", menu_item.url_pattern),
                                description=f"Shopee {page_info.get('name', section_key)}页面（推断）",
                                data_types=page_info.get("data_types", ["基础数据"]),
                                export_options=page_info.get("export_options", ["截图"]),
                                access_level="basic"
                            )
                            sections.append(section)
                            logger.info(f"[OK] 推断可用区域: {section.name}")
            
            # 如果没有找到匹配的菜单，添加基础区域
            if not sections:
                basic_section = ShopeeDataSection(
                    name="当前页面",
                    url=self.page.url if hasattr(self, 'page') else "",
                    description="当前页面的基础数据",
                    data_types=["页面数据"],
                    export_options=["截图"],
                    access_level="basic"
                )
                sections.append(basic_section)
            
            return sections
            
        except Exception as e:
            logger.warning(f"[WARN] 推断可用区域失败: {e}")
            return []
    
    def _analyze_current_page_downloads(self) -> List[Dict[str, Any]]:
        """分析当前页面的下载能力"""
        downloads = []
        
        try:
            # 查找下载相关按钮
            download_selectors = [
                "button:has-text('下载')",
                "button:has-text('导出')",
                "button:has-text('Export')",
                "button:has-text('Download')",
                "a:has-text('下载')",
                "a:has-text('导出')",
                "[class*='download']",
                "[class*='export']"
            ]
            
            for selector in download_selectors:
                try:
                    elements = self.page.locator(selector)
                    count = min(elements.count(), 5)  # 限制检查数量
                    
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            text = element.inner_text().strip()
                            if text:
                                downloads.append({
                                    "type": "button",
                                    "text": text,
                                    "format": self._guess_download_format(text),
                                    "available": True
                                })
                                
                except Exception:
                    continue
            
            # 如果没有找到下载选项，添加默认选项
            if not downloads:
                downloads.append({
                    "type": "screenshot",
                    "text": "页面截图",
                    "format": "png",
                    "available": True
                })
            
            logger.info(f"[OK] 发现下载选项: {len(downloads)} 个")
            return downloads
            
        except Exception as e:
            logger.warning(f"[WARN] 分析下载能力失败: {e}")
            return []
    
    def _guess_download_format(self, text: str) -> str:
        """根据文本猜测下载格式"""
        text_lower = text.lower()
        if "excel" in text_lower or "xlsx" in text_lower:
            return "excel"
        elif "csv" in text_lower:
            return "csv"
        elif "pdf" in text_lower:
            return "pdf"
        else:
            return "unknown"
    
    def _generate_safe_collection_strategy(self, available_sections: List[ShopeeDataSection], 
                                         download_capabilities: List[Dict[str, Any]], 
                                         data_access_level: str) -> Dict[str, Any]:
        """生成安全的采集策略"""
        strategy = {
            "priority_sections": [section.name for section in available_sections[:3]],
            "collection_method": "safe_mode",
            "download_sequence": download_capabilities[:3],
            "estimated_time": 60,  # 保守估计1分钟
            "risk_level": "low",
            "notes": "基于菜单推断的安全策略"
        }
        
        return strategy

def create_shopee_page_analyzer(page: Page, account_config: Dict[str, Any]) -> ShopeePageAnalyzer:
    """
    创建Shopee页面分析器
    
    Args:
        page: Playwright页面对象
        account_config: 账号配置信息
        
    Returns:
        ShopeePageAnalyzer: Shopee页面分析器实例
    """
    return ShopeePageAnalyzer(page, account_config) 
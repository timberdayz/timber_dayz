"""
账号健康状态检测器 - 通用多平台版本
=======================================

功能特性：
- 🔍 智能检测账号登录后的健康状态
- ⚠️ 识别异常账号（权限不足、被封禁、店铺不匹配等）
- 🚨 自动处理异常账号（停止操作、关闭进程、记录日志）
- 📊 生成账号健康报告
- 🔄 支持多平台（Shopee、Amazon、妙手ERP等）

版本：v1.0.0
作者：跨境电商ERP系统
更新：2025-08-29
"""

import time
from typing import Dict, List, Optional, Tuple
from enum import Enum
from playwright.sync_api import Page
from modules.utils.logger import logger


class AccountStatus(Enum):
    """账号状态枚举"""
    HEALTHY = "healthy"              # 正常健康
    PERMISSION_DENIED = "permission_denied"  # 权限不足
    SHOP_MISMATCH = "shop_mismatch"  # 店铺不匹配
    ACCOUNT_SUSPENDED = "suspended"   # 账号被封
    ACCOUNT_LOCKED = "locked"        # 账号被锁定
    VERIFICATION_REQUIRED = "verification_required"  # 需要验证
    UNKNOWN_ERROR = "unknown_error"  # 未知错误
    LOGIN_FAILED = "login_failed"    # 登录失败


class AccountHealthChecker:
    """账号健康状态检测器"""

    def __init__(self, platform: str):
        """
        初始化账号健康检测器

        Args:
            platform: 平台名称 (shopee, amazon, miaoshow等)
        """
        self.platform = platform.lower()
        self.platform_configs = self._get_platform_configs()

    def check_account_health(self, page: Page, account: Dict) -> Tuple[AccountStatus, str, Dict]:
        """
        检查账号健康状态

        Args:
            page: Playwright页面对象
            account: 账号配置信息

        Returns:
            Tuple[AccountStatus, str, Dict]: (状态, 详细信息, 额外数据)
        """
        try:
            logger.info(f"🔍 开始检测账号健康状态: {account.get('username', 'Unknown')}")

            current_url = page.url
            page_content = page.text_content('body') or ""

            # 根据平台执行相应的检测逻辑
            if self.platform == 'shopee':
                return self._check_shopee_health(page, current_url, page_content, account)
            elif self.platform == 'amazon':
                return self._check_amazon_health(page, current_url, page_content, account)
            elif self.platform == 'miaoshow':
                return self._check_miaoshow_health(page, current_url, page_content, account)
            elif self.platform in ('tiktok', 'tt', 'tiktokshop'):
                return self._check_tiktok_health(page, current_url, page_content, account)
            else:
                return self._check_generic_health(page, current_url, page_content, account)

        except Exception as e:
            logger.error(f"❌ 账号健康检测失败: {e}")
            return AccountStatus.UNKNOWN_ERROR, f"检测过程异常: {e}", {}

    def _check_shopee_health(self, page: Page, url: str, content: str, account: Dict) -> Tuple[AccountStatus, str, Dict]:
        """检查Shopee账号健康状态"""
        try:
            logger.info(f"🔍 检查Shopee账号健康状态 - URL: {url}")

            # 调试：输出页面内容的前500个字符
            content_preview = content[:500] if content else "无内容"
            logger.debug(f"📄 页面内容预览: {content_preview}...")

            # 首先检查是否是正常的后台页面
            healthy_indicators = [
                "我的商品",
                "商品管理",
                "订单管理",
                "Product Settings",
                "Mass Function",
                "全部商品",
                "上架商品",
                "违规商品",
                "已下架",
                "商品列表"
            ]

            # 检查URL是否为正常后台URL
            normal_backend_urls = [
                "/portal/product/list",
                "/portal/order",
                "/portal/marketing",
                "/portal/finance",
                "/portal/shop",
                "/portal/dashboard"
            ]

            is_normal_backend_url = any(pattern in url for pattern in normal_backend_urls)
            has_healthy_content = any(indicator in content for indicator in healthy_indicators)

            if is_normal_backend_url and has_healthy_content:
                logger.success("✅ 检测到正常后台页面，账号健康")
                return AccountStatus.HEALTHY, "账号状态正常，功能完整可用", {
                    "url": url,
                    "shop_id": self._extract_shop_id_from_url(url),
                    "features_available": [indicator for indicator in healthy_indicators if indicator in content]
                }

            # 1. 检查权限不足页面 - 更精确的检测
            permission_denied_indicators = [
                "您访问的店铺不在当前账号下",
                "您没有权限查看这个页面",
                "您没有权限访问该页面",
                "Access Denied",
                "Permission Denied"
            ]

            # 检查URL中的no-permission标识
            has_no_permission_url = "no-permission" in url
            has_permission_denied_content = any(indicator in content for indicator in permission_denied_indicators)

            if has_no_permission_url or has_permission_denied_content:
                logger.warning("⚠️ 检测到权限不足页面")
                return AccountStatus.PERMISSION_DENIED, "账号权限不足，无法访问指定店铺", {
                    "url": url,
                    "shop_id": self._extract_shop_id_from_url(url)
                }

            # 2. 检查账号被封禁
            suspension_indicators = [
                "账号已被暂停",
                "账号被封禁",
                "Account Suspended",
                "账号异常",
                "违规处理"
            ]

            if any(indicator in content for indicator in suspension_indicators):
                logger.error("🚨 检测到账号被封禁")
                return AccountStatus.ACCOUNT_SUSPENDED, "账号已被平台封禁或暂停", {"url": url}

            # 3. 检查需要验证
            verification_indicators = [
                "需要验证",
                "身份验证",
                "安全验证",
                "Verification Required",
                "请完成验证"
            ]

            if any(indicator in content for indicator in verification_indicators):
                logger.warning("🔐 检测到需要额外验证")
                return AccountStatus.VERIFICATION_REQUIRED, "账号需要完成额外验证", {"url": url}

            # 4. 如果既不是明确的权限不足，也不是正常后台，进行更详细的检查

            # 检查是否有商品数据（即使没有明确的后台标识）
            has_product_data = any(indicator in content for indicator in [
                "商品ID", "Product ID", "SKU", "库存", "价格", "销量"
            ])

            # 检查是否有Shopee卖家中心的基本元素
            has_seller_elements = any(indicator in content for indicator in [
                "卖家中心", "Seller Center", "店铺", "Shop"
            ])

            if has_product_data or has_seller_elements:
                logger.info("✅ 检测到商品数据或卖家中心元素，账号可能正常")
                return AccountStatus.HEALTHY, "账号状态正常，检测到有效数据", {
                    "url": url,
                    "shop_id": self._extract_shop_id_from_url(url)
                }

            # 5. 如果都不匹配，返回未知状态但不关闭页面
            logger.warning("❓ 无法确定账号状态，建议人工检查")
            return AccountStatus.UNKNOWN_ERROR, "无法确定账号状态，页面内容不明确，建议人工检查", {"url": url}

        except Exception as e:
            logger.error(f"❌ Shopee账号检测失败: {e}")
            return AccountStatus.UNKNOWN_ERROR, f"检测过程异常: {e}", {}

    def _check_amazon_health(self, page: Page, url: str, content: str, account: Dict) -> Tuple[AccountStatus, str, Dict]:
        """检查Amazon账号健康状态"""
        try:
            # Amazon特定的健康检测逻辑
            # 权限不足检测
            if any(indicator in content for indicator in [
                "You don't have permission",
                "Access denied",
                "权限不足"
            ]):
                return AccountStatus.PERMISSION_DENIED, "Amazon账号权限不足", {"url": url}

            # 正常状态检测
            if any(indicator in content for indicator in [
                "Seller Central",
                "Inventory",
                "Orders",
                "卖家中心"
            ]):
                return AccountStatus.HEALTHY, "Amazon账号状态正常", {"url": url}

            return AccountStatus.UNKNOWN_ERROR, "Amazon账号状态不明确", {"url": url}

        except Exception as e:
            return AccountStatus.UNKNOWN_ERROR, f"Amazon检测异常: {e}", {}

    def _check_miaoshow_health(self, page: Page, url: str, content: str, account: Dict) -> Tuple[AccountStatus, str, Dict]:
        """检查妙手ERP账号健康状态"""
        try:
            # 妙手ERP特定的健康检测逻辑
            if any(indicator in content for indicator in [
                "权限不足",
                "无权访问",
                "登录失效"
            ]):
                return AccountStatus.PERMISSION_DENIED, "妙手ERP账号权限不足", {"url": url}

            if any(indicator in content for indicator in [
                "商品管理",
                "订单管理",
                "数据分析"
            ]):
                return AccountStatus.HEALTHY, "妙手ERP账号状态正常", {"url": url}

            return AccountStatus.UNKNOWN_ERROR, "妙手ERP账号状态不明确", {"url": url}

        except Exception as e:
            return AccountStatus.UNKNOWN_ERROR, f"妙手ERP检测异常: {e}", {}
    def _check_tiktok_health(self, page: Page, url: str, content: str, account: Dict) -> Tuple[AccountStatus, str, Dict]:
        """检查TikTok卖家中心账号健康状态"""
        try:
            logger.info(f"🔍 检查TikTok账号健康状态 - URL: {url}")

            # 等待页面稳定，减少误判
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            time.sleep(0.3)

            lower_url = url.lower()

            # 明确的登录页判定
            if any(token in lower_url for token in ["/account/login", "/login", "signin", "login?"]):
                return AccountStatus.LOGIN_FAILED, "仍在登录页，未完成登录", {"url": url}

            # 域名与主页路径判定
            domain_ok = any(host in lower_url for host in [
                "seller.tiktokglobalshop.com",
                "seller.tiktokshopglobalselling.com",
            ])
            on_home = any(p in lower_url for p in ["/homepage", "/home", "/dashboard"])

            # 页面特征关键词（命中≥2视为健康）
            healthy_indicators = [
                "首页", "商品", "订单", "数据罗盘", "成长中心", "财务", "帮助中心",
                "店铺洞察", "待办事项", "店铺健康度", "Fast Dispatch Rate", "Average Response Time",
            ]
            hits = [t for t in healthy_indicators if t in content]

            # 需要验证/权限不足识别
            verification_indicators = [
                "验证码", "安全验证", "身份验证", "Two-step verification", "OTP", "请输入验证码",
            ]
            if any(t in content for t in verification_indicators):
                return AccountStatus.VERIFICATION_REQUIRED, "需要完成安全验证/验证码", {"url": url}

            permission_indicators = ["权限不足", "无权访问", "Access Denied", "Permission Denied"]
            if any(t in content for t in permission_indicators):
                return AccountStatus.PERMISSION_DENIED, "权限不足，无法访问后台", {"url": url}

            # 健康：在正确域名且处于主页/仪表盘，或命中足够多的后台元素
            if domain_ok and (on_home or len(hits) >= 2):
                return AccountStatus.HEALTHY, "TikTok账号状态正常", {
                    "url": url,
                    "features_available": hits,
                }

            # 其他情况：不明确，但不直接判失败，交给上层决定
            return AccountStatus.UNKNOWN_ERROR, "TikTok账号状态不明确，建议人工检查", {"url": url}

        except Exception as e:
            return AccountStatus.UNKNOWN_ERROR, f"TikTok检测异常: {e}", {}


    def _check_generic_health(self, page: Page, url: str, content: str, account: Dict) -> Tuple[AccountStatus, str, Dict]:
        """通用账号健康检测"""
        try:
            # 通用的权限检测
            if any(indicator in content.lower() for indicator in [
                "permission denied",
                "access denied",
                "unauthorized",
                "权限不足",
                "无权访问"
            ]):
                return AccountStatus.PERMISSION_DENIED, "账号权限不足", {"url": url}

            # 通用的登录检测
            if any(indicator in content.lower() for indicator in [
                "login",
                "signin",
                "登录",
                "登入"
            ]):
                return AccountStatus.LOGIN_FAILED, "账号未正确登录", {"url": url}

            return AccountStatus.UNKNOWN_ERROR, "无法确定账号状态", {"url": url}

        except Exception as e:
            return AccountStatus.UNKNOWN_ERROR, f"通用检测异常: {e}", {}

    def handle_unhealthy_account(self, status: AccountStatus, message: str, account: Dict, page: Page) -> bool:
        """
        处理异常账号

        Args:
            status: 账号状态
            message: 详细信息
            account: 账号配置
            page: 页面对象

        Returns:
            bool: 是否应该继续操作
        """
        account_name = account.get('username', 'Unknown')

        if status == AccountStatus.HEALTHY:
            logger.success(f"✅ 账号 {account_name} 状态正常，继续数据采集")
            return True

        # 记录异常账号
        logger.error(f"🚨 账号异常检测 - {account_name}")
        logger.error(f"   状态: {status.value}")
        logger.error(f"   详情: {message}")
        logger.error(f"   URL: {page.url}")

        # 根据不同状态采取不同处理策略
        if status in [AccountStatus.PERMISSION_DENIED, AccountStatus.SHOP_MISMATCH]:
            logger.warning(f"⚠️ 账号 {account_name} 权限不足，停止操作并关闭进程")
            self._close_account_process(page, account)
            return False

        elif status in [AccountStatus.ACCOUNT_SUSPENDED, AccountStatus.ACCOUNT_LOCKED]:
            logger.error(f"🚨 账号 {account_name} 被封禁/锁定，立即停止所有操作")
            self._close_account_process(page, account)
            self._mark_account_as_disabled(account)
            return False

        elif status == AccountStatus.VERIFICATION_REQUIRED:
            logger.warning(f"🔐 账号 {account_name} 需要验证，暂停操作")
            return False

        else:
            logger.warning(f"❓ 账号 {account_name} 状态不明确，建议人工检查")
            # 对于未知状态，不自动关闭页面，让用户决定
            if status == AccountStatus.UNKNOWN_ERROR:
                logger.info(f"💡 账号 {account_name} 状态不明确，但不自动关闭，请人工确认")
                return True  # 允许继续，让用户手动判断
            return False

    def _close_account_process(self, page: Page, account: Dict):
        """关闭账号进程，释放资源"""
        try:
            logger.info(f"🔄 正在关闭账号进程: {account.get('username', 'Unknown')}")

            # 关闭页面
            if page and not page.is_closed():
                page.close()
                logger.info("✅ 页面已关闭")

            # 可以在这里添加更多清理逻辑
            # 例如：清理临时文件、释放数据库连接等

        except Exception as e:
            logger.error(f"❌ 关闭进程失败: {e}")

    def _mark_account_as_disabled(self, account: Dict):
        """标记账号为禁用状态"""
        try:
            account_name = account.get('username', 'Unknown')
            logger.warning(f"🚫 标记账号为禁用状态: {account_name}")

            # 这里可以实现账号状态持久化
            # 例如：更新数据库、写入配置文件等

        except Exception as e:
            logger.error(f"❌ 标记账号状态失败: {e}")

    def _extract_shop_id_from_url(self, url: str) -> Optional[str]:
        """从URL中提取店铺ID"""
        try:
            if 'cnsc_shop_id=' in url:
                return url.split('cnsc_shop_id=')[1].split('&')[0]
            return None
        except:
            return None

    def _get_platform_configs(self) -> Dict:
        """获取平台配置"""
        return {
            'shopee': {
                'name': 'Shopee',
                'timeout': 30000,
                'retry_count': 3,
            },
            'amazon': {
                'name': 'Amazon',
                'timeout': 45000,
                'retry_count': 2,
            },
            'tiktok': {
                'name': 'TikTok',
                'timeout': 30000,
                'retry_count': 3,
            },
            'miaoshow': {
                'name': '妙手ERP',
                'timeout': 20000,
                'retry_count': 3,
            },
        }


# 使用示例
def create_account_health_checker(platform: str) -> AccountHealthChecker:
    """
    创建账号健康检测器实例

    Args:
        platform: 平台名称

    Returns:
        AccountHealthChecker: 健康检测器实例
    """
    return AccountHealthChecker(platform)

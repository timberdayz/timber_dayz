"""
文件路径解析和重建服务

职责：
- 从标准文件名解析元数据（平台/账号/店铺/数据域/粒度）
- 基于落盘规则重建完整文件路径
- 支持多路径搜索和文件查找
- 应用safe_slug规范化

参考：docs/guides/OUTPUTS_NAMING.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, List
import re
import unicodedata
from dataclasses import dataclass

from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedFileMetadata:
    """解析后的文件元数据"""
    timestamp: str
    account: str
    shop: str
    data_type: str
    granularity: str = "daily"
    date_range: str = ""
    platform: str = "unknown"


class FilePathResolver:
    """
    文件路径解析和重建服务
    基于文件名反向推导完整文件路径
    """
    
    # 标准路径模板
    PATH_TEMPLATE = "temp/outputs/{platform}/{account}/{shop}/{data_type}/{granularity}/{filename}"
    
    # 平台关键词映射（支持中文）
    PLATFORM_KEYWORDS = {
        'shopee': ['shopee', '虾皮', 'xiāpí'],
        'tiktok': ['tiktok', 'tik tok', 'tt'],
        'amazon': ['amazon', '亚马逊', 'amz'],
        'lazada': ['lazada'],
        'miaoshou': ['miaoshou', '妙手', 'miàoshǒu'],
    }
    
    # 数据域关键词映射
    DOMAIN_KEYWORDS = {
        'products': ['product', 'products', '商品', 'sku', 'item'],
        'orders': ['order', 'orders', '订单', 'transaction'],
        'analytics': ['analytic', 'analytics', 'traffic', '流量', '客流'],
        'finance': ['finance', '财务', 'payment', '支付', 'bill'],
        'services': ['service', 'services', '服务', 'customer'],
    }
    
    # 搜索基础目录
    SEARCH_BASE_DIRS = [
        Path('temp/outputs'),
        Path('downloads'),
        Path('data/input'),
        Path('profiles'),  # 浏览器下载目录
    ]
    
    def __init__(self):
        """初始化文件路径解析器"""
        pass
    
    def parse_filename(self, filename: str) -> Optional[ParsedFileMetadata]:
        """
        解析标准文件名格式
        
        格式：{TS}__{account}__{shop}__{data_type}__{granularity}[__{start}_{end}].xlsx
        示例：20250924_185940__虾皮巴西_东朗照明主体__the_king_s_lucky_shop__products__daily__2025-09-23_2025-09-23.xlsx
        
        Args:
            filename: 文件名（可以包含路径）
        
        Returns:
            ParsedFileMetadata对象，解析失败返回None
        """
        try:
            # 提取文件名（去除路径和扩展名）
            name = Path(filename).stem
            
            # 分割文件名
            parts = name.split('__')
            
            if len(parts) < 4:
                logger.warning(f"文件名格式不符合标准: {filename}")
                return None
            
            parsed = ParsedFileMetadata(
                timestamp=parts[0],
                account=parts[1],
                shop=parts[2],
                data_type=parts[3],
            )
            
            # 处理粒度和日期范围（如果存在）
            if len(parts) >= 5:
                # 第5部分可能是粒度或粒度+日期范围
                remaining = '__'.join(parts[4:])
                
                # 尝试匹配粒度
                granularity_match = re.match(r'(daily|weekly|monthly|snapshot|hour|manual)', remaining)
                
                if granularity_match:
                    parsed.granularity = granularity_match.group(1)
                    
                    # 提取日期范围
                    date_part = remaining[len(parsed.granularity):].strip('_')
                    if date_part:
                        parsed.date_range = date_part.replace('_', ' 到 ')
            
            # 从账号名推断平台
            parsed.platform = self._infer_platform_from_text(parsed.account)
            
            # 如果还是unknown，尝试从店铺名推断
            if parsed.platform == 'unknown':
                parsed.platform = self._infer_platform_from_text(parsed.shop)
            
            logger.debug(f"解析文件名成功: {filename} -> {parsed}")
            return parsed
            
        except Exception as e:
            logger.error(f"解析文件名失败 {filename}: {e}")
            return None
    
    def _infer_platform_from_text(self, text: str) -> str:
        """
        从文本推断平台
        
        Args:
            text: 要分析的文本（账号名或店铺名）
        
        Returns:
            平台代码，未识别返回'unknown'
        """
        text_lower = text.lower()
        
        for platform, keywords in self.PLATFORM_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return platform
        
        return 'unknown'
    
    def _infer_domain_from_text(self, text: str) -> Optional[str]:
        """
        从文本推断数据域
        
        Args:
            text: 要分析的文本
        
        Returns:
            数据域，未识别返回None
        """
        text_lower = text.lower()
        
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return domain
        
        return None
    
    def safe_slug(self, text: str) -> str:
        """
        应用safe_slug规范化
        
        参考：docs/guides/OUTPUTS_NAMING.md
        
        规则：
        - Unicode正规化：NFKD分解并去除音标；再执行NFKC
        - 小写化：统一为小写
        - 允许字符：字母、数字、-_.；其余替换为_
        - 连续下划线折叠：多个_折叠为一个
        - 去除首尾的.与_
        - 为空时回退为unknown
        
        Args:
            text: 要规范化的文本
        
        Returns:
            规范化后的文本
        """
        if not text:
            return 'unknown'
        
        # Unicode正规化
        text = unicodedata.normalize('NFKD', text)
        text = ''.join([c for c in text if not unicodedata.combining(c)])
        text = unicodedata.normalize('NFKC', text)
        
        # 小写化
        text = text.lower()
        
        # 允许字符：字母、数字、-_.
        text = re.sub(r'[^a-z0-9\-_.]', '_', text)
        
        # 连续下划线折叠
        text = re.sub(r'_+', '_', text)
        
        # 去除首尾的.和_
        text = text.strip('._')
        
        # 空值回退
        if not text:
            text = 'unknown'
        
        return text
    
    def rebuild_file_path(self, filename: str, use_slug: bool = True) -> Optional[str]:
        """
        从文件名重建完整文件路径
        
        Args:
            filename: 文件名
            use_slug: 是否对账号和店铺名应用safe_slug规范化
        
        Returns:
            完整文件路径，如果解析失败返回None
        """
        parsed = self.parse_filename(filename)
        
        if not parsed or parsed.platform == 'unknown':
            logger.warning(f"无法重建文件路径，解析失败或平台未识别: {filename}")
            return None
        
        # 应用safe_slug规范化（可选）
        if use_slug:
            account = self.safe_slug(parsed.account)
            shop = self.safe_slug(parsed.shop)
        else:
            account = parsed.account
            shop = parsed.shop
        
        # 构建路径
        path = self.PATH_TEMPLATE.format(
            platform=parsed.platform,
            account=account,
            shop=shop,
            data_type=parsed.data_type,
            granularity=parsed.granularity,
            filename=filename
        )
        
        logger.debug(f"重建文件路径: {filename} -> {path}")
        return path
    
    def verify_file_exists(self, file_path: str | Path) -> bool:
        """
        验证文件是否存在
        
        Args:
            file_path: 文件路径
        
        Returns:
            文件是否存在
        """
        return Path(file_path).exists()
    
    def find_file_locations(self, filename: str, include_slug_variants: bool = True) -> List[str]:
        """
        查找文件可能存在的所有位置
        
        优先级：
        1. 标准路径（从文件名重建）
        2. 标准路径的slug变体
        3. 递归搜索基础目录
        
        Args:
            filename: 文件名
            include_slug_variants: 是否包含slug变体
        
        Returns:
            可能的文件路径列表（按优先级排序，已验证存在）
        """
        locations = []
        
        # 1. 标准路径（从文件名重建）
        standard_path = self.rebuild_file_path(filename, use_slug=False)
        if standard_path:
            if self.verify_file_exists(standard_path):
                locations.append(standard_path)
        
        # 2. slug变体路径
        if include_slug_variants:
            slug_path = self.rebuild_file_path(filename, use_slug=True)
            if slug_path and slug_path != standard_path:
                if self.verify_file_exists(slug_path):
                    locations.append(slug_path)
        
        # 3. 如果标准路径没找到，递归搜索基础目录
        if not locations:
            logger.debug(f"标准路径未找到文件，开始递归搜索: {filename}")
            for base_dir in self.SEARCH_BASE_DIRS:
                if not base_dir.exists():
                    continue
                
                # 递归查找文件名匹配的文件
                for file_path in base_dir.rglob(filename):
                    if file_path.is_file():
                        locations.append(str(file_path.as_posix()))
                        logger.info(f"在 {base_dir} 中找到文件: {file_path}")
        
        # 去重并保持顺序
        seen = set()
        unique_locations = []
        for loc in locations:
            if loc not in seen:
                seen.add(loc)
                unique_locations.append(loc)
        
        logger.info(f"找到 {len(unique_locations)} 个文件位置: {filename}")
        return unique_locations
    
    def get_file_info(self, filename: str) -> Dict:
        """
        获取文件完整信息
        
        Args:
            filename: 文件名
        
        Returns:
            文件信息字典
        """
        # 解析文件名
        parsed = self.parse_filename(filename)
        
        # 重建文件路径
        rebuilt_path = self.rebuild_file_path(filename)
        
        # 查找所有可能的位置
        possible_locations = self.find_file_locations(filename)
        
        # 确定实际路径
        actual_path = possible_locations[0] if possible_locations else None
        
        # 获取文件大小
        file_size = None
        if actual_path:
            try:
                file_size = Path(actual_path).stat().st_size
            except Exception:
                pass
        
        return {
            "file_name": filename,
            "parsed_metadata": {
                "timestamp": parsed.timestamp if parsed else None,
                "account": parsed.account if parsed else None,
                "shop": parsed.shop if parsed else None,
                "data_type": parsed.data_type if parsed else None,
                "granularity": parsed.granularity if parsed else None,
                "date_range": parsed.date_range if parsed else None,
                "platform": parsed.platform if parsed else "unknown",
            } if parsed else {},
            "rebuilt_path": rebuilt_path,
            "actual_path": actual_path,
            "possible_locations": possible_locations,
            "file_exists": actual_path is not None,
            "file_size": file_size,
        }


# 全局单例
_resolver_instance: Optional[FilePathResolver] = None


def get_file_path_resolver() -> FilePathResolver:
    """获取文件路径解析器单例"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = FilePathResolver()
    return _resolver_instance


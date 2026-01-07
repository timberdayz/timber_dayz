#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catalog scanner - 方案B+版本

功能：
1. 扫描data/raw/目录（按年分区）
2. 从标准化文件名解析元数据
3. 读取.meta.json伴生文件补充信息
4. 写入catalog_files表（包含方案B+新字段）

改进：
- 不再扫描temp/outputs（已废弃）
- 使用StandardFileName解析（零歧义）
- 支持source_platform和sub_domain
- 支持质量评分和元数据文件
- 支持按年分区和跨年查询
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date as date_type
from pathlib import Path
from typing import List, Optional
import hashlib
import os
import re

from sqlalchemy import create_engine, select, or_
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.core.db.schema import CatalogFile
from modules.core.file_naming import StandardFileName
from modules.services.metadata_manager import MetadataManager
from modules.services.shop_resolver import get_shop_resolver
from modules.core.logger import get_logger
from modules.core.path_manager import to_relative_path  # v4.18.0: 统一路径存储格式
from modules.core.validators import (
    normalize_platform, normalize_data_domain, normalize_granularity,
    is_valid_platform, is_valid_data_domain, is_valid_granularity,
    VALID_PLATFORMS, VALID_DATA_DOMAINS, VALID_GRANULARITIES
)

logger = get_logger(__name__)

# 方案B+扫描目录（按年分区）
DEFAULT_SCAN_DIR = Path("data/raw")

SUPPORTED_EXTS = {".csv", ".xlsx", ".xls"}

# v4.3.5: 使用统一的白名单（从validators导入，避免重复维护）
KNOWN_PLATFORMS = VALID_PLATFORMS
KNOWN_DATA_DOMAINS = VALID_DATA_DOMAINS
KNOWN_GRANULARITIES = VALID_GRANULARITIES


@dataclass
class ScanResult:
    """扫描结果"""
    seen: int
    registered: int
    skipped: int
    new_file_ids: List[int] = field(default_factory=list)


def _get_engine() -> Engine:
    """
    获取数据库引擎（方案B+：优先使用PostgreSQL）
    
    优先级：
    1. DATABASE_URL环境变量（PostgreSQL优先）
    2. backend配置（Settings）
    3. SQLite兜底
    """
    # 优先级1：环境变量（PostgreSQL优先）
    url = os.getenv("DATABASE_URL")
    
    # 优先级2：backend配置
    if not url:
        try:
            from backend.utils.config import get_settings
            settings = get_settings()
            url = settings.DATABASE_URL
            logger.debug(f"使用backend配置的数据库: {url[:20]}...")
        except Exception as e:
            logger.warning(f"无法读取backend配置: {e}")
    
    # 优先级3：SQLite兜底（仅开发环境使用）
    if not url:
        from modules.core.secrets_manager import get_secrets_manager
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
        logger.warning(f"使用SQLite数据库: {url}")

    # 统一日志提示（PostgreSQL优先）
    try:
        if url.startswith('postgresql'):
            logger.info("[DB] 使用PostgreSQL（生产优先）")
        else:
            logger.info("[DB] 使用SQLite（开发环境）")
    except Exception:
        pass
    
    return create_engine(url, pool_pre_ping=True, future=True)


def _compute_sha256(file_path: Path, block_size: int = 1024 * 1024, shop_id: str = None, platform_code: str = None) -> str:
    """
    计算文件SHA256哈希（包含shop_id和platform_code）
    
    ⭐ v4.17.3修复：将shop_id和platform_code纳入hash计算，避免不同店铺/平台的相同内容文件被误判为重复
    
    Args:
        file_path: 文件路径
        block_size: 读取块大小（默认1MB）
        shop_id: 店铺ID（可选）
        platform_code: 平台代码（可选）
    
    Returns:
        SHA256哈希值（hex字符串）
    """
    h = hashlib.sha256()
    
    # ⭐ v4.17.3修复：先加入shop_id和platform_code（如果存在）
    # 这样可以区分不同店铺/平台的相同内容文件
    if shop_id:
        h.update(f"shop_id:{shop_id}".encode('utf-8'))
    if platform_code:
        h.update(f"platform:{platform_code}".encode('utf-8'))
    
    # 再加入文件内容
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    
    return h.hexdigest()


def _parse_date(date_str: str) -> Optional[date_type]:
    """解析日期字符串"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).date()
    except:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            return None


def _is_repaired_cache(file_path: Path) -> bool:
    """判断是否为自动修复缓存目录下的文件（data/raw/repaired/**）。"""
    parts = [p.lower() for p in file_path.parts]
    try:
        # 仅在 data/raw/repaired/ 目录下的缓存文件需要跳过（它们由ExcelParser自动读取，无需注册到catalog）
        repaired_idx = parts.index("repaired")
        # 确保前缀包含 data/raw
        return repaired_idx > 1 and parts[repaired_idx - 2:repaired_idx] == ["data", "raw"]
    except ValueError:
        return False


def _fallback_parse_legacy(file_path: Path) -> Optional[dict]:
    """解析遗留命名（以日期开头或双下划线分隔的老格式）。

    兼容示例：
    - 20250925_105724__xihong__xihong__orders__monthly__2025-08-27_000000_2025-09-25_235959.xls
    - 20250925_095046__xihong__xihong__products__snapshot.xlsx

    策略：
    1) 平台：优先从目录路径识别（parents中包含已知平台名）
    2) 数据域/粒度：从文件名中查找已知关键词；找不到则从路径中推断
    3) 子域：如包含 agent/ai_assistant 也能识别
    4) 账号/店铺：若匹配到旧格式，则提取第2、3段作为 account/shop_id
    """
    stem = file_path.stem

    # 平台：从路径 parents 兜底识别
    source_platform = "unknown"
    for parent in file_path.parents:
        name = parent.name.lower()
        if name in KNOWN_PLATFORMS:
            source_platform = name
            break

    # 先尝试通过双下划线格式拆分
    # 形如：YYYYMMDD_HHMMSS__account__shop__domain__granularity__...
    account = None
    shop_id = None
    domain = None
    granularity = None
    sub_domain = ""

    legacy_parts = stem.split("__")
    if len(legacy_parts) >= 4 and re.fullmatch(r"\d{8}_\d{6}", legacy_parts[0]):
        # 提取账号与店铺
        account = legacy_parts[1] or None
        shop_id = legacy_parts[2] or None
        # 解析数据域与粒度（如果存在）
        if len(legacy_parts) >= 5:
            domain = legacy_parts[3].lower()
            # 兼容 services 子域
            if domain == "services" and len(legacy_parts) >= 6 and legacy_parts[4] in {"agent", "ai_assistant", "ai"}:
                sub_domain = legacy_parts[4]
                if len(legacy_parts) >= 7:
                    granularity = legacy_parts[5].lower()
            else:
                granularity = legacy_parts[4].lower() if len(legacy_parts) >= 5 else None

    # 如仍缺失，从文件名整体字符串里搜索已知关键词
    lower_stem = stem.lower()
    if not domain:
        for d in KNOWN_DATA_DOMAINS:
            if f"_{d}_" in lower_stem or f"__{d}__" in lower_stem:
                domain = d
                break
    if not granularity:
        for g in KNOWN_GRANULARITIES:
            if f"_{g}_" in lower_stem or f"__{g}__" in lower_stem:
                granularity = g
                break

    # 若仍缺失，从路径中再兜底一次
    if not domain:
        for parent in file_path.parents:
            name = parent.name.lower()
            if name in KNOWN_DATA_DOMAINS:
                domain = name
                break
    if not granularity:
        for parent in file_path.parents:
            name = parent.name.lower()
            if name in KNOWN_GRANULARITIES:
                granularity = name
                break

    # 必须识别出 data_domain 与 granularity 才认为有效
    if not domain or not granularity:
        return None

    return {
        'source_platform': source_platform,
        'data_domain': domain,
        'granularity': granularity,
        'sub_domain': sub_domain,
        'account': account,
        'shop_id': shop_id,
    }


def scan_and_register(base_dir: str = "data/raw") -> ScanResult:
    """
    扫描data/raw目录并注册到catalog_files
    
    v4.3.5特点：
    1. 目录白名单：仅扫描data/raw/YYYY/（年份分区）
    2. 跳过修复缓存：data/raw/repaired/**
    3. 从标准化文件名解析元数据（极简）
    4. 读取.meta.json补充信息（date_from/to, quality_score）
    5. 幂等性：基于file_hash去重
    6. 强制小写化 + 白名单校验
    
    Args:
        base_dir: 扫描基础目录（默认data/raw）
        
    Returns:
        ScanResult: 扫描结果统计
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        logger.warning(f"扫描目录不存在: {base_path}")
        return ScanResult(seen=0, registered=0, skipped=0)
    
    logger.info(f"开始扫描: {base_path}")
    logger.info(f"  [白名单] 平台: {', '.join(sorted(VALID_PLATFORMS))}")
    logger.info(f"  [白名单] 数据域: {', '.join(sorted(VALID_DATA_DOMAINS))}")
    logger.info(f"  [白名单] 粒度: {', '.join(sorted(VALID_GRANULARITIES))}")
    
    engine = _get_engine()
    session = Session(engine)
    
    seen = 0
    registered = 0
    skipped = 0
    new_file_ids: List[int] = []
    
    try:
        # v4.3.5: 目录白名单 - 仅扫描data/raw/YYYY/年份分区
        year_dirs = []
        for item in base_path.iterdir():
            if item.is_dir() and re.fullmatch(r'20\d{2}', item.name):
                year_dirs.append(item)
        
        if not year_dirs:
            logger.warning(f"未找到年份分区目录（格式: YYYY），尝试扫描整个目录")
            year_dirs = [base_path]  # 兜底：扫描整个目录
        else:
            logger.info(f"  [目录白名单] 发现 {len(year_dirs)} 个年份分区: {', '.join([d.name for d in year_dirs])}")
        
        # 递归扫描年份目录
        for year_dir in year_dirs:
            for file_path in year_dir.rglob("*.*"):
                # 跳过元数据文件
                if file_path.suffix == '.json':
                    continue
                
                # 只处理支持的格式
                if file_path.suffix.lower() not in SUPPORTED_EXTS:
                    continue

                # 跳过自动修复缓存文件（data/raw/repaired/**）
                if _is_repaired_cache(file_path):
                    continue
                
                seen += 1
                
                try:
                    # 1. 从文件名解析基础元数据（方案B+核心）
                    use_legacy = False
                    file_metadata = None
                    try:
                        file_metadata = StandardFileName.parse(file_path.name)
                        # 若解析结果不在已知域/粒度集合内，则判为遗留命名
                        if (
                            file_metadata.get('data_domain') not in KNOWN_DATA_DOMAINS or
                            file_metadata.get('granularity') not in KNOWN_GRANULARITIES or
                            re.fullmatch(r"\d{8}", str(file_metadata.get('source_platform', '')))
                        ):
                            use_legacy = True
                    except Exception:
                        use_legacy = True

                    if use_legacy:
                        legacy = _fallback_parse_legacy(file_path)
                        if not legacy:
                            logger.warning(f"不符合命名规范且无法解析，已跳过: {file_path.name}")
                            skipped += 1
                            continue
                        file_metadata = {
                            'source_platform': legacy['source_platform'],
                            'data_domain': legacy['data_domain'],
                            'sub_domain': legacy.get('sub_domain', ''),
                            'granularity': legacy['granularity'],
                        }
                    
                    # 2. 读取.meta.json补充信息
                    meta_file = file_path.with_suffix('.meta.json')
                    quality_score = None
                    date_from = None
                    date_to = None
                    
                    # 用于传递给ShopResolver的元数据
                    meta_for_resolver = {}
                    
                    if meta_file.exists():
                        try:
                            meta_content = MetadataManager.read_meta_file(meta_file)
                            
                            # 提取质量分数
                            quality_data = meta_content.get('data_quality', {})
                            quality_score = quality_data.get('quality_score')
                            
                            # 提取日期范围
                            biz_meta = meta_content.get('business_metadata', {})
                            date_from = _parse_date(biz_meta.get('date_from'))
                            date_to = _parse_date(biz_meta.get('date_to'))
                            
                            # ⭐ 提取账号和店铺信息（collection_info）
                            collection_info = meta_content.get('collection_info', {})
                            meta_account = collection_info.get('account')
                            meta_shop_id = collection_info.get('shop_id')
                            
                            # ⭐ v4.17.0修复：对于miaoshou平台的inventory和orders数据域，统一shop_id
                            # 检测并统一处理包含日期的shop_id（如 products_snapshot_20250926）
                            if meta_shop_id and file_metadata:
                                # 提前计算norm_platform和norm_domain用于判断
                                temp_norm_platform = normalize_platform(file_metadata.get('source_platform', ''))
                                temp_norm_domain = normalize_data_domain(file_metadata.get('data_domain', ''))
                                
                                # 检测是否包含日期格式或snapshot关键字
                                shop_id_str = str(meta_shop_id)
                                has_date_pattern = bool(re.search(r'\d{8}', shop_id_str))
                                has_snapshot = '_snapshot_' in shop_id_str.lower()
                                
                                # 如果是miaoshou平台的inventory或orders数据域，且shop_id包含日期，统一为'none'
                                if (temp_norm_platform == 'miaoshou' and 
                                    temp_norm_domain in ['inventory', 'orders'] and 
                                    (has_date_pattern or has_snapshot)):
                                    logger.warning(
                                        f"[CatalogScanner] [v4.17.0] 检测到shop_id包含日期或snapshot: {meta_shop_id}，"
                                        f"统一为固定值 'none'（避免去重失败）"
                                    )
                                    meta_shop_id = 'none'
                            
                            # 传递给ShopResolver（优先级最高，直接覆盖）
                            if meta_shop_id:
                                meta_for_resolver['shop_id'] = str(meta_shop_id)
                            if meta_account:
                                meta_for_resolver['account'] = str(meta_account)
                            
                            # 如果date_from/date_to未提取，尝试从original_path解析
                            if not date_from or not date_to:
                                original_path = collection_info.get('original_path', '')
                                # 示例: "...\\20250918_163152__tiktok_2店__tiktok_2店_sg__services__monthly__2025-08-21_2025-09-18.xlsx"
                                date_range_match = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', original_path)
                                if date_range_match:
                                    date_from = _parse_date(date_range_match.group(1))
                                    date_to = _parse_date(date_range_match.group(2))
                            
                            logger.debug(f"读取元数据: {file_path.name}, shop_id={meta_shop_id}, account={meta_account}, date: {date_from} ~ {date_to}")
                            
                        except Exception as e:
                            logger.warning(f"读取元数据文件失败 {meta_file}: {e}")
                    else:
                        # 遗留场景：如果无法读取到.meta.json而legacy解析得到账号/店铺，则补充
                        if use_legacy:
                            legacy = locals().get('legacy')  # 已在上面解析
                            if legacy:
                                if legacy.get('account'):
                                    meta_for_resolver['account'] = legacy['account']
                                if legacy.get('shop_id'):
                                    meta_for_resolver['shop_id'] = legacy['shop_id']
                    
                    # 3. 解析店铺归属（全域智能解析）- ⭐ v4.17.3修复：先解析店铺归属，再计算hash
                    resolver = get_shop_resolver()
                    # 如果.meta.json提供了shop_id，直接以最高置信度使用，不再推断
                    if meta_for_resolver.get('shop_id'):
                        resolved_shop = type('RS', (), {
                            'shop_id': meta_for_resolver['shop_id'],
                            'confidence': 1.0,
                            'source': '.meta.json',
                            'detail': '来自伴生元数据文件'
                        })()
                    else:
                        resolved_shop = resolver.resolve(
                            file_path=str(file_path),
                            platform_code=file_metadata['source_platform'],
                            file_metadata=meta_for_resolver  # ⭐ 传递.meta.json中的shop_id/account
                        )
                    
                    # 决定初始状态：高置信度直接写shop_id并保持pending；低置信度标记needs_shop
                    initial_shop_id = None
                    initial_status = 'pending'
                    shop_resolution_meta = {
                        'confidence': resolved_shop.confidence,
                        'source': resolved_shop.source,
                        'detail': resolved_shop.detail
                    }
                    
                    # v4.3.6: miaoshou平台特殊处理需要提前计算norm_platform
                    norm_platform = normalize_platform(file_metadata['source_platform'])
                    # ⭐ 需要提前计算norm_domain（用于判断订单和库存数据域）
                    norm_domain = normalize_data_domain(file_metadata.get('data_domain', ''))
                    
                    # ⭐ v4.18.1重构：简化shop_id逻辑
                    # 规则：shop_id完全从伴生JSON文件获取，如果没有则设为'none'
                    # 移除needs_shop状态，所有文件都可以直接同步
                    if resolved_shop.shop_id:
                        initial_shop_id = resolved_shop.shop_id
                        initial_status = 'pending'
                        logger.debug(f"[{file_path.name}] 从.meta.json获取shop_id: {initial_shop_id}")
                    else:
                        # 没有shop_id时，设为'none'（而非需要人工指派）
                        initial_shop_id = 'none'
                        initial_status = 'pending'
                        logger.info(f"[{file_path.name}] .meta.json无shop_id，设为'none'")
                    
                    # 3.5. ⭐ v4.17.3修复：计算文件哈希（包含shop_id和platform_code）
                    # 这样可以区分不同店铺/平台的相同内容文件
                    file_hash = _compute_sha256(
                        file_path,
                        shop_id=initial_shop_id,
                        platform_code=norm_platform
                    )
                    
                    # 4. 标准化与校验（v4.3.5: 强制小写化 + 白名单）
                    # norm_platform和norm_domain已在上面计算
                    norm_granularity = normalize_granularity(file_metadata['granularity'])
                    norm_sub_domain = file_metadata.get('sub_domain', '').lower().strip()
                    
                    # ⭐ 新增：services数据域，如果sub_domain为空，默认设置为'agent'（适用于所有平台）
                    if norm_domain == 'services' and not norm_sub_domain:
                        norm_sub_domain = 'agent'
                        logger.info(f"[{file_path.name}] services数据域缺少sub_domain，自动设置为'agent'")
                    
                    # 白名单校验（严格模式）
                    if not is_valid_platform(norm_platform):
                        logger.warning(f"跳过无效平台: {file_path.name} (platform={norm_platform})")
                        skipped += 1
                        continue
                    
                    if not is_valid_data_domain(norm_domain):
                        logger.warning(f"跳过无效数据域: {file_path.name} (domain={norm_domain})")
                        skipped += 1
                        continue
                    
                    if not is_valid_granularity(norm_granularity):
                        logger.warning(f"跳过无效粒度: {file_path.name} (granularity={norm_granularity})")
                        skipped += 1
                        continue
                    
                    # 5. 创建catalog记录
                    # v4.18.0: 使用统一的相对路径存储格式（云端部署兼容）
                    relative_file_path = to_relative_path(file_path)
                    relative_meta_path = to_relative_path(meta_file) if meta_file.exists() else None
                    
                    catalog = CatalogFile(
                        file_path=relative_file_path,  # v4.18.0: 存储相对路径
                        file_name=file_path.name,
                        file_size=file_path.stat().st_size,
                        file_hash=file_hash,
                        source="data/raw",  # 新的数据源标识
                        
                        # v4.3.5: 强制小写化后的字段
                        source_platform=norm_platform,
                        data_domain=norm_domain,
                        sub_domain=norm_sub_domain,
                        granularity=norm_granularity,
                        
                        # ⭐ 账号和店铺归属（从.meta.json提取）
                        account=meta_for_resolver.get('account'),
                        shop_id=initial_shop_id,
                        
                        # 时间范围（从.meta.json读取）
                        date_from=date_from,
                        date_to=date_to,
                        
                        # 方案B+数据治理字段
                        storage_layer='raw',
                        quality_score=quality_score,
                        meta_file_path=relative_meta_path,  # v4.18.0: 存储相对路径
                        file_metadata={'shop_resolution': shop_resolution_meta},
                        
                        # 兼容性字段 - v4.3.5: 同样小写化
                        platform_code=norm_platform,
                        
                        # 状态（基于店铺解析结果）
                        status=initial_status,
                        first_seen_at=datetime.now()
                    )
                    
                    # 6. Upsert（基于file_hash和file_path双重去重）
                    # ⭐ v4.17.3修复：增强去重机制，同时检查file_hash和file_path
                    # ⭐ v4.18.0修复：使用相对路径匹配，保持与存储格式一致，确保云端迁移兼容
                    existing = session.execute(
                        select(CatalogFile).where(
                            or_(
                                CatalogFile.file_hash == file_hash,
                                CatalogFile.file_path == relative_file_path
                            )
                        )
                    ).scalar_one_or_none()
                    
                    if existing:
                        # 更新现有记录（文件可能被移动）- v4.3.5: 同样强制小写化
                        # v4.18.0: 更新为相对路径格式
                        existing.file_path = relative_file_path
                        existing.file_name = file_path.name
                        existing.source_platform = norm_platform
                        existing.data_domain = norm_domain
                        existing.sub_domain = norm_sub_domain
                        existing.granularity = norm_granularity
                        existing.platform_code = norm_platform  # v4.3.5: 兼容性字段同步
                        existing.storage_layer = 'raw'
                        existing.quality_score = quality_score
                        existing.meta_file_path = relative_meta_path  # v4.18.0: 存储相对路径
                        
                        # ⭐ 账号信息更新（从.meta.json提取）
                        if meta_for_resolver.get('account'):
                            existing.account = meta_for_resolver['account']

                        # 店铺归属更新策略（v4.3.5 修复）：
                        # 1) 若 .meta.json 提供 shop_id → 无条件覆盖，置信度1.0
                        # 2) 否则：若当前解析得到的置信度更高，或原值为空 → 覆盖
                        existing_meta = existing.file_metadata or {}
                        prev_resolution = existing_meta.get('shop_resolution', {}) if isinstance(existing_meta, dict) else {}
                        prev_confidence = prev_resolution.get('confidence', 0) if isinstance(prev_resolution, dict) else 0

                        # ⭐ v4.17.0修复：在更新记录时也应用shop_id修复逻辑
                        final_shop_id = None
                        if meta_for_resolver.get('shop_id'):
                            # meta_for_resolver中的shop_id已经经过修复处理（第356-376行）
                            final_shop_id = str(meta_for_resolver['shop_id'])
                        elif initial_shop_id:
                            # 对于initial_shop_id，也需要检查并修复
                            shop_id_str = str(initial_shop_id)
                            has_date_pattern = bool(re.search(r'\d{8}', shop_id_str))
                            has_snapshot = '_snapshot_' in shop_id_str.lower()
                            if (norm_platform == 'miaoshou' and 
                                norm_domain in ['inventory', 'orders'] and 
                                (has_date_pattern or has_snapshot)):
                                logger.warning(
                                    f"[CatalogScanner] [v4.17.0] 更新记录时检测到shop_id包含日期: {initial_shop_id}，"
                                    f"统一为固定值 'none'（避免去重失败）"
                                )
                                final_shop_id = 'none'
                            else:
                                final_shop_id = initial_shop_id
                        
                        if final_shop_id:
                            existing.shop_id = final_shop_id
                            existing_meta = existing_meta if isinstance(existing_meta, dict) else {}
                            if meta_for_resolver.get('shop_id'):
                                existing_meta['shop_resolution'] = {
                                    'confidence': 1.0,
                                    'source': '.meta.json',
                                    'detail': '伴生元数据优先覆盖',
                                }
                            else:
                                existing_meta['shop_resolution'] = shop_resolution_meta
                            existing.file_metadata = existing_meta
                        else:
                            # 没有.meta.json提供shop_id时，按置信度规则更新
                            if initial_shop_id and (not existing.shop_id or prev_confidence < shop_resolution_meta.get('confidence', 0)):
                                existing.shop_id = initial_shop_id
                                existing_meta = existing_meta if isinstance(existing_meta, dict) else {}
                                existing_meta['shop_resolution'] = shop_resolution_meta
                                existing.file_metadata = existing_meta
                        
                        # 状态更新：若之前是needs_shop且现在解析到了，则改为pending
                        if existing.status == 'needs_shop' and initial_shop_id:
                            existing.status = 'pending'
                        elif not initial_shop_id and existing.status == 'pending':
                            existing.status = 'needs_shop'
                        
                        # ⭐ v4.17.3修复：更新file_hash（如果hash计算方式改变）
                        if existing.file_hash != file_hash:
                            logger.info(f"[CatalogScanner] [v4.17.3] 更新file_hash: {file_path.name} (旧hash: {existing.file_hash[:16] if existing.file_hash else 'None'}..., 新hash: {file_hash[:16]}...)")
                            existing.file_hash = file_hash
                        
                        logger.debug(f"更新: {file_path.name}")
                    else:
                        # 新记录
                        session.add(catalog)
                        session.flush()  # 确保获取主键ID
                        if catalog.id is not None:
                            new_file_ids.append(catalog.id)
                        logger.debug(f"注册: {file_path.name}")
                        
                        # ⭐ v4.17.0新增：文件注册时确保对应的表存在
                        try:
                            from backend.services.platform_table_manager import get_platform_table_manager
                            table_manager = get_platform_table_manager(session)
                            table_name = table_manager.ensure_table_exists(
                                platform=norm_platform or '',
                                data_domain=norm_domain or '',
                                sub_domain=norm_sub_domain,
                                granularity=norm_granularity or ''
                            )
                            logger.debug(f"[CatalogScanner] 确保表存在: {table_name}")
                        except Exception as table_error:
                            # 表创建失败不影响文件注册（数据入库时会再次尝试创建）
                            logger.warning(
                                f"[CatalogScanner] 创建表失败（继续）: {table_error}",
                                exc_info=True
                            )
                    
                    registered += 1
                    
                except Exception as e:
                    logger.warning(f"跳过文件 {file_path.name}: {e}")
                    skipped += 1
        
        # 提交事务
        session.commit()
        logger.info(f"扫描完成: 发现{seen}个文件, 注册{registered}个, 跳过{skipped}个")
        
        return ScanResult(seen=seen, registered=registered, skipped=skipped, new_file_ids=new_file_ids)

    except Exception as e:
        session.rollback()
        logger.error(f"扫描失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


def scan_legacy_outputs() -> ScanResult:
    """
    扫描旧的temp/outputs目录（兼容性）
    
    警告：此函数已废弃，请先执行文件迁移脚本
    """
    logger.warning("scan_legacy_outputs已废弃，请使用migrate_legacy_files.py迁移文件")
    return ScanResult(seen=0, registered=0, skipped=0)


def register_single_file(file_path: str) -> Optional[int]:
    """
    注册单个文件到 catalog_files 表
    
    v4.12.0新增（Phase 0 - 数据采集器自动注册）：
    - 用于数据采集器下载文件后自动注册
    - 只注册指定文件，不扫描整个目录
    - 复用 scan_and_register() 中的文件处理逻辑
    
    Args:
        file_path: 文件路径（绝对路径或相对路径）
        
    Returns:
        Optional[int]: 注册成功返回文件ID，失败或已存在返回None
    """
    file_path_obj = Path(file_path)
    
    if not file_path_obj.exists():
        logger.warning(f"文件不存在，无法注册: {file_path}")
        return None
    
    # 检查文件格式
    if file_path_obj.suffix.lower() not in SUPPORTED_EXTS:
        logger.warning(f"不支持的文件格式: {file_path} (扩展名: {file_path_obj.suffix})")
        return None
    
    # 跳过修复缓存文件
    if _is_repaired_cache(file_path_obj):
        logger.debug(f"跳过修复缓存文件: {file_path}")
        return None
    
    engine = _get_engine()
    session = Session(engine)
    
    try:
        # 1. 从文件名解析基础元数据（复用scan_and_register的逻辑）
        use_legacy = False
        file_metadata = None
        legacy = None  # 初始化legacy变量
        
        try:
            file_metadata = StandardFileName.parse(file_path_obj.name)
            # 若解析结果不在已知域/粒度集合内，则判为遗留命名
            if (
                file_metadata.get('data_domain') not in KNOWN_DATA_DOMAINS or
                file_metadata.get('granularity') not in KNOWN_GRANULARITIES or
                re.fullmatch(r"\d{8}", str(file_metadata.get('source_platform', '')))
            ):
                use_legacy = True
        except Exception:
            use_legacy = True

        if use_legacy:
            legacy = _fallback_parse_legacy(file_path_obj)
            if not legacy:
                logger.warning(f"不符合命名规范且无法解析，已跳过: {file_path_obj.name}")
                return None
            file_metadata = {
                'source_platform': legacy['source_platform'],
                'data_domain': legacy['data_domain'],
                'sub_domain': legacy.get('sub_domain', ''),
                'granularity': legacy['granularity'],
            }
        
        # 2. 读取.meta.json补充信息
        meta_file = file_path_obj.with_suffix('.meta.json')
        quality_score = None
        date_from = None
        date_to = None
        meta_for_resolver = {}
        
        if meta_file.exists():
            try:
                meta_content = MetadataManager.read_meta_file(meta_file)
                quality_data = meta_content.get('data_quality', {})
                quality_score = quality_data.get('quality_score')
                biz_meta = meta_content.get('business_metadata', {})
                date_from = _parse_date(biz_meta.get('date_from'))
                date_to = _parse_date(biz_meta.get('date_to'))
                collection_info = meta_content.get('collection_info', {})
                meta_account = collection_info.get('account')
                meta_shop_id = collection_info.get('shop_id')
                if meta_shop_id:
                    meta_for_resolver['shop_id'] = str(meta_shop_id)
                if meta_account:
                    meta_for_resolver['account'] = str(meta_account)
                if not date_from or not date_to:
                    original_path = collection_info.get('original_path', '')
                    date_range_match = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', original_path)
                    if date_range_match:
                        date_from = _parse_date(date_range_match.group(1))
                        date_to = _parse_date(date_range_match.group(2))
            except Exception as e:
                logger.warning(f"读取元数据文件失败 {meta_file}: {e}")
        else:
            # 遗留场景：如果无法读取到.meta.json而legacy解析得到账号/店铺，则补充
            if use_legacy and legacy:
                if legacy.get('account'):
                    meta_for_resolver['account'] = legacy['account']
                if legacy.get('shop_id'):
                    meta_for_resolver['shop_id'] = legacy['shop_id']
        
        # 3. ⭐ v4.17.3修复：先解析店铺归属，再计算hash
        resolver = get_shop_resolver()
        if meta_for_resolver.get('shop_id'):
            resolved_shop = type('RS', (), {
                'shop_id': meta_for_resolver['shop_id'],
                'confidence': 1.0,
                'source': '.meta.json',
                'detail': '来自伴生元数据文件'
            })()
        else:
            resolved_shop = resolver.resolve(
                file_path=str(file_path_obj),
                platform_code=file_metadata['source_platform'],
                file_metadata=meta_for_resolver
            )
        
        # 4. 决定初始状态
        initial_shop_id = None
        initial_status = 'pending'
        shop_resolution_meta = {
            'confidence': resolved_shop.confidence,
            'source': resolved_shop.source,
            'detail': resolved_shop.detail
        }
        norm_platform = normalize_platform(file_metadata['source_platform'])
        
        # ⭐ 需要先获取norm_domain（在判断之前）
        norm_domain = normalize_data_domain(file_metadata.get('data_domain', ''))
        
        # ⭐ v4.18.1重构：简化shop_id逻辑
        # 规则：shop_id完全从伴生JSON文件获取，如果没有则设为'none'
        # 移除needs_shop状态，所有文件都可以直接同步
        if resolved_shop.shop_id:
            initial_shop_id = resolved_shop.shop_id
            initial_status = 'pending'
            logger.debug(f"[{file_path_obj.name}] 从.meta.json获取shop_id: {initial_shop_id}")
        else:
            # 没有shop_id时，设为'none'（而非需要人工指派）
            initial_shop_id = 'none'
            initial_status = 'pending'
            logger.info(f"[{file_path_obj.name}] .meta.json无shop_id，设为'none'")
        
        # 5. ⭐ v4.17.3修复：计算文件哈希（包含shop_id和platform_code）
        # 这样可以区分不同店铺/平台的相同内容文件
        file_hash = _compute_sha256(
            file_path_obj,
            shop_id=initial_shop_id,
            platform_code=norm_platform
        )
        
        # 6. 标准化与校验
        norm_domain = normalize_data_domain(file_metadata['data_domain'])
        norm_granularity = normalize_granularity(file_metadata['granularity'])
        norm_sub_domain = file_metadata.get('sub_domain', '').lower().strip()
        
        # ⭐ 新增：services数据域，如果sub_domain为空，默认设置为'agent'（适用于所有平台）
        if norm_domain == 'services' and not norm_sub_domain:
            norm_sub_domain = 'agent'
            logger.info(f"[{file_path_obj.name}] services数据域缺少sub_domain，自动设置为'agent'")
        
        if not is_valid_platform(norm_platform):
            logger.warning(f"跳过无效平台: {file_path_obj.name} (platform={norm_platform})")
            return None
        if not is_valid_data_domain(norm_domain):
            logger.warning(f"跳过无效数据域: {file_path_obj.name} (domain={norm_domain})")
            return None
        if not is_valid_granularity(norm_granularity):
            logger.warning(f"跳过无效粒度: {file_path_obj.name} (granularity={norm_granularity})")
            return None
        
        # 7. 检查是否已存在（基于file_hash和file_path双重去重）
        # ⭐ v4.17.3修复：增强去重机制，同时检查file_hash和file_path
        # ⭐ v4.18.0修复：使用相对路径匹配，保持与存储格式一致，确保云端迁移兼容
        relative_file_path = to_relative_path(file_path_obj)
        relative_meta_path = to_relative_path(meta_file) if meta_file.exists() else None
        
        existing = session.execute(
            select(CatalogFile).where(
                or_(
                    CatalogFile.file_hash == file_hash,
                    CatalogFile.file_path == relative_file_path
                )
            )
        ).scalar_one_or_none()
        
        if existing:
            # 更新现有记录
            # v4.18.0: 更新为相对路径格式
            existing.file_path = relative_file_path
            existing.file_name = file_path_obj.name
            existing.source_platform = norm_platform
            existing.data_domain = norm_domain
            existing.sub_domain = norm_sub_domain
            existing.granularity = norm_granularity
            existing.platform_code = norm_platform
            existing.storage_layer = 'raw'
            existing.quality_score = quality_score
            existing.meta_file_path = relative_meta_path  # v4.18.0: 存储相对路径
            if meta_for_resolver.get('account'):
                existing.account = meta_for_resolver['account']
            
            existing_meta = existing.file_metadata or {}
            prev_resolution = existing_meta.get('shop_resolution', {}) if isinstance(existing_meta, dict) else {}
            prev_confidence = prev_resolution.get('confidence', 0) if isinstance(prev_resolution, dict) else 0
            
            # ⭐ v4.17.0修复：在更新记录时也应用shop_id修复逻辑
            final_shop_id = None
            if meta_for_resolver.get('shop_id'):
                # meta_for_resolver中的shop_id已经经过修复处理
                final_shop_id = str(meta_for_resolver['shop_id'])
            elif initial_shop_id:
                # 对于initial_shop_id，也需要检查并修复
                shop_id_str = str(initial_shop_id)
                has_date_pattern = bool(re.search(r'\d{8}', shop_id_str))
                has_snapshot = '_snapshot_' in shop_id_str.lower()
                if (norm_platform == 'miaoshou' and 
                    norm_domain in ['inventory', 'orders'] and 
                    (has_date_pattern or has_snapshot)):
                    logger.warning(
                        f"[AutoRegister] [v4.17.0] 更新记录时检测到shop_id包含日期: {initial_shop_id}，"
                        f"统一为固定值 'none'（避免去重失败）"
                    )
                    final_shop_id = 'none'
                else:
                    final_shop_id = initial_shop_id
            
            if final_shop_id:
                existing.shop_id = final_shop_id
                existing_meta = existing_meta if isinstance(existing_meta, dict) else {}
                if meta_for_resolver.get('shop_id'):
                    existing_meta['shop_resolution'] = {
                        'confidence': 1.0,
                        'source': '.meta.json',
                        'detail': '伴生元数据优先覆盖',
                    }
                else:
                    existing_meta['shop_resolution'] = shop_resolution_meta
                existing.file_metadata = existing_meta
            else:
                if initial_shop_id and (not existing.shop_id or prev_confidence < shop_resolution_meta.get('confidence', 0)):
                    existing.shop_id = initial_shop_id
                    existing_meta = existing_meta if isinstance(existing_meta, dict) else {}
                    existing_meta['shop_resolution'] = shop_resolution_meta
                    existing.file_metadata = existing_meta
            
            if existing.status == 'needs_shop' and initial_shop_id:
                existing.status = 'pending'
            elif not initial_shop_id and existing.status == 'pending':
                existing.status = 'needs_shop'
            
            # ⭐ v4.17.3修复：更新file_hash（如果hash计算方式改变）
            if existing.file_hash != file_hash:
                logger.info(f"[AutoRegister] [v4.17.3] 更新file_hash: {file_path_obj.name} (旧hash: {existing.file_hash[:16] if existing.file_hash else 'None'}..., 新hash: {file_hash[:16]}...)")
                existing.file_hash = file_hash
            
            session.commit()
            logger.info(f"[AutoRegister] 更新已存在文件: {file_path_obj.name} (ID: {existing.id})")
            return existing.id
        else:
            # 创建新记录
            # v4.18.0: 使用统一的相对路径存储格式（云端部署兼容）
            catalog = CatalogFile(
                file_path=relative_file_path,  # v4.18.0: 存储相对路径
                file_name=file_path_obj.name,
                file_size=file_path_obj.stat().st_size,
                file_hash=file_hash,
                source="data/raw",
                source_platform=norm_platform,
                data_domain=norm_domain,
                sub_domain=norm_sub_domain,
                granularity=norm_granularity,
                account=meta_for_resolver.get('account'),
                shop_id=initial_shop_id,
                date_from=date_from,
                date_to=date_to,
                storage_layer='raw',
                quality_score=quality_score,
                meta_file_path=relative_meta_path,  # v4.18.0: 存储相对路径
                file_metadata={'shop_resolution': shop_resolution_meta},
                platform_code=norm_platform,
                status=initial_status,
                first_seen_at=datetime.now()
            )
            session.add(catalog)
            session.flush()
            file_id = catalog.id
            
            # ⭐ v4.17.0新增：文件注册时确保对应的表存在
            try:
                from backend.services.platform_table_manager import get_platform_table_manager
                table_manager = get_platform_table_manager(session)
                table_name = table_manager.ensure_table_exists(
                    platform=norm_platform or '',
                    data_domain=norm_domain or '',
                    sub_domain=norm_sub_domain,
                    granularity=norm_granularity or ''
                )
                logger.debug(f"[AutoRegister] 确保表存在: {table_name}")
            except Exception as table_error:
                # 表创建失败不影响文件注册（数据入库时会再次尝试创建）
                logger.warning(
                    f"[AutoRegister] 创建表失败（继续）: {table_error}",
                    exc_info=True
                )
            
            session.commit()
            logger.info(f"[AutoRegister] 成功注册文件: {file_path_obj.name} (ID: {file_id})")
            return file_id
            
    except Exception as e:
        session.rollback()
        logger.error(f"[AutoRegister] 注册文件失败 {file_path}: {e}", exc_info=True)
        return None
    finally:
        session.close()


# 便捷函数
def scan_files(base_dir: str = "data/raw") -> ScanResult:
    """便捷函数：扫描文件"""
    return scan_and_register(base_dir)

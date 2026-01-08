#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动入库编排服务

v4.5.0新增：
- 编排自动入库流程
- 复用现有的preview和ingest接口
- 不重复实现验证、入库、隔离逻辑
- 支持批量处理和进度跟踪
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from datetime import datetime, timedelta, timezone
import uuid

from modules.core.db import CatalogFile
from modules.core.logger import get_logger
from backend.services.template_matcher import get_template_matcher
from backend.services.excel_parser import ExcelParser
from backend.services.progress_tracker import progress_tracker
from backend.services.c_class_data_validator import get_c_class_data_validator
from datetime import date
import httpx

logger = get_logger(__name__)


class AutoIngestOrchestrator:
    """
    自动入库编排服务
    
    职责：
    - 编排流程（查找模板 -> 预览文件 -> 应用模板 -> 调用ingest）
    - 不重复实现（复用现有服务）
    - 并发控制（状态机）
    - 进度跟踪（复用progress_tracker）
    """
    
    def __init__(self, db: AsyncSession):
        """
        [*] v4.18.2修复：支持 AsyncSession
        [*] v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
        self.template_matcher = get_template_matcher(db)
        self.progress_tracker = progress_tracker

    @staticmethod
    def _touch_auto_meta(catalog_file: CatalogFile) -> tuple[Dict[str, Any], Dict[str, Any]]:
        meta = catalog_file.file_metadata if isinstance(catalog_file.file_metadata, dict) else {}
        auto_meta = meta.get("auto_ingest")
        if not isinstance(auto_meta, dict):
            auto_meta = {}
        return meta, auto_meta

    def _save_auto_meta(self, catalog_file: CatalogFile, meta: Dict[str, Any], auto_meta: Dict[str, Any]) -> None:
        meta["auto_ingest"] = auto_meta
        catalog_file.file_metadata = meta

    def _record_attempt(self, catalog_file: CatalogFile) -> None:
        meta, auto_meta = self._touch_auto_meta(catalog_file)
        auto_meta["attempts"] = auto_meta.get("attempts", 0) + 1
        auto_meta["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
        self._save_auto_meta(catalog_file, meta, auto_meta)

    def _record_status(self, catalog_file: CatalogFile, status: str, message: Optional[str] = None) -> None:
        meta, auto_meta = self._touch_auto_meta(catalog_file)
        auto_meta["last_status"] = status
        timestamp = datetime.now(timezone.utc).isoformat()
        if status in ("success", "quarantined"):
            auto_meta["last_success_at"] = timestamp
            if message:
                auto_meta["last_success_message"] = message
        else:
            auto_meta["last_failure_at"] = timestamp
            if message:
                auto_meta["last_reason"] = message
        self._save_auto_meta(catalog_file, meta, auto_meta)

    async def ingest_single_file(
        self, 
        file_id: int,
        only_with_template: bool = True,
        allow_quarantine: bool = True,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            # 1. 获取文件信息
            # [*] v4.18.2修复：统一使用异步查询
            result = await self.db.execute(
                select(CatalogFile).where(CatalogFile.id == file_id)
            )
            catalog_file = result.scalar_one_or_none()
            
            if not catalog_file:
                return {
                    'success': False,
                    'file_id': file_id,
                    'status': 'failed',
                    'message': '文件不存在'
                }
            
            # 2. 检查状态（防止并发）
            if catalog_file.status == 'processing':
                return {
                    'success': False,
                    'file_id': file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'skipped',
                    'message': '文件正在处理中'
                }
            
            if catalog_file.status in ['ingested', 'partial_success']:
                return {
                    'success': False,
                    'file_id': file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'skipped',
                    'message': '文件已入库'
                }
            
            # 记录尝试
            self._record_attempt(catalog_file)
            
            # 3. 查找模板
            # 3. 查找模板（规范化sub_domain：空字符串转为None）
            normalized_sub_domain = catalog_file.sub_domain if catalog_file.sub_domain else None
            # [*] v4.18.2：添加 await
            template = await self.template_matcher.find_best_template(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=normalized_sub_domain
            )
            
            if not template and only_with_template:
                self._record_status(catalog_file, "skipped", "no_template")
                await self.db.commit()
                
                return {
                    'success': False,
                    'file_id': file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'skipped',
                    'message': '无模板'
                }
            
            # 4. 设置processing状态（防止并发）
            catalog_file.status = 'processing'
            await self.db.commit()
            
            # 5. 预览文件（复用ExcelParser）
            try:
                file_path = catalog_file.file_path
                # [*] v4.10.0修复：如果用户已设置表头行，严格使用用户设置的值，不进行自动检测
                user_defined_header = None
                if template:
                    user_defined_header = template.header_row if hasattr(template, "header_row") else None
                
                # 确定使用的表头行
                if user_defined_header is not None:
                    # 用户已设置表头行，严格使用用户设置的值
                    header_row = user_defined_header
                    logger.info(f"[AutoIngest] 使用模板指定的表头行: {header_row}")
                else:
                    # 用户未设置表头行，使用默认值0，并允许自动检测
                    header_row = 0
                    logger.info(f"[AutoIngest] 模板未指定表头行，使用默认值0，将尝试自动检测")
                
                # 尝试读取文件
                df = ExcelParser.read_excel(file_path, header=header_row, nrows=100)
                columns = df.columns.tolist()
                
                # 应用模板映射
                initial_mapping = {}
                if template:
                    # [*] v4.18.2：添加 await
                    initial_mapping = await self.template_matcher.apply_template_to_columns(template, columns)
                
                # [*] v4.10.0修复：如果用户已设置表头行，不进行自动检测，直接使用用户设置的值
                if user_defined_header is not None:
                    # 用户已设置表头行，严格使用用户设置的值
                    if not initial_mapping or len(initial_mapping) < len(columns) * 0.3:
                        # 如果匹配失败，记录警告但不自动检测
                        logger.warning(
                            f"[AutoIngest] 表头行{header_row}匹配失败（匹配{len(initial_mapping)}/{len(columns)}），"
                            f"但模板已指定表头行，严格按照模板设置执行，不进行自动检测"
                        )
                else:
                    # 用户未设置表头行，允许自动检测（兜底机制）
                    if not initial_mapping or len(initial_mapping) < len(columns) * 0.3:
                        logger.warning(
                            f"[AutoIngest] 表头行{header_row}匹配失败（匹配{len(initial_mapping)}/{len(columns)}），"
                            f"尝试自动检测表头行（模板未指定表头行）"
                        )
                        # 尝试表头行0-5
                        for test_header in [0, 1, 2, 3, 4, 5]:
                            if test_header == header_row:
                                continue  # 跳过已尝试的
                            try:
                                test_df = ExcelParser.read_excel(file_path, header=test_header, nrows=10)
                                test_columns = test_df.columns.tolist()
                                # 尝试应用模板
                                # [*] v4.18.2：添加 await
                                test_mapping = await self.template_matcher.apply_template_to_columns(
                                    template, test_columns
                                )
                                # 如果匹配成功（至少匹配30%的列），使用这个表头行
                                if test_mapping and len(test_mapping) >= len(test_columns) * 0.3:
                                    logger.info(
                                        f"[AutoIngest] 自动检测到表头行: {test_header}"
                                        f"（匹配{len(test_mapping)}/{len(test_columns)}个字段）"
                                    )
                                    df = test_df
                                    columns = test_columns
                                    header_row = test_header
                                    break
                            except Exception as e:
                                logger.debug(f"[AutoIngest] 尝试表头行{test_header}失败: {e}")
                                continue
            except Exception as e:
                logger.error(f"[AutoIngest] 预览文件失败: {e}")
                catalog_file.status = 'failed'
                self._record_status(catalog_file, "failed", f'preview_failed: {str(e)}')
                await self.db.commit()
                return {
                    'success': False,
                    'file_id': file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'failed',
                    'message': f'预览失败: {str(e)}'
                }
            
            # 6. 应用模板（如果有）
            field_mapping = {}
            if template:
                # [*] v4.18.2：添加 await
                field_mapping = await self.template_matcher.apply_template_to_columns(
                    template, columns
                )
            
            # 如果没有模板或映射为空，返回
            if not field_mapping:
                catalog_file.status = 'pending'  # 恢复待处理状态
                self._record_status(catalog_file, "skipped", "no_mapping")
                await self.db.commit()
                return {
                    'success': False,
                    'file_id': file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'skipped',
                    'message': '无字段映射'
                }
            
            # 7. 调用ingest接口（通过HTTP API）
            try:
                # 通过HTTP调用现有的ingest API
                # [*] 修复：传递完整的参数，确保与手动入库一致
                # [*] v4.11.5新增：传递task_id到ingest API
                # 如果task_id为空，使用single_file_{file_id}作为默认值
                ingest_task_id = task_id if task_id else f"single_file_{file_id}"
                
                async with httpx.AsyncClient() as client:
                    try:
                        response = await client.post(
                            'http://localhost:8001/api/field-mapping/ingest',
                            json={
                                'file_id': file_id,
                                'platform': catalog_file.platform_code or catalog_file.source_platform or '',
                                'domain': catalog_file.data_domain or '',
                                'mappings': field_mapping,  # [*] 修复：使用mappings而不是field_mapping
                                'header_row': header_row,  # [*] 修复：传递header_row参数
                                'task_id': ingest_task_id  # [*] v4.11.5新增：传递task_id用于追踪
                            },
                            timeout=180.0  # 3分钟超时
                        )
                        
                        # [*] v4.11.6修复：检查HTTP响应状态
                        if response.status_code != 200:
                            error_text = response.text
                            logger.error(f"[AutoIngest] HTTP请求失败: status={response.status_code}, body={error_text}")
                            raise Exception(f"HTTP请求失败: {response.status_code} - {error_text}")
                        
                        result = response.json()
                    except httpx.HTTPError as e:
                        # [*] v4.11.6修复：处理HTTP错误（连接错误、超时等）
                        logger.error(f"[AutoIngest] HTTP请求异常: {e}", exc_info=True)
                        raise Exception(f"HTTP请求异常: {str(e)}")
                    except Exception as e:
                        # [*] v4.11.6修复：处理其他异常（JSON解析错误等）
                        logger.error(f"[AutoIngest] 处理HTTP响应异常: {e}", exc_info=True)
                        raise
                
                # [*] 修复：检查实际入库行数，而不仅仅是success标志
                imported = result.get('imported', 0)  # 实际入库行数
                quarantined = result.get('quarantined', 0)  # 隔离行数
                staged = result.get('staged', 0)  # 暂存行数
                
                # 更新状态
                if result.get('success'):
                    await self.db.refresh(catalog_file)
                    catalog_status = (catalog_file.status or '').lower()
                    
                    # [*] 修复：如果imported=0且quarantined=0，说明没有数据入库，应该标记为失败
                    if imported == 0 and quarantined == 0:
                        # 检查是否是全0数据文件（这是正常情况）
                        analysis = result.get('analysis', {})
                        all_zero_data = analysis.get('all_zero_data', False)
                        
                        if all_zero_data:
                            # 全0数据文件，标记为成功但记录警告
                            final_status = 'success'
                            message = result.get('message', '入库成功（全0数据文件）')
                            logger.warning(f"[AutoIngest] 文件{file_id}入库0行（全0数据）: {catalog_file.file_name}")
                        else:
                            # 没有数据入库，标记为失败
                            final_status = 'failed'
                            message = f"入库失败：没有数据入库（imported=0, quarantined=0, staged={staged}）"
                            logger.error(f"[AutoIngest] 文件{file_id}入库失败（无数据）: {catalog_file.file_name}, staged={staged}")
                    elif catalog_status == 'quarantined':
                        final_status = 'quarantined'
                        message = result.get('message', '部分数据已隔离')
                    else:
                        final_status = 'success'
                        message = result.get('message', f'入库成功（{imported}行）')
                    
                    self._record_status(catalog_file, final_status, message)
                    await self.db.commit()
                    return {
                        'success': final_status != 'failed',
                        'file_id': file_id,
                        'file_name': catalog_file.file_name,
                        'status': final_status,
                        'message': message,
                        'rows_ingested': imported,  # [*] 修复：使用imported而不是rows_ingested
                        'quarantined': quarantined,
                        'staged': staged
                    }
                else:
                    catalog_file.status = 'failed'
                    failure_reason = result.get('message', '入库失败')
                    self._record_status(catalog_file, "failed", failure_reason)
                    await self.db.commit()
                    
                    return {
                        'success': False,
                        'file_id': file_id,
                        'file_name': catalog_file.file_name,
                        'status': 'failed',
                        'message': failure_reason
                    }
            except Exception as e:
                logger.error(f"[AutoIngest] 入库失败: {e}", exc_info=True)
                catalog_file.status = 'failed'
                self._record_status(catalog_file, "failed", f'入库失败: {str(e)}')
                await self.db.commit()
                
                return {
                    'success': False,
                    'file_id': file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'failed',
                    'message': f'入库失败: {str(e)}'
                }
                
        except Exception as e:
            logger.error(f"[AutoIngest] 单文件自动入库异常: {e}", exc_info=True)
            return {
                'success': False,
                'file_id': file_id,
                'status': 'failed',
                'message': f'异常: {str(e)}'
            }
    
    async def batch_ingest(
        self,
        platform: Optional[str] = None,
        domains: List[str] = None,
        granularities: List[str] = None,
        since_hours: int = None,
        limit: int = 100,
        only_with_template: bool = True,
        allow_quarantine: bool = True
    ) -> Dict[str, Any]:
        """
        批量自动入库
        
        流程：
        1. 扫描符合条件的文件
        2. 创建进度任务
        3. 逐个调用ingest_single_file
        4. 返回汇总统计
        
        Args:
            platform: 平台代码（可选，None 或 '*' 表示全部平台）
            domains: 数据域列表（可选，空=全部）
            granularities: 粒度列表（可选，空=全部）
            since_hours: 只处理最近N小时的文件
            limit: 最多处理N个文件
            only_with_template: 只处理有模板的文件
            allow_quarantine: 允许隔离错误数据
        
        Returns:
            {
                success: bool,
                task_id: str,
                summary: {
                    total_files: int,
                    processed: int,
                    succeeded: int,
                    quarantined: int,
                    failed: int,
                    skipped_no_template: int
                },
                files: [...]
            }
        """
        try:
            # 1. 扫描符合条件的文件
            stmt = select(CatalogFile).where(CatalogFile.status == 'pending')

            normalized_platform: Optional[str] = None
            if platform and platform.strip():
                platform = platform.strip()
                if platform not in ("*", "all", "ALL"):
                    normalized_platform = platform.lower()

            if normalized_platform:
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == normalized_platform,
                        func.lower(CatalogFile.source_platform) == normalized_platform,
                    )
                )
            
            if domains:
                stmt = stmt.where(CatalogFile.data_domain.in_(domains))
            if granularities:
                stmt = stmt.where(CatalogFile.granularity.in_(granularities))
            if since_hours:
                since_time = datetime.now() - timedelta(hours=since_hours)
                stmt = stmt.where(CatalogFile.first_seen_at >= since_time)
            
            stmt = stmt.order_by(CatalogFile.first_seen_at.desc())
            stmt = stmt.limit(limit)
            
            result = await self.db.execute(stmt)
            files = result.scalars().all()
            total_files = len(files)
            
            if total_files == 0:
                return {
                    'success': True,
                    'task_id': None,
                    'summary': {
                        'total_files': 0,
                        'processed': 0,
                        'succeeded': 0,
                        'quarantined': 0,
                        'failed': 0,
                        'skipped_no_template': 0
                    },
                    'message': '没有符合条件的待入库文件'
                }
            
            # 2. 创建进度任务
            task_id = str(uuid.uuid4())
            await self.progress_tracker.create_task(task_id, total_files, task_type='auto_ingest')
            await self.progress_tracker.update_task(task_id, {
                'status': 'processing',
                'total': total_files,
                'processed': 0,
                'succeeded': 0,
                'quarantined': 0,
                'failed': 0,
                'skipped': 0,
                'files': []
            })
            
            logger.info(f"[AutoIngest] 批量入库开始: {total_files}个文件, task_id={task_id}")
            
            # 3. 逐个处理文件
            succeeded = 0
            quarantined = 0
            failed = 0
            skipped_no_template = 0
            processed_files = []
            
            for idx, file in enumerate(files):
                try:
                    result = await self.ingest_single_file(
                        file_id=file.id,
                        only_with_template=only_with_template,
                        allow_quarantine=allow_quarantine,
                        task_id=task_id  # [*] v4.11.5新增：传递批量task_id
                    )
                    
                    # 统计结果
                    if result['status'] == 'success':
                        succeeded += 1
                    elif result['status'] == 'quarantined':
                        quarantined += 1
                    elif result['status'] == 'failed':
                        failed += 1
                    elif result['status'] == 'skipped':
                        message = result.get('message', '')
                        message_lower = message.lower()
                        if (
                            'no_template' in message_lower
                            or 'no template' in message_lower
                            or '无模板' in message
                        ):
                            skipped_no_template += 1
                    
                    processed_files.append(result)
                    
                    # 更新进度
                    await self.progress_tracker.update_task(task_id, {
                        'processed_files': idx + 1,
                        'processed': idx + 1,
                        'valid_rows': succeeded,
                        'succeeded': succeeded,
                        'quarantined_rows': quarantined,
                        'quarantined': quarantined,
                        'error_rows': failed,
                        'failed': failed,
                        'skipped': skipped_no_template,
                        'files': processed_files[-10:]  # 只保留最近10个
                    })
                    
                except Exception as e:
                    logger.error(f"[AutoIngest] 处理文件失败: {file.id}, {e}")
                    failed += 1
            
            # 4. 完成任务
            summary = {
                'total_files': total_files,
                'processed': total_files,
                'succeeded': succeeded,
                'quarantined': quarantined,
                'failed': failed,
                'skipped_no_template': skipped_no_template
            }
            
            # [*] v4.11.5新增：批量入库完成后执行数据质量检查
            quality_check_results = {}
            try:
                # 收集所有成功处理的文件的平台和店铺信息
                platform_shop_pairs = set()
                for file_result in processed_files:
                    if file_result.get('status') == 'success':
                        file_id = file_result.get('file_id')
                        if file_id:
                            # [*] v4.18.2修复：统一使用异步查询
                            result = await self.db.execute(
                                select(CatalogFile).where(CatalogFile.id == file_id)
                            )
                            catalog_file = result.scalar_one_or_none()
                            if catalog_file and catalog_file.platform_code:
                                # 尝试从文件元数据或文件名中提取shop_id
                                shop_id = catalog_file.shop_id or catalog_file.source_shop_id or 'unknown'
                                platform_shop_pairs.add((catalog_file.platform_code, shop_id))
                
                # 对每个平台+店铺组合进行质量检查
                if platform_shop_pairs:
                    validator = get_c_class_data_validator(self.db)
                    today = date.today()
                    quality_scores = []
                    missing_fields_list = []
                    
                    for platform_code, shop_id in platform_shop_pairs:
                        try:
                            check_result = validator.check_b_class_completeness(
                                platform_code=platform_code,
                                shop_id=shop_id,
                                metric_date=today
                            )
                            quality_scores.append(check_result.get('data_quality_score', 0.0))
                            missing_fields_list.extend(check_result.get('missing_fields', []))
                            
                            quality_check_results[f"{platform_code}_{shop_id}"] = {
                                'platform_code': platform_code,
                                'shop_id': shop_id,
                                'data_quality_score': check_result.get('data_quality_score', 0.0),
                                'orders_complete': check_result.get('orders_complete', False),
                                'products_complete': check_result.get('products_complete', False),
                                'inventory_complete': check_result.get('inventory_complete', False),
                                'missing_fields': check_result.get('missing_fields', [])
                            }
                        except Exception as e:
                            logger.warning(f"[AutoIngest] 数据质量检查失败 ({platform_code}/{shop_id}): {e}")
                    
                    # 计算平均质量评分
                    avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
                    unique_missing_fields = list(set(missing_fields_list))
                    
                    logger.info(f"[AutoIngest] 数据质量检查完成: 平均评分={avg_quality_score:.2f}, 缺失字段={len(unique_missing_fields)}")
                else:
                    logger.info("[AutoIngest] 无成功处理的文件，跳过数据质量检查")
            except Exception as e:
                logger.warning(f"[AutoIngest] 数据质量检查过程出错: {e}", exc_info=True)
                quality_check_results = {'error': str(e)}
            
            await self.progress_tracker.complete_task(task_id, success=True)
            await self.progress_tracker.update_task(task_id, {
                'processed_files': total_files,
                'processed': total_files,
                'valid_rows': succeeded,
                'succeeded': succeeded,
                'quarantined_rows': quarantined,
                'quarantined': quarantined,
                'error_rows': failed,
                'failed': failed,
                'skipped': skipped_no_template,
                'files': processed_files[-10:],
                'quality_check': quality_check_results  # [*] v4.11.5新增：数据质量检查结果
            })
            
            logger.info(f"[AutoIngest] 批量入库完成: {summary}")
            
            return {
                'success': True,
                'task_id': task_id,
                'summary': summary,
                'files': processed_files,
                'quality_check': quality_check_results  # [*] v4.11.5新增：返回质量检查结果
            }
            
        except Exception as e:
            logger.error(f"[AutoIngest] 批量入库异常: {e}", exc_info=True)
            return {
                'success': False,
                'task_id': None,
                'message': f'批量入库异常: {str(e)}'
            }


def get_auto_ingest_orchestrator(db: AsyncSession) -> AutoIngestOrchestrator:
    """
    获取自动入库编排器实例
    
    [*] v4.18.2修复：支持 AsyncSession
    [*] v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    return AutoIngestOrchestrator(db)


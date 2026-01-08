#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
智能数据处理管道
负责：文件重命名 -> 目录组织 -> 数据清洗 -> 数据库记录
按data_organizer规范实现细粒度账号级别分离
"""

import os
import shutil
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import pandas as pd

from modules.core.logger import get_logger
from models.database import CollectionTask, DatabaseManager

logger = get_logger(__name__)


class DataProcessingPipeline:
    """数据处理管道"""
    
    def __init__(self):
        """初始化数据处理管道"""
        self.base_downloads_dir = Path("downloads")
        self.base_processed_dir = Path("processed_data")
        self.backup_dir = Path("temp/backups")
        
        # 确保目录存在
        for directory in [self.base_downloads_dir, self.base_processed_dir, self.backup_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def process_collection_result(self, collection_result: Dict[str, Any], 
                                account: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理采集结果的完整流程
        
        Args:
            collection_result: 采集结果字典
            account: 账号信息
            
        Returns:
            Dict: 处理结果
        """
        processing_result = {
            "success": False,
            "processed_files": [],
            "database_records": [],
            "error": None,
            "processing_time": 0
        }
        
        start_time = datetime.now()
        
        try:
            logger.info(f"[RETRY] 开始数据处理流程")
            
            # 1. 文件重命名和组织
            if collection_result.get("downloaded_files"):
                for file_path in collection_result["downloaded_files"]:
                    renamed_result = self._rename_and_organize_file(
                        file_path, account, collection_result
                    )
                    if renamed_result["success"]:
                        processing_result["processed_files"].append(renamed_result)
            
            # 2. 数据清洗（如果有处理的文件）
            for file_info in processing_result["processed_files"]:
                if file_info["success"]:
                    cleaned_result = self._clean_data_file(file_info["new_path"], account)
                    file_info["cleaned"] = cleaned_result
            
            # 3. 数据库记录
            db_record = self._create_database_record(collection_result, account, processing_result)
            if db_record:
                processing_result["database_records"].append(db_record)
            
            # 4. 判断整体成功状态
            successful_files = [f for f in processing_result["processed_files"] if f["success"]]
            if successful_files or db_record:
                processing_result["success"] = True
                logger.info(f"[OK] 数据处理完成，处理{len(successful_files)}个文件")
            else:
                processing_result["error"] = "没有成功处理的文件"
                
        except Exception as e:
            processing_result["error"] = f"数据处理异常: {e}"
            logger.error(f"[FAIL] {processing_result['error']}")
        
        finally:
            end_time = datetime.now()
            processing_result["processing_time"] = (end_time - start_time).total_seconds()
            
        return processing_result
    
    def _rename_and_organize_file(self, file_path: str, account: Dict, 
                                collection_result: Dict) -> Dict[str, Any]:
        """重命名和组织文件到规范目录结构"""
        result = {
            "success": False,
            "original_path": file_path,
            "new_path": None,
            "error": None
        }
        
        try:
            original_file = Path(file_path)
            if not original_file.exists():
                result["error"] = f"原文件不存在: {file_path}"
                return result
            
            # 生成账号键
            account_key = self._generate_account_key(account)
            
            # 获取平台和数据类型
            platform = account.get("platform", "unknown").lower()
            data_type = collection_result.get("data_type", "sales")
            
            # 获取日期信息
            date_range = collection_result.get("date_range", {})
            start_date = date_range.get("start_date", datetime.now().strftime("%Y-%m-%d"))
            end_date = date_range.get("end_date", start_date)
            
            # 解析日期
            try:
                date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            except:
                date_obj = datetime.now()
            
            # 构建目录结构：downloads/{platform}/{account_key}/{data_type}/{YYYY}/{YYYYMM}/{YYYYMMDD}/raw
            target_dir = (self.base_downloads_dir / platform / account_key / data_type / 
                         f"{date_obj.year}" / f"{date_obj.year:04d}{date_obj.month:02d}" / 
                         f"{date_obj.year:04d}{date_obj.month:02d}{date_obj.day:02d}" / "raw")
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成新文件名
            new_filename = self._generate_filename(
                platform, account_key, data_type, start_date, end_date, original_file.suffix
            )
            
            new_file_path = target_dir / new_filename
            
            # 移动文件
            shutil.move(str(original_file), str(new_file_path))
            
            result["success"] = True
            result["new_path"] = str(new_file_path)
            
            logger.info(f"[OK] 文件重命名完成: {original_file.name} -> {new_filename}")
            
        except Exception as e:
            result["error"] = f"文件重命名失败: {e}"
            logger.error(f"[FAIL] {result['error']}")
        
        return result
    
    def _generate_account_key(self, account: Dict) -> str:
        """生成账号键"""
        platform = account.get("platform", "unknown").lower()
        store_name = account.get("store_name", "")
        username = account.get("username", "")
        
        # 优先使用store_name，其次username
        identifier = store_name or username or "unknown"
        
        # 清理特殊字符
        clean_identifier = "".join(c for c in identifier if c.isalnum() or c in "._-")
        
        return f"{platform}_{clean_identifier}".lower().replace("@", "_")
    
    def _generate_filename(self, platform: str, account_key: str, data_type: str,
                          start_date: str, end_date: str, file_extension: str) -> str:
        """生成标准化文件名"""
        try:
            # 当前时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 日期范围字符串
            if start_date == end_date:
                date_range_str = start_date.replace("-", "")
            else:
                start_str = start_date.replace("-", "")
                end_str = end_date.replace("-", "")
                date_range_str = f"{start_str}_{end_str}"
            
            # 生成文件内容哈希（用于去重）
            content_hash = hashlib.md5(f"{platform}_{account_key}_{data_type}_{timestamp}".encode()).hexdigest()[:8]
            
            # 文件名格式：YYYYMMDD_HHMMSS_{platform}_{account_key}_{data_type}_{daterange}_{hash}.xlsx
            filename = f"{timestamp}_{platform}_{account_key}_{data_type}_{date_range_str}_{content_hash}{file_extension}"
            
            return filename
            
        except Exception as e:
            logger.error(f"[FAIL] 生成文件名失败: {e}")
            # 降级到简单文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{timestamp}_{platform}_{data_type}{file_extension}"
    
    def _clean_data_file(self, file_path: str, account: Dict) -> Dict[str, Any]:
        """数据清洗"""
        result = {
            "success": False,
            "cleaned_file": None,
            "row_count": 0,
            "error": None
        }
        
        try:
            file_path_obj = Path(file_path)
            
            # 目前只处理Excel文件
            if file_path_obj.suffix.lower() not in ['.xlsx', '.xls', '.csv']:
                result["error"] = "不支持的文件格式"
                return result
            
            # 读取数据
            if file_path_obj.suffix.lower() == '.csv':
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            else:
                df = pd.read_excel(file_path)
            
            if df.empty:
                result["error"] = "文件为空"
                return result
            
            # 基本数据清洗
            df_cleaned = self._perform_basic_cleaning(df, account)
            
            # 保存清洗后的文件到processed_data目录
            processed_file = self._save_cleaned_data(df_cleaned, file_path_obj, account)
            
            result["success"] = True
            result["cleaned_file"] = str(processed_file)
            result["row_count"] = len(df_cleaned)
            
            logger.info(f"[OK] 数据清洗完成: {result['row_count']}行数据")
            
        except Exception as e:
            result["error"] = f"数据清洗失败: {e}"
            logger.error(f"[FAIL] {result['error']}")
        
        return result
    
    def _perform_basic_cleaning(self, df: pd.DataFrame, account: Dict) -> pd.DataFrame:
        """执行基本数据清洗"""
        try:
            df_cleaned = df.copy()
            
            # 1. 删除完全空白的行和列
            df_cleaned = df_cleaned.dropna(how='all').dropna(axis=1, how='all')
            
            # 2. 标准化日期列（常见的日期列名）
            date_columns = ['日期', '时间', 'date', 'time', '下单时间', '创建时间', '更新时间']
            for col in df_cleaned.columns:
                if any(date_keyword in str(col).lower() for date_keyword in date_columns):
                    try:
                        df_cleaned[col] = pd.to_datetime(df_cleaned[col], errors='coerce')
                    except:
                        pass
            
            # 3. 标准化金额列（移除货币符号，转换为数值）
            amount_columns = ['金额', '价格', '费用', 'amount', 'price', 'cost', '销售额', '利润']
            for col in df_cleaned.columns:
                if any(amount_keyword in str(col).lower() for amount_keyword in amount_columns):
                    try:
                        # 移除货币符号和逗号
                        df_cleaned[col] = df_cleaned[col].astype(str).str.replace(r'[￥$,]', '', regex=True)
                        df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors='coerce')
                    except:
                        pass
            
            # 4. 添加处理元数据
            df_cleaned['_processed_at'] = datetime.now()
            df_cleaned['_account_platform'] = account.get('platform', '')
            df_cleaned['_account_key'] = self._generate_account_key(account)
            
            return df_cleaned
            
        except Exception as e:
            logger.error(f"[FAIL] 数据清洗处理失败: {e}")
            return df
    
    def _save_cleaned_data(self, df: pd.DataFrame, original_file: Path, account: Dict) -> Path:
        """保存清洗后的数据"""
        try:
            # 构建processed_data目录结构
            account_key = self._generate_account_key(account)
            platform = account.get("platform", "unknown").lower()
            
            # 从原文件路径提取日期信息
            date_parts = original_file.parts
            year = month = day = None
            for part in date_parts:
                if part.isdigit() and len(part) == 4:  # 年份
                    year = part
                elif part.isdigit() and len(part) == 6:  # 年月
                    year, month = part[:4], part[4:6]
                elif part.isdigit() and len(part) == 8:  # 年月日
                    year, month, day = part[:4], part[4:6], part[6:8]
            
            if not year:
                year = datetime.now().strftime("%Y")
                month = datetime.now().strftime("%m")
                day = datetime.now().strftime("%d")
            
            processed_dir = (self.base_processed_dir / platform / account_key / "sales" / 
                           year / f"{year}{month}" / f"{year}{month}{day}")
            processed_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成处理后文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            row_count = len(df)
            processed_filename = f"{timestamp}_{platform}_{account_key}_sales_{row_count}_v1.parquet"
            
            processed_file = processed_dir / processed_filename
            
            # 保存为Parquet格式（更高效）
            df.to_parquet(processed_file, index=False)
            
            logger.info(f"[OK] 清洗数据已保存: {processed_filename}")
            return processed_file
            
        except Exception as e:
            logger.error(f"[FAIL] 保存清洗数据失败: {e}")
            # 降级保存为CSV
            fallback_file = original_file.parent / f"cleaned_{original_file.stem}.csv"
            df.to_csv(fallback_file, index=False, encoding='utf-8-sig')
            return fallback_file
    
    def _create_database_record(self, collection_result: Dict, account: Dict,
                              processing_result: Dict) -> Optional[int]:
        """创建数据库记录"""
        try:
            db_manager = DatabaseManager()
            session = db_manager.get_session()
            
            # 创建CollectionTask记录
            task = CollectionTask(
                platform=account.get("platform", "unknown"),
                account_name=account.get("store_name") or account.get("username", "unknown"),
                data_type=collection_result.get("data_type", "sales"),
                status="completed" if collection_result.get("success") else "failed",
                start_date=datetime.fromisoformat(collection_result.get("start_time", datetime.now().isoformat())),
                end_date=datetime.now(),
                file_path=";".join([f["new_path"] for f in processing_result["processed_files"] if f["success"]]),
                error_message=collection_result.get("error") or processing_result.get("error")
            )
            
            session.add(task)
            session.commit()
            
            task_id = task.id
            session.close()
            
            logger.info(f"[OK] 数据库记录创建成功: Task ID {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"[FAIL] 创建数据库记录失败: {e}")
            return None

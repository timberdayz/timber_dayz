#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据存储组织器 - 多账号多店铺精细化管理
基于账号维度进行文件夹级别的细致区分管理
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import shutil

# 导入本地账号配置
try:
    from local_accounts import get_all_local_accounts, get_accounts_by_platform
except ImportError:
    print("⚠️ 警告：未找到local_accounts.py，使用默认配置")
    def get_all_local_accounts():
        return []
    def get_accounts_by_platform(platform):
        return []

@dataclass
class AccountStorageInfo:
    """账号存储信息"""
    account_id: str
    platform: str
    store_name: str
    region: str
    currency: str
    base_path: Path
    enabled: bool = True

class DataOrganizer:
    """数据存储组织器"""
    
    def __init__(self, base_output_dir: str = "temp/outputs"):
        self.base_output_dir = Path(base_output_dir)
        self.account_storage_map = {}
        self._initialize_storage_structure()
    
    def _initialize_storage_structure(self):
        """初始化存储结构"""
        print("🗂️ 初始化账号存储结构...")
        
        # 读取所有账号配置
        all_accounts = get_all_local_accounts()
        
        for account in all_accounts:
            account_info = self._create_account_storage_info(account)
            if account_info:
                self.account_storage_map[account_info.account_id] = account_info
                self._create_account_directories(account_info)
        
        # 打印存储结构总览
        self._print_storage_overview()
    
    def _create_account_storage_info(self, account: Dict) -> Optional[AccountStorageInfo]:
        """创建账号存储信息"""
        try:
            account_id = account.get('account_id', '')
            platform = account.get('platform', '').lower()
            store_name = account.get('store_name', account.get('account_name', ''))
            region = account.get('region', 'global').lower()
            currency = account.get('currency', 'USD')
            enabled = account.get('enabled', True)
            
            if not account_id or not platform:
                return None
            
            # 标准化路径名称（移除特殊字符）
            safe_account_id = self._sanitize_name(account_id)
            safe_store_name = self._sanitize_name(store_name)
            safe_region = self._sanitize_name(region)
            
            # 构建基础路径: platform/account_id_store_name_region
            account_dir_name = f"{safe_account_id}_{safe_store_name}_{safe_region}"
            base_path = self.base_output_dir / platform / account_dir_name
            
            return AccountStorageInfo(
                account_id=account_id,
                platform=platform,
                store_name=store_name,
                region=region,
                currency=currency,
                base_path=base_path,
                enabled=enabled
            )
        
        except Exception as e:
            print(f"❌ 创建账号存储信息失败: {e}")
            return None
    
    def _sanitize_name(self, name: str) -> str:
        """清理名称中的特殊字符"""
        import re
        # 移除或替换特殊字符
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', str(name))
        sanitized = re.sub(r'[^\w\-_.]', '_', sanitized)
        return sanitized.strip('_')
    
    def _create_account_directories(self, account_info: AccountStorageInfo):
        """为账号创建完整的目录结构"""
        base_path = account_info.base_path
        
        # 定义目录结构
        directories = {
            # 原始数据目录
            "raw_data": {
                "orders": "原始订单数据",
                "products": "原始商品数据", 
                "finance": "原始财务数据",
                "inventory": "原始库存数据",
                "advertising": "原始广告数据",
                "customer": "原始客户数据"
            },
            
            # 处理后数据目录
            "processed_data": {
                "sales": "处理后销售数据",
                "products": "处理后商品数据",
                "finance": "处理后财务数据",
                "inventory": "处理后库存数据",
                "analytics": "分析结果数据"
            },
            
            # 手动下载目录
            "manual_downloads": {
                "sales_reports": "手动下载销售报告",
                "finance_reports": "手动下载财务报告",
                "product_reports": "手动下载商品报告",
                "advertising_reports": "手动下载广告报告",
                "other_reports": "其他手动下载文件"
            },
            
            # 自动采集目录
            "auto_collection": {
                "daily": "每日自动采集",
                "weekly": "每周自动采集", 
                "monthly": "每月自动采集",
                "real_time": "实时数据采集"
            },
            
            # 分析报告目录
            "reports": {
                "daily_reports": "日报告",
                "weekly_reports": "周报告",
                "monthly_reports": "月报告",
                "custom_reports": "自定义报告"
            },
            
            # 备份目录
            "backups": {
                "data_backups": "数据备份",
                "config_backups": "配置备份",
                "report_backups": "报告备份"
            },
            
            # 日志目录
            "logs": {
                "collection_logs": "采集日志",
                "error_logs": "错误日志",
                "performance_logs": "性能日志"
            },
            
            # 临时文件目录
            "temp": {
                "processing": "数据处理临时文件",
                "uploads": "上传临时文件",
                "downloads": "下载临时文件"
            }
        }
        
        # 创建目录结构
        for main_dir, sub_dirs in directories.items():
            main_path = base_path / main_dir
            main_path.mkdir(parents=True, exist_ok=True)
            
            if isinstance(sub_dirs, dict):
                for sub_dir, description in sub_dirs.items():
                    sub_path = main_path / sub_dir
                    sub_path.mkdir(parents=True, exist_ok=True)
                    
                    # 创建目录说明文件
                    readme_file = sub_path / "README.md"
                    if not readme_file.exists():
                        with open(readme_file, 'w', encoding='utf-8') as f:
                            f.write(f"# {sub_dir}\n\n{description}\n\n")
                            f.write(f"账号信息:\n")
                            f.write(f"- 账号ID: {account_info.account_id}\n")
                            f.write(f"- 平台: {account_info.platform}\n")
                            f.write(f"- 店铺: {account_info.store_name}\n")
                            f.write(f"- 地区: {account_info.region}\n")
                            f.write(f"- 币种: {account_info.currency}\n")
                            f.write(f"- 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 创建账号配置文件
        self._create_account_config_file(account_info)
        
        print(f"✅ 创建目录结构: {account_info.platform}/{account_info.account_id}")
    
    def _create_account_config_file(self, account_info: AccountStorageInfo):
        """创建账号配置文件"""
        config_file = account_info.base_path / "account_config.json"
        
        config_data = {
            "account_info": asdict(account_info),
            "directory_structure": self._get_directory_structure(account_info.base_path),
            "created_time": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "data_statistics": {
                "total_files": 0,
                "total_size_mb": 0,
                "last_collection_time": None,
                "collection_count": 0
            }
        }
        
        # 转换Path对象为字符串
        config_data["account_info"]["base_path"] = str(account_info.base_path)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    
    def _get_directory_structure(self, base_path: Path) -> Dict:
        """获取目录结构"""
        structure = {}
        if base_path.exists():
            for item in base_path.iterdir():
                if item.is_dir():
                    structure[item.name] = [
                        sub_item.name for sub_item in item.iterdir() 
                        if sub_item.is_dir()
                    ]
        return structure
    
    def _print_storage_overview(self):
        """打印存储结构总览"""
        print("\n" + "="*80)
        print("📁 账号存储结构总览")
        print("="*80)
        
        platform_stats = {}
        
        for account_id, account_info in self.account_storage_map.items():
            platform = account_info.platform
            if platform not in platform_stats:
                platform_stats[platform] = {"total": 0, "enabled": 0, "accounts": []}
            
            platform_stats[platform]["total"] += 1
            if account_info.enabled:
                platform_stats[platform]["enabled"] += 1
            
            platform_stats[platform]["accounts"].append({
                "account_id": account_info.account_id,
                "store_name": account_info.store_name,
                "region": account_info.region,
                "path": str(account_info.base_path),
                "enabled": account_info.enabled
            })
        
        for platform, stats in platform_stats.items():
            print(f"\n🏪 {platform.upper()} 平台 ({stats['enabled']}/{stats['total']} 账号启用)")
            print("-" * 60)
            
            for account in stats["accounts"]:
                status = "🟢" if account["enabled"] else "🔴"
                print(f"  {status} {account['account_id']} ({account['store_name']}) - {account['region']}")
                print(f"     📂 {account['path']}")
        
        print(f"\n📊 总计: {len(self.account_storage_map)} 个账号配置")
        print("="*80)
    
    def get_account_path(self, account_id: str, data_type: str = "", sub_category: str = "") -> Optional[Path]:
        """获取账号的数据路径"""
        if account_id not in self.account_storage_map:
            print(f"❌ 未找到账号: {account_id}")
            return None
        
        account_info = self.account_storage_map[account_id]
        base_path = account_info.base_path
        
        if data_type:
            path = base_path / data_type
            if sub_category:
                path = path / sub_category
            return path
        
        return base_path
    
    def store_data_file(self, account_id: str, data_type: str, sub_category: str, 
                       filename: str, source_path: str = None, data: Any = None) -> bool:
        """存储数据文件到指定账号目录"""
        try:
            target_path = self.get_account_path(account_id, data_type, sub_category)
            if not target_path:
                return False
            
            target_path.mkdir(parents=True, exist_ok=True)
            target_file = target_path / filename
            
            if source_path and Path(source_path).exists():
                # 复制源文件
                shutil.copy2(source_path, target_file)
                print(f"✅ 文件已存储: {target_file}")
            elif data is not None:
                # 保存数据
                if isinstance(data, (dict, list)):
                    with open(target_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                else:
                    with open(target_file, 'w', encoding='utf-8') as f:
                        f.write(str(data))
                print(f"✅ 数据已存储: {target_file}")
            
            # 更新账号统计信息
            self._update_account_statistics(account_id)
            return True
            
        except Exception as e:
            print(f"❌ 存储文件失败: {e}")
            return False
    
    def _update_account_statistics(self, account_id: str):
        """更新账号统计信息"""
        if account_id not in self.account_storage_map:
            return
        
        account_info = self.account_storage_map[account_id]
        config_file = account_info.base_path / "account_config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 统计文件数量和大小
                total_files = 0
                total_size = 0
                
                for root, dirs, files in os.walk(account_info.base_path):
                    total_files += len(files)
                    for file in files:
                        file_path = Path(root) / file
                        if file_path.exists():
                            total_size += file_path.stat().st_size
                
                config_data["data_statistics"].update({
                    "total_files": total_files,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "last_updated": datetime.now().isoformat()
                })
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                print(f"⚠️ 更新统计信息失败: {e}")
    
    def get_account_statistics(self, account_id: str = None) -> Dict:
        """获取账号统计信息"""
        if account_id:
            if account_id in self.account_storage_map:
                account_info = self.account_storage_map[account_id]
                config_file = account_info.base_path / "account_config.json"
                
                if config_file.exists():
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        return config_data.get("data_statistics", {})
                    except:
                        pass
            return {}
        else:
            # 返回所有账号统计
            all_stats = {}
            for acc_id in self.account_storage_map:
                all_stats[acc_id] = self.get_account_statistics(acc_id)
            return all_stats
    
    def list_account_files(self, account_id: str, data_type: str = "", sub_category: str = "") -> List[Dict]:
        """列出账号的文件"""
        target_path = self.get_account_path(account_id, data_type, sub_category)
        if not target_path or not target_path.exists():
            return []
        
        files = []
        for file_path in target_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith('.'):
                files.append({
                    "name": file_path.name,
                    "path": str(file_path.relative_to(target_path)),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
        
        return sorted(files, key=lambda x: x["modified"], reverse=True)

def initialize_data_organizer() -> DataOrganizer:
    """初始化数据组织器"""
    return DataOrganizer()

if __name__ == "__main__":
    # 测试数据组织器
    organizer = initialize_data_organizer()
    
    # 示例：存储Shopee数据
    shopee_accounts = get_accounts_by_platform("Shopee")
    if shopee_accounts:
        account_id = shopee_accounts[0].get("account_id")
        if account_id:
            # 存储手动下载的Excel文件
            source_file = "downloads/miaoshou/妙手erp_18876067809/sales/妙手1月~6月销售数据（SP）.xlsx"
            if Path(source_file).exists():
                organizer.store_data_file(
                    account_id=account_id,
                    data_type="manual_downloads",
                    sub_category="sales_reports", 
                    filename="20250126_妙手ERP下载_Shopee销售数据_1-6月.xlsx",
                    source_path=source_file
                )
            
            # 获取统计信息
            stats = organizer.get_account_statistics(account_id)
            print(f"\n📊 账号 {account_id} 统计信息:")
            print(f"   文件数量: {stats.get('total_files', 0)}")
            print(f"   总大小: {stats.get('total_size_mb', 0)} MB") 
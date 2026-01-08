#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
代理监控工具

用于监控代理使用状态、测试代理连接、查看统计信息
帮助用户判断代理是否正常使用
"""

import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import argparse

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.utils.proxy_config_manager import ProxyConfigManager, get_account_proxy
from modules.utils.account_manager import AccountManager


class ProxyMonitor:
    """代理监控器"""
    
    def __init__(self):
        """初始化代理监控器"""
        self.proxy_manager = ProxyConfigManager()
        self.account_manager = AccountManager()
        
    def test_proxy_connectivity(self, proxy_info: Dict[str, str], test_urls: List[str] = None) -> Dict[str, Any]:
        """
        测试代理连接性
        
        Args:
            proxy_info: 代理信息
            test_urls: 测试URL列表
            
        Returns:
            测试结果
        """
        if test_urls is None:
            test_urls = [
                "https://httpbin.org/ip",
                "https://api.ipify.org?format=json", 
                "https://ipinfo.io/json"
            ]
        
        results = {
            "proxy_server": proxy_info.get("server", "unknown"),
            "test_time": datetime.now().isoformat(),
            "tests": [],
            "success_count": 0,
            "total_tests": len(test_urls),
            "average_response_time": 0.0,
            "detected_ip": None,
            "status": "unknown"
        }
        
        total_response_time = 0.0
        
        # 构建代理配置
        proxy_url = proxy_info.get("server", "")
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        
        for test_url in test_urls:
            test_result = {
                "url": test_url,
                "success": False,
                "response_time": 0.0,
                "error": None,
                "response_data": None
            }
            
            try:
                start_time = time.time()
                response = requests.get(
                    test_url, 
                    proxies=proxies, 
                    timeout=30,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                )
                response.raise_for_status()
                
                response_time = time.time() - start_time
                test_result.update({
                    "success": True,
                    "response_time": response_time,
                    "response_data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:200]
                })
                
                # 尝试提取IP信息
                if response.headers.get("content-type", "").startswith("application/json"):
                    data = response.json()
                    if "origin" in data:
                        results["detected_ip"] = data["origin"]
                    elif "ip" in data:
                        results["detected_ip"] = data["ip"]
                
                results["success_count"] += 1
                total_response_time += response_time
                
            except Exception as e:
                test_result["error"] = str(e)
            
            results["tests"].append(test_result)
        
        # 计算平均响应时间
        if results["success_count"] > 0:
            results["average_response_time"] = total_response_time / results["success_count"]
        
        # 判断状态
        success_rate = results["success_count"] / results["total_tests"]
        if success_rate >= 0.8:
            results["status"] = "excellent"
        elif success_rate >= 0.5:
            results["status"] = "good"
        elif success_rate > 0:
            results["status"] = "poor"
        else:
            results["status"] = "failed"
        
        return results
    
    def test_account_proxy(self, account_id: str) -> Dict[str, Any]:
        """
        测试指定账号的代理配置
        
        Args:
            account_id: 账号ID
            
        Returns:
            测试结果
        """
        # 获取账号信息
        accounts_data = self.account_manager.load_accounts()
        account_info = None
        
        for account in accounts_data.get("accounts", []):
            if account.get("account_id") == account_id:
                account_info = account
                break
        
        if not account_info:
            return {
                "error": f"账号 {account_id} 不存在",
                "status": "error"
            }
        
        # 获取代理配置
        proxy_config = get_account_proxy(account_info)
        
        if not proxy_config:
            return {
                "account_id": account_id,
                "platform": account_info.get("platform", "unknown"),
                "region": account_info.get("region", "unknown"),
                "proxy_status": "no_proxy",
                "message": "该账号当前不需要使用代理",
                "test_time": datetime.now().isoformat()
            }
        
        # 测试代理连接
        connectivity_result = self.test_proxy_connectivity(proxy_config)
        
        return {
            "account_id": account_id,
            "platform": account_info.get("platform", "unknown"),
            "region": account_info.get("region", "unknown"),
            "proxy_status": "using_proxy",
            "proxy_config": proxy_config,
            "connectivity_test": connectivity_result,
            "test_time": datetime.now().isoformat()
        }
    
    def get_proxy_usage_stats(self) -> Dict[str, Any]:
        """获取代理使用统计"""
        stats = self.proxy_manager.get_proxy_stats()
        
        # 添加配置统计
        config_stats = {
            "configured_regions": len(self.proxy_manager.proxy_config),
            "enabled_providers": 0,
            "total_providers": 0
        }
        
        for region_config in self.proxy_manager.proxy_config.values():
            providers = region_config.get("providers", [])
            config_stats["total_providers"] += len(providers)
            config_stats["enabled_providers"] += len([p for p in providers if p.get("enabled", False)])
        
        stats.update(config_stats)
        return stats
    
    def monitor_all_accounts(self) -> List[Dict[str, Any]]:
        """监控所有账号的代理状态"""
        accounts_data = self.account_manager.load_accounts()
        results = []
        
        for account in accounts_data.get("accounts", []):
            account_id = account.get("account_id", "")
            if account_id:
                result = self.test_account_proxy(account_id)
                results.append(result)
        
        return results
    
    def cleanup_expired_proxies(self) -> Dict[str, Any]:
        """清理过期代理"""
        expired_count = self.proxy_manager.cleanup_expired_proxies()
        
        return {
            "cleaned_proxies": expired_count,
            "cleanup_time": datetime.now().isoformat(),
            "message": f"已清理 {expired_count} 个过期代理"
        }


def print_test_result(result: Dict[str, Any]) -> None:
    """打印测试结果"""
    print(f"\n{'='*60}")
    print(f"[LIST] 账号代理测试报告")
    print(f"{'='*60}")
    
    if "error" in result:
        print(f"[FAIL] 错误: {result['error']}")
        return
    
    print(f"[SEARCH] 账号ID: {result['account_id']}")
    print(f"[WEB] 平台: {result['platform']}")
    print(f"[LOC] 地区: {result['region']}")
    print(f"[TIME] 测试时间: {result['test_time']}")
    
    if result['proxy_status'] == 'no_proxy':
        print(f"[OK] 代理状态: {result['message']}")
        return
    
    print(f"[LINK] 代理服务器: {result['proxy_config']['server']}")
    
    conn_test = result.get('connectivity_test', {})
    status = conn_test.get('status', 'unknown')
    
    status_icons = {
        'excellent': '[GREEN]',
        'good': '[YELLOW]', 
        'poor': '[ORANGE]',
        'failed': '[RED]',
        'unknown': '[WHITE]'
    }
    
    print(f"{status_icons.get(status, '[WHITE]')} 连接状态: {status.upper()}")
    print(f"[OK] 成功率: {conn_test.get('success_count', 0)}/{conn_test.get('total_tests', 0)}")
    print(f"[FLASH] 平均响应时间: {conn_test.get('average_response_time', 0):.2f}秒")
    
    if conn_test.get('detected_ip'):
        print(f"[GLOBE] 检测到的IP: {conn_test['detected_ip']}")
    
    # 显示详细测试结果
    print(f"\n[DATA] 详细测试结果:")
    for i, test in enumerate(conn_test.get('tests', []), 1):
        status_icon = "[OK]" if test['success'] else "[FAIL]"
        print(f"  {i}. {status_icon} {test['url']}")
        if test['success']:
            print(f"     [TIME] 响应时间: {test['response_time']:.2f}秒")
        else:
            print(f"     [FAIL] 错误: {test.get('error', '未知错误')}")


def print_stats(stats: Dict[str, Any]) -> None:
    """打印统计信息"""
    print(f"\n{'='*60}")
    print(f"[DATA] 代理使用统计")
    print(f"{'='*60}")
    
    print(f"[TOOL] 配置统计:")
    print(f"  [LOC] 配置地区数: {stats.get('configured_regions', 0)}")
    print(f"  [PLUG] 启用提供商: {stats.get('enabled_providers', 0)}")
    print(f"  [PKG] 总提供商数: {stats.get('total_providers', 0)}")
    
    print(f"\n[TARGET] 使用统计:")
    print(f"  [NOTE] 总分配数: {stats.get('total_assignments', 0)}")
    print(f"  [OK] 活跃代理: {stats.get('active_proxies', 0)}")
    print(f"  [TIME] 过期代理: {stats.get('expired_proxies', 0)}")
    
    regions = stats.get('regions', {})
    if regions:
        print(f"\n[GLOBE] 按地区统计:")
        for region, region_stats in regions.items():
            print(f"  [LOC] {region}:")
            print(f"    [DATA] 总数: {region_stats.get('count', 0)}")
            print(f"    [OK] 活跃: {region_stats.get('active', 0)}")
            print(f"    [TIME] 过期: {region_stats.get('expired', 0)}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="代理监控工具")
    parser.add_argument("--account", "-a", help="测试指定账号的代理")
    parser.add_argument("--all", action="store_true", help="监控所有账号")
    parser.add_argument("--stats", action="store_true", help="显示代理使用统计")
    parser.add_argument("--cleanup", action="store_true", help="清理过期代理")
    parser.add_argument("--test-proxy", help="测试指定代理服务器 (格式: http://ip:port)")
    
    args = parser.parse_args()
    
    monitor = ProxyMonitor()
    
    if args.account:
        # 测试指定账号
        result = monitor.test_account_proxy(args.account)
        print_test_result(result)
    
    elif args.all:
        # 监控所有账号
        results = monitor.monitor_all_accounts()
        print(f"\n[SEARCH] 监控 {len(results)} 个账号的代理状态")
        
        for result in results:
            print_test_result(result)
    
    elif args.stats:
        # 显示统计信息
        stats = monitor.get_proxy_usage_stats()
        print_stats(stats)
    
    elif args.cleanup:
        # 清理过期代理
        result = monitor.cleanup_expired_proxies()
        print(f"\n[CLEAN] {result['message']}")
    
    elif args.test_proxy:
        # 测试指定代理
        proxy_config = {"server": args.test_proxy}
        result = monitor.test_proxy_connectivity(proxy_config)
        
        print(f"\n{'='*60}")
        print(f"[TEST] 代理连接测试")
        print(f"{'='*60}")
        print(f"[LINK] 代理服务器: {result['proxy_server']}")
        print(f"[OK] 成功率: {result['success_count']}/{result['total_tests']}")
        print(f"[FLASH] 平均响应时间: {result['average_response_time']:.2f}秒")
        print(f"[DATA] 状态: {result['status'].upper()}")
        
        if result.get('detected_ip'):
            print(f"[GLOBE] 检测到的IP: {result['detected_ip']}")
    
    else:
        # 显示帮助信息
        parser.print_help()
        print(f"\n[TIP] 使用示例:")
        print(f"  python tools/proxy_monitor.py --account shopee_cn_001  # 测试指定账号")
        print(f"  python tools/proxy_monitor.py --all                    # 监控所有账号")
        print(f"  python tools/proxy_monitor.py --stats                  # 查看统计信息")
        print(f"  python tools/proxy_monitor.py --cleanup                # 清理过期代理")
        print(f"  python tools/proxy_monitor.py --test-proxy http://1.2.3.4:8080  # 测试代理")


if __name__ == "__main__":
    main() 
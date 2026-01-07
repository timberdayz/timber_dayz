#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
代理配置向导

帮助用户轻松配置和更换代理服务
支持天启IP和其他代理服务的配置
"""

import sys
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ProxyConfigWizard:
    """代理配置向导"""
    
    def __init__(self):
        """初始化配置向导"""
        self.config_file = Path("config/proxy_config.py")
        self.backup_dir = Path("backups/proxy_configs")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def backup_current_config(self) -> str:
        """备份当前配置"""
        if not self.config_file.exists():
            return "无需备份（配置文件不存在）"
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"proxy_config_backup_{timestamp}.py"
        
        shutil.copy2(self.config_file, backup_file)
        return str(backup_file)
    
    def update_tianqi_ip_config(self, secret: str, sign: str, region: str = "440000", time_hours: int = 1) -> bool:
        """
        更新天启IP配置
        
        Args:
            secret: API密钥
            sign: 签名
            region: 地区代码，默认440000（广东）
            time_hours: 有效时长（小时）
            
        Returns:
            更新是否成功
        """
        try:
            # 读取现有配置
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                # 使用默认模板
                content = self._get_default_config_template()
            
            # 更新天启IP配置
            import re
            
            # 更新secret
            content = re.sub(
                r'"secret":\s*"[^"]*"',
                f'"secret": "{secret}"',
                content
            )
            
            # 更新sign
            content = re.sub(
                r'"sign":\s*"[^"]*"',
                f'"sign": "{sign}"',
                content
            )
            
            # 更新地区
            content = re.sub(
                r'"region":\s*"[^"]*"',
                f'"region": "{region}"',
                content
            )
            
            # 更新时长
            time_minutes = time_hours * 60
            content = re.sub(
                r'"time":\s*\d+',
                f'"time": {time_minutes}',
                content
            )
            
            # 更新轮换间隔
            rotation_seconds = time_hours * 3600
            content = re.sub(
                r'"rotation_interval":\s*\d+',
                f'"rotation_interval": {rotation_seconds}',
                content
            )
            
            # 确保天启IP提供商启用
            content = re.sub(
                r'("provider_name":\s*"tianqi_ip"[^}]*"enabled":\s*)False',
                r'\1True',
                content
            )
            
            # 保存配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
            
        except Exception as e:
            print(f"❌ 更新天启IP配置失败: {e}")
            return False
    
    def add_static_proxy(self, region: str, provider_name: str, proxies: List[Dict[str, Any]]) -> bool:
        """
        添加静态代理配置
        
        Args:
            region: 地区代码
            provider_name: 提供商名称
            proxies: 代理列表
            
        Returns:
            添加是否成功
        """
        try:
            # 这里可以实现静态代理的添加逻辑
            # 由于配置文件格式复杂，建议用户手动编辑
            print(f"💡 请手动编辑 {self.config_file} 文件添加静态代理配置")
            print(f"📝 在 {region} 地区的 providers 列表中添加:")
            
            proxy_template = {
                "provider_name": provider_name,
                "provider_type": "static",
                "enabled": True,
                "priority": 2,
                "static_proxies": proxies
            }
            
            print(json.dumps(proxy_template, indent=4, ensure_ascii=False))
            return True
            
        except Exception as e:
            print(f"❌ 添加静态代理配置失败: {e}")
            return False
    
    def disable_provider(self, region: str, provider_name: str) -> bool:
        """
        禁用指定提供商
        
        Args:
            region: 地区代码
            provider_name: 提供商名称
            
        Returns:
            操作是否成功
        """
        try:
            if not self.config_file.exists():
                print("❌ 配置文件不存在")
                return False
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 构建匹配模式
            import re
            pattern = rf'("provider_name":\s*"{provider_name}"[^}}]*"enabled":\s*)True'
            
            if re.search(pattern, content):
                content = re.sub(pattern, r'\1False', content)
                
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"✅ 已禁用 {region}/{provider_name} 提供商")
                return True
            else:
                print(f"⚠️ 未找到 {region}/{provider_name} 提供商")
                return False
                
        except Exception as e:
            print(f"❌ 禁用提供商失败: {e}")
            return False
    
    def enable_provider(self, region: str, provider_name: str) -> bool:
        """
        启用指定提供商
        
        Args:
            region: 地区代码
            provider_name: 提供商名称
            
        Returns:
            操作是否成功
        """
        try:
            if not self.config_file.exists():
                print("❌ 配置文件不存在")
                return False
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 构建匹配模式
            import re
            pattern = rf'("provider_name":\s*"{provider_name}"[^}}]*"enabled":\s*)False'
            
            if re.search(pattern, content):
                content = re.sub(pattern, r'\1True', content)
                
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"✅ 已启用 {region}/{provider_name} 提供商")
                return True
            else:
                print(f"⚠️ 未找到 {region}/{provider_name} 提供商或已启用")
                return False
                
        except Exception as e:
            print(f"❌ 启用提供商失败: {e}")
            return False
    
    def show_current_config(self) -> None:
        """显示当前配置"""
        try:
            # 动态加载配置
            import sys
            import importlib.util
            
            if not self.config_file.exists():
                print("❌ 配置文件不存在")
                return
            
            spec = importlib.util.spec_from_file_location("proxy_config", str(self.config_file))
            if spec and spec.loader:
                proxy_config_module = importlib.util.module_from_spec(spec)
                sys.modules["proxy_config"] = proxy_config_module
                spec.loader.exec_module(proxy_config_module)
                
                proxy_config = getattr(proxy_config_module, "PROXY_CONFIG", {})
                
                print(f"\n{'='*60}")
                print(f"📋 当前代理配置")
                print(f"{'='*60}")
                
                for region, config in proxy_config.items():
                    print(f"\n🌍 {config.get('name', region)} ({region})")
                    print(f"   📝 描述: {config.get('description', '无描述')}")
                    
                    providers = config.get('providers', [])
                    if providers:
                        print(f"   🔧 提供商:")
                        for provider in providers:
                            status = "✅ 启用" if provider.get('enabled', False) else "❌ 禁用"
                            priority = provider.get('priority', 999)
                            provider_type = provider.get('provider_type', 'unknown')
                            
                            print(f"     • {provider.get('provider_name', 'unknown')} ({provider_type})")
                            print(f"       状态: {status} | 优先级: {priority}")
                            
                            if provider_type == 'api' and provider.get('enabled', False):
                                api_config = provider.get('api_config', {})
                                api_url = api_config.get('api_url', '未配置')
                                print(f"       API: {api_url}")
                    else:
                        print(f"   ⚠️ 无配置的提供商")
                
        except Exception as e:
            print(f"❌ 显示配置失败: {e}")
    
    def _get_default_config_template(self) -> str:
        """获取默认配置模板"""
        return '''"""
代理配置文件 - 类似local_accounts.py的设计模式
为不同地区和平台配置代理服务器

使用方法：
1. 修改下面的PROXY_CONFIG配置
2. 系统会自动读取并应用到对应的账号
3. 支持按地区、平台、账号类型分配代理

安全提示：
- 此文件包含敏感信息，已添加到.gitignore
- 生产环境请使用加密存储
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta


# 代理配置主体 - 按地区分类
PROXY_CONFIG = {
    # 中国地区代理 - 用于中国账号或需要中国IP的场景
    "china": {
        "name": "中国代理",
        "description": "适用于中国Shopee卖家端、中国Amazon账号等",
        "providers": [
            {
                "provider_name": "tianqi_ip",
                "provider_type": "api",  # api | static | rotation
                "enabled": True,
                "priority": 1,  # 优先级，数字越小优先级越高
                "api_config": {
                    "api_url": "http://api.tianqiip.com/getip",
                    "secret": "your_secret_here",
                    "sign": "your_sign_here",
                    "params": {
                        "num": 1,
                        "type": "json",
                        "region": "440000",  # 广东地区
                        "port": 1,
                        "time": 60,  # 1小时有效期
                        "mr": 1,
                        "tl": 1
                    }
                },
                "rotation_interval": 3600,  # 1小时轮换一次
                "max_concurrent": 5,  # 最大并发使用数
                "notes": "天启IP - 1小时有效期，适合短期使用"
            }
        ]
    }
}


# 平台账号类型与代理地区映射规则
ACCOUNT_PROXY_MAPPING = {
    # Shopee平台映射规则
    "Shopee": {
        # 按账号地区映射
        "region_mapping": {
            "CN": "china",      # 中国Shopee账号使用中国代理
        }
    }
}


# 代理使用策略配置
PROXY_STRATEGY = {
    # 全局策略
    "global": {
        "enable_smart_switching": True,    # 启用智能切换
        "fallback_to_direct": True,       # 代理失败时回退到直连
        "max_retry_attempts": 3,          # 最大重试次数
        "retry_delay": 5,                 # 重试延迟(秒)
        "health_check_interval": 300,     # 健康检查间隔(秒)
        "proxy_timeout": 30,              # 代理连接超时(秒)
    },
    
    # 按平台策略
    "platform_specific": {
        "Shopee": {
            "force_proxy": False,          # 是否强制使用代理
            "smart_detection": True,       # 智能检测是否需要代理
            "preferred_protocol": "http",  # 优先协议
        }
    }
}


def get_proxy_config() -> Dict[str, Any]:
    """获取代理配置"""
    return PROXY_CONFIG


def get_account_proxy_mapping() -> Dict[str, Any]:
    """获取账号代理映射规则"""
    return ACCOUNT_PROXY_MAPPING


def get_proxy_strategy() -> Dict[str, Any]:
    """获取代理策略配置"""
    return PROXY_STRATEGY
'''
    
    def interactive_setup(self) -> None:
        """交互式设置"""
        print(f"\n{'='*60}")
        print(f"🔧 代理配置向导")
        print(f"{'='*60}")
        
        # 备份现有配置
        backup_file = self.backup_current_config()
        if backup_file != "无需备份（配置文件不存在）":
            print(f"📁 已备份现有配置到: {backup_file}")
        
        print(f"\n请选择配置类型:")
        print(f"1. 更新天启IP配置")
        print(f"2. 添加静态代理")
        print(f"3. 启用/禁用提供商")
        print(f"4. 查看当前配置")
        print(f"5. 退出")
        
        while True:
            choice = input(f"\n请输入选择 (1-5): ").strip()
            
            if choice == "1":
                self._setup_tianqi_ip()
                break
            elif choice == "2":
                self._setup_static_proxy()
                break
            elif choice == "3":
                self._manage_providers()
                break
            elif choice == "4":
                self.show_current_config()
                break
            elif choice == "5":
                print("👋 退出配置向导")
                break
            else:
                print("❌ 无效选择，请重新输入")
    
    def _setup_tianqi_ip(self) -> None:
        """设置天启IP"""
        print(f"\n🔧 天启IP配置")
        print(f"{'='*40}")
        
        print(f"请输入天启IP的配置信息:")
        secret = input("Secret: ").strip()
        sign = input("Sign: ").strip()
        
        print(f"\n可选配置:")
        region = input("地区代码 (默认440000-广东): ").strip() or "440000"
        time_hours_str = input("代理有效时长(小时，默认1): ").strip() or "1"
        
        try:
            time_hours = int(time_hours_str)
        except ValueError:
            time_hours = 1
            print("⚠️ 无效的时长，使用默认值1小时")
        
        if secret and sign:
            success = self.update_tianqi_ip_config(secret, sign, region, time_hours)
            if success:
                print(f"✅ 天启IP配置更新成功！")
                print(f"📝 配置详情:")
                print(f"   Secret: {secret}")
                print(f"   Sign: {sign}")
                print(f"   地区: {region}")
                print(f"   有效时长: {time_hours}小时")
                print(f"\n💡 现在可以使用代理监控工具测试配置:")
                print(f"   python tools/proxy_monitor.py --stats")
            else:
                print(f"❌ 配置更新失败")
        else:
            print(f"❌ Secret和Sign不能为空")
    
    def _setup_static_proxy(self) -> None:
        """设置静态代理"""
        print(f"\n🔧 静态代理配置")
        print(f"{'='*40}")
        
        print(f"请输入静态代理信息:")
        region = input("地区代码 (china/singapore/malaysia/usa): ").strip()
        provider_name = input("提供商名称: ").strip()
        
        proxies = []
        while True:
            print(f"\n添加代理服务器 #{len(proxies) + 1}:")
            ip = input("IP地址: ").strip()
            port_str = input("端口: ").strip()
            protocol = input("协议 (http/https，默认http): ").strip() or "http"
            username = input("用户名 (可选): ").strip()
            password = input("密码 (可选): ").strip()
            
            if ip and port_str:
                try:
                    port = int(port_str)
                    proxy = {
                        "ip": ip,
                        "port": port,
                        "protocol": protocol,
                        "username": username,
                        "password": password
                    }
                    proxies.append(proxy)
                    print(f"✅ 已添加代理: {ip}:{port}")
                except ValueError:
                    print(f"❌ 无效的端口号")
            
            more = input("是否添加更多代理? (y/n): ").strip().lower()
            if more != 'y':
                break
        
        if region and provider_name and proxies:
            success = self.add_static_proxy(region, provider_name, proxies)
            if success:
                print(f"✅ 静态代理配置模板已生成")
        else:
            print(f"❌ 配置信息不完整")
    
    def _manage_providers(self) -> None:
        """管理提供商"""
        print(f"\n🔧 提供商管理")
        print(f"{'='*40}")
        
        print(f"请选择操作:")
        print(f"1. 启用提供商")
        print(f"2. 禁用提供商")
        
        choice = input("请输入选择 (1-2): ").strip()
        
        region = input("地区代码 (china/singapore/malaysia/usa): ").strip()
        provider_name = input("提供商名称: ").strip()
        
        if choice == "1":
            self.enable_provider(region, provider_name)
        elif choice == "2":
            self.disable_provider(region, provider_name)
        else:
            print("❌ 无效选择")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="代理配置向导")
    parser.add_argument("--tianqi", nargs=2, metavar=("SECRET", "SIGN"), help="更新天启IP配置")
    parser.add_argument("--region", default="440000", help="天启IP地区代码，默认440000")
    parser.add_argument("--time", type=int, default=1, help="代理有效时长(小时)，默认1")
    parser.add_argument("--show", action="store_true", help="显示当前配置")
    parser.add_argument("--enable", nargs=2, metavar=("REGION", "PROVIDER"), help="启用提供商")
    parser.add_argument("--disable", nargs=2, metavar=("REGION", "PROVIDER"), help="禁用提供商")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式配置")
    
    args = parser.parse_args()
    
    wizard = ProxyConfigWizard()
    
    if args.tianqi:
        # 更新天启IP配置
        secret, sign = args.tianqi
        success = wizard.update_tianqi_ip_config(secret, sign, args.region, args.time)
        if success:
            print(f"✅ 天启IP配置更新成功")
        else:
            print(f"❌ 天启IP配置更新失败")
    
    elif args.show:
        # 显示当前配置
        wizard.show_current_config()
    
    elif args.enable:
        # 启用提供商
        region, provider = args.enable
        wizard.enable_provider(region, provider)
    
    elif args.disable:
        # 禁用提供商
        region, provider = args.disable
        wizard.disable_provider(region, provider)
    
    elif args.interactive:
        # 交互式配置
        wizard.interactive_setup()
    
    else:
        # 显示帮助信息
        parser.print_help()
        print(f"\n💡 使用示例:")
        print(f"  python tools/proxy_config_wizard.py --tianqi SECRET SIGN     # 更新天启IP")
        print(f"  python tools/proxy_config_wizard.py --show                   # 显示配置")
        print(f"  python tools/proxy_config_wizard.py --enable china tianqi_ip # 启用提供商")
        print(f"  python tools/proxy_config_wizard.py --interactive            # 交互式配置")


if __name__ == "__main__":
    main() 
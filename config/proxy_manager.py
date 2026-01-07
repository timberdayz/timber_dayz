#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专用代理管理器
为不同网站分配最优的代理设置

作者: AI Assistant
日期: 2025-01-08
"""

import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from urllib.parse import urlparse


class ProxyManager:
    """代理管理器 - 智能分配代理设置"""
    
    def __init__(self, config_file: str = "config/proxy_config.yaml"):
        """
        初始化代理管理器
        
        Args:
            config_file: 代理配置文件路径
        """
        self.config_file = Path(config_file)
        self.proxy_config = self._load_config()
        
    def _load_config(self) -> Dict:
        """加载代理配置"""
        if not self.config_file.exists():
            # 创建默认配置
            default_config = self._create_default_config()
            self._save_config(default_config)
            return default_config
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ 加载代理配置失败: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict:
        """创建默认代理配置"""
        return {
            'version': '1.0',
            'description': '网站代理配置 - 根据需要调整',
            
            # 直连访问的国内网站
            'direct_domains': [
                'miaoshou.com',
                '91miaoshou.com', 
                'baidu.com',
                'taobao.com',
                'tmall.com',
                'jd.com',
                'pinduoduo.com',
                'douyin.com',
                'weibo.com',
                'qq.com',
                'bilibili.com',
            ],
            
            # VPN代理访问的海外网站
            'vpn_domains': [
                'shopee.sg',
                'shopee.my', 
                'shopee.th',
                'shopee.ph',
                'shopee.vn',
                'shopee.tw',
                'shopee.com.br',
                'lazada.sg',
                'lazada.my',
                'lazada.th',
                'amazon.com',
                'amazon.co.uk',
                'ebay.com',
                'temu.com',
                'aliexpress.com',
                'ozon.ru',
                'github.com',
                'google.com',
                'facebook.com',
                'tiktok.com',
            ],
            
            # 代理设置
            'proxy_settings': {
                'direct': {
                    'type': 'direct',
                    'description': '直连访问，不使用代理'
                },
                'system_vpn': {
                    'type': 'system',
                    'description': '使用系统VPN代理'
                },
                'custom_proxy': {
                    'type': 'custom',
                    'server': '',  # 用户自定义代理地址
                    'username': '',
                    'password': '',
                    'description': '自定义代理服务器'
                }
            },
            
            # 特殊规则
            'special_rules': {
                # 可以为特定URL设置特殊规则
                'erp.91miaoshou.com': {
                    'proxy_type': 'direct',
                    'browser_args': ['--disable-web-security'],
                    'description': '妙手ERP专用设置'
                }
            }
        }
    
    def _save_config(self, config: Dict) -> None:
        """保存配置到文件"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, 
                         allow_unicode=True, sort_keys=False)
            print(f"✅ 代理配置已保存: {self.config_file}")
        except Exception as e:
            print(f"❌ 保存代理配置失败: {e}")
    
    def get_domain_from_url(self, url: str) -> str:
        """从URL提取域名"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return url.lower()
    
    def get_proxy_setting(self, url: str) -> Tuple[str, Dict, List[str]]:
        """
        获取URL对应的代理设置
        
        Args:
            url: 目标URL
            
        Returns:
            tuple: (proxy_type, proxy_config, browser_args)
        """
        domain = self.get_domain_from_url(url)
        
        # 检查特殊规则
        if domain in self.proxy_config.get('special_rules', {}):
            rule = self.proxy_config['special_rules'][domain]
            proxy_type = rule.get('proxy_type', 'direct')
            browser_args = rule.get('browser_args', [])
            proxy_config = self._get_proxy_config(proxy_type)
            return proxy_type, proxy_config, browser_args
        
        # 检查直连域名
        direct_domains = self.proxy_config.get('direct_domains', [])
        for direct_domain in direct_domains:
            if direct_domain in domain:
                proxy_config = self._get_proxy_config('direct')
                browser_args = ['--no-proxy-server', '--disable-web-security']
                return 'direct', proxy_config, browser_args
        
        # 检查VPN域名
        vpn_domains = self.proxy_config.get('vpn_domains', [])
        for vpn_domain in vpn_domains:
            if vpn_domain in domain:
                proxy_config = self._get_proxy_config('system_vpn')
                browser_args = []
                return 'system_vpn', proxy_config, browser_args
        
        # 默认使用系统VPN
        proxy_config = self._get_proxy_config('system_vpn')
        browser_args = []
        return 'system_vpn', proxy_config, browser_args
    
    def _get_proxy_config(self, proxy_type: str) -> Dict:
        """获取代理配置"""
        proxy_settings = self.proxy_config.get('proxy_settings', {})
        
        if proxy_type == 'direct':
            return {'type': 'direct'}
        elif proxy_type == 'system_vpn':
            return {'type': 'system'}
        elif proxy_type == 'custom_proxy':
            custom = proxy_settings.get('custom_proxy', {})
            if custom.get('server'):
                return {
                    'type': 'custom',
                    'server': custom['server'],
                    'username': custom.get('username'),
                    'password': custom.get('password')
                }
            else:
                return {'type': 'system'}  # 回退到系统代理
        else:
            return {'type': 'system'}
    
    def add_direct_domain(self, domain: str) -> None:
        """添加直连域名"""
        if domain not in self.proxy_config.get('direct_domains', []):
            self.proxy_config.setdefault('direct_domains', []).append(domain)
            self._save_config(self.proxy_config)
            print(f"✅ 已添加直连域名: {domain}")
    
    def add_vpn_domain(self, domain: str) -> None:
        """添加VPN域名"""
        if domain not in self.proxy_config.get('vpn_domains', []):
            self.proxy_config.setdefault('vpn_domains', []).append(domain)
            self._save_config(self.proxy_config)
            print(f"✅ 已添加VPN域名: {domain}")
    
    def set_custom_proxy(self, server: str, username: str = '', password: str = '') -> None:
        """设置自定义代理"""
        self.proxy_config.setdefault('proxy_settings', {})['custom_proxy'] = {
            'type': 'custom',
            'server': server,
            'username': username,
            'password': password,
            'description': '自定义代理服务器'
        }
        self._save_config(self.proxy_config)
        print(f"✅ 已设置自定义代理: {server}")
    
    def get_summary(self) -> str:
        """获取配置摘要"""
        direct_count = len(self.proxy_config.get('direct_domains', []))
        vpn_count = len(self.proxy_config.get('vpn_domains', []))
        special_count = len(self.proxy_config.get('special_rules', {}))
        
        return f"""
🔧 代理配置摘要:
   📍 直连域名: {direct_count} 个
   🌍 VPN域名: {vpn_count} 个  
   ⚙️ 特殊规则: {special_count} 个
   📄 配置文件: {self.config_file}
"""


def test_proxy_manager():
    """测试代理管理器"""
    print("🧪 测试代理管理器")
    print("="*50)
    
    # 创建代理管理器
    manager = ProxyManager()
    
    # 测试不同URL的代理设置
    test_urls = [
        'https://erp.91miaoshou.com',
        'https://seller.shopee.sg',
        'https://seller.amazon.com',
        'https://www.baidu.com',
        'https://github.com',
        'https://unknown-site.com',
    ]
    
    print("🔍 URL代理设置测试:")
    for url in test_urls:
        proxy_type, proxy_config, browser_args = manager.get_proxy_setting(url)
        domain = manager.get_domain_from_url(url)
        
        print(f"\n📱 {url}")
        print(f"   域名: {domain}")
        print(f"   代理类型: {proxy_type}")
        print(f"   代理配置: {proxy_config}")
        print(f"   浏览器参数: {browser_args}")
    
    # 显示配置摘要
    print("\n" + manager.get_summary())


if __name__ == "__main__":
    test_proxy_manager() 
"""
代理测试模块

提供代理连接和平台访问测试功能。
"""

import requests
import time
from typing import Dict, Any, Optional
from modules.utils.logger import Logger


class ProxyTester:
    """代理测试器"""
    
    def __init__(self):
        self.logger = Logger(__name__)
        self.session = requests.Session()
        self.timeout = 10
        
    def test_proxy_connection(self, proxy_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        测试代理连接
        
        Args:
            proxy_config: 代理配置
            
        Returns:
            测试结果
        """
        try:
            proxies = {
                'http': f"http://{proxy_config['host']}:{proxy_config['port']}",
                'https': f"http://{proxy_config['host']}:{proxy_config['port']}"
            }
            
            if proxy_config.get('username') and proxy_config.get('password'):
                auth = (proxy_config['username'], proxy_config['password'])
            else:
                auth = None
            
            start_time = time.time()
            response = self.session.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                auth=auth,
                timeout=self.timeout
            )
            end_time = time.time()
            
            if response.status_code == 200:
                result = {
                    'success': True,
                    'response_time': round(end_time - start_time, 2),
                    'ip': response.json().get('origin', 'unknown'),
                    'status_code': response.status_code
                }
                self.logger.info(f"代理连接测试成功: {result['ip']} ({result['response_time']}s)")
            else:
                result = {
                    'success': False,
                    'error': f"HTTP {response.status_code}",
                    'status_code': response.status_code
                }
                self.logger.warning(f"代理连接测试失败: {result['error']}")
            
            return result
            
        except requests.exceptions.ProxyError as e:
            result = {
                'success': False,
                'error': f"代理错误: {str(e)}"
            }
            self.logger.error(f"代理连接测试失败: {result['error']}")
            return result
            
        except requests.exceptions.Timeout as e:
            result = {
                'success': False,
                'error': f"连接超时: {str(e)}"
            }
            self.logger.error(f"代理连接测试失败: {result['error']}")
            return result
            
        except Exception as e:
            result = {
                'success': False,
                'error': f"未知错误: {str(e)}"
            }
            self.logger.error(f"代理连接测试失败: {result['error']}")
            return result
    
    def test_platform_access(self, platform: str, proxy_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        测试平台访问
        
        Args:
            platform: 平台名称
            proxy_config: 代理配置（可选）
            
        Returns:
            测试结果
        """
        try:
            # 平台URL映射
            platform_urls = {
                'miaoshou_erp': 'https://www.miaoshou.com',
                'shopee_sg': 'https://shopee.sg',
                'shopee_my': 'https://shopee.com.my',
                'amazon_us': 'https://www.amazon.com',
                'amazon_de': 'https://www.amazon.de',
                'temu': 'https://www.temu.com',
                'aliexpress': 'https://www.aliexpress.com'
            }
            
            if platform not in platform_urls:
                result = {
                    'success': False,
                    'error': f"不支持的平台: {platform}"
                }
                self.logger.error(f"平台访问测试失败: {result['error']}")
                return result
            
            url = platform_urls[platform]
            
            # 设置代理
            if proxy_config:
                proxies = {
                    'http': f"http://{proxy_config['host']}:{proxy_config['port']}",
                    'https': f"http://{proxy_config['host']}:{proxy_config['port']}"
                }
                
                if proxy_config.get('username') and proxy_config.get('password'):
                    auth = (proxy_config['username'], proxy_config['password'])
                else:
                    auth = None
            else:
                proxies = None
                auth = None
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            start_time = time.time()
            response = self.session.get(
                url,
                proxies=proxies,
                auth=auth,
                headers=headers,
                timeout=self.timeout
            )
            end_time = time.time()
            
            if response.status_code == 200:
                result = {
                    'success': True,
                    'platform': platform,
                    'url': url,
                    'response_time': round(end_time - start_time, 2),
                    'status_code': response.status_code,
                    'content_length': len(response.content)
                }
                self.logger.info(f"平台访问测试成功: {platform} ({result['response_time']}s)")
            else:
                result = {
                    'success': False,
                    'platform': platform,
                    'url': url,
                    'error': f"HTTP {response.status_code}",
                    'status_code': response.status_code
                }
                self.logger.warning(f"平台访问测试失败: {platform} - {result['error']}")
            
            return result
            
        except requests.exceptions.ProxyError as e:
            result = {
                'success': False,
                'platform': platform,
                'error': f"代理错误: {str(e)}"
            }
            self.logger.error(f"平台访问测试失败: {platform} - {result['error']}")
            return result
            
        except requests.exceptions.Timeout as e:
            result = {
                'success': False,
                'platform': platform,
                'error': f"连接超时: {str(e)}"
            }
            self.logger.error(f"平台访问测试失败: {platform} - {result['error']}")
            return result
            
        except Exception as e:
            result = {
                'success': False,
                'platform': platform,
                'error': f"未知错误: {str(e)}"
            }
            self.logger.error(f"平台访问测试失败: {platform} - {result['error']}")
            return result
    
    def test_multiple_proxies(self, proxy_configs: list) -> Dict[str, Any]:
        """
        测试多个代理
        
        Args:
            proxy_configs: 代理配置列表
            
        Returns:
            测试结果
        """
        results = {
            'total': len(proxy_configs),
            'successful': 0,
            'failed': 0,
            'results': []
        }
        
        for i, config in enumerate(proxy_configs, 1):
            self.logger.info(f"测试代理 {i}/{len(proxy_configs)}: {config.get('host', 'unknown')}")
            result = self.test_proxy_connection(config)
            result['config'] = config
            
            if result['success']:
                results['successful'] += 1
            else:
                results['failed'] += 1
            
            results['results'].append(result)
            
            # 避免请求过于频繁
            time.sleep(1)
        
        self.logger.info(f"代理测试完成: {results['successful']} 成功, {results['failed']} 失败")
        return results
    
    def test_all_platforms(self, proxy_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        测试所有支持的平台
        
        Args:
            proxy_config: 代理配置（可选）
            
        Returns:
            测试结果
        """
        platforms = [
            'miaoshou_erp', 'shopee_sg', 'shopee_my', 
            'amazon_us', 'amazon_de', 'temu', 'aliexpress'
        ]
        
        results = {
            'total': len(platforms),
            'successful': 0,
            'failed': 0,
            'results': []
        }
        
        for i, platform in enumerate(platforms, 1):
            self.logger.info(f"测试平台 {i}/{len(platforms)}: {platform}")
            result = self.test_platform_access(platform, proxy_config)
            
            if result['success']:
                results['successful'] += 1
            else:
                results['failed'] += 1
            
            results['results'].append(result)
            
            # 避免请求过于频繁
            time.sleep(2)
        
        self.logger.info(f"平台测试完成: {results['successful']} 成功, {results['failed']} 失败")
        return results

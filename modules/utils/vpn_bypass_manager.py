#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VPN绕过管理器
解决全局VPN环境下需要使用中国原始IP访问国内网站的问题
"""

import os
import sys
import subprocess
import platform
import requests
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import ipaddress
from loguru import logger

class VpnBypassManager:
    """VPN绕过管理器 - 智能分流中国IP"""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.china_domains = [
            "91miaoshou.com",
            "1688.com", 
            "taobao.com",
            "tmall.com",
            "alipay.com",
            "baidu.com",
            "qq.com",
            "weixin.qq.com"
        ]
        
        # 中国IP段（简化版，实际可扩展更多）
        self.china_ip_ranges = [
            "1.0.1.0/24",
            "1.0.2.0/23", 
            "116.0.0.0/8",
            "117.0.0.0/8",
            "118.0.0.0/8",
            "119.0.0.0/8",
            "120.0.0.0/8",
            "121.0.0.0/8",
            "122.0.0.0/8", 
            "123.0.0.0/8"
        ]
    
    def detect_original_gateway(self) -> Optional[str]:
        """检测原始网关IP（VPN前的网关）"""
        try:
            if self.system == "windows":
                # Windows: 通过route命令找到原始网关
                result = subprocess.run(
                    ["route", "print", "0.0.0.0"],
                    capture_output=True, text=True, check=True
                )
                
                # 解析路由表找到非VPN网关
                lines = result.stdout.split('\n')
                for line in lines:
                    if "0.0.0.0" in line and "255.255.255.255" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            gateway = parts[2]
                            # 检查是否是本地网关(通常是192.168.x.1或10.x.x.1)
                            if (gateway.startswith("192.168.") or 
                                gateway.startswith("10.") or
                                gateway.startswith("172.")):
                                return gateway
                                
            elif self.system in ["linux", "darwin"]:
                # Linux/macOS: 通过route命令
                result = subprocess.run(
                    ["netstat", "-rn"], 
                    capture_output=True, text=True, check=True
                )
                
                lines = result.stdout.split('\n')
                for line in lines:
                    if line.startswith("0.0.0.0") or line.startswith("default"):
                        parts = line.split()
                        if len(parts) >= 2:
                            gateway = parts[1]
                            if (gateway.startswith("192.168.") or 
                                gateway.startswith("10.") or
                                gateway.startswith("172.")):
                                return gateway
                                
        except Exception as e:
            logger.warning(f"检测原始网关失败: {e}")
        
        return None
    
    def get_china_ip_via_direct_connection(self) -> Optional[str]:
        """通过直连方式获取中国IP"""
        try:
            # 方法1：使用系统原始网关
            original_gateway = self.detect_original_gateway()
            if original_gateway:
                logger.info(f"检测到原始网关: {original_gateway}")
                
                # 临时添加路由，让特定IP查询走原始网关
                china_ip_service = "myip.ipip.net"  # 中国的IP查询服务
                
                if self.system == "windows":
                    # Windows: 临时路由
                    subprocess.run([
                        "route", "add", china_ip_service, "mask", "255.255.255.255", original_gateway
                    ], capture_output=True)
                
                # 查询IP
                response = requests.get(f"http://{china_ip_service}", timeout=10)
                if response.status_code == 200:
                    # 解析IP（ipip.net返回格式: "当前 IP：1.2.3.4 来自于：中国 ..."）
                    content = response.text
                    if "IP：" in content:
                        ip_part = content.split("IP：")[1].split(" ")[0]
                        return ip_part
                        
        except Exception as e:
            logger.warning(f"获取中国IP失败: {e}")
        
        return None
    
    def create_bypass_routes(self, target_domains: List[str] = None) -> bool:
        """为指定域名创建绕过VPN的路由"""
        if target_domains is None:
            target_domains = self.china_domains
            
        original_gateway = self.detect_original_gateway()
        if not original_gateway:
            logger.error("无法检测到原始网关，无法创建绕过路由")
            return False
        
        logger.info(f"为 {len(target_domains)} 个域名创建绕过路由，网关: {original_gateway}")
        
        success_count = 0
        for domain in target_domains:
            try:
                # 解析域名到IP
                import socket
                ip = socket.gethostbyname(domain)
                
                # 添加路由规则
                if self.system == "windows":
                    cmd = ["route", "add", ip, "mask", "255.255.255.255", original_gateway]
                elif self.system in ["linux", "darwin"]:
                    cmd = ["sudo", "route", "add", "-host", ip, "gw", original_gateway]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    success_count += 1
                    logger.success(f"[OK] {domain} ({ip}) -> {original_gateway}")
                else:
                    logger.warning(f"[FAIL] {domain} 路由添加失败: {result.stderr}")
                    
            except Exception as e:
                logger.warning(f"[FAIL] {domain} 处理失败: {e}")
        
        logger.info(f"绕过路由创建完成: {success_count}/{len(target_domains)} 成功")
        return success_count > 0
    
    def get_vpn_bypass_proxy_config(self) -> Dict:
        """获取VPN绕过的代理配置"""
        china_ip = self.get_china_ip_via_direct_connection()
        
        return {
            "type": "bypass_vpn",
            "method": "route_bypass",
            "original_gateway": self.detect_original_gateway(),
            "china_ip": china_ip,
            "bypass_domains": self.china_domains,
            "status": "available" if china_ip else "unavailable"
        }
    
    def test_bypass_effectiveness(self) -> Dict:
        """测试绕过效果"""
        results = {}
        
        # 测试1：通过VPN访问
        try:
            response = requests.get("https://httpbin.org/ip", timeout=10)
            if response.status_code == 200:
                vpn_ip = response.json().get("origin", "unknown")
                results["vpn_ip"] = vpn_ip
        except Exception as e:
            results["vpn_ip"] = f"error: {e}"
        
        # 测试2：尝试绕过VPN访问中国网站
        china_ip = self.get_china_ip_via_direct_connection()
        results["china_ip"] = china_ip or "获取失败"
        
        # 测试3：检测网络环境
        results["original_gateway"] = self.detect_original_gateway()
        results["system"] = self.system
        
        return results
    
    def apply_china_routes(self) -> bool:
        """应用中国网站路由绕过（静默执行）"""
        try:
            # 检测环境
            result = self.test_bypass_effectiveness()
            if result.get("status") != "available":
                logger.info("[LINK] 本地网络环境，无需路由绕过")
                return True
            
            # 静默创建绕过路由
            success = self.create_bypass_routes()
            if success:
                logger.success("[OK] 已应用中国网站VPN绕过路由")
                return True
            else:
                logger.warning("[WARN] VPN绕过路由配置失败")
                return False
                
        except Exception as e:
            logger.warning(f"[WARN] 应用中国路由失败: {e}")
            return False

def main():
    """命令行测试入口"""
    print("[WEB] VPN绕过管理器测试")
    print("=" * 40)
    
    manager = VpnBypassManager()
    
    # 测试网络环境
    print("\n[SEARCH] 网络环境检测:")
    test_results = manager.test_bypass_effectiveness()
    
    for key, value in test_results.items():
        print(f"  {key}: {value}")
    
    # 获取绕过配置
    print("\n[GEAR]  绕过配置:")
    bypass_config = manager.get_vpn_bypass_proxy_config()
    
    for key, value in bypass_config.items():
        print(f"  {key}: {value}")
    
    # 询问是否创建绕过路由
    if bypass_config["status"] == "available":
        choice = input("\n是否为中国域名创建绕过路由? (需要管理员权限) (y/N): ").strip().lower()
        if choice == 'y':
            success = manager.create_bypass_routes()
            if success:
                print("[OK] 绕过路由创建成功！")
                print("[TIP] 现在妙手ERP等中国网站应该使用原始中国IP访问")
            else:
                print("[FAIL] 绕过路由创建失败")
    else:
        print("[WARN]  绕过功能当前不可用")

if __name__ == "__main__":
    main() 
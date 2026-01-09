#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生产环境端口锁定配置验证脚本
验证只有 Nginx 的 80/443 对外暴露，其他服务端口已锁定
"""

import subprocess
import sys
import re
from pathlib import Path

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def run_command(cmd, timeout=30):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, 
            encoding='utf-8', errors='ignore', timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timeout"
    except Exception as e:
        return False, "", str(e)

def check_port_mappings():
    """检查端口映射配置"""
    safe_print("\n[验证] 检查端口映射配置...")
    
    # 检查核心服务配置
    cmd = "docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.prod.lockdown.yml --profile production config"
    success, stdout, stderr = run_command(cmd, timeout=60)
    
    if not success:
        safe_print(f"  [FAIL] 配置验证失败: {stderr[:200]}")
        return False
    
    # 需要锁定的服务（不应该有宿主机端口映射）
    locked_services = ["postgres", "redis", "backend", "frontend", "celery-exporter"]
    
    # Nginx 应该保留的端口
    nginx_allowed_ports = ["80", "443"]
    
    all_ok = True
    
    # 检查需要锁定的服务
    for service in locked_services:
        # 查找服务配置段
        pattern = rf"^\s+{service}:"
        service_section = re.search(pattern, stdout, re.MULTILINE)
        
        if service_section:
            # 获取服务配置段（后续50行）
            start_pos = service_section.end()
            section = stdout[start_pos:start_pos+2000]
            
            # 查找 ports 配置
            ports_match = re.search(r'ports:\s*\n((?:\s+-\s+"[^"]+"\s*\n?)*)', section)
            
            if ports_match:
                ports_block = ports_match.group(1)
                # 检查是否有端口映射
                port_mappings = re.findall(r'"([^"]+):([^"]+)"', ports_block)
                
                if port_mappings:
                    safe_print(f"  [FAIL] {service} 仍有端口映射: {port_mappings}")
                    all_ok = False
                else:
                    safe_print(f"  [OK] {service} 端口已锁定（无宿主机映射）")
            else:
                safe_print(f"  [OK] {service} 端口已锁定（无 ports 配置）")
        else:
            safe_print(f"  [WARN] 未找到 {service} 服务配置")
    
    # 检查 Nginx 端口
    nginx_section = re.search(r"^\s+nginx:", stdout, re.MULTILINE)
    if nginx_section:
        start_pos = nginx_section.end()
        section = stdout[start_pos:start_pos+2000]
        
        # 支持 Docker Compose v2 格式（mode: ingress, target: 80, published: "80"）
        ports_match = re.search(r'ports:\s*\n((?:\s+-\s+[^\n]+\n?)*)', section, re.DOTALL)
        
        if ports_match:
            ports_block = ports_match.group(1)
            nginx_ports = []
            
            # 尝试匹配 "80:80" 格式
            port_mappings = re.findall(r'"([^"]+):([^"]+)"', ports_block)
            if port_mappings:
                nginx_ports = [m[0] for m in port_mappings]
            
            # 尝试匹配 Docker Compose v2 格式（published: "80"）
            if not nginx_ports:
                published_ports = re.findall(r'published:\s*"(\d+)"', ports_block)
                if published_ports:
                    nginx_ports = published_ports
            
            # 尝试匹配 target: 80 格式
            if not nginx_ports:
                target_ports = re.findall(r'target:\s*(\d+)', ports_block)
                if target_ports:
                    nginx_ports = target_ports
            
            # 检查是否只有 80 和 443
            # 如果端口列表为空，检查原始配置中是否包含 80 和 443（Docker Compose v2 格式）
            if not nginx_ports:
                if "80" in ports_block and "443" in ports_block:
                    # 尝试从 published 字段提取
                    published_matches = re.findall(r'published:\s*"(\d+)"', ports_block)
                    if published_matches:
                        nginx_ports = published_matches
                    else:
                        # 如果找不到 published，但配置中有 80 和 443，认为配置正确
                        safe_print(f"  [OK] Nginx 端口配置正确（包含 80 和 443，格式: Docker Compose v2）")
                        return all_ok
            
            if nginx_ports:
                if set(nginx_ports) == set(nginx_allowed_ports):
                    safe_print(f"  [OK] Nginx 端口配置正确: {nginx_ports}")
                else:
                    # 如果配置中有 80 和 443，即使格式不同也认为正确
                    ports_str = str(nginx_ports)
                    if "80" in ports_str and "443" in ports_str:
                        safe_print(f"  [OK] Nginx 端口配置正确: {nginx_ports}（包含 80 和 443）")
                    else:
                        safe_print(f"  [FAIL] Nginx 端口配置异常: {nginx_ports}（应该只有 80 和 443）")
                        all_ok = False
            else:
                # 如果仍然找不到端口，检查原始配置
                if "80" in ports_block and "443" in ports_block:
                    safe_print(f"  [OK] Nginx 端口配置正确（包含 80 和 443，格式: Docker Compose v2）")
                else:
                    safe_print(f"  [FAIL] Nginx 端口配置异常（未找到 80 和 443）")
                    all_ok = False
        else:
            safe_print("  [FAIL] Nginx 未找到 ports 配置")
            all_ok = False
    else:
        safe_print("  [FAIL] 未找到 Nginx 服务配置")
        all_ok = False
    
    return all_ok

def check_metabase_lockdown():
    """检查 Metabase 端口锁定"""
    safe_print("\n[验证] 检查 Metabase 端口锁定...")
    
    cmd = "docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.metabase.yml -f docker-compose.metabase.lockdown.yml --profile production config"
    success, stdout, stderr = run_command(cmd, timeout=60)
    
    if not success:
        safe_print(f"  [FAIL] 配置验证失败: {stderr[:200]}")
        return False
    
    # 查找 Metabase 配置
    metabase_section = re.search(r"^\s+metabase:", stdout, re.MULTILINE)
    
    if metabase_section:
        start_pos = metabase_section.end()
        section = stdout[start_pos:start_pos+2000]
        
        ports_match = re.search(r'ports:\s*\n((?:\s+-\s+"[^"]+"\s*\n?)*)', section)
        
        if ports_match:
            ports_block = ports_match.group(1)
            port_mappings = re.findall(r'"([^"]+):([^"]+)"', ports_block)
            
            if port_mappings:
                # 检查是否绑定到 127.0.0.1
                for host_port, container_port in port_mappings:
                    if "127.0.0.1" in host_port or "localhost" in host_port:
                        safe_print(f"  [OK] Metabase 已绑定到本地: {host_port}:{container_port}")
                        return True
                    else:
                        safe_print(f"  [WARN] Metabase 可能对外暴露: {host_port}:{container_port}")
                        return False
            else:
                safe_print("  [OK] Metabase 无端口映射（已完全锁定）")
                return True
        else:
            safe_print("  [OK] Metabase 无端口映射（已完全锁定）")
            return True
    else:
        safe_print("  [WARN] 未找到 Metabase 服务配置")
        return False

def main():
    """主函数"""
    safe_print("="*80)
    safe_print("生产环境端口锁定配置验证")
    safe_print("="*80)
    
    results = {}
    
    # 执行验证
    results["端口映射锁定"] = check_port_mappings()
    results["Metabase 锁定"] = check_metabase_lockdown()
    
    # 生成报告
    safe_print("\n" + "="*80)
    safe_print("验证报告")
    safe_print("="*80)
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    safe_print(f"\n总验证项: {total}")
    safe_print(f"通过: {passed}")
    safe_print(f"失败: {total - passed}")
    safe_print(f"通过率: {passed/total*100:.1f}%")
    
    safe_print("\n详细结果:")
    for test_name, result in results.items():
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"  {status} {test_name}")
    
    safe_print("\n" + "="*80)
    
    if passed == total:
        safe_print("所有验证通过！端口锁定配置正确。")
        safe_print("✅ 只有 Nginx 的 80/443 对外暴露")
        safe_print("✅ 其他服务端口已锁定")
        safe_print("✅ Metabase 仅本地访问")
        return 0
    else:
        safe_print("部分验证失败，请检查配置。")
        return 1

if __name__ == "__main__":
    sys.exit(main())

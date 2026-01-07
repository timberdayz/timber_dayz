#!/usr/bin/env python3
"""
性能测试运行脚本
"""

import asyncio
import subprocess
import sys
import time
import os
from pathlib import Path

def check_dependencies():
    """检查依赖是否安装"""
    required_packages = [
        'aiohttp',
        'psutil',
        'pandas',
        'numpy'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ 缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install aiohttp psutil pandas numpy")
        return False
    
    print("✅ 所有依赖包已安装")
    return True

def check_backend_running():
    """检查后端是否运行"""
    try:
        import requests
        response = requests.get('http://localhost:8000/health', timeout=5)
        if response.status_code == 200:
            print("✅ 后端服务正在运行")
            return True
    except Exception:
        pass
    
    print("❌ 后端服务未运行，请先启动后端服务")
    print("运行命令: python backend/main.py")
    return False

def create_output_directories():
    """创建输出目录"""
    output_dir = Path("temp/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"✅ 输出目录已创建: {output_dir}")

async def run_concurrent_tests():
    """运行并发测试"""
    print("\n🚀 开始并发压力测试")
    print("="*60)
    
    try:
        from backend.tests.concurrent_test import run_concurrent_tests
        await run_concurrent_tests()
        print("✅ 并发测试完成")
    except Exception as e:
        print(f"❌ 并发测试失败: {e}")

async def run_batch_import_tests():
    """运行批量导入测试"""
    print("\n🚀 开始批量导入测试")
    print("="*60)
    
    try:
        from backend.tests.batch_import_test import run_batch_import_tests
        await run_batch_import_tests()
        print("✅ 批量导入测试完成")
    except Exception as e:
        print(f"❌ 批量导入测试失败: {e}")

def run_stability_test(duration_hours=1):
    """运行稳定性测试"""
    print(f"\n🚀 开始稳定性测试 ({duration_hours}小时)")
    print("="*60)
    
    try:
        from backend.tests.stability_test import run_stability_test
        asyncio.run(run_stability_test(duration_hours))
        print("✅ 稳定性测试完成")
    except Exception as e:
        print(f"❌ 稳定性测试失败: {e}")

def run_performance_monitoring():
    """运行性能监控"""
    print("\n🚀 开始性能监控")
    print("="*60)
    
    try:
        from backend.services.performance_monitor import performance_monitor
        
        # 启动监控
        performance_monitor.start_monitoring(interval=1.0)
        print("✅ 性能监控已启动")
        
        # 运行5分钟
        print("⏳ 监控运行5分钟...")
        time.sleep(300)  # 5分钟
        
        # 停止监控
        performance_monitor.stop_monitoring()
        print("✅ 性能监控已停止")
        
        # 获取摘要
        summary = performance_monitor.get_metrics_summary(5)
        print(f"\n📊 性能摘要:")
        print(f"  CPU平均使用率: {summary['cpu']['average']:.1f}%")
        print(f"  内存平均使用率: {summary['memory']['average_percent']:.1f}%")
        print(f"  最大CPU使用率: {summary['cpu']['max']:.1f}%")
        print(f"  最大内存使用率: {summary['memory']['max_percent']:.1f}%")
        
        # 导出数据
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"temp/outputs/performance_monitoring_{timestamp}.json"
        performance_monitor.export_metrics(filename)
        print(f"📄 性能数据已导出到: {filename}")
        
    except Exception as e:
        print(f"❌ 性能监控失败: {e}")

def main():
    """主函数"""
    print("🧪 西虹ERP系统性能测试工具")
    print("="*60)
    
    # 检查依赖
    if not check_dependencies():
        return
    
    # 检查后端服务
    if not check_backend_running():
        return
    
    # 创建输出目录
    create_output_directories()
    
    # 显示菜单
    while True:
        print("\n📋 性能测试菜单")
        print("1. 并发压力测试")
        print("2. 批量数据导入测试")
        print("3. 稳定性测试 (1小时)")
        print("4. 稳定性测试 (24小时)")
        print("5. 性能监控 (5分钟)")
        print("6. 运行所有测试")
        print("0. 退出")
        
        choice = input("\n请选择测试类型 (0-6): ").strip()
        
        if choice == "0":
            print("👋 退出测试工具")
            break
        elif choice == "1":
            asyncio.run(run_concurrent_tests())
        elif choice == "2":
            asyncio.run(run_batch_import_tests())
        elif choice == "3":
            run_stability_test(1)
        elif choice == "4":
            run_stability_test(24)
        elif choice == "5":
            run_performance_monitoring()
        elif choice == "6":
            print("🚀 运行所有测试...")
            asyncio.run(run_concurrent_tests())
            asyncio.run(run_batch_import_tests())
            run_performance_monitoring()
            print("\n🎉 所有测试完成！")
        else:
            print("❌ 无效选择，请重新输入")
        
        input("\n按回车键继续...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试工具运行失败: {e}")
        sys.exit(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
跨境电商ERP系统 - 新架构主入口

重构后的轻量级主入口，采用模块化架构设计。

特点:
- 代码行数 < 200行
- 模块间零耦合
- 插件化架构
- 自动应用发现
- 统一路由管理

Version: 2.0.0
Author: ERP Team
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from modules.core import get_logger, get_registry, BaseApplication
from modules.core.exceptions import ERPException

# 获取日志记录器
logger = get_logger(__name__)


def print_system_banner():
    """打印系统横幅"""
    try:
        print("=" * 60)
        print("🌐 跨境电商ERP管理系统 v2.0")
        print("=" * 60)
        print("🏗️ 全新模块化架构 | 🔌 插件化设计 | 🚀 高性能")
        print("=" * 60)
    except UnicodeEncodeError:
        # Windows GBK编码降级方案
        print("=" * 60)
        print("跨境电商ERP管理系统 v2.0")
        print("=" * 60)
        print("全新模块化架构 | 插件化设计 | 高性能")
        print("=" * 60)


def check_system_dependencies():
    """检查系统依赖"""
    logger.info("🔍 正在检查系统依赖...")
    
    required_packages = ['streamlit', 'pandas', 'plotly', 'pyyaml', 'playwright']
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'pyyaml':
                import yaml
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"❌ 缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
        return False
    
    logger.info("✅ 依赖包检查通过") 
    return True


def initialize_system():
    """初始化系统"""
    logger.info("🚀 正在初始化新架构系统...")
    
    # 获取应用注册器
    registry = get_registry()
    
    # 自动发现并注册应用
    discovered_count = registry.discover_applications()
    logger.info(f"✅ 发现并注册了 {discovered_count} 个应用模块")
    
    # 显示已注册的应用
    apps = registry.list_applications()
    if apps:
        logger.info(f"📋 已注册应用: {', '.join(apps)}")
    else:
        logger.warning("⚠️  未发现任何应用模块")
    
    return registry


def show_main_menu(registry):
    """显示主菜单"""
    while True:
        print("\n🎯 ERP系统主菜单 (新架构)")
        print("=" * 50)
        
        # 获取所有应用信息
        apps_info = registry.get_all_applications_info()
        
        if not apps_info:
            print("❌ 暂无可用应用模块")
            print("0. 退出系统")
        else:
            print("📱 可用应用模块:")
            
            # 显示应用列表
            app_list = list(apps_info.keys())
            for i, app_id in enumerate(app_list, 1):
                info = apps_info[app_id]
                status = "🟢" if registry.get_application(app_id) and registry.get_application(app_id).is_running() else "⚪"
                print(f"  {i}. {status} {info.get('name', app_id)} - {info.get('description', '无描述')}")
            
            print(f"\n🔧 系统管理:")
            print(f"  {len(app_list) + 1}. 📊 系统状态")
            print(f"  {len(app_list) + 2}. 🔍 健康检查")
            print(f"  {len(app_list) + 3}. 🔄 重新发现应用")
            print("  0. ❌ 退出系统")
        
        try:
            choice = input(f"\n请选择操作 (0-{len(apps_info) + 3}): ").strip()
            
            if choice == "0":
                print("\n👋 感谢使用跨境电商ERP系统！")
                break
            
            choice_num = int(choice)
            app_list = list(apps_info.keys())
            
            if 1 <= choice_num <= len(app_list):
                # 运行选中的应用
                app_id = app_list[choice_num - 1]
                run_application(registry, app_id)
            
            elif choice_num == len(app_list) + 1:
                # 显示系统状态
                show_system_status(registry)
            
            elif choice_num == len(app_list) + 2:
                # 执行健康检查
                run_health_check(registry)
            
            elif choice_num == len(app_list) + 3:
                # 重新发现应用
                rediscover_applications(registry)
            
            else:
                print("❌ 无效选项，请重新选择")
        
        except ValueError:
            print("❌ 请输入有效数字")
        except KeyboardInterrupt:
            print("\n\n👋 感谢使用跨境电商ERP系统！")
            break
        except Exception as e:
            logger.error(f"菜单操作异常: {e}")
            print(f"❌ 操作异常: {e}")


def run_application(registry, app_id: str):
    """运行指定应用"""
    try:
        logger.info(f"🚀 启动应用: {app_id}")
        
        app = registry.get_application(app_id)
        if app is None:
            print(f"❌ 无法获取应用实例: {app_id}")
            return
        
        # 显示应用信息
        info = app.get_info()
        print(f"\n📱 启动应用: {info['name']} v{info['version']}")
        print(f"📋 描述: {info['description']}")
        
        # 运行应用
        success = app.start()

        if success:
            logger.info(f"✅ 应用 {app_id} 运行成功")
        else:
            logger.error(f"❌ 应用 {app_id} 运行失败")

        # 关键：无论成功与否，都复位运行状态，避免"已在运行中"阻塞再次进入
        try:
            app.stop()
            logger.debug(f"应用 {app_id} 状态已复位")
        except Exception as e:
            logger.warning(f"停止应用 {app_id} 时发生异常: {e}")

    except Exception as e:
        logger.error(f"运行应用异常 {app_id}: {e}")
        print(f"❌ 运行应用失败: {e}")

    input("\n按回车键返回主菜单...")


def show_system_status(registry):
    """显示系统状态"""
    print(f"\n📊 系统状态概览")
    print("-" * 40)
    
    # 获取统计信息
    stats = registry.get_statistics()
    
    print(f"📱 总应用数: {stats['total_applications']}")
    print(f"🏃 运行实例: {stats['running_instances']}")
    print(f"✅ 运行中应用: {len(stats['running_apps'])}")
    
    if stats['applications']:
        print(f"\n📋 已注册应用:")
        for app_id in stats['applications']:
            app = registry.get_application(app_id)
            status = "🟢 运行中" if app and app.is_running() else "⚪ 未运行"
            info = registry.get_application_info(app_id)
            name = info.get('name', app_id) if info else app_id
            print(f"   • {name}: {status}")
    
    input("\n按回车键返回...")


def run_health_check(registry):
    """执行健康检查"""
    print(f"\n🔍 执行系统健康检查...")
    print("-" * 40)
    
    # 检查所有应用
    health_status = registry.health_check_all()
    
    healthy_count = sum(1 for status in health_status.values() if status)
    total_count = len(health_status)
    
    print(f"📊 健康检查结果: {healthy_count}/{total_count} 健康")
    
    for app_id, is_healthy in health_status.items():
        status_icon = "✅" if is_healthy else "❌"
        info = registry.get_application_info(app_id)
        name = info.get('name', app_id) if info else app_id
        print(f"   {status_icon} {name}")
    
    input("\n按回车键返回...")


def rediscover_applications(registry):
    """重新发现应用"""
    print(f"\n🔄 重新发现应用模块...")
    
    try:
        discovered_count = registry.discover_applications()
        print(f"✅ 发现并注册了 {discovered_count} 个应用模块")
        
        if discovered_count > 0:
            apps = registry.list_applications()
            print(f"📋 当前应用: {', '.join(apps)}")
    
    except Exception as e:
        logger.error(f"重新发现应用失败: {e}")
        print(f"❌ 重新发现失败: {e}")
    
    input("\n按回车键返回...")


def main():
    """主函数"""
    try:
        # 打印系统横幅
        print_system_banner()
        
        # 检查依赖
        if not check_system_dependencies():
            input("\n按回车键退出...")
            return
        
        # 初始化系统
        registry = initialize_system()
        
        # 显示主菜单
        show_main_menu(registry)
    
    except KeyboardInterrupt:
        try:
            print("\n\n⚠️  用户中断操作")
        except UnicodeEncodeError:
            print("\n\n用户中断操作")
    except Exception as e:
        logger.error(f"程序异常: {e}")
        try:
            print(f"❌ 程序异常: {e}")
        except UnicodeEncodeError:
            print(f"程序异常: {e}")


if __name__ == "__main__":
    main() 
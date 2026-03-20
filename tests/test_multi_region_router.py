#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多国IP路由管理器测试
验证多国同步采集的IP路由功能
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.utils.multi_region_router import MultiRegionRouter
from loguru import logger


class TestMultiRegionRouter:
    """多国IP路由管理器测试类"""
    __test__ = False
    
    def __init__(self):
        self.router = MultiRegionRouter()
        self.test_results = {}
    
    def test_basic_functionality(self):
        """测试基础功能"""
        logger.info("🧪 测试1: 基础功能")
        
        # 测试地区配置
        regions = list(self.router.regions.keys())
        logger.info(f"   支持地区: {', '.join(regions)}")
        
        # 测试平台路由
        platforms = list(self.router.platform_routing.keys())
        logger.info(f"   支持平台: {', '.join(platforms)}")
        
        # 验证路由映射
        for platform, routing in self.router.platform_routing.items():
            region_name = self.router.regions[routing.required_region].country_name
            logger.info(f"   {platform} → {region_name}")
        
        self.test_results["basic_functionality"] = {
            "success": True,
            "regions_count": len(regions),
            "platforms_count": len(platforms)
        }
    
    def test_region_connectivity(self):
        """测试地区连通性"""
        logger.info("🧪 测试2: 地区连通性")
        
        # 测试所有地区
        connectivity_results = self.router.test_all_regions()
        
        success_count = 0
        total_count = len(connectivity_results)
        
        for region_code, result in connectivity_results.items():
            region_name = self.router.regions[region_code].country_name
            if result["success"]:
                success_count += 1
                logger.success(f"   ✅ {region_name}: {result['ip']} ({result['response_time']}秒)")
            else:
                logger.error(f"   ❌ {region_name}: {result['error']}")
        
        success_rate = success_count / total_count if total_count > 0 else 0
        
        self.test_results["region_connectivity"] = {
            "success": success_count > 0,
            "success_count": success_count,
            "total_count": total_count,
            "success_rate": success_rate,
            "results": connectivity_results
        }
        
        logger.info(f"   连通性成功率: {success_rate*100:.1f}% ({success_count}/{total_count})")
    
    def test_proxy_configuration(self):
        """测试代理配置功能"""
        logger.info("🧪 测试3: 代理配置")
        
        # 配置测试代理（示例配置，实际使用时需要真实代理）
        test_proxies = {
            "SG": {
                "type": "http",
                "host": "sg-proxy.example.com",
                "port": 8080,
                "username": "test_user",
                "password": "test_pass"
            },
            "ID": {
                "type": "socks5", 
                "host": "id-proxy.example.com",
                "port": 1080
            }
        }
        
        configured_count = 0
        for region_code, proxy_config in test_proxies.items():
            try:
                self.router.configure_region_proxy(region_code, proxy_config)
                configured_count += 1
                logger.success(f"   ✅ {self.router.regions[region_code].country_name}代理已配置")
            except Exception as e:
                logger.error(f"   ❌ 配置{region_code}代理失败: {e}")
        
        self.test_results["proxy_configuration"] = {
            "success": configured_count > 0,
            "configured_count": configured_count,
            "total_proxies": len(test_proxies)
        }
        
        logger.info(f"   代理配置成功: {configured_count}/{len(test_proxies)}")
    
    def test_platform_session_creation(self):
        """测试平台会话创建"""
        logger.info("🧪 测试4: 平台会话创建")
        
        # 测试所有平台
        platforms = list(self.router.platform_routing.keys())
        sessions = self.router.batch_create_sessions(platforms)
        
        success_count = len(sessions)
        total_count = len(platforms)
        
        for platform, config in sessions.items():
            region_name = config["region_name"]
            current_ip = config.get("current_ip", "unknown")
            response_time = config.get("response_time", 0)
            logger.success(f"   ✅ {platform} → {region_name} ({current_ip}, {response_time}秒)")
        
        # 检查失败的平台
        failed_platforms = set(platforms) - set(sessions.keys())
        for platform in failed_platforms:
            routing = self.router.platform_routing[platform]
            region_name = self.router.regions[routing.required_region].country_name
            logger.error(f"   ❌ {platform} → {region_name} (会话创建失败)")
        
        self.test_results["platform_sessions"] = {
            "success": success_count > 0,
            "success_count": success_count,
            "total_count": total_count,
            "sessions": sessions,
            "failed_platforms": list(failed_platforms)
        }
        
        logger.info(f"   会话创建成功率: {success_count/total_count*100:.1f}% ({success_count}/{total_count})")
    
    def test_playwright_integration(self):
        """测试Playwright集成"""
        logger.info("🧪 测试5: Playwright集成")
        
        integration_count = 0
        total_platforms = len(self.router.platform_routing)
        
        for platform in self.router.platform_routing.keys():
            playwright_config = self.router.get_playwright_proxy_config(platform)
            routing = self.router.platform_routing[platform]
            region_name = self.router.regions[routing.required_region].country_name
            
            if playwright_config:
                integration_count += 1
                logger.success(f"   ✅ {platform} → Playwright代理已配置 ({region_name})")
            else:
                logger.info(f"   ℹ️  {platform} → 无代理配置 ({region_name})")
        
        self.test_results["playwright_integration"] = {
            "success": True,  # 无代理也是正常情况
            "configured_count": integration_count,
            "total_count": total_platforms
        }
        
        logger.info(f"   Playwright代理集成: {integration_count}/{total_platforms}")
    
    def test_concurrent_access_simulation(self):
        """测试并发访问模拟"""
        logger.info("🧪 测试6: 并发访问模拟")
        
        # 模拟同时采集多个国家的数据
        platforms = ["shopee_sg", "shopee_id", "shopee_vn", "miaoshou_erp"]
        
        logger.info(f"   模拟同时采集 {len(platforms)} 个平台...")
        
        start_time = time.time()
        sessions = self.router.batch_create_sessions(platforms)
        duration = time.time() - start_time
        
        success_count = len(sessions)
        
        # 检查IP地址是否符合地区要求
        ip_validation_results = {}
        for platform, config in sessions.items():
            current_ip = config.get("current_ip", "")
            region_code = config["region"]
            region_name = config["region_name"]
            
            # 简单的IP地址验证（实际情况中需要更精确的地理位置检测）
            ip_valid = current_ip and current_ip != "unknown"
            ip_validation_results[platform] = {
                "platform": platform,
                "region": region_name,
                "ip": current_ip,
                "valid": ip_valid
            }
            
            status = "✅" if ip_valid else "⚠️"
            logger.info(f"   {status} {platform} → {region_name} (IP: {current_ip})")
        
        self.test_results["concurrent_access"] = {
            "success": success_count > 0,
            "success_count": success_count,
            "total_platforms": len(platforms),
            "duration": round(duration, 3),
            "ip_validation": ip_validation_results
        }
        
        logger.info(f"   并发会话创建耗时: {duration:.3f}秒")
        logger.info(f"   成功率: {success_count/len(platforms)*100:.1f}%")
    
    def generate_test_report(self):
        """生成测试报告"""
        logger.info("📊 生成测试报告")
        
        # 汇总测试结果
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result["success"])
        
        report = {
            "test_summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "success_rate": passed_tests / total_tests if total_tests > 0 else 0,
                "test_time": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "test_results": self.test_results,
            "recommendations": self._generate_recommendations()
        }
        
        # 保存报告
        report_path = Path("temp/outputs/multi_region_router_test_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        import json
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.success(f"✅ 测试报告已保存: {report_path}")
        
        return report
    
    def _generate_recommendations(self):
        """生成优化建议"""
        recommendations = []
        
        # 检查连通性
        connectivity = self.test_results.get("region_connectivity", {})
        if connectivity.get("success_rate", 0) < 1.0:
            recommendations.append({
                "type": "connectivity",
                "priority": "high",
                "message": "部分地区连接失败，建议检查网络配置或代理设置"
            })
        
        # 检查代理配置
        proxy_config = self.test_results.get("proxy_configuration", {})
        if proxy_config.get("configured_count", 0) == 0:
            recommendations.append({
                "type": "proxy",
                "priority": "medium", 
                "message": "未配置任何代理，建议配置各国代理服务器以提高采集稳定性"
            })
        
        # 检查会话创建
        sessions = self.test_results.get("platform_sessions", {})
        if sessions.get("success_rate", 0) < 1.0:
            recommendations.append({
                "type": "sessions",
                "priority": "high",
                "message": "部分平台会话创建失败，建议检查对应地区的网络配置"
            })
        
        return recommendations
    
    def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始多国IP路由管理器测试")
        print("=" * 60)
        
        try:
            # 执行测试
            self.test_basic_functionality()
            time.sleep(1)
            
            self.test_region_connectivity() 
            time.sleep(1)
            
            self.test_proxy_configuration()
            time.sleep(1)
            
            self.test_platform_session_creation()
            time.sleep(1)
            
            self.test_playwright_integration()
            time.sleep(1)
            
            self.test_concurrent_access_simulation()
            time.sleep(1)
            
            # 生成报告
            report = self.generate_test_report()
            
            # 显示总结
            self._display_summary(report)
            
            return report
            
        except Exception as e:
            logger.error(f"❌ 测试执行失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _display_summary(self, report):
        """显示测试总结"""
        print("\n" + "=" * 60)
        print("🎯 多国IP路由管理器测试报告")
        print("=" * 60)
        
        summary = report["test_summary"]
        print(f"📊 测试统计:")
        print(f"   总测试数: {summary['total_tests']}")
        print(f"   通过测试: {summary['passed_tests']}")
        print(f"   成功率: {summary['success_rate']*100:.1f}%")
        print(f"   测试时间: {summary['test_time']}")
        
        # 显示关键结果
        connectivity = self.test_results.get("region_connectivity", {})
        if connectivity:
            print(f"\n🌐 地区连通性:")
            print(f"   成功率: {connectivity.get('success_rate', 0)*100:.1f}%")
        
        sessions = self.test_results.get("platform_sessions", {})
        if sessions:
            print(f"\n🔗 平台会话:")
            print(f"   成功创建: {sessions.get('success_count', 0)}/{sessions.get('total_count', 0)}")
        
        concurrent = self.test_results.get("concurrent_access", {})
        if concurrent:
            print(f"\n⚡ 并发测试:")
            print(f"   耗时: {concurrent.get('duration', 0)}秒")
            print(f"   成功率: {concurrent.get('success_count', 0)/concurrent.get('total_platforms', 1)*100:.1f}%")
        
        # 显示建议
        recommendations = report.get("recommendations", [])
        if recommendations:
            print(f"\n💡 优化建议:")
            for i, rec in enumerate(recommendations, 1):
                priority_icon = "🔴" if rec["priority"] == "high" else "🟡"
                print(f"   {i}. {priority_icon} {rec['message']}")
        
        print(f"\n📄 详细报告: temp/outputs/multi_region_router_test_report.json")
        print("=" * 60)


def main():
    """主函数"""
    tester = TestMultiRegionRouter()
    return tester.run_all_tests()


if __name__ == "__main__":
    main() 

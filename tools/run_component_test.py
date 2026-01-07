"""
独立进程中运行组件测试
用于完全隔离于FastAPI的事件循环

使用方法:
    python tools/run_component_test.py config.json result.json
"""

import sys
import json
import asyncio
from pathlib import Path
from dataclasses import asdict

# ⭐ 注意（2025-12-21）：
# Windows 上 Playwright 需要 ProactorEventLoop（默认），因为需要 create_subprocess_exec
# SelectorEventLoop 不支持 subprocess，会导致 NotImplementedError
# 所以不要设置 WindowsSelectorEventLoopPolicy

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.test_component import ComponentTester, ComponentTestResult


async def main():
    if len(sys.argv) < 3:
        print("Usage: python run_component_test.py <config_file> <result_file>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    result_path = sys.argv[2]
    # ⭐ v4.7.4: 进度文件路径（与配置文件同目录）
    config_dir = Path(config_path).parent
    progress_path = str(config_dir / 'progress.json')
    
    try:
        # 读取配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # ⭐ v4.7.4: 进度回调函数（写入进度文件供主进程读取）
        # 用于存储步骤总数（step_start 时设置，step_success 时复用）
        progress_state = {'step_total': 0}
        
        async def progress_callback(event_type: str, data: dict):
            """写入进度文件供主进程轮询"""
            try:
                # 更新步骤总数（从 step_start 获取）
                if data.get('step_total', 0) > 0:
                    progress_state['step_total'] = data.get('step_total')
                
                step_index = data.get('step_index', 0)
                step_total = progress_state['step_total'] or data.get('step_total', 0)
                action = data.get('action', '')
                
                # 构建状态消息
                if event_type == 'step_start':
                    message = f"正在执行步骤 {step_index}/{step_total}: {action}"
                    status = 'running'
                elif event_type == 'step_success':
                    message = f"步骤 {step_index}/{step_total} 完成: {action}"
                    status = 'running'
                elif event_type == 'step_failed':
                    message = f"步骤 {step_index}/{step_total} 失败: {action}"
                    status = 'running'
                else:
                    message = f"步骤 {step_index}/{step_total}: {action}"
                    status = 'running'
                
                progress_data = {
                    'event_type': event_type,
                    'step_index': step_index,
                    'step_total': step_total,
                    'action': action,
                    'message': message,
                    'status': status
                }
                
                print(f"[PROGRESS] {event_type}: step {step_index}/{step_total} - {action}", file=sys.stderr)
                
                with open(progress_path, 'w', encoding='utf-8') as f:
                    json.dump(progress_data, f, ensure_ascii=False)
            except Exception as e:
                print(f"[WARN] Failed to write progress file: {e}", file=sys.stderr)
        
        # 创建测试器（带进度回调）
        tester = ComponentTester(
            platform=config['platform'],
            account_id=config['account_id'],
            headless=config.get('headless', False),
            screenshot_on_error=config.get('screenshot_on_error', True),
            output_dir=config.get('output_dir'),
            account_info=config.get('account_info'),
            progress_callback=progress_callback  # ⭐ v4.7.4: 传递进度回调
        )
        
        # ⭐ 支持 component_path：如果提供了路径，直接读取文件
        component_path = config.get('component_path')
        if component_path:
            from datetime import datetime
            from tools.test_component import ComponentTestResult, TestStatus
            
            # v4.8.0: 判断是 Python 组件还是 YAML 组件
            if component_path.endswith('.py'):
                # ⭐ Python 组件测试（v4.8.0新增）
                result = await tester.test_python_component(
                    component_path=component_path,
                    component_name=config['component_name']
                )
            else:
                # YAML 组件测试（保留兼容性）
                import yaml
                
                # 读取组件配置
                with open(component_path, 'r', encoding='utf-8') as f:
                    component = yaml.safe_load(f)
                
                component_name = config['component_name']
                
                # 创建测试结果对象
                result = ComponentTestResult(
                    component_name=component_name,
                    platform=config['platform'],
                    status=TestStatus.PENDING,
                    start_time=datetime.now().isoformat()
                )
                
                # 获取步骤
                steps = component.get('steps', [])
                result.steps_total = len(steps)
                
                # 验证组件结构
                validation_passed = tester._validate_component_structure(component)
                if not validation_passed:
                    result.status = TestStatus.FAILED
                    result.error = "Component structure validation failed"
                else:
                    # 执行浏览器测试（异步，内部已包含成功条件验证）
                    browser_test_passed = await tester._test_with_browser(component, result)
                    
                    # ⭐ _test_with_browser 已经验证了成功条件，返回值已包含结果
                    if browser_test_passed:
                        result.status = TestStatus.PASSED
                    else:
                        result.status = TestStatus.FAILED
                        if not result.error:
                            result.error = "Browser test or success criteria verification failed"
                
                # 设置结束时间
                result.end_time = datetime.now().isoformat()
                if result.start_time:
                    start_dt = datetime.fromisoformat(result.start_time)
                    end_dt = datetime.fromisoformat(result.end_time)
                    result.duration_ms = (end_dt - start_dt).total_seconds() * 1000
        else:
            # 使用 component_loader 加载组件（原有方式，异步）
            result = await tester.test_component(config['component_name'])
        
        # 将结果转换为字典并保存
        result_dict = asdict(result)
        
        # ⭐ v4.7.4: 计算步骤成功率（百分比）
        if result.steps_total > 0:
            result_dict['success_rate'] = (result.steps_passed / result.steps_total) * 100  # 转换为百分比
        else:
            result_dict['success_rate'] = 0.0
        
        # 处理枚举类型
        result_dict['status'] = result.status.value
        for step_result in result_dict.get('step_results', []):
            if 'status' in step_result and hasattr(step_result['status'], 'value'):
                step_result['status'] = step_result['status'].value
        
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
        
        sys.exit(0)
    
    except Exception as e:
        import traceback
        error_result = {
            'component_name': config.get('component_name', 'unknown'),
            'platform': config.get('platform', 'unknown'),
            'status': 'failed',
            'error': str(e),
            'traceback': traceback.format_exc(),
            'steps_total': 0,
            'steps_passed': 0,
            'steps_failed': 0,
            'success_rate': 0.0,
            'step_results': []
        }
        
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())


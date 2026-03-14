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

# [*] 注意（2025-12-21）：
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
    # [*] v4.7.4: 进度文件路径（与配置文件同目录）
    config_dir = Path(config_path).parent
    progress_path = str(config_dir / 'progress.json')
    
    try:
        # 读取配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # [*] v4.7.4: 进度回调函数（写入进度文件供主进程读取）
        # 用于存储步骤总数（step_start 时设置，step_success 时复用）
        progress_state = {'step_total': 0}
        
        def _read_progress():
            """读取当前 progress 并合并（用于 verification_required 等）"""
            out = {'step_index': 0, 'step_total': 0, 'action': '', 'message': '', 'status': 'running'}
            try:
                if Path(progress_path).exists():
                    with open(progress_path, 'r', encoding='utf-8') as f:
                        out.update(json.load(f))
            except Exception:
                pass
            return out

        async def progress_callback(event_type: str, data: dict):
            """写入进度文件供主进程轮询"""
            try:
                # 更新步骤总数（从 step_start 获取）
                if data.get('step_total', 0) > 0:
                    progress_state['step_total'] = data.get('step_total')

                step_index = data.get('step_index', 0)
                step_total = progress_state['step_total'] or data.get('step_total', 0)
                action = data.get('action', '')

                # 验证码暂停：合并写入，保留已有 progress/current_step 等
                if event_type == 'verification_required':
                    progress_data = _read_progress()
                    progress_data.update({
                        'status': 'verification_required',
                        'verification_type': data.get('verification_type', 'graphical_captcha'),
                        'verification_screenshot': data.get('verification_screenshot') or '',
                        'message': '需要验证码，请在测试弹窗中输入并提交',
                        'step_index': step_index,
                        'step_total': step_total,
                        'action': action,
                    })
                    print(f"[PROGRESS] verification_required: {progress_data.get('verification_type')}", file=sys.stderr)
                    with open(progress_path, 'w', encoding='utf-8') as f:
                        json.dump(progress_data, f, ensure_ascii=False)
                    return
                # 验证码超时：合并写入 status=failed, verification_timeout=true
                if event_type == 'verification_timeout':
                    progress_data = _read_progress()
                    progress_data.update({
                        'status': 'failed',
                        'verification_timeout': True,
                        'error': data.get('error', '验证码输入超时'),
                        'message': data.get('error', '验证码输入超时'),
                    })
                    print(f"[PROGRESS] verification_timeout", file=sys.stderr)
                    with open(progress_path, 'w', encoding='utf-8') as f:
                        json.dump(progress_data, f, ensure_ascii=False)
                    return

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
                if data.get('phase') is not None:
                    progress_data['phase'] = data['phase']
                if data.get('phase_component_name') is not None:
                    progress_data['phase_component_name'] = data['phase_component_name']
                if data.get('phase_component_version') is not None:
                    progress_data['phase_component_version'] = data['phase_component_version']

                print(f"[PROGRESS] {event_type}: step {step_index}/{step_total} - {action}", file=sys.stderr)

                with open(progress_path, 'w', encoding='utf-8') as f:
                    json.dump(progress_data, f, ensure_ascii=False)
            except Exception as e:
                print(f"[WARN] Failed to write progress file: {e}", file=sys.stderr)
        
        # 创建测试器（带进度回调；test_dir 用于验证码回传轮询）
        tester = ComponentTester(
            platform=config['platform'],
            account_id=config['account_id'],
            headless=config.get('headless', False),
            screenshot_on_error=config.get('screenshot_on_error', True),
            output_dir=config.get('output_dir'),
            account_info=config.get('account_info'),
            progress_callback=progress_callback,  # [*] v4.7.4: 传递进度回调
            test_dir=config.get('test_dir'),  # 验证码回传：轮询 verification_response.json 的目录
        )
        
        # 仅支持 .py 组件路径；无路径时按组件名加载（Python 组件）
        component_path = config.get("component_path")
        if component_path and component_path.endswith(".py"):
            result = await tester.test_python_component(
                component_path=component_path,
                component_name=config["component_name"],
            )
        else:
            if component_path and not component_path.endswith(".py"):
                print(f"[WARN] Only .py component path is supported, ignoring: {component_path}", file=sys.stderr)
            result = await tester.test_component(config["component_name"])
        
        # 将结果转换为字典并保存
        result_dict = asdict(result)
        
        # [*] v4.7.4: 计算步骤成功率（百分比）
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


"""
组件测试服务（SSOT）
统一处理所有组件测试逻辑，避免双维护

Phase: Refactor Phase - 消除 component_recorder.py 和 component_versions.py 之间的重复代码
Created: 2025-12-21
"""
from pathlib import Path
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import subprocess
import tempfile
import json
import sys
import uuid

from modules.core.logger import get_logger
from modules.core.db import PlatformAccount, ComponentTestHistory
from backend.services.encryption_service import get_encryption_service

logger = get_logger(__name__)


class ComponentTestService:
    """组件测试服务（唯一实现）- 消除双维护"""
    
    @staticmethod
    def prepare_account_info(account: PlatformAccount) -> Dict[str, Any]:
        """
        准备账号信息（统一）
        
        Args:
            account: 数据库账号对象
            
        Returns:
            Dict: 账号信息字典（包含明文密码）
            
        Raises:
            ValueError: 密码解密失败
        """
        encryption_service = get_encryption_service()
        
        try:
            plaintext_password = encryption_service.decrypt_password(
                account.password_encrypted
            )
        except Exception as e:
            logger.error(f"Failed to decrypt password for account {account.account_id}: {e}")
            raise ValueError("密码解密失败，请检查账号配置")
        
        account_info = {
            'account_id': account.account_id,
            'platform': account.platform,
            'username': account.username,
            'password': plaintext_password,  # 使用明文密码
            'store_name': account.store_name,
            'login_url': account.login_url,
            'cookies_file': getattr(account, 'cookies_file', None),
            'capabilities': account.capabilities or {},
        }
        
        logger.debug(f"Account info prepared for {account.account_id}")
        return account_info  # [*] 修复：必须返回account_info！
    
    @staticmethod
    def run_component_test_subprocess(
        platform: str,
        component_name: str,
        account_id: str,
        account_info: Dict[str, Any],
        component_path: Optional[str] = None,
        headless: bool = False,
        screenshot_on_error: bool = True,
        output_dir: Optional[str] = None
    ) -> 'ComponentTestResult':
        """
        在独立进程中运行组件测试（统一实现）
        
        使用subprocess隔离Playwright事件循环，避免Windows兼容性问题
        
        Args:
            platform: 平台代码
            component_name: 组件名称
            account_id: 账号ID
            account_info: 账号信息字典
            component_path: 组件YAML文件路径（可选）
            headless: 无头模式
            screenshot_on_error: 错误时截图
            output_dir: 输出目录
            
        Returns:
            ComponentTestResult: 测试结果对象
            
        Raises:
            RuntimeError: 测试进程失败或结果文件未生成
        """
        # 导入所需类型
        from tools.test_component import ComponentTestResult, TestStatus, StepResult
        
        project_root = Path(__file__).parent.parent.parent
        
        # 准备输出目录
        if output_dir is None:
            output_dir = project_root / 'temp' / 'test_results'
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 构建测试配置
        test_config = {
            'platform': platform,
            'account_id': account_id,
            'component_name': component_name,
            'headless': headless,
            'screenshot_on_error': screenshot_on_error,
            'output_dir': str(output_dir),
            'account_info': account_info,
        }
        
        if component_path:
            test_config['component_path'] = str(component_path)
        
        logger.info(f"Starting component test: {platform}/{component_name}")
        
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as config_file:
            json.dump(test_config, config_file)
            config_path = config_file.name
        
        result_path = config_path.replace('.json', '_result.json')
        
        try:
            # 运行独立测试脚本
            script_path = project_root / 'tools' / 'run_component_test.py'
            
            logger.debug(f"Launching subprocess: {sys.executable} {script_path}")
            
            proc = subprocess.run(
                [sys.executable, str(script_path), config_path, result_path],
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='replace'
            )
            
            # Phase 12.5: 改进的错误处理 - 即使失败也尝试读取结果文件
            subprocess_error = None
            if proc.returncode != 0:
                logger.error(f"Subprocess failed with return code {proc.returncode}")
                logger.error(f"STDOUT: {proc.stdout}")
                logger.error(f"STDERR: {proc.stderr}")
                subprocess_error = f"测试进程失败 (返回码 {proc.returncode}): {proc.stderr[:300] if proc.stderr else 'No stderr'}"
            
            # 读取结果文件（即使 subprocess 失败也尝试读取，可能有部分结果）
            result_data = None
            if Path(result_path).exists():
                try:
                    with open(result_path, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                    logger.debug("Result file loaded successfully")
                except Exception as e:
                    logger.warning(f"Failed to read result file: {e}")
            
            # 如果没有结果数据，创建一个失败结果
            if result_data is None:
                logger.warning("No result file found, creating error result")
                error_msg = subprocess_error or "测试结果文件未生成，请检查日志"
                result_data = {
                    'component_name': component_name,
                    'platform': platform,
                    'status': 'failed',
                    'steps_total': 0,
                    'steps_passed': 0,
                    'steps_failed': 1,
                    'step_results': [{
                        'step_id': 'error',
                        'action': 'subprocess_error',
                        'status': 'failed',
                        'duration_ms': 0,
                        'error': error_msg,
                        'screenshot': None
                    }],
                    'error': error_msg
                }
            
            logger.debug(f"Test result loaded: status={result_data.get('status')}")
            
            # 重建StepResult对象列表
            step_results = []
            for step_data in result_data.get('step_results', []):
                step_result = StepResult(
                    step_id=step_data['step_id'],
                    action=step_data['action'],
                    status=TestStatus(step_data['status']) if not isinstance(step_data['status'], TestStatus) else step_data['status'],
                    duration_ms=step_data.get('duration_ms', 0),
                    error=step_data.get('error'),
                    screenshot=step_data.get('screenshot')
                )
                step_results.append(step_result)
            
            # 创建ComponentTestResult对象
            result = ComponentTestResult(
                component_name=result_data['component_name'],
                platform=result_data['platform'],
                status=TestStatus(result_data['status']) if not isinstance(result_data['status'], TestStatus) else result_data['status'],
                start_time=result_data.get('start_time'),
                end_time=result_data.get('end_time'),
                duration_ms=result_data.get('duration_ms', 0),
                steps_total=result_data.get('steps_total', 0),
                steps_passed=result_data.get('steps_passed', 0),
                steps_failed=result_data.get('steps_failed', 0),
                step_results=step_results,
                error=result_data.get('error')
            )
            
            logger.info(
                f"Test completed: {result.status.value if hasattr(result.status, 'value') else result.status}, "
                f"{result.steps_passed}/{result.steps_total} steps passed"
            )
            
            return result
            
        finally:
            # 清理临时文件
            for temp_file in [config_path, result_path]:
                try:
                    if Path(temp_file).exists():
                        Path(temp_file).unlink()
                        logger.debug(f"Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
    
    @staticmethod
    def format_test_response(
        result: 'ComponentTestResult',
        additional_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        格式化测试响应（统一格式）
        
        Args:
            result: 测试结果对象
            additional_info: 额外信息（如版本信息）
            
        Returns:
            Dict: 统一的响应格式，符合前端期望
        """
        import base64
        
        def image_to_base64(image_path: str) -> Optional[str]:
            """将图片转换为Base64编码"""
            if not image_path or not Path(image_path).exists():
                return None
            try:
                with open(image_path, 'rb') as f:
                    return base64.b64encode(f.read()).decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to encode image {image_path}: {e}")
                return None
        
        # 格式化步骤结果
        step_results = []
        for step_result in result.step_results:
            # 处理status（可能是字符串或枚举）
            step_status = (
                step_result.status 
                if isinstance(step_result.status, str) 
                else step_result.status.value
            )
            
            step_data = {
                'step_id': step_result.step_id,
                'action': step_result.action,
                'status': step_status,
                'duration_ms': step_result.duration_ms,
                'error': step_result.error,
                'screenshot_base64': image_to_base64(step_result.screenshot) if step_result.screenshot else None
            }
            step_results.append(step_data)
        
        # 计算成功率
        success_rate = (
            (result.steps_passed / result.steps_total * 100) 
            if result.steps_total > 0 
            else 0
        )
        
        # 处理result.status（可能是字符串或枚举）
        result_status = (
            result.status 
            if isinstance(result.status, str) 
            else result.status.value
        )
        
        # v4.8.0: 综合判断测试是否成功
        # 如果有 error，即使 status 是 passed，也应该标记为失败
        has_error = bool(result.error)
        is_success = result_status == 'passed' and not has_error
        
        # 构建消息
        if is_success:
            message = "组件测试通过"
        elif has_error:
            message = f"组件测试失败: {result.error}"
        else:
            message = "组件测试失败"
        
        # 构建基础响应
        response = {
            "success": is_success,
            "message": message,
            "test_result": {
                "status": result_status,
                "duration_ms": result.duration_ms,
                "steps_total": result.steps_total,
                "steps_passed": result.steps_passed,
                "steps_failed": result.steps_failed,
                "success_rate": round(success_rate, 1),
                "step_results": step_results,
                "error": result.error
            }
        }
        
        # 添加额外信息（如版本信息）
        if additional_info:
            response.update(additional_info)
        
        logger.debug(f"Response formatted: success={response['success']}, steps={len(step_results)}")
        
        return response
    
    @staticmethod
    async def save_test_history(
        db,
        component_name: str,
        platform: str,
        account_id: str,
        test_result: 'ComponentTestResult',
        version_id: Optional[int] = None,
        tested_by: str = "api"
    ) -> None:
        """
        保存测试历史记录（统一实现，异步版本）
        
        [*] v4.18.2修复：改为异步方法，支持 AsyncSession
        
        Args:
            db: 数据库会话（Session 或 AsyncSession）
            component_name: 组件名称
            platform: 平台代码
            account_id: 账号ID
            test_result: 测试结果对象
            version_id: 版本ID（可选）
            tested_by: 测试来源（recorder/version_manager/api）
        """
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import Session
        
        try:
            # 计算成功率
            success_rate = (
                test_result.steps_passed / test_result.steps_total 
                if test_result.steps_total > 0 
                else 0.0
            )
            
            # 格式化步骤结果为JSON
            step_results_json = [
                {
                    'step_id': s.step_id,
                    'action': s.action,
                    'status': s.status.value if hasattr(s.status, 'value') else s.status,
                    'duration_ms': s.duration_ms,
                    'error': s.error
                }
                for s in test_result.step_results
            ]
            
            # 处理result.status
            result_status = (
                test_result.status.value 
                if hasattr(test_result.status, 'value') 
                else test_result.status
            )
            
            # 创建历史记录
            history = ComponentTestHistory(
                test_id=str(uuid.uuid4()),
                component_name=component_name,
                version_id=version_id,
                platform=platform,
                account_id=account_id,
                headless=False,  # 前端测试默认有头模式
                status=result_status,
                duration_ms=test_result.duration_ms,
                steps_total=test_result.steps_total,
                steps_passed=test_result.steps_passed,
                steps_failed=test_result.steps_failed,
                success_rate=success_rate,
                step_results=step_results_json,
                error_message=test_result.error,
                tested_by=tested_by
            )
            
            db.add(history)
            # [*] v4.18.2修复：统一使用异步操作
            if isinstance(db, AsyncSession):
                await db.commit()
            else:
                # 同步 Session（不应该发生，但保留兼容性）
                db.commit()
            
            logger.info(
                f"Test history saved: {history.test_id}, "
                f"component={component_name}, status={result_status}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to save test history: {e}")
            if isinstance(db, AsyncSession):
                await db.rollback()
            else:
                db.rollback()
            # 不抛出异常，测试历史保存失败不应影响主流程


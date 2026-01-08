"""
组件录制工具API路由
Phase 8.1: UI化组件录制工具
v4.8.0: 仅支持 Inspector API 模式

功能：
1. 启动Playwright Inspector录制会话（支持持久化上下文和固定指纹）
2. 实时返回录制步骤（支持 Trace 解析）
3. 保存组件配置（支持 Python 组件代码生成）
4. 测试组件有效性

录制模式：
- Inspector 模式（唯一）：使用 page.pause() + Trace 录制，支持持久化会话
- v4.8.0: 移除 Codegen 模式支持
"""

import asyncio
import threading
import subprocess
import sys
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.database import get_db, get_async_db
from modules.core.logger import get_logger
from modules.core.db import PlatformAccount, ComponentVersion, ComponentTestHistory

logger = get_logger(__name__)

# v4.8.0: 仅支持 Inspector 模式（移除 Codegen）
# 保留常量用于兼容性
RECORDING_MODE = "inspector"

router = APIRouter()

# ==================== 测试会话管理 ====================
# 跟踪正在运行的测试任务
active_test_tasks: Dict[str, Any] = {}


# [*] v4.18.2修复：移除本地 save_test_history 函数，统一使用 ComponentTestService.save_test_history


# ==================== Pydantic Models ====================

class RecorderStartRequest(BaseModel):
    """开始录制请求"""
    platform: str
    component_type: str
    account_id: str


class RecorderStepResponse(BaseModel):
    """录制步骤响应"""
    id: int
    action: str
    selector: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    comment: Optional[str] = None
    optional: bool = False


class RecorderSaveRequest(BaseModel):
    """保存组件请求（v4.8.0 支持 Python 组件）"""
    platform: str
    component_type: str
    component_name: str
    # v4.8.0: 支持 Python 组件
    python_code: Optional[str] = None  # Python 组件代码
    data_domain: Optional[str] = None  # 数据域（export 组件必填）
    # 向后兼容：保留 YAML 支持
    yaml_content: Optional[str] = None  # 已废弃，保留兼容


class RecorderTestRequest(BaseModel):
    """测试组件请求"""
    platform: str
    component_type: str
    account_id: str
    steps: List[Dict[str, Any]]


# ==================== 全局录制会话管理 ====================

class RecorderSession:
    """录制会话管理（v4.8.0 仅 Inspector 模式）"""
    def __init__(self):
        self.active = False
        self.platform = None
        self.component_type = None
        self.account_id = None
        self.steps = []
        self.started_at = None
        self.browser_context = None
        self.page = None
        self.browser = None
        self.playwright_task = None  # 存储后台任务引用
        self.output_file = None  # 存储录制输出文件路径（trace.zip）
        # v4.8.0: 仅支持 Inspector 模式
        self.recording_mode = "inspector"  # 唯一模式
        self.steps_file = None  # Inspector 模式的步骤输出文件
        self.config_file = None  # Inspector 模式的配置文件
        self.trace_file = None  # Inspector 模式的 Trace 文件
    
    def start(self, platform: str, component_type: str, account_id: str):
        """开始录制会话"""
        self.active = True
        self.platform = platform
        self.component_type = component_type
        self.account_id = account_id
        self.steps = []
        self.started_at = datetime.now()
        logger.info(f"Recording session started: {platform}/{component_type}")
    
    def stop(self):
        """停止录制会话"""
        self.active = False
        logger.info(f"Recording session stopped: {len(self.steps)} steps recorded")
    
    def add_step(self, step: Dict[str, Any]):
        """添加录制步骤"""
        step['id'] = len(self.steps) + 1
        self.steps.append(step)
        logger.debug(f"Step added: {step['action']}")
    
    def cleanup_sync(self):
        """清理浏览器资源（同步）"""
        try:
            # 如果playwright_task是subprocess.Popen对象，终止进程
            if self.playwright_task and hasattr(self.playwright_task, 'terminate'):
                logger.info(f"Terminating Playwright subprocess (PID: {self.playwright_task.pid})")
                self.playwright_task.terminate()
                try:
                    self.playwright_task.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Subprocess didn't terminate, killing...")
                    self.playwright_task.kill()
        except Exception as e:
            logger.warning(f"Failed to cleanup subprocess: {e}")
        
        try:
            if self.page:
                self.page.close()
        except Exception as e:
            logger.warning(f"Failed to close page: {e}")
        
        try:
            if self.browser_context:
                self.browser_context.close()
        except Exception as e:
            logger.warning(f"Failed to close context: {e}")
        
        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.warning(f"Failed to close browser: {e}")
    
    def clear(self):
        """清空会话"""
        self.active = False
        self.platform = None
        self.component_type = None
        self.account_id = None
        self.steps = []
        self.started_at = None
        self.browser_context = None
        self.page = None
        self.browser = None
        self.playwright_task = None
        self.output_file = None
        # v4.8.0: 仅支持 Inspector 模式
        self.recording_mode = "inspector"
        self.steps_file = None
        self.config_file = None
        self.trace_file = None


# 全局录制会话实例
recorder_session = RecorderSession()


# ==================== API Endpoints ====================

def _launch_inspector_recorder_subprocess(
    account: PlatformAccount,
    platform: str,
    component_type: str
):
    """
    [新模式] 使用 Inspector API + Trace 录制（v4.7.5）
    
    功能：
    1. 使用 PersistentBrowserManager 创建持久化上下文
    2. 应用固定指纹（DeviceFingerprintManager）
    3. 自动执行登录组件（如果不是 login 组件）
    4. 启动 Trace 录制
    5. 打开 Inspector（page.pause()）
    6. 停止后解析 Trace 文件
    
    优势：
    - 持久化会话：复用已登录状态
    - 固定指纹：降低检测风险
    - Trace 录制：更准确的步骤提取
    """
    try:
        # 构建启动脚本路径
        script_path = Path(__file__).parent.parent.parent / "tools" / "launch_inspector_recorder.py"
        
        # 构建输出目录
        temp_dir = Path(__file__).parent.parent.parent / "temp" / "recordings"
        temp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Trace 文件路径
        trace_file = temp_dir / f"{platform}_{component_type}_{timestamp}_trace.zip"
        # 步骤输出文件路径
        steps_file = temp_dir / f"{platform}_{component_type}_{timestamp}_steps.json"
        
        # 保存输出文件路径到session
        recorder_session.output_file = str(trace_file)
        recorder_session.steps_file = str(steps_file)
        recorder_session.recording_mode = "inspector"
        
        # 准备账号信息
        account_info = {
            'account_id': account.account_id,
            'platform': account.platform,
            'store_name': account.store_name,
            'login_url': account.login_url,
            'username': account.username,
            'password': account.password_encrypted,  # 加密密码
        }
        
        # 构建配置文件
        config = {
            'platform': platform,
            'component_type': component_type,
            'account_info': account_info,
            'trace_file': str(trace_file),
            'steps_file': str(steps_file),
            'skip_login': component_type == 'login',  # login 组件不自动登录
            'enable_trace': True,
            'use_persistent_context': True,  # 使用持久化上下文
            'use_fingerprint': True,  # 使用固定指纹
        }
        
        # 保存配置文件
        config_file = temp_dir / f"{platform}_{component_type}_{timestamp}_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 构建命令
        cmd = [
            sys.executable,
            str(script_path),
            '--config', str(config_file)
        ]
        
        logger.info(f"Starting Inspector recorder: {' '.join(cmd)}")
        logger.info(f"Trace will be saved to: {trace_file}")
        logger.info(f"Steps will be saved to: {steps_file}")
        
        # 启动独立进程
        process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )
        
        # 保存进程引用和配置文件路径
        recorder_session.playwright_task = process
        recorder_session.config_file = str(config_file)
        
        logger.info(f"Inspector recorder subprocess started with PID: {process.pid}")
        
    except Exception as e:
        logger.error(f"Failed to launch Inspector recorder: {e}", exc_info=True)
        recorder_session.stop()


def _launch_playwright_browser_subprocess(
    account: PlatformAccount,
    platform: str,
    component_type: str
):
    """
    v4.8.0: 启动 Inspector 录制器（唯一模式）
    
    功能：
    1. 使用 PersistentBrowserManager 创建持久化上下文
    2. 应用固定指纹（DeviceFingerprintManager）
    3. 自动执行登录组件（如果不是 login 组件）
    4. 启动 Trace 录制
    5. 打开 Inspector（page.pause()）
    """
    _launch_inspector_recorder_subprocess(account, platform, component_type)


@router.post("/recorder/start")
async def start_recording(
    request: RecorderStartRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    开始录制组件
    
    功能：
    1. 验证账号存在
    2. 启动Playwright浏览器（后台任务）
    3. 打开Playwright Inspector
    4. 开始监听用户操作
    """
    try:
        # 检查是否已有活跃会话
        if recorder_session.active:
            return {
                "success": False,
                "message": "已有活跃的录制会话，请先停止"
            }
        
        # 验证账号存在
        result = await db.execute(
            select(PlatformAccount).where(PlatformAccount.account_id == request.account_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")
        
        # 启动录制会话
        recorder_session.start(
            request.platform,
            request.component_type,
            request.account_id
        )
        
        # 启动Playwright浏览器（使用subprocess在独立进程中运行）
        # 在单独线程中启动subprocess，避免阻塞API响应
        thread = threading.Thread(
            target=_launch_playwright_browser_subprocess,
            args=(account, request.platform, request.component_type),
            daemon=True
        )
        thread.start()
        
        logger.info(
            f"Recording started: {request.platform}/{request.component_type} "
            f"with account {request.account_id}"
        )
        
        return {
            "success": True,
            "message": "录制已开始，Playwright浏览器正在启动...",
            "session_id": id(recorder_session),
            "account": {
                "account_id": account.account_id,
                "platform": account.platform,
                "store_name": account.store_name
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动录制失败: {str(e)}")


def _parse_inspector_output() -> Dict[str, Any]:
    """
    解析 Inspector 模式的输出（Trace 文件或步骤 JSON）
    
    v4.7.5: 优先读取步骤 JSON 文件（由录制脚本生成）
    如果不存在，则解析 Trace 文件
    
    Phase 11: 支持发现模式，返回完整的数据结构
    - 步骤模式: {"mode": "steps", "steps": [...]}
    - 发现模式: {"mode": "discovery", "open_action": {...}, "available_options": [...]}
    
    Returns:
        Dict: 包含 mode 和相应数据的字典
    """
    # 1. 优先读取步骤 JSON 文件（由录制脚本直接生成）
    if recorder_session.steps_file:
        steps_path = Path(recorder_session.steps_file)
        if steps_path.exists():
            logger.info(f"Reading steps from JSON file: {steps_path}")
            try:
                with open(steps_path, 'r', encoding='utf-8') as f:
                    steps_data = json.load(f)
                
                # Phase 11: 检查是否为发现模式
                mode = steps_data.get('mode', 'steps')
                
                if mode == 'discovery':
                    options_count = len(steps_data.get('available_options', []))
                    logger.info(f"Loaded discovery mode: {options_count} options")
                    return {
                        'mode': 'discovery',
                        'open_action': steps_data.get('open_action'),
                        'available_options': steps_data.get('available_options', []),
                        'default_option': steps_data.get('default_option'),
                        'test_config': steps_data.get('test_config', {}),  # Phase 12.2: 自动捕获的测试配置
                    }
                else:
                    parsed_steps = steps_data.get('steps', [])
                    logger.info(f"Loaded {len(parsed_steps)} steps from JSON file")
                    return {
                        'mode': 'steps',
                        'steps': parsed_steps,
                    }
                
            except Exception as e:
                logger.error(f"Failed to read steps JSON: {e}", exc_info=True)
    
    # 2. 备选：解析 Trace 文件
    if recorder_session.output_file:
        trace_path = Path(recorder_session.output_file)
        if trace_path.exists() and trace_path.suffix == '.zip':
            logger.info(f"Parsing trace file: {trace_path}")
            try:
                from backend.utils.trace_parser import TraceParser
                
                parser = TraceParser()
                result = parser.parse(str(trace_path))
                
                if result.success:
                    logger.info(f"Parsed {len(result.steps)} steps from trace file")
                    return {
                        'mode': 'steps',
                        'steps': result.steps,
                    }
                else:
                    logger.error(f"Trace parsing failed: {result.error}")
                    
            except Exception as e:
                logger.error(f"Failed to parse trace file: {e}", exc_info=True)
    
    logger.warning("No valid output found for Inspector mode")
    return {'mode': 'steps', 'steps': []}


@router.post("/recorder/stop")
async def stop_recording():
    """
    停止录制（v4.7.5 支持 Inspector API）
    
    功能：
    1. 等待subprocess结束
    2. 根据录制模式读取输出文件：
       - Codegen 模式：解析生成的 Python 代码
       - Inspector 模式：解析 Trace 文件或步骤 JSON 文件
    3. 返回录制的步骤
    """
    try:
        if not recorder_session.active:
            return {
                "success": False,
                "message": "当前没有活跃的录制会话"
            }
        
        # 等待subprocess结束（用户关闭浏览器）
        if recorder_session.playwright_task:
            logger.info("Waiting for Playwright subprocess to finish...")
            try:
                # 等待进程结束（最多120秒，Inspector模式可能需要更长时间）
                recorder_session.playwright_task.wait(timeout=120)
                logger.info("Playwright subprocess finished")
            except subprocess.TimeoutExpired:
                logger.warning("Subprocess timeout, terminating...")
                recorder_session.playwright_task.terminate()
                recorder_session.playwright_task.wait(timeout=5)
        
        # v4.8.0: 仅支持 Inspector 模式
        # Phase 11: 支持发现模式
        parsed_data = _parse_inspector_output()
        
        # 更新 session 的步骤（兼容旧逻辑）
        if parsed_data.get('mode') == 'discovery':
            recorder_session.steps = []  # 发现模式没有 steps
            steps_count = len(parsed_data.get('available_options', []))
        else:
            recorder_session.steps = parsed_data.get('steps', [])
            steps_count = len(recorder_session.steps)
        
        # 关闭浏览器资源（清理subprocess引用）
        def cleanup_thread():
            try:
                recorder_session.cleanup_sync()
            except Exception as e:
                logger.warning(f"Error during browser cleanup: {e}")
        
        threading.Thread(target=cleanup_thread, daemon=True).start()
        
        # 停止录制
        recorder_session.stop()
        
        # Phase 11: 根据模式返回不同的数据
        mode = parsed_data.get('mode', 'steps')
        
        if mode == 'discovery':
            logger.info(f"Recording stopped: {steps_count} options discovered")
            
            response = {
                "success": True,
                "message": f"录制已停止，共发现 {steps_count} 个选项",
                "mode": "discovery",
                "options_count": steps_count,
                "open_action": parsed_data.get('open_action'),
                "available_options": parsed_data.get('available_options', []),
                "default_option": parsed_data.get('default_option'),
                "test_config": parsed_data.get('test_config', {}),  # Phase 12.2: 自动捕获的测试配置
            }
        else:
            logger.info(f"Recording stopped: {steps_count} steps recorded")
            
            # 不清空steps，让前端可以获取
            steps = recorder_session.steps.copy()
            
            response = {
                "success": True,
                "message": f"录制已停止，共记录 {steps_count} 个步骤",
                "mode": "steps",
                "steps_count": steps_count,
                "steps": steps,
            }
        
        recorder_session.clear()
        return response
    
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"停止录制失败: {str(e)}")


@router.get("/recorder/steps")
async def get_recording_steps():
    """
    获取录制步骤（用于前端轮询）
    
    返回当前会话中录制的所有步骤
    """
    try:
        return {
            "success": True,
            "data": {
                "active": recorder_session.active,
                "steps": recorder_session.steps,
                "steps_count": len(recorder_session.steps),
                "started_at": recorder_session.started_at.isoformat() if recorder_session.started_at else None
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get recording steps: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取步骤失败: {str(e)}")


@router.post("/recorder/test")
async def test_component(
    request: RecorderTestRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    测试组件（录制器）- 使用统一服务层
    
    功能：
    1. 使用录制的步骤创建临时组件
    2. 使用指定账号执行组件（有头模式）
    3. 返回详细执行结果（每步状态/耗时/截图）
    
    重构说明：使用 ComponentTestService 统一服务，消除与 component_versions.py 的重复代码
    """
    import yaml
    from pathlib import Path
    from datetime import datetime
    from backend.services.component_test_service import ComponentTestService
    
    try:
        # 1. 验证账号
        result = await db.execute(
            select(PlatformAccount).where(PlatformAccount.account_id == request.account_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")
        
        logger.info(
            f"Testing component: {request.platform}/{request.component_type} "
            f"with {len(request.steps)} steps, account: {request.account_id}"
        )
        
        # 2. 创建临时YAML组件文件
        config_dir = Path(__file__).parent.parent.parent / 'config' / 'collection_components' / request.platform
        config_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        component_name = f"{request.component_type}_test_{timestamp}"
        temp_yaml_path = config_dir / f"{component_name}.yaml"
        
        # 构建YAML内容
        component_config = {
            'name': component_name,
            'platform': request.platform,
            'type': request.component_type,
            'version': '1.0.0',
            'description': f'临时测试组件 - {datetime.now().isoformat()}',
            'steps': [
                {
                    'action': step.get('action'),
                    'selector': step.get('selector'),
                    'url': step.get('url'),
                    'value': step.get('value'),
                    'comment': step.get('comment'),
                    'optional': step.get('optional', False),
                    'timeout': step.get('timeout', 30000),
                }
                for step in request.steps
            ],
            'success_criteria': [
                {
                    'type': 'url_contains',
                    'value': '',  # [*] 空字符串，表示需要填写
                    'optional': True,  # [*] 标记为可选，避免测试失败
                    'comment': '临时测试：建议保存后补充验证条件（使用 Playwright Inspector 提取）'
                }
            ]
        }
        
        # 保存YAML文件
        with open(temp_yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(component_config, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Temporary component file created: {temp_yaml_path}")
        
        # 3. 使用统一服务准备账号信息 [*]
        account_info = ComponentTestService.prepare_account_info(account)
        
        # 4. 使用统一服务执行测试 [*]
        result = ComponentTestService.run_component_test_subprocess(
            platform=request.platform,
            component_name=component_name,
            account_id=request.account_id,
            account_info=account_info,
            component_path=str(temp_yaml_path),
            headless=False,  # 有头模式
            screenshot_on_error=True
        )
        
        # 5. 使用统一服务格式化响应 [*]
        response = ComponentTestService.format_test_response(result)
        
        # 6. 使用统一服务保存测试历史 [*]
        # [*] v4.18.2修复：使用异步方法保存测试历史
        await ComponentTestService.save_test_history(
            db=db,
            component_name=component_name,
            platform=request.platform,
            account_id=request.account_id,
            test_result=result,
            version_id=None,  # 临时组件无版本ID
            tested_by="recorder"
        )
        
        # 7. 清理临时YAML文件
        try:
            if temp_yaml_path.exists():
                temp_yaml_path.unlink()
                logger.info(f"Cleaned up temporary component file: {temp_yaml_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary file: {e}")
        
        return response
    
    except HTTPException:
        raise
    except ValueError as ve:
        # 密码解密失败等业务异常
        raise HTTPException(status_code=500, detail=str(ve))
    except RuntimeError as re:
        # 测试进程失败等运行时异常
        raise HTTPException(status_code=500, detail=str(re))
    except Exception as e:
        logger.error(f"Failed to test component: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"测试组件失败: {str(e)}")


@router.post("/recorder/save")
async def save_component(request: RecorderSaveRequest, db: AsyncSession = Depends(get_async_db)):
    """
    保存组件到文件并自动注册到版本管理系统（v4.8.0 支持 Python 组件）
    
    功能：
    1. 优先保存 Python 组件（推荐）
    2. 向后兼容 YAML 组件
    3. 验证代码/配置格式
    4. 保存到正确目录
    5. 自动注册到 component_versions 表
    6. 同名组件更新现有版本（不创建新版本）
    """
    import ast
    from pathlib import Path
    import yaml
    from modules.core.db import ComponentVersion
    from datetime import datetime
    
    try:
        project_root = Path(__file__).parent.parent.parent
        
        # v4.8.0: 优先使用 Python 组件
        is_python_component = bool(request.python_code)
        
        if is_python_component:
            # ==================== Python 组件保存逻辑 ====================
            
            # 1. 验证 Python 代码语法
            try:
                ast.parse(request.python_code)
            except SyntaxError as e:
                raise HTTPException(status_code=400, detail=f"Python 代码语法错误: {str(e)}")
            
            # 2. 确定保存路径
            component_dir = project_root / "modules" / "platforms" / request.platform / "components"
            component_dir.mkdir(parents=True, exist_ok=True)
            
            # 3. 文件名
            filename = f"{request.component_name}.py"
            file_path = component_dir / filename
            
            # 4. 检查文件是否已存在
            file_exists = file_path.exists()
            
            # 5. 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(request.python_code)
            
            logger.info(
                f"Python component saved: {request.platform}/{filename} "
                f"({'updated' if file_exists else 'created'})"
            )
            
            # 6. 自动注册到 component_versions 表
            component_name = f"{request.platform}/{request.component_name}"
            relative_file_path = f"modules/platforms/{request.platform}/components/{filename}"
            
        else:
            # ==================== YAML 组件保存逻辑（向后兼容） ====================
            
            if not request.yaml_content:
                raise HTTPException(status_code=400, detail="必须提供 python_code 或 yaml_content")
            
            # 1. 验证 YAML 格式
            try:
                yaml.safe_load(request.yaml_content)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"YAML 格式错误: {str(e)}")
            
            # 2. 确定保存路径
            component_dir = project_root / "config" / "collection_components" / request.platform
            component_dir.mkdir(parents=True, exist_ok=True)
            
            # 3. 文件名
            filename = f"{request.component_name}.yaml"
            file_path = component_dir / filename
            
            # 4. 检查文件是否已存在
            file_exists = file_path.exists()
            
            # 5. 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(request.yaml_content)
            
            logger.info(
                f"YAML component saved: {request.platform}/{filename} "
                f"({'updated' if file_exists else 'created'})"
            )
            
            # 6. 自动注册到 component_versions 表
            component_name = f"{request.platform}/{request.component_type}"
            relative_file_path = f"config/collection_components/{request.platform}/{filename}"
        
        # ==================== 版本管理逻辑（通用） ====================
        
        # 查询现有版本（按 file_path 查询，确保更新正确的版本）
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.file_path == relative_file_path)
        )
        existing_version = result.scalar_one_or_none()
        
        if existing_version:
            # 更新现有版本（不创建新版本）
            existing_version.description = f"录制工具更新 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            existing_version.updated_at = datetime.utcnow()
            await db.commit()
            
            version = existing_version.version
            is_new_version = False
            version_action = "更新"
            logger.info(f"Updated existing version: {component_name} v{version}")
        else:
            # 检查是否有同名组件的其他版本
            result = await db.execute(
                select(ComponentVersion).where(
                    ComponentVersion.component_name == component_name
                ).order_by(ComponentVersion.version.desc())
            )
            existing_name_versions = result.scalars().all()
            
            if existing_name_versions:
                # 自动递增版本号
                latest_version = existing_name_versions[0].version
                major, minor, patch = map(int, latest_version.split('.'))
                version = f"{major}.{minor}.{patch + 1}"
            else:
                # 首次创建
                version = "1.0.0"
            
            # 创建新版本记录
            new_version = ComponentVersion(
                component_name=component_name,
                version=version,
                file_path=relative_file_path,
                is_stable=True if is_python_component else False,  # Python 组件默认稳定
                is_active=True,
                description=f"录制工具创建 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                created_by="recorder"
            )
            db.add(new_version)
            await db.commit()
            await db.refresh(new_version)
            
            is_new_version = True
            version_action = "创建"
            logger.info(f"Created new version: {component_name} v{version}")
        
        return {
            "success": True,
            "message": f"组件已保存并{version_action}",
            "file_path": str(file_path),
            "file_exists_before": file_exists,
            "component_type": "python" if is_python_component else "yaml",
            "version_info": {
                "version": version,
                "is_new_version": is_new_version,
                "action": version_action,
                "component_name": component_name
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save component: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存组件失败: {str(e)}")


@router.post("/recorder/add-step")
async def add_recording_step(step: Dict[str, Any]):
    """
    添加录制步骤（由Playwright监听器调用）
    
    这个endpoint用于后台服务推送录制的步骤
    """
    try:
        if not recorder_session.active:
            return {
                "success": False,
                "message": "当前没有活跃的录制会话"
            }
        
        recorder_session.add_step(step)
        
        return {
            "success": True,
            "step_id": step.get('id'),
            "steps_count": len(recorder_session.steps)
        }
    
    except Exception as e:
        logger.error(f"Failed to add recording step: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加步骤失败: {str(e)}")


@router.get("/recorder/status")
async def get_recorder_status():
    """获取录制器状态"""
    return {
        "success": True,
        "data": {
            "active": recorder_session.active,
            "platform": recorder_session.platform,
            "component_type": recorder_session.component_type,
            "steps_count": len(recorder_session.steps),
            "started_at": recorder_session.started_at.isoformat() if recorder_session.started_at else None
        }
    }


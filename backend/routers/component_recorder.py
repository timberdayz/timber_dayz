"""
组件录制工具API路由
Phase 8.1: UI化组件录制工具
v4.8.0: 仅支持 Inspector API 模式

功能:
1. 启动Playwright Inspector录制会话(支持持久化上下文和固定指纹)
2. 实时返回录制步骤(支持 Trace 解析)
3. 保存组件配置(支持 Python 组件代码生成)

录制模式:
- Inspector 模式(唯一):使用 page.pause() + Trace 录制,支持持久化会话
- v4.8.0: 移除 Codegen 模式支持
"""

import asyncio
import threading
import subprocess
import sys
import json
import ast
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.database import get_db, get_async_db
from backend.services.steps_to_python import generate_python_code
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.logger import get_logger
from modules.core.db import PlatformAccount, ComponentVersion, ComponentTestHistory

logger = get_logger(__name__)

# v4.8.0: 仅支持 Inspector 模式(移除 Codegen)
# 保留常量用于兼容性
RECORDING_MODE = "inspector"

router = APIRouter()

# [*] v4.18.2修复:移除本地 save_test_history 函数,统一使用 ComponentTestService.save_test_history


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
    """保存组件请求(v4.8.0 支持 Python 组件)"""
    platform: str
    component_type: str
    component_name: str
    # v4.8.0: 支持 Python 组件
    python_code: Optional[str] = None  # Python 组件代码
    data_domain: Optional[str] = None  # 数据域(export 组件必填)
    # 登录成功条件（可选），如 {"url_contains": "/dashboard"}，保存时写入组件内校验逻辑
    success_criteria: Optional[Dict[str, Any]] = None
    # 向后兼容:保留 YAML 支持
    yaml_content: Optional[str] = None  # 已废弃,保留兼容


class GeneratePythonRequest(BaseModel):
    """生成 Python 代码请求（供前端「重新生成」使用）"""
    platform: str
    component_type: str
    component_name: str
    steps: List[Dict[str, Any]]


def _inject_login_success_criteria_block(python_code: str, crit: Dict[str, Any]) -> str:
    """
    根据 success_criteria 注入统一的登录成功检测代码块，替换生成器默认的 TODO 占位。
    支持的字段：
    - url_contains: 字符串或字符串列表，表示登录后 URL 必须包含的片段
    - url_not_contains: 字符串或字符串列表，表示登录后 URL 不应包含的片段
    - element_visible_selector: 登录成功后应可见的关键元素选择器
    """
    old_block = (
        "        # TODO: 根据实际成功条件校验 (e.g. URL / element)\n"
        "        return LoginResult(success=True, message=\"ok\")"
    )

    if old_block not in python_code:
        return python_code

    lines: list[str] = []
    lines.append("        # 登录成功条件：由 success_criteria 注入")
    lines.append("        current_url = page.url")

    # url_contains: 字符串或字符串列表
    url_contains = crit.get("url_contains")
    if url_contains:
        if isinstance(url_contains, str):
            url_contains_values = [url_contains]
        else:
            try:
                url_contains_values = list(url_contains)
            except TypeError as e:
                logger.error(f"url_contains type conversion failed: {e}")
                url_contains_values = [str(url_contains)]
        for val in url_contains_values:
            msg = f"登录后 URL 未包含预期片段: {val}"
            lines.append(f"        if {val!r} not in current_url:")
            lines.append(f"            return LoginResult(success=False, message={msg!r})")

    # url_not_contains: 字符串或字符串列表
    url_not_contains = crit.get("url_not_contains")
    if url_not_contains:
        if isinstance(url_not_contains, str):
            url_not_values = [url_not_contains]
        else:
            try:
                url_not_values = list(url_not_contains)
            except TypeError as e:
                logger.error(f"url_not_contains type conversion failed: {e}")
                url_not_values = [str(url_not_contains)]
        for val in url_not_values:
            msg = f"登录后 URL 仍包含禁止片段: {val}"
            lines.append(f"        if {val!r} in current_url:")
            lines.append(f"            return LoginResult(success=False, message={msg!r})")

    # element_visible_selector: 登录成功后应可见的关键元素
    elem_sel = crit.get("element_visible_selector")
    if elem_sel:
        msg = f"登录后未找到预期元素: {elem_sel}"
        lines.append(f"        _succ_elem = page.locator({elem_sel!r}).first")
        lines.append("        if await _succ_elem.count() == 0:")
        lines.append(f"            return LoginResult(success=False, message={msg!r})")
        lines.append("        await _succ_elem.wait_for(state=\"visible\", timeout=10000)")

    # 若未配置任何字段，保持默认行为（视为成功）
    lines.append("        return LoginResult(success=True, message=\"ok\")")

    new_block = "\n".join(lines)
    return python_code.replace(old_block, new_block, 1)


# ==================== 全局录制会话管理 ====================

class RecorderSession:
    """录制会话管理(v4.8.0 仅 Inspector 模式)"""
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
        self.output_file = None  # 存储录制输出文件路径(trace.zip)
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
        """清理浏览器资源(同步)"""
        try:
            # 如果playwright_task是subprocess.Popen对象,终止进程
            if self.playwright_task and hasattr(self.playwright_task, 'terminate'):
                logger.info(f"Terminating Playwright subprocess (PID: {self.playwright_task.pid})")
                self.playwright_task.terminate()
                try:
                    self.playwright_task.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.error("Subprocess didn't terminate, killing...")
                    self.playwright_task.kill()
        except Exception as e:
            logger.error(f"Failed to cleanup subprocess: {e}", exc_info=True)
        
        try:
            if self.page:
                self.page.close()
        except Exception as e:
            logger.error(f"Failed to close page: {e}", exc_info=True)
        
        try:
            if self.browser_context:
                self.browser_context.close()
        except Exception as e:
            logger.error(f"Failed to close context: {e}", exc_info=True)
        
        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.error(f"Failed to close browser: {e}", exc_info=True)
    
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


def _normalize_login_steps_and_suggestions(
    steps: List[Dict[str, Any]],
    component_type: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    针对 login 组件，对录制步骤中的账号/密码字段执行自动变量化，并生成前端可展示的建议列表。
    - 被识别为用户名/密码输入的步骤，其 value 将规范化为 {{account.username}} / {{account.password}}。
    - 同时在 scene_tags 中打上 login_form/login_username_field/login_password_field 等标签。
    """
    if component_type != "login" or not steps:
        return steps, []

    normalized: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []

    for idx, raw_step in enumerate(steps):
        step = dict(raw_step) if isinstance(raw_step, dict) else {"action": raw_step}
        action = str(step.get("action") or "").strip().lower()
        if action != "fill":
            normalized.append(step)
            continue

        selector = str(step.get("selector") or "")
        comment = str(step.get("comment") or "")
        value = step.get("value")
        scene_tags = list(step.get("scene_tags") or [])

        lower_comment = comment.lower()
        sel_lower = selector.lower()

        is_username_field = any(k in comment for k in ["账号", "用户名", "子账号", "邮箱", "手机号"]) or any(
            k in sel_lower for k in ["account", "username", "user", "email", "phone"]
        )
        is_password_field = ("密码" in comment) or ("password" in lower_comment) or ("password" in sel_lower)

        # 默认不改动
        applied = False
        original_value = value

        if is_username_field:
            # 若已有模板变量，则视为已应用，仅补充标签
            if isinstance(value, str) and "{{account.username}}" in value:
                applied = True
                suggested_value = value
            else:
                suggested_value = "{{account.username}}"
                step["value"] = suggested_value
                applied = True

            if "login_form" not in scene_tags:
                scene_tags.append("login_form")
            if "login_username_field" not in scene_tags:
                scene_tags.append("login_username_field")

            suggestions.append(
                {
                    "step_index": idx,
                    "kind": "username",
                    "original_value": original_value,
                    "suggested_value": suggested_value,
                    "confidence": 0.9,
                    "applied": applied,
                }
            )

        elif is_password_field:
            if isinstance(value, str) and "{{account.password}}" in value:
                applied = True
                suggested_value = value
            else:
                suggested_value = "{{account.password}}"
                step["value"] = suggested_value
                applied = True

            if "login_form" not in scene_tags:
                scene_tags.append("login_form")
            if "login_password_field" not in scene_tags:
                scene_tags.append("login_password_field")

            suggestions.append(
                {
                    "step_index": idx,
                    "kind": "password",
                    "original_value": original_value,
                    "suggested_value": suggested_value,
                    "confidence": 0.9,
                    "applied": applied,
                }
            )

        if scene_tags:
            step["scene_tags"] = scene_tags

        normalized.append(step)

    return normalized, suggestions


def _analyze_python_code_for_lints(python_code: str) -> Dict[str, List[Dict[str, str]]]:
    """
    对生成的 Python 代码做基础质量检查：
    - 语法检查（ast.parse）
    - 明显不推荐模式提示（例如 wait_for_timeout）
    返回 errors / warnings 列表，供前端展示。
    """
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if not python_code:
        return {"errors": errors, "warnings": warnings}

    # 语法检查
    try:
        ast.parse(python_code)
    except SyntaxError as e:
        logger.error("Python syntax error in lint check: %s", e)
        errors.append(
            {
                "type": "syntax_error",
                "message": str(e),
            }
        )
        # 语法错误时无需继续做其他检查
        return {"errors": errors, "warnings": warnings}

    # 简单规则：检测 wait_for_timeout 使用，建议改用条件等待
    if "wait_for_timeout(" in python_code:
        warnings.append(
            {
                "type": "wait_for_timeout_usage",
                "message": "检测到 wait_for_timeout 调用，建议优先使用条件等待或 expect(locator).to_be_visible() 以符合《采集脚本编写规范》。",
            }
        )

    return {"errors": errors, "warnings": warnings}


def _enrich_steps_semantics(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据 step_group 为步骤补充 step_type / scene_tags，供生成器选择场景模板。
    兼容无 step_group 的旧数据；有 step_group 时写入 scene_tags（及可选 step_type）。
    """
    if not steps:
        return steps
    enriched = []
    for s in steps:
        step = dict(s) if isinstance(s, dict) else {"action": s.get("action")}
        group = (step.get("step_group") or "").strip().lower()
        tags = list(step.get("scene_tags") or [])
        if group == "navigation":
            if "navigation" not in tags:
                tags.append("navigation")
            step["step_type"] = step.get("step_type") or "navigation"
        elif group == "popup":
            if "popup" not in tags:
                tags.append("popup")
            if "notification_bar" not in tags:
                tags.append("notification_bar")
            step["step_type"] = step.get("step_type") or "popup"
        elif group == "date_picker":
            if "date_picker" not in tags:
                tags.append("date_picker")
        elif group == "filters":
            if "filters" not in tags:
                tags.append("filters")
        elif group == "captcha_graphical":
            if "captcha" not in tags:
                tags.append("captcha")
            if "graphical_captcha" not in tags:
                tags.append("graphical_captcha")
            step["step_type"] = step.get("step_type") or "captcha_graphical"
        elif group == "captcha_otp":
            if "captcha" not in tags:
                tags.append("captcha")
            if "otp" not in tags:
                tags.append("otp")
            if "otp_dialog" not in tags:
                tags.append("otp_dialog")
            step["step_type"] = step.get("step_type") or "captcha_otp"
        elif group == "captcha":
            # 向后兼容：未区分子类型时视为图形验证码（需截图）
            if "captcha" not in tags:
                tags.append("captcha")
            if "graphical_captcha" not in tags:
                tags.append("graphical_captcha")
            if "otp_dialog" not in tags:
                tags.append("otp_dialog")
            step["step_type"] = step.get("step_type") or "captcha"
        if tags:
            step["scene_tags"] = tags
        enriched.append(step)
    return enriched


# ==================== API Endpoints ====================

def _launch_inspector_recorder_subprocess(
    account: PlatformAccount,
    platform: str,
    component_type: str
):
    """
    [新模式] 使用 Inspector API + Trace 录制(v4.7.5)
    
    功能:
    1. 使用 PersistentBrowserManager 创建持久化上下文
    2. 应用固定指纹(DeviceFingerprintManager)
    3. 自动执行登录组件(如果不是 login 组件)
    4. 启动 Trace 录制
    5. 打开 Inspector(page.pause())
    6. 停止后解析 Trace 文件
    
    优势:
    - 持久化会话:复用已登录状态
    - 固定指纹:降低检测风险
    - Trace 录制:更准确的步骤提取
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
    v4.8.0: 启动 Inspector 录制器(唯一模式)
    
    功能:
    1. 使用 PersistentBrowserManager 创建持久化上下文
    2. 应用固定指纹(DeviceFingerprintManager)
    3. 自动执行登录组件(如果不是 login 组件)
    4. 启动 Trace 录制
    5. 打开 Inspector(page.pause())
    """
    _launch_inspector_recorder_subprocess(account, platform, component_type)


@router.post("/recorder/start")
async def start_recording(
    request: RecorderStartRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    开始录制组件
    
    功能:
    1. 验证账号存在
    2. 启动Playwright浏览器(后台任务)
    3. 打开Playwright Inspector
    4. 开始监听用户操作
    """
    try:
        # 检查是否已有活跃会话
        if recorder_session.active:
            return {
                "success": False,
                "message": "已有活跃的录制会话,请先停止"
            }
        
        # 验证账号存在
        result = await db.execute(
            select(PlatformAccount).where(PlatformAccount.account_id == request.account_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="账号不存在",
                status_code=404,
                recovery_suggestion="请检查账号ID是否正确，或在平台管理中先添加账号",
            )
        
        # 启动录制会话
        recorder_session.start(
            request.platform,
            request.component_type,
            request.account_id
        )
        
        # 启动Playwright浏览器(使用subprocess在独立进程中运行)
        # 在单独线程中启动subprocess,避免阻塞API响应
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
            "message": "录制已开始,Playwright浏览器正在启动...",
            "session_id": id(recorder_session),
            "account": {
                "account_id": account.account_id,
                "platform": account.platform,
                "store_name": account.store_name
            }
        }
    
    except HTTPException as he:
        logger.error(f"HTTPException in start_recording: {he.detail}", exc_info=True)
        raise he
    except Exception as e:
        logger.error(f"Failed to start recording: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"启动录制失败: {str(e)}",
            status_code=500,
            recovery_suggestion="请确认 Playwright 已安装且账号配置正确，稍后重试",
        )


def _parse_inspector_output() -> Dict[str, Any]:
    """
    解析 Inspector 模式的输出(Trace 文件或步骤 JSON)
    
    v4.7.5: 优先读取步骤 JSON 文件(由录制脚本生成)
    如果不存在,则解析 Trace 文件
    
    Phase 11: 支持发现模式,返回完整的数据结构
    - 步骤模式: {"mode": "steps", "steps": [...]}
    - 发现模式: {"mode": "discovery", "open_action": {...}, "available_options": [...]}
    
    Returns:
        Dict: 包含 mode 和相应数据的字典
    """
    # 1. 优先读取步骤 JSON 文件(由录制脚本直接生成)
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
    
    # 2. 备选:解析 Trace 文件
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
    停止录制(v4.7.5 支持 Inspector API)
    
    功能:
    1. 等待subprocess结束
    2. 根据录制模式读取输出文件:
       - Codegen 模式:解析生成的 Python 代码
       - Inspector 模式:解析 Trace 文件或步骤 JSON 文件
    3. 返回录制的步骤
    """
    try:
        if not recorder_session.active:
            return {
                "success": False,
                "message": "当前没有活跃的录制会话"
            }
        
        # 等待subprocess结束(用户关闭浏览器)
        if recorder_session.playwright_task:
            logger.info("Waiting for Playwright subprocess to finish...")
            try:
                # 等待进程结束(最多120秒,Inspector模式可能需要更长时间)
                recorder_session.playwright_task.wait(timeout=120)
                logger.info("Playwright subprocess finished")
            except subprocess.TimeoutExpired:
                logger.error("Subprocess timeout, terminating...")
                recorder_session.playwright_task.terminate()
                recorder_session.playwright_task.wait(timeout=5)
        
        # v4.8.0: 仅支持 Inspector 模式
        # Phase 11: 支持发现模式
        parsed_data = _parse_inspector_output()
        
        # 更新 session 的步骤(兼容旧逻辑)
        if parsed_data.get('mode') == 'discovery':
            recorder_session.steps = []  # 发现模式没有 steps
            steps_count = len(parsed_data.get('available_options', []))
        else:
            recorder_session.steps = parsed_data.get('steps', [])
            steps_count = len(recorder_session.steps)
        
        # 关闭浏览器资源(清理subprocess引用)
        def cleanup_thread():
            try:
                recorder_session.cleanup_sync()
            except Exception as e:
                logger.error(f"Error during browser cleanup: {e}", exc_info=True)
        
        threading.Thread(target=cleanup_thread, daemon=True).start()
        
        # 停止录制
        recorder_session.stop()
        
        # Phase 11: 根据模式返回不同的数据
        mode = parsed_data.get('mode', 'steps')
        
        if mode == 'discovery':
            logger.info(f"Recording stopped: {steps_count} options discovered")
            response = {
                "success": True,
                "message": f"录制已停止,共发现 {steps_count} 个选项",
                "mode": "discovery",
                "options_count": steps_count,
                "open_action": parsed_data.get('open_action'),
                "available_options": parsed_data.get('available_options', []),
                "default_option": parsed_data.get('default_option'),
                "test_config": parsed_data.get('test_config', {}),  # Phase 12.2: 自动捕获的测试配置
            }
        else:
            logger.info(f"Recording stopped: {steps_count} steps recorded")
            steps = recorder_session.steps.copy()
            # 在 clear() 之前从会话取元数据并生成 Python 代码（仅 mode=steps 且存在 steps 时）
            platform = getattr(recorder_session, 'platform', None) or ''
            component_type = getattr(recorder_session, 'component_type', None) or ''

            # 根据 step_group 补充 step_type / scene_tags（6.6 步骤语义）
            steps = _enrich_steps_semantics(steps)

            login_field_suggestions: List[Dict[str, Any]] = []
            if component_type:
                # 针对 login 组件进行账号/密码字段自动变量化与语义标记
                steps, login_field_suggestions = _normalize_login_steps_and_suggestions(
                    steps=steps,
                    component_type=component_type,
                )

            python_code = ''
            lint_errors: List[Dict[str, Any]] = []
            lint_warnings: List[Dict[str, Any]] = []

            if platform and component_type and steps:
                try:
                    default_component_name = component_type
                    python_code = generate_python_code(
                        platform=platform,
                        component_type=component_type,
                        component_name=default_component_name,
                        steps=steps,
                    )
                    lint_result = _analyze_python_code_for_lints(python_code)
                    lint_errors = lint_result.get("errors", [])
                    lint_warnings = lint_result.get("warnings", [])
                except Exception as e:
                    logger.error(f"Steps to Python generator failed: {e}", exc_info=True)

            response = {
                "success": True,
                "message": f"录制已停止,共记录 {steps_count} 个步骤",
                "mode": "steps",
                "steps_count": steps_count,
                "steps": steps,
                "platform": platform,
                "component_type": component_type,
                "python_code": python_code if python_code else None,
                "login_field_suggestions": login_field_suggestions or None,
                "lint_errors": lint_errors or [],
                "lint_warnings": lint_warnings or [],
            }
        recorder_session.clear()
        return response
    
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"停止录制失败: {str(e)}",
            status_code=500,
            recovery_suggestion="请稍后重试或检查录制会话状态",
        )


@router.post("/recorder/generate-python")
async def generate_python_from_steps(request: GeneratePythonRequest):
    """
    根据步骤重新生成 Python 代码（供前端「重新生成」按钮调用）。
    """
    try:
        steps = list(request.steps or [])
        steps = _enrich_steps_semantics(steps)
        login_field_suggestions: List[Dict[str, Any]] = []
        if request.component_type:
            steps, login_field_suggestions = _normalize_login_steps_and_suggestions(
                steps=steps,
                component_type=request.component_type,
            )

        code = generate_python_code(
            platform=request.platform,
            component_type=request.component_type,
            component_name=request.component_name,
            steps=steps,
        )
        lint_result = _analyze_python_code_for_lints(code)
        return {
            "success": True,
            "python_code": code,
            "login_field_suggestions": login_field_suggestions or None,
            "lint_errors": lint_result.get("errors", []) or [],
            "lint_warnings": lint_result.get("warnings", []) or [],
        }
    except Exception as e:
        logger.error(f"Generate Python failed: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"生成 Python 失败: {str(e)}",
            status_code=500,
            recovery_suggestion="请检查步骤数据格式是否正确，或联系管理员",
        )


@router.get("/recorder/steps")
async def get_recording_steps():
    """
    获取录制步骤(用于前端轮询)
    
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
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"获取步骤失败: {str(e)}",
            status_code=500,
            recovery_suggestion="请确认录制会话已启动，稍后重试",
        )


@router.post("/recorder/save")
async def save_component(request: RecorderSaveRequest, db: AsyncSession = Depends(get_async_db)):
    """
    保存组件到文件并自动注册到版本管理系统。
    仅支持 Python 组件：请求体必须提供 python_code，不再接受 yaml_content。
    """
    import ast
    from pathlib import Path
    from modules.core.db import ComponentVersion
    from datetime import datetime

    if not request.python_code:
        return error_response(
            code=ErrorCode.PARAMETER_INVALID,
            message="仅支持保存 Python 组件，请提供 python_code。yaml_content 已废弃。",
            status_code=400,
            recovery_suggestion="请使用录制工具生成 Python 代码后保存",
        )

    is_python_component = True  # 本接口仅保存 Python 组件
    try:
        project_root = Path(__file__).parent.parent.parent

        # 1. 验证 Python 代码语法
        try:
            ast.parse(request.python_code)
        except SyntaxError as e:
            logger.error(f"Python syntax error in save: {e}", exc_info=True)
            return error_response(
                code=ErrorCode.DATA_FORMAT_INVALID,
                message=f"Python 代码语法错误: {str(e)}",
                status_code=400,
                recovery_suggestion="请检查 Python 代码语法，或使用「重新生成」按钮",
            )

        # 2. 确定保存路径
        component_dir = project_root / "modules" / "platforms" / request.platform / "components"
        component_dir.mkdir(parents=True, exist_ok=True)

        # 3. 文件名
        filename = f"{request.component_name}.py"
        file_path = component_dir / filename

        # 4. 检查文件是否已存在
        file_exists = file_path.exists()

        # 4.5 登录组件且提供 success_criteria 时，在写入前注入成功条件校验
        code_to_write = request.python_code
        if (
            request.component_type == "login"
            and request.success_criteria
            and isinstance(request.success_criteria, dict)
        ):
            code_to_write = _inject_login_success_criteria_block(code_to_write, request.success_criteria)

        # 5. 保存文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code_to_write)

        logger.info(
            f"Python component saved: {request.platform}/{filename} "
            f"({'updated' if file_exists else 'created'})"
        )

        # 6. 自动注册到 component_versions 表（仅记录 .py 路径）
        component_name = f"{request.platform}/{request.component_name}"
        relative_file_path = f"modules/platforms/{request.platform}/components/{filename}"

        # ==================== 版本管理逻辑(通用) ====================
        
        # 查询现有版本(按 file_path 查询,确保更新正确的版本)
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.file_path == relative_file_path)
        )
        existing_version = result.scalar_one_or_none()
        
        if existing_version:
            # 更新现有版本(不创建新版本)
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
    
    except HTTPException as he:
        logger.error("Re-raising HTTPException from save_component: %s", he)
        raise he
    except Exception as e:
        logger.error(f"Failed to save component: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"保存组件失败: {str(e)}",
            status_code=500,
            recovery_suggestion="请检查文件权限和平台/组件名称，稍后重试",
        )


@router.post("/recorder/add-step")
async def add_recording_step(step: Dict[str, Any]):
    """
    添加录制步骤(由Playwright监听器调用)
    
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
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"添加步骤失败: {str(e)}",
            status_code=500,
            recovery_suggestion="请确认录制会话处于活跃状态，稍后重试",
        )


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


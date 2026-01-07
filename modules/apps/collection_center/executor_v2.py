"""
采集执行引擎 V2 - Collection Executor V2

组件驱动的采集执行引擎，支持：
- 组件加载和执行
- 弹窗自动处理
- 状态回调和进度报告
- 超时控制和取消检测
- 验证码暂停处理
"""

import os
import asyncio
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field

from modules.core.logger import get_logger
from modules.apps.collection_center.component_loader import ComponentLoader
from modules.apps.collection_center.popup_handler import UniversalPopupHandler, StepPopupHandler
from modules.apps.collection_center.python_component_adapter import PythonComponentAdapter, create_adapter

logger = get_logger(__name__)

# Phase 9.4: 版本管理支持（懒加载，避免循环依赖）
_version_service = None

def _get_version_service():
    """懒加载版本管理服务（避免导入时的循环依赖）"""
    global _version_service
    if _version_service is None:
        try:
            from backend.services.component_version_service import ComponentVersionService
            from backend.models.database import SessionLocal
            
            db = SessionLocal()
            _version_service = ComponentVersionService(db)
            logger.info("ComponentVersionService initialized for executor")
        except Exception as e:
            logger.warning(f"Failed to initialize ComponentVersionService: {e}")
            _version_service = False  # 标记为尝试过但失败
    
    return _version_service if _version_service is not False else None


@dataclass
class CollectionResult:
    """采集结果（v4.7.0）"""
    task_id: str
    status: str  # completed, partial_success, failed, cancelled, paused
    files_collected: int = 0
    collected_files: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    # v4.7.0: 任务粒度优化
    completed_domains: List[str] = field(default_factory=list)
    failed_domains: List[Dict[str, str]] = field(default_factory=list)
    total_domains: int = 0


@dataclass
class TaskContext:
    """任务上下文（用于任务恢复）v4.7.0"""
    task_id: str
    platform: str
    account_id: str
    data_domains: List[str]
    date_range: Dict[str, str]
    granularity: str
    
    # v4.7.0: 子域支持
    sub_domains: Optional[List[str]] = None
    
    # 执行状态
    current_component_index: int = 0
    current_step_index: int = 0
    current_data_domain_index: int = 0
    collected_files: List[str] = field(default_factory=list)
    
    # v4.7.0: 任务粒度优化
    completed_domains: List[str] = field(default_factory=list)
    failed_domains: List[Dict[str, str]] = field(default_factory=list)
    
    # 验证码状态
    verification_required: bool = False
    verification_type: Optional[str] = None
    screenshot_path: Optional[str] = None


class StepExecutionError(Exception):
    """步骤执行错误"""
    pass


class VerificationRequiredError(Exception):
    """需要验证码"""
    def __init__(self, verification_type: str, screenshot_path: str = None):
        self.verification_type = verification_type
        self.screenshot_path = screenshot_path
        super().__init__(f"Verification required: {verification_type}")


class TaskCancelledError(Exception):
    """任务被取消"""
    pass


class CollectionExecutorV2:
    """
    组件驱动的采集执行引擎
    
    功能：
    1. 组件加载和顺序执行
    2. 弹窗自动处理
    3. 状态回调和进度报告
    4. 超时控制
    5. 任务取消检测
    6. 验证码暂停处理
    7. 文件处理和注册
    8. ⭐ Phase 9.1: 并行执行支持（多域并行采集）
    """
    
    # 默认超时配置
    DEFAULT_COMPONENT_TIMEOUT = int(os.getenv('COMPONENT_TIMEOUT', 300))  # 5分钟
    DEFAULT_TASK_TIMEOUT = int(os.getenv('TASK_TIMEOUT', 1800))  # 30分钟
    DEFAULT_DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', 120))  # 2分钟
    
    def __init__(
        self,
        component_loader: ComponentLoader = None,
        popup_handler: UniversalPopupHandler = None,
        status_callback: Callable[[str, int, str], Awaitable[None]] = None,
        is_cancelled_callback: Callable[[str], Awaitable[bool]] = None,
    ):
        """
        初始化执行引擎
        
        Args:
            component_loader: 组件加载器
            popup_handler: 弹窗处理器
            status_callback: 状态回调函数 (task_id, progress, message) -> None
            is_cancelled_callback: 取消检测函数 (task_id) -> bool
        
        Note: v4.7.4 移除 WebSocket，统一使用 HTTP 轮询
        """
        self.component_loader = component_loader or ComponentLoader()
        self.popup_handler = popup_handler or UniversalPopupHandler()
        self.status_callback = status_callback
        self.is_cancelled_callback = is_cancelled_callback
        
        # 任务上下文缓存（用于暂停/恢复）
        self._task_contexts: Dict[str, TaskContext] = {}
        
        # 下载目录
        self.temp_dir = Path(os.getenv('TEMP_DIR', 'temp'))
        self.downloads_dir = self.temp_dir / 'downloads'
        self.screenshots_dir = self.temp_dir / 'screenshots'
        
        # 确保目录存在
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # v4.8.0: Python 组件模式（移除 YAML 支持）
        # 设置为 True 强制使用 Python 组件
        self.use_python_components = True  # 默认使用 Python 组件
        
        logger.info("CollectionExecutorV2 initialized (Python components mode)")
    
    def _load_component_with_version(
        self,
        component_name: str,
        params: Dict[str, Any],
        enable_ab_test: bool = True,
        force_version: str = None
    ) -> Dict[str, Any]:
        """
        加载组件，支持版本选择（Phase 9.4）
        
        Args:
            component_name: 组件名称（如shopee/login）
            params: 组件参数
            enable_ab_test: 是否启用A/B测试
            force_version: 强制使用指定版本
        
        Returns:
            加载的组件配置
        """
        version_service = _get_version_service()
        
        # 如果版本服务不可用，直接加载默认组件
        if version_service is None:
            logger.debug(f"Version service not available, loading default component: {component_name}")
            return self.component_loader.load(component_name, params)
        
        try:
            # 使用版本服务选择版本
            selected_version = version_service.select_version_for_use(
                component_name=component_name,
                force_version=force_version,
                enable_ab_test=enable_ab_test
            )
            
            if selected_version:
                logger.info(
                    f"Loading component {component_name} v{selected_version.version} "
                    f"(stable={selected_version.is_stable}, testing={selected_version.is_testing})"
                )
                
                # 加载选定的版本
                component = self.component_loader.load(
                    selected_version.file_path.replace('.yaml', ''),  # 移除.yaml扩展名
                    params
                )
                
                # 记录版本ID用于后续统计
                component['_version_id'] = selected_version.id
                component['_version_number'] = selected_version.version
                
                return component
            else:
                # 没有找到版本记录，加载默认组件
                logger.debug(f"No version record found, loading default component: {component_name}")
                return self.component_loader.load(component_name, params)
                
        except Exception as e:
            logger.warning(f"Failed to use version service for {component_name}: {e}, falling back to default")
            return self.component_loader.load(component_name, params)
    
    def _load_execution_order(self, platform: str) -> Optional[List[Dict]]:
        """
        加载平台执行顺序配置（Phase 7.2优化）
        
        Args:
            platform: 平台名称（shopee, tiktok等）
        
        Returns:
            执行顺序列表，如果没有配置则返回None
        """
        try:
            import yaml
            
            # 尝试加载平台特定配置
            platform_order_file = self.component_loader.components_dir / platform / "execution_order.yaml"
            
            if platform_order_file.exists():
                with open(platform_order_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    execution_seq = config.get('execution_sequence', [])
                    logger.info(f"Loaded execution order for {platform}: {len(execution_seq)} components")
                    return execution_seq
            
            # 尝试加载默认配置
            default_order_file = self.component_loader.components_dir.parent / "collection_components" / "default_execution_order.yaml"
            
            if default_order_file.exists():
                with open(default_order_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    execution_seq = config.get('execution_sequence', [])
                    logger.info(f"Loaded default execution order for {platform}: {len(execution_seq)} components")
                    return execution_seq
        
        except Exception as e:
            logger.warning(f"Failed to load execution order for {platform}: {e}")
        
        return None
    
    def _get_default_execution_order(self) -> List[Dict]:
        """
        获取硬编码的默认执行顺序（向后兼容）
        
        Returns:
            默认执行顺序列表
        """
        return [
            {'component': 'login', 'required': True, 'index': 0},
            {'component': 'shop_switch', 'required': False, 'index': 1},
            {'component': 'navigation', 'required': False, 'index': 2},
            {'component': 'export', 'required': True, 'index': 3},
        ]
    
    def _evaluate_condition(self, condition: Optional[str], params: Dict[str, Any]) -> bool:
        """
        评估条件表达式（Phase 7.2优化）
        
        Args:
            condition: 条件字符串（如 "{{not account.has_multiple_shops}}"）
            params: 参数字典
        
        Returns:
            True表示条件满足，False表示不满足
        """
        if not condition:
            return True
        
        try:
            # 简单的变量替换和评估
            # TODO: 实现更完整的表达式评估器
            
            # 替换变量
            import re
            def replace_var(match):
                var_path = match.group(1).strip()
                
                # 处理 not 运算符
                negate = False
                if var_path.startswith('not '):
                    negate = True
                    var_path = var_path[4:].strip()
                
                # 获取变量值
                parts = var_path.split('.')
                value = params
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                    if value is None:
                        break
                
                # 应用 not
                if negate:
                    value = not value
                
                return str(value).lower() if isinstance(value, bool) else str(value)
            
            evaluated = re.sub(r'\{\{(.+?)\}\}', replace_var, condition)
            
            # 评估布尔值
            if evaluated.lower() in ('true', '1', 'yes'):
                return True
            elif evaluated.lower() in ('false', '0', 'no', 'none'):
                return False
            
            return bool(evaluated)
        
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return True  # 默认执行
    
    async def start_browser(self, debug_mode: bool = False):
        """
        启动浏览器（v4.7.0 - 环境感知配置）
        
        根据环境自动选择有头/无头模式：
        - 开发环境：默认有头模式（便于观察）
        - 生产环境：自动无头模式（适合Docker）
        - 调试模式：强制有头模式（覆盖生产环境配置）
        
        Args:
            debug_mode: 调试模式（临时启用有头浏览器）
            
        Returns:
            tuple: (playwright, browser, context)
        """
        from playwright.async_api import async_playwright
        from backend.utils.config import get_settings
        
        settings = get_settings()
        browser_config = settings.browser_config.copy()
        
        # v4.7.0: 调试模式覆盖（生产环境临时有头）
        if debug_mode:
            browser_config['headless'] = False
            logger.info("Debug mode enabled: forcing headful browser")
        
        logger.info(f"Starting browser: environment={settings.ENVIRONMENT}, headless={browser_config['headless']}, slow_mo={browser_config.get('slow_mo', 0)}")
        
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(**browser_config)
        
        # 创建浏览器上下文（反检测指纹）
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            accept_downloads=True,
            downloads_path=str(self.downloads_dir),
        )
        
        return playwright, browser, context
    
    async def execute(
        self,
        task_id: str,
        platform: str,
        account_id: str,
        account: Dict[str, Any],
        data_domains: List[str],
        date_range: Dict[str, str],
        granularity: str,
        page = None,  # Playwright Page对象
        context: TaskContext = None,  # 用于恢复任务
        sub_domains: Optional[List[str]] = None,  # v4.7.0: 子域数组
        debug_mode: bool = False,  # v4.7.0: 调试模式
    ) -> CollectionResult:
        """
        执行采集任务（v4.7.0 - 任务粒度优化）
        
        v4.7.0 更新：
        - 支持子域数组循环（sub_domains）
        - 支持部分成功机制（单域失败不影响其他域）
        - 实时更新进度字段（completed_domains, failed_domains）
        - 一次登录后循环采集所有域（浏览器复用）
        
        Args:
            task_id: 任务ID
            platform: 平台代码（shopee/tiktok/miaoshou）
            account_id: 账号ID
            account: 账号信息（包含username, password等）
            data_domains: 数据域列表
            date_range: 日期范围 {"start": "2025-01-01", "end": "2025-01-31"}
            granularity: 粒度（daily/weekly/monthly）
            page: Playwright Page对象
            context: 任务上下文（用于恢复任务）
            sub_domains: 子域数组（v4.7.0）
            debug_mode: 调试模式（v4.7.0，仅用于日志记录）
            
        Returns:
            CollectionResult: 采集结果
        """
        start_time = datetime.now()
        
        # v4.7.0: 计算总数据域数量（含子域）
        total_domains_count = len(data_domains)
        if sub_domains:
            # 如果有子域，每个数据域 × 子域数量
            total_domains_count = len(data_domains) * len(sub_domains)
        
        logger.info(f"Task {task_id}: Starting collection for {total_domains_count} domains (debug_mode={debug_mode})")
        
        # 创建或恢复任务上下文
        if context is None:
            context = TaskContext(
                task_id=task_id,
                platform=platform,
                account_id=account_id,
                data_domains=data_domains,
                date_range=date_range,
                granularity=granularity,
                sub_domains=sub_domains,  # v4.7.0
            )
        
        self._task_contexts[task_id] = context
        
        # 创建任务下载目录
        task_download_dir = self.downloads_dir / task_id
        task_download_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建步骤弹窗处理器
        step_popup_handler = StepPopupHandler(self.popup_handler, platform)
        
        # 准备参数（用于变量替换）
        params = {
            'account': account,
            'params': {
                'date_from': date_range.get('start', ''),
                'date_to': date_range.get('end', ''),
                'granularity': granularity,
            },
            'task': {
                'id': task_id,
                'download_dir': str(task_download_dir),
                'screenshot_dir': str(self.screenshots_dir / task_id),
            },
            'platform': platform,
        }
        
        # Phase 9 架构简化（方案B）：导出组件自包含
        # 
        # 执行顺序简化为: Login → Export（循环各数据域）
        # 
        # 导出组件职责（自包含）：
        # 1. 导航到目标页面（URL 或点击菜单）
        # 2. 切换店铺（如需要，可调用 shop_switch 子组件）
        # 3. 选择日期范围（可调用 date_picker 子组件）
        # 4. 设置筛选条件（可调用 filters 子组件）
        # 5. 触发导出并下载文件
        # 
        # 执行器只关心 step 的 action 字段，不理解业务含义
        
        try:
            # v4.8.0: Python 组件模式
            if self.use_python_components:
                return await self._execute_with_python_components(
                    task_id=task_id,
                    platform=platform,
                    account=account,
                    params=params,
                    context=context,
                    page=page,
                    step_popup_handler=step_popup_handler,
                    task_download_dir=task_download_dir,
                    data_domains=data_domains,
                    sub_domains=sub_domains,
                    total_domains_count=total_domains_count,
                    start_time=start_time,
                )
            
            # ===== 以下为旧的 YAML 组件执行流程（将被废弃） =====
            
            # 检查是否需要跳过登录（恢复任务）
            if context.current_component_index == 0:
                # 1. 执行登录组件（⭐ Phase 9.4: 使用版本选择）
                await self._update_status(task_id, 5, "正在加载登录组件...")
                await self._check_cancelled(task_id)
                
                login_component = self._load_component_with_version(
                    f"{platform}/login",
                    params,
                    enable_ab_test=True  # 启用A/B测试
                )
                
                await self._update_status(task_id, 10, "正在登录...")
                login_success = await self._execute_component(page, login_component, step_popup_handler)
                
                if not login_success:
                    raise StepExecutionError("登录组件执行失败，成功标准验证未通过")
                
                logger.info(f"Task {task_id}: Login component completed successfully")
                context.current_component_index = 1
            
            # Phase 9 架构简化（方案B）：导出组件自包含
            # 执行顺序简化为: Login → Export（循环各数据域）
            # 
            # 导出组件现在包含完整流程：
            # - 导航到目标页面
            # - 切换店铺（如需要）
            # - 选择日期范围
            # - 设置筛选条件
            # - 触发导出并下载文件
            #
            # 导出组件可以通过 component_call 调用子组件（date_picker, shop_switch, filters）
            # 执行器只关心 action 字段，不理解业务含义
            
            context.current_component_index = 1  # 登录完成后直接进入导出阶段
            
            # 2. 循环执行各数据域导出（v4.7.0: 支持子域和部分成功）
            domain_index = 0
            for i, domain in enumerate(data_domains):
                # 跳过已完成的数据域（恢复任务）
                if i < context.current_data_domain_index:
                    continue
                
                context.current_data_domain_index = i
                
                # v4.7.0: 如果有子域，循环采集每个子域
                sub_domain_list = sub_domains if sub_domains else [None]
                
                for sub_domain in sub_domain_list:
                    # v4.7.0: 构造完整域名（domain:sub_domain）
                    full_domain = f"{domain}:{sub_domain}" if sub_domain else domain
                    
                    # 跳过已完成的域（恢复任务）
                    if full_domain in context.completed_domains:
                        continue
                    
                    domain_index += 1
                    progress = 20 + int(70 * domain_index / total_domains_count)
                    await self._update_status(task_id, progress, f"正在采集 {full_domain}...")
                    await self._check_cancelled(task_id)
                    
                    # 更新参数中的数据域
                    params['params']['data_domain'] = domain
                    if sub_domain:
                        params['params']['sub_domain'] = sub_domain
                    
                    try:
                        # v4.7.0: 回调更新 current_domain
                        if self.status_callback:
                            try:
                                # 尝试调用扩展版本的回调（带current_domain参数）
                                await self.status_callback(task_id, progress, f"正在采集 {full_domain}...", full_domain)
                            except TypeError:
                                # 降级到旧版本回调
                                await self.status_callback(task_id, progress, f"正在采集 {full_domain}...")
                        
                        # 加载并执行导出组件
                        component_name = f"{platform}/{domain}_export"
                        if sub_domain:
                            # 尝试子域特定组件，如 shopee/services_agent_export（⭐ Phase 9.4: 版本选择）
                            component_name = f"{platform}/{domain}_{sub_domain}_export"
                            try:
                                export_component = self._load_component_with_version(component_name, params, enable_ab_test=True)
                            except FileNotFoundError:
                                # 回退到通用组件
                                component_name = f"{platform}/{domain}_export"
                                export_component = self._load_component_with_version(component_name, params, enable_ab_test=True)
                        else:
                            export_component = self._load_component_with_version(component_name, params, enable_ab_test=True)
                        
                        file_path = await self._execute_export_component(
                            page, 
                            export_component, 
                            step_popup_handler,
                            task_download_dir
                        )
                        
                        if file_path:
                            context.collected_files.append(file_path)
                        
                        # v4.7.0: 标记为成功
                        context.completed_domains.append(full_domain)
                        logger.info(f"Task {task_id}: Successfully collected {full_domain}")
                    
                    except FileNotFoundError as e:
                        # 组件不存在，标记为失败但继续
                        error_msg = f"Export component not found: {component_name}"
                        logger.warning(f"Task {task_id}: {error_msg}")
                        context.failed_domains.append({
                            "domain": full_domain,
                            "error": error_msg
                        })
                        continue
                    
                    except VerificationRequiredError as e:
                        # 验证码暂停，不更新completed/failed，等待恢复
                        context.verification_required = True
                        context.verification_type = e.verification_type
                        context.screenshot_path = e.screenshot_path
                        
                        # v4.7.4: 验证码状态通过 HTTP 轮询获取，不再使用 WebSocket
                        
                        return CollectionResult(
                            task_id=task_id,
                            status="paused",
                            files_collected=len(context.collected_files),
                            collected_files=context.collected_files,
                            error_message=f"需要验证码: {e.verification_type}",
                            duration_seconds=(datetime.now() - start_time).total_seconds(),
                            completed_domains=context.completed_domains,
                            failed_domains=context.failed_domains,
                            total_domains=total_domains_count,
                        )
                    
                    except Exception as e:
                        # v4.7.0: 部分成功机制 - 单域失败不影响其他域
                        error_msg = f"{type(e).__name__}: {str(e)}"
                        logger.error(f"Task {task_id}: Failed to collect {full_domain} - {error_msg}")
                        context.failed_domains.append({
                            "domain": full_domain,
                            "error": error_msg
                        })
                        # 继续执行其他域
                        continue
            
            # 4. 处理采集到的文件
            await self._update_status(task_id, 95, "正在处理文件...")
            processed_files = await self._process_files(
                context.collected_files, 
                platform, 
                data_domains, 
                granularity,
                account=account,
                date_range=date_range
            )
            
            # 5. v4.7.0: 根据成功/失败情况决定最终状态
            duration = (datetime.now() - start_time).total_seconds()
            
            completed_count = len(context.completed_domains)
            failed_count = len(context.failed_domains)
            
            if completed_count == 0 and failed_count > 0:
                # 全部失败
                final_status = "failed"
                final_message = f"采集失败，0/{total_domains_count} 个域成功"
            elif failed_count > 0:
                # 部分成功
                final_status = "partial_success"
                final_message = f"部分成功，{completed_count}/{total_domains_count} 个域成功，{failed_count} 个失败"
            else:
                # 全部成功
                final_status = "completed"
                final_message = f"采集完成，共采集 {len(processed_files)} 个文件"
            
            await self._update_status(task_id, 100, final_message)
            
            logger.info(f"Task {task_id}: {final_status} - completed={completed_count}, failed={failed_count}, files={len(processed_files)}")
            
            # v4.7.4: 完成状态通过 HTTP 轮询获取，不再使用 WebSocket
            
            # 清理任务上下文
            self._task_contexts.pop(task_id, None)
            
            return CollectionResult(
                task_id=task_id,
                status=final_status,
                files_collected=len(processed_files),
                collected_files=processed_files,
                duration_seconds=duration,
                completed_domains=context.completed_domains,
                failed_domains=context.failed_domains,
                total_domains=total_domains_count,
            )
        
        except TaskCancelledError:
            logger.info(f"Task {task_id} was cancelled")
            
            # v4.7.4: 取消状态通过 HTTP 轮询获取，不再使用 WebSocket
            
            return CollectionResult(
                task_id=task_id,
                status="cancelled",
                files_collected=len(context.collected_files),
                collected_files=context.collected_files,
                error_message="任务已取消",
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                completed_domains=context.completed_domains,
                failed_domains=context.failed_domains,
                total_domains=total_domains_count,
            )
        
        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            
            # 保存错误截图
            try:
                if page:
                    screenshot_path = self.screenshots_dir / task_id / "error.png"
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(screenshot_path))
            except Exception as screenshot_error:
                logger.error(f"Failed to save error screenshot: {screenshot_error}")
            
            # v4.7.4: 失败状态通过 HTTP 轮询获取，不再使用 WebSocket
            
            return CollectionResult(
                task_id=task_id,
                status="failed",
                files_collected=len(context.collected_files),
                collected_files=context.collected_files,
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                completed_domains=context.completed_domains,
                failed_domains=context.failed_domains,
                total_domains=total_domains_count,
            )
    
    def _record_version_usage(self, component: Dict[str, Any], success: bool) -> None:
        """
        记录版本使用情况（Phase 9.4）
        
        Args:
            component: 组件配置
            success: 是否成功
        """
        version_id = component.get('_version_id')
        version_number = component.get('_version_number')
        component_name = component.get('name', 'unknown')
        
        if not version_id or not version_number:
            # 没有版本信息，跳过记录
            return
        
        try:
            version_service = _get_version_service()
            if version_service:
                # 从组件名称中提取实际的组件路径（移除版本号）
                # 例如：shopee_login_v1.0 -> shopee/login
                base_name = component_name.rsplit('_v', 1)[0] if '_v' in component_name else component_name
                base_name = base_name.replace('_', '/')
                
                version_service.record_usage(
                    component_name=base_name,
                    version=version_number,
                    success=success
                )
                
                logger.debug(
                    f"Recorded version usage: {base_name} v{version_number}, "
                    f"success={success}"
                )
        except Exception as e:
            logger.warning(f"Failed to record version usage: {e}")
    
    async def _execute_python_component(
        self,
        page,
        adapter: PythonComponentAdapter,
        component_type: str,
        params: Dict[str, Any] = None,
    ) -> bool:
        """
        使用 Python 组件适配层执行组件（v4.8.0）
        
        替代 YAML 组件的执行逻辑，直接调用异步 Python 组件。
        
        Args:
            page: Playwright Page 对象
            adapter: Python 组件适配器
            component_type: 组件类型（login/navigation/orders_export 等）
            params: 组件参数
        
        Returns:
            bool: True 表示执行成功
        """
        params = params or {}
        
        try:
            logger.info(f"[PythonComponent] Executing: {component_type}")
            
            result = await adapter.execute_component(component_type, page, params)
            
            if result.success:
                logger.info(f"[PythonComponent] {component_type} completed successfully")
                if result.file_path:
                    logger.info(f"[PythonComponent] File saved: {result.file_path}")
                return True
            else:
                logger.error(f"[PythonComponent] {component_type} failed: {result.message}")
                return False
                
        except Exception as e:
            logger.error(f"[PythonComponent] {component_type} exception: {e}")
            return False
    
    async def _execute_with_python_components(
        self,
        task_id: str,
        platform: str,
        account: Dict[str, Any],
        params: Dict[str, Any],
        context: TaskContext,
        page,
        step_popup_handler: StepPopupHandler,
        task_download_dir: Path,
        data_domains: List[str],
        sub_domains: Optional[List[str]],
        total_domains_count: int,
        start_time: datetime,
    ) -> CollectionResult:
        """
        v4.8.0: 使用 Python 组件执行采集流程
        
        完全替代 YAML 组件的执行流程，直接调用异步 Python 组件。
        
        执行顺序：
        1. Login（登录组件）
        2. Loop: Export（循环执行各数据域的导出组件）
        
        Args:
            task_id: 任务ID
            platform: 平台代码
            account: 账号信息
            params: 采集参数
            context: 任务上下文
            page: Playwright Page 对象
            step_popup_handler: 步骤弹窗处理器
            task_download_dir: 下载目录
            data_domains: 数据域列表
            sub_domains: 子域列表
            total_domains_count: 总域数量
            start_time: 开始时间
        
        Returns:
            CollectionResult: 采集结果
        """
        # 创建 Python 组件适配器
        adapter = create_adapter(
            platform=platform,
            account=account,
            params=params.get('params', {}),
            download_dir=str(task_download_dir),
        )
        
        # 1. 执行登录组件
        if context.current_component_index == 0:
            await self._update_status(task_id, 5, "正在登录...")
            await self._check_cancelled(task_id)
            
            # 检查弹窗
            await self.popup_handler.close_popups(page, platform=platform)
            
            login_success = await self._execute_python_component(
                page=page,
                adapter=adapter,
                component_type="login",
                params=params,
            )
            
            if not login_success:
                raise StepExecutionError("登录组件执行失败")
            
            logger.info(f"Task {task_id}: [Python] Login completed successfully")
            context.current_component_index = 1
        
        # 2. 循环执行各数据域导出
        domain_index = 0
        for i, domain in enumerate(data_domains):
            if i < context.current_data_domain_index:
                continue
            
            context.current_data_domain_index = i
            sub_domain_list = sub_domains if sub_domains else [None]
            
            for sub_domain in sub_domain_list:
                full_domain = f"{domain}:{sub_domain}" if sub_domain else domain
                
                if full_domain in context.completed_domains:
                    continue
                
                domain_index += 1
                progress = 20 + int(70 * domain_index / total_domains_count)
                await self._update_status(task_id, progress, f"正在采集 {full_domain}...")
                await self._check_cancelled(task_id)
                
                # 更新参数
                export_params = params.copy()
                export_params['params'] = {
                    **export_params.get('params', {}),
                    'data_domain': domain,
                }
                if sub_domain:
                    export_params['params']['sub_domain'] = sub_domain
                
                try:
                    # 回调更新 current_domain
                    if self.status_callback:
                        try:
                            await self.status_callback(task_id, progress, f"正在采集 {full_domain}...", full_domain)
                        except TypeError:
                            await self.status_callback(task_id, progress, f"正在采集 {full_domain}...")
                    
                    # 检查弹窗
                    await self.popup_handler.close_popups(page, platform=platform)
                    
                    # 确定导出组件名称
                    component_name = f"{domain}_export"
                    if sub_domain:
                        component_name = f"{domain}_{sub_domain}_export"
                    
                    # 执行导出组件
                    export_result = await adapter.export(
                        data_domain=domain,
                        page=page,
                        params=export_params.get('params', {}),
                    )
                    
                    if export_result.success:
                        if export_result.file_path:
                            context.collected_files.append(export_result.file_path)
                        context.completed_domains.append(full_domain)
                        logger.info(f"Task {task_id}: [Python] Successfully collected {full_domain}")
                    else:
                        raise StepExecutionError(f"Export failed: {export_result.message}")
                
                except FileNotFoundError as e:
                    error_msg = f"Export component not found: {component_name}"
                    logger.warning(f"Task {task_id}: {error_msg}")
                    context.failed_domains.append({
                        "domain": full_domain,
                        "error": error_msg
                    })
                    continue
                
                except VerificationRequiredError as e:
                    context.verification_required = True
                    context.verification_type = e.verification_type
                    context.screenshot_path = e.screenshot_path
                    
                    return CollectionResult(
                        task_id=task_id,
                        status="paused",
                        files_collected=len(context.collected_files),
                        collected_files=context.collected_files,
                        error_message=f"Need verification: {e.verification_type}",
                        duration_seconds=(datetime.now() - start_time).total_seconds(),
                        completed_domains=context.completed_domains,
                        failed_domains=context.failed_domains,
                        total_domains=total_domains_count,
                    )
                
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    logger.error(f"Task {task_id}: Failed to collect {full_domain} - {error_msg}")
                    context.failed_domains.append({
                        "domain": full_domain,
                        "error": error_msg
                    })
                    continue
        
        # 3. 处理采集到的文件
        await self._update_status(task_id, 95, "Processing files...")
        processed_files = await self._process_files(
            context.collected_files,
            platform,
            data_domains,
            params.get('params', {}).get('granularity', 'daily'),
            account=account,
            date_range=context.date_range
        )
        
        # 4. 生成最终结果
        duration = (datetime.now() - start_time).total_seconds()
        completed_count = len(context.completed_domains)
        failed_count = len(context.failed_domains)
        
        if completed_count == 0 and failed_count > 0:
            final_status = "failed"
            final_message = f"Collection failed, 0/{total_domains_count} domains succeeded"
        elif failed_count > 0:
            final_status = "partial_success"
            final_message = f"Partial success, {completed_count}/{total_domains_count} domains succeeded, {failed_count} failed"
        else:
            final_status = "completed"
            final_message = f"Collection completed, {len(processed_files)} files collected"
        
        await self._update_status(task_id, 100, final_message)
        logger.info(f"Task {task_id}: [Python] {final_status} - completed={completed_count}, failed={failed_count}, files={len(processed_files)}")
        
        self._task_contexts.pop(task_id, None)
        
        return CollectionResult(
            task_id=task_id,
            status=final_status,
            files_collected=len(processed_files),
            collected_files=processed_files,
            duration_seconds=duration,
            completed_domains=context.completed_domains,
            failed_domains=context.failed_domains,
            total_domains=total_domains_count,
        )
    
    async def _execute_component(
        self, 
        page, 
        component: Dict[str, Any], 
        step_popup_handler: StepPopupHandler
    ) -> bool:
        """
        执行组件中的所有步骤并验证成功标准（v4.7.0+: Phase 7.1）
        
        Phase 11: 支持发现模式组件（date_picker, filters）
        
        Args:
            page: Playwright Page对象
            component: 组件配置
            step_popup_handler: 步骤弹窗处理器
        
        Returns:
            bool: True表示组件执行成功并通过验证，False表示失败
        """
        component_name = component.get('name', 'unknown')
        component_type = component.get('type', '')
        
        # Phase 11: 检测发现模式组件
        if component_type in ['date_picker', 'filters']:
            return await self._execute_discovery_component(page, component, step_popup_handler)
        
        # v4.7.0: 执行预检测
        pre_check = component.get('pre_check', [])
        if pre_check:
            pre_check_result = await self._run_pre_checks(page, component, pre_check)
            if not pre_check_result:
                logger.warning(f"Component {component_name}: Pre-check failed, skipping")
                return False
        
        steps = component.get('steps', [])
        
        # 组件执行前检查弹窗
        popup_handling = component.get('popup_handling', {})
        if popup_handling.get('check_before_steps', True):
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
        
        # 执行所有步骤（v4.7.2增强：智能重试+Optional步骤处理）
        step_failed = False
        for i, step in enumerate(steps):
            step_name = step.get('action', 'unknown')
            optional = step.get('optional', False)
            max_retries = step.get('max_retries', 2)  # ⭐ 可配置重试次数，默认2次
            
            # 步骤执行前检查弹窗
            await step_popup_handler.before_step(page, step, component)
            
            success = False
            last_error = None
            
            # ⭐ 改进：支持多次重试
            for attempt in range(max_retries + 1):
                try:
                    # 执行步骤
                    await self._execute_step(page, step, component)
                    success = True
                    break  # 成功，退出重试循环
                
                except Exception as e:
                    last_error = e
                    
                    if attempt < max_retries:
                        # ⭐ 还有重试机会，处理弹窗后重试
                        logger.warning(
                            f"Component {component_name}: Step {i} ({step_name}) failed "
                            f"(attempt {attempt + 1}/{max_retries + 1}): {str(e)[:100]}"
                        )
                        
                        # ⭐ 关键改进：关闭弹窗并等待页面稳定
                        await step_popup_handler.on_error(page, step, component)
                        
                        logger.info(f"Retrying step {i} ({step_name})...")
                    else:
                        # ⭐ 所有重试都失败了
                        logger.error(
                            f"Component {component_name}: Step {i} ({step_name}) failed "
                            f"after {max_retries + 1} attempts: {str(e)[:100]}"
                        )
            
            # ⭐ 改进：根据步骤类型决定是否继续
            if not success:
                if optional:
                    # ⭐ Optional 步骤失败，记录警告但继续执行
                    logger.warning(
                        f"Component {component_name}: Optional step {i} ({step_name}) failed, "
                        f"continuing with next steps"
                    )
                else:
                    # ⭐ 必需步骤失败，标记并退出
                    logger.error(
                        f"Component {component_name}: Required step {i} ({step_name}) failed, "
                        f"stopping component execution"
                    )
                    step_failed = True
                    break  # 退出步骤循环
            
            # 步骤执行后检查弹窗
            await step_popup_handler.after_step(page, step, component)
        
        # 组件执行后检查弹窗
        if popup_handling.get('check_after_steps', True):
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
        
        # Phase 7.1: 验证成功标准
        success_criteria = component.get('success_criteria', [])
        success_result = False
        
        if success_criteria:
            verification_result = await self._verify_success_criteria(
                page, 
                success_criteria, 
                component
            )
            
            if verification_result['success']:
                logger.info(f"Component {component_name}: Success criteria verified")
                success_result = True
            else:
                logger.warning(
                    f"Component {component_name}: Success criteria verification failed: "
                    f"{verification_result['reason']}"
                )
                
                # 检查是否有错误处理器
                error_handlers = component.get('error_handlers', [])
                if error_handlers:
                    error_handled = await self._handle_errors(page, error_handlers, component)
                    if error_handled:
                        # 错误已处理，重新验证
                        retry_verification = await self._verify_success_criteria(page, success_criteria, component)
                        success_result = retry_verification['success']
                    else:
                        success_result = False
                else:
                    success_result = False
        else:
            # 没有成功标准，只要步骤执行完就认为成功
            if step_failed:
                logger.warning(f"Component {component_name}: Steps failed but no success criteria to verify")
                success_result = False
            else:
                logger.debug(f"Component {component_name}: No success criteria, assuming success")
                success_result = True
        
        # ⭐ Phase 9.4: 记录版本使用情况
        self._record_version_usage(component, success_result)
        
        return success_result
    
    async def _execute_discovery_component(
        self,
        page,
        component: Dict[str, Any],
        step_popup_handler: StepPopupHandler
    ) -> bool:
        """
        执行发现模式组件（Phase 11）
        
        发现模式组件结构：
        - open_action: 打开动作（如点击日期控件）
        - available_options: 可用选项列表
        - params.date_range 或 params.filter_value: 要选择的选项 key
        
        执行流程：
        1. 执行 open_action（打开选择器）
        2. 根据参数找到对应的选项
        3. 点击该选项
        
        Args:
            page: Playwright Page对象
            component: 发现模式组件配置
            step_popup_handler: 步骤弹窗处理器
        
        Returns:
            bool: 是否执行成功
        """
        component_name = component.get('name', 'unknown')
        component_type = component.get('type', '')
        params = component.get('_params', {})
        
        logger.info(f"Executing discovery component: {component_name} (type: {component_type})")
        
        # 获取 open_action
        open_action = component.get('open_action')
        if not open_action:
            logger.error(f"Discovery component {component_name}: Missing open_action")
            return False
        
        # 获取 available_options
        available_options = component.get('available_options', [])
        if not available_options:
            logger.error(f"Discovery component {component_name}: No available options")
            return False
        
        # 确定要选择的选项 key
        # date_picker 使用 date_range，filters 使用 filter_value
        option_key = params.get('date_range') or params.get('filter_value')
        if not option_key:
            # 使用默认选项
            option_key = component.get('default_option')
            if not option_key and available_options:
                option_key = available_options[0].get('key')
        
        logger.info(f"Discovery component {component_name}: Selecting option '{option_key}'")
        
        # 找到对应的选项
        selected_option = None
        for opt in available_options:
            if opt.get('key') == option_key:
                selected_option = opt
                break
        
        if not selected_option:
            logger.error(f"Discovery component {component_name}: Option '{option_key}' not found")
            logger.info(f"Available options: {[o.get('key') for o in available_options]}")
            return False
        
        try:
            # 1. 执行 open_action（打开选择器）
            await step_popup_handler.before_step(page, open_action, component)
            
            open_step = {
                'action': 'click',
                'selectors': open_action.get('selectors', []),
                'selector': self._get_primary_selector_from_list(open_action.get('selectors', [])),
                'timeout': open_action.get('timeout', 5000),
            }
            await self._execute_step(page, open_step, component)
            
            # 等待选项出现
            await asyncio.sleep(0.5)
            
            # 2. 点击选中的选项
            option_step = {
                'action': 'click',
                'selectors': selected_option.get('selectors', []),
                'selector': self._get_primary_selector_from_list(selected_option.get('selectors', [])),
                'timeout': 5000,
            }
            await self._execute_step(page, option_step, component)
            
            logger.info(f"Discovery component {component_name}: Successfully selected '{option_key}'")
            return True
            
        except Exception as e:
            logger.error(f"Discovery component {component_name}: Failed to execute: {e}")
            return False
    
    def _get_primary_selector_from_list(self, selectors: list) -> str:
        """从选择器列表中获取主选择器（用于降级）"""
        if not selectors:
            return ''
        
        # 优先使用 text 类型（更稳定）
        for sel in selectors:
            if sel.get('type') == 'text':
                return f"text={sel.get('value', '')}"
        
        # 其次使用 css 类型
        for sel in selectors:
            if sel.get('type') == 'css':
                return sel.get('value', '')
        
        # 降级使用第一个
        first = selectors[0]
        if first.get('type') == 'text':
            return f"text={first.get('value', '')}"
        return first.get('value', '')
    
    async def _execute_step(self, page, step: Dict[str, Any], component: Dict[str, Any]) -> Any:
        """
        执行单个步骤（v4.7.0: 支持optional和retry，Phase 2.5.5: 支持fallback）
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component: 组件配置（用于获取平台等信息）
            
        Returns:
            Any: 步骤执行结果
        """
        action = step.get('action')
        timeout = step.get('timeout', 5000)
        optional = step.get('optional', False)  # v4.7.0: 可选步骤
        retry_config = step.get('retry')  # v4.7.0: 重试配置
        fallback_methods = step.get('fallback_methods')  # Phase 2.5.5: 降级方法
        
        # Phase 2.5.5: 如果配置了fallback，使用降级策略
        if fallback_methods:
            return await self._execute_with_fallback(page, step, component)
        
        # v4.7.0: 如果配置了重试，使用重试机制
        if retry_config:
            return await self._execute_step_with_retry(page, step, component)
        
        # v4.7.0: 对于需要定位元素的操作，支持optional
        needs_element = action in ['click', 'fill', 'select', 'check_element', 'wait']
        
        if optional and needs_element:
            # 快速检测元素是否存在
            selector = step.get('selector')
            if selector and not await self._check_element_exists_quick(page, selector):
                logger.info(f"Optional step skipped: {action} {selector} - element not found")
                return None  # 跳过，不报错
        
        if action == 'navigate':
            url = step.get('url')
            wait_until = step.get('wait_until', 'load')
            await page.goto(url, wait_until=wait_until, timeout=timeout)
        
        elif action == 'click':
            wait_for = step.get('wait_for')
            delay = step.get('delay', 0)
            
            if wait_for:
                await page.wait_for_selector(wait_for, timeout=timeout)
            
            # Phase 10: 使用多选择器降级
            locator = await self._get_locator_with_fallback(page, step, timeout)
            await locator.click(timeout=timeout)
            
            if delay > 0:
                await asyncio.sleep(delay / 1000)
        
        elif action == 'fill':
            value = step.get('value', '')
            clear = step.get('clear', True)
            
            # Phase 10: 使用多选择器降级
            locator = await self._get_locator_with_fallback(page, step, timeout)
            
            if clear:
                await locator.clear(timeout=timeout)
            
            await locator.fill(value, timeout=timeout)
        
        elif action == 'wait':
            wait_type = step.get('type', 'timeout')
            
            if wait_type == 'timeout':
                duration = step.get('duration', 1000)
                await asyncio.sleep(duration / 1000)
            
            elif wait_type == 'selector':
                selector = step.get('selector')
                state = step.get('state', 'visible')
                smart_wait = step.get('smart_wait', False)  # Phase 2.5.4.2: 自适应等待
                
                if smart_wait:
                    # 使用自适应等待策略
                    await self._smart_wait_for_element(page, selector, timeout, state)
                else:
                    # 使用标准等待
                    await page.wait_for_selector(selector, state=state, timeout=timeout)
            
            elif wait_type == 'navigation':
                wait_until = step.get('wait_until', 'load')
                await page.wait_for_load_state(wait_until, timeout=timeout)
        
        elif action == 'select':
            value = step.get('value')
            by = step.get('by', 'value')
            
            # Phase 10: 使用多选择器降级
            locator = await self._get_locator_with_fallback(page, step, timeout)
            
            if by == 'value':
                await locator.select_option(value=value, timeout=timeout)
            elif by == 'label':
                await locator.select_option(label=value, timeout=timeout)
            elif by == 'index':
                await locator.select_option(index=int(value), timeout=timeout)
        
        elif action == 'check_element':
            selector = step.get('selector')
            expect = step.get('expect', 'visible')
            on_fail = step.get('on_fail', 'error')
            
            try:
                locator = page.locator(selector).first
                
                if expect == 'exists':
                    await locator.wait_for(state='attached', timeout=timeout)
                elif expect == 'not_exists':
                    await locator.wait_for(state='detached', timeout=timeout)
                elif expect == 'visible':
                    await locator.wait_for(state='visible', timeout=timeout)
                elif expect == 'hidden':
                    await locator.wait_for(state='hidden', timeout=timeout)
            
            except Exception as e:
                if on_fail == 'error':
                    raise
                elif on_fail == 'skip':
                    logger.warning(f"check_element failed, skipping: {e}")
                # on_fail == 'continue' 什么都不做
        
        elif action == 'screenshot':
            path = step.get('path', f'screenshot_{uuid.uuid4().hex[:8]}.png')
            full_page = step.get('full_page', False)
            await page.screenshot(path=path, full_page=full_page)
        
        elif action == 'component_call':
            component_path = step.get('component')
            component_params = step.get('params', {})
            
            # 合并参数
            merged_params = {**component.get('_params', {}), **component_params}
            
            # 加载并执行子组件
            sub_component = self.component_loader.load(component_path, merged_params)
            step_popup_handler = StepPopupHandler(
                self.popup_handler, 
                sub_component.get('platform')
            )
            await self._execute_component(page, sub_component, step_popup_handler)
        
        elif action == 'close_popups':
            platform = component.get('platform')
            await self.popup_handler.close_popups(page, platform=platform)
        
        else:
            logger.warning(f"Unknown action: {action}")
    
    async def _check_element_exists_quick(self, page, selector: str, timeout: int = 1000) -> bool:
        """
        快速检测元素是否存在（v4.7.0新增）
        
        Args:
            page: Playwright Page对象
            selector: 元素选择器
            timeout: 超时时间（毫秒，默认1秒）
            
        Returns:
            bool: 元素是否存在
        """
        try:
            await page.wait_for_selector(selector, state='attached', timeout=timeout)
            return True
        except Exception:
            return False
    
    async def _get_locator_with_fallback(
        self,
        page,
        step: Dict[str, Any],
        timeout: int = 5000
    ):
        """
        获取元素定位器，支持多选择器降级（Phase 10）
        
        按优先级尝试多个选择器：
        1. 如果配置了 selectors 数组，按优先级逐个尝试
        2. 降级到传统 selector 字段
        
        Args:
            page: Playwright Page对象
            step: 步骤配置（包含 selector 或 selectors）
            timeout: 超时时间（毫秒）
            
        Returns:
            Locator: 成功匹配的定位器
            
        Raises:
            Exception: 所有选择器都失败时抛出异常
        """
        selectors = step.get('selectors', [])
        legacy_selector = step.get('selector')
        
        # 如果没有 selectors 数组，使用传统 selector
        if not selectors and legacy_selector:
            return page.locator(legacy_selector).first
        
        # 按优先级排序
        sorted_selectors = sorted(selectors, key=lambda x: x.get('priority', 99))
        
        errors = []
        for sel_config in sorted_selectors:
            sel_type = sel_config.get('type', 'css')
            sel_value = sel_config.get('value', '')
            
            if not sel_value:
                continue
            
            try:
                # 根据类型构建定位器
                if sel_type == 'role':
                    # 解析 role[name="xxx"] 格式
                    if '[name=' in sel_value:
                        role = sel_value.split('[')[0]
                        name = sel_value.split('name="')[1].rstrip('"]')
                        locator = page.get_by_role(role, name=name)
                    else:
                        locator = page.get_by_role(sel_value)
                elif sel_type == 'text':
                    locator = page.get_by_text(sel_value)
                elif sel_type == 'css':
                    locator = page.locator(sel_value)
                elif sel_type == 'xpath':
                    locator = page.locator(f'xpath={sel_value}')
                else:
                    locator = page.locator(sel_value)
                
                # 快速验证元素是否存在
                await locator.first.wait_for(state='attached', timeout=1000)
                logger.debug(f"Selector matched: {sel_type}={sel_value}")
                return locator.first
                
            except Exception as e:
                errors.append(f"{sel_type}={sel_value}: {str(e)[:50]}")
                continue
        
        # 所有 selectors 都失败，尝试 legacy selector
        if legacy_selector:
            logger.debug(f"Fallback to legacy selector: {legacy_selector}")
            return page.locator(legacy_selector).first
        
        # 全部失败
        error_msg = f"All selectors failed: {'; '.join(errors[:3])}"
        logger.warning(error_msg)
        raise Exception(error_msg)
    
    async def _smart_wait_for_element(
        self,
        page,
        selector: str,
        max_timeout: int = 30000,
        state: str = 'visible'
    ) -> bool:
        """
        自适应等待元素（Phase 2.5.4.2）
        
        多层次等待策略，处理网络延迟和弹窗遮挡：
        1. 快速检测（1秒）- 元素已存在
        2. 关闭弹窗 + 重试（10秒）- 弹窗遮挡
        3. 等待网络空闲（5秒）- 网络慢
        4. 长时间等待（剩余时间）- 页面加载慢
        
        Args:
            page: Playwright Page对象
            selector: 元素选择器
            max_timeout: 最大超时时间（毫秒）
            state: 等待状态（visible/attached/hidden/detached）
            
        Returns:
            bool: 元素是否成功等待到
            
        Raises:
            Exception: 所有策略都失败时抛出异常
        """
        start_time = asyncio.get_event_loop().time()
        remaining_timeout = max_timeout
        
        # 策略1: 快速检测（1秒）
        try:
            logger.debug(f"Smart wait strategy 1: Quick check (1s) for {selector}")
            await page.wait_for_selector(selector, state=state, timeout=1000)
            logger.debug(f"Element found immediately: {selector}")
            return True
        except Exception:
            elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
            remaining_timeout = max(0, max_timeout - elapsed)
            logger.debug(f"Quick check failed, remaining timeout: {remaining_timeout}ms")
        
        # 策略2: 关闭弹窗 + 重试（10秒）
        if remaining_timeout > 0:
            try:
                logger.debug(f"Smart wait strategy 2: Close popups + retry (10s)")
                # 尝试关闭弹窗
                await self.popup_handler.close_popups(page)
                
                # 重试等待
                retry_timeout = min(10000, remaining_timeout)
                await page.wait_for_selector(selector, state=state, timeout=retry_timeout)
                logger.info(f"Element found after closing popups: {selector}")
                return True
            except Exception as e:
                elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
                remaining_timeout = max(0, max_timeout - elapsed)
                logger.debug(f"Popup strategy failed: {e}, remaining: {remaining_timeout}ms")
        
        # 策略3: 等待网络空闲（5秒）
        if remaining_timeout > 0:
            try:
                logger.debug(f"Smart wait strategy 3: Wait for network idle (5s)")
                network_timeout = min(5000, remaining_timeout)
                await page.wait_for_load_state('networkidle', timeout=network_timeout)
                
                # 网络空闲后再次尝试
                elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
                remaining_timeout = max(0, max_timeout - elapsed)
                
                if remaining_timeout > 0:
                    retry_timeout = min(5000, remaining_timeout)
                    await page.wait_for_selector(selector, state=state, timeout=retry_timeout)
                    logger.info(f"Element found after network idle: {selector}")
                    return True
            except Exception as e:
                elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
                remaining_timeout = max(0, max_timeout - elapsed)
                logger.debug(f"Network idle strategy failed: {e}, remaining: {remaining_timeout}ms")
        
        # 策略4: 长时间等待（剩余时间）
        if remaining_timeout > 0:
            try:
                logger.debug(f"Smart wait strategy 4: Long wait ({remaining_timeout}ms)")
                await page.wait_for_selector(selector, state=state, timeout=remaining_timeout)
                logger.info(f"Element found with long wait: {selector}")
                return True
            except Exception as e:
                logger.error(f"All smart wait strategies failed for {selector}: {e}")
                raise
        else:
            raise Exception(f"Smart wait timeout: {selector} not found after {max_timeout}ms")
    
    async def _run_pre_checks(
        self,
        page,
        component: Dict[str, Any],
        pre_checks: List[Dict[str, Any]]
    ) -> bool:
        """
        执行预检测（v4.7.0新增）
        
        Args:
            page: Playwright Page对象
            component: 组件配置
            pre_checks: 预检测配置列表
            
        Returns:
            bool: 是否通过所有预检测
        """
        for check in pre_checks:
            check_type = check.get('type')
            on_failure = check.get('on_failure', 'skip_task')
            
            try:
                if check_type == 'url_accessible':
                    # URL可访问性检测
                    url = check.get('url')
                    if not await self._check_url_accessible(page, url):
                        logger.warning(f"Pre-check failed: URL not accessible: {url}")
                        if on_failure == 'skip_task':
                            return False
                        elif on_failure == 'fail_task':
                            raise Exception(f"URL not accessible: {url}")
                        # on_failure == 'continue' 则继续
                
                elif check_type == 'element_exists':
                    # 元素存在性检测
                    selector = check.get('selector')
                    timeout = check.get('timeout', 3000)
                    if not await self._check_element_exists_quick(page, selector, timeout):
                        logger.warning(f"Pre-check failed: Element not found: {selector}")
                        if on_failure == 'skip_task':
                            return False
                        elif on_failure == 'fail_task':
                            raise Exception(f"Element not found: {selector}")
                        # on_failure == 'continue' 则继续
                
                else:
                    logger.warning(f"Unknown pre-check type: {check_type}")
            
            except Exception as e:
                logger.error(f"Pre-check error: {e}")
                if on_failure in ['skip_task', 'fail_task']:
                    return False
        
        return True
    
    async def _check_url_accessible(self, page, url: str, timeout: int = 5000) -> bool:
        """
        检查URL是否可访问（v4.7.0新增）
        
        Args:
            page: Playwright Page对象
            url: 要检查的URL
            timeout: 超时时间（毫秒）
            
        Returns:
            bool: URL是否可访问
        """
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            if response and response.status >= 400:
                logger.warning(f"URL returned error status: {response.status}")
                return False
            return True
        except Exception as e:
            logger.error(f"URL accessibility check failed: {e}")
            return False
    
    async def _verify_success_criteria(
        self,
        page,
        success_criteria: List[Dict[str, Any]],
        component: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        验证组件的成功标准（Phase 7.1: 显式成功验证机制）
        
        Args:
            page: Playwright Page对象
            success_criteria: 成功标准列表
            component: 组件配置（用于获取参数）
        
        Returns:
            Dict: {
                'success': bool,
                'reason': str,  # 失败原因
                'passed_criteria': List[str],  # 通过的验证项
                'failed_criteria': List[str]  # 失败的验证项
            }
        """
        # P1增强：验证前先处理弹窗，避免弹窗遮挡验证元素
        try:
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
            await page.wait_for_timeout(500)  # 等待弹窗关闭动画
        except Exception as e:
            logger.debug(f"Pre-verification popup handling failed: {e}")
        
        passed = []
        failed = []
        
        for criterion in success_criteria:
            criterion_type = criterion.get('type')
            optional = criterion.get('optional', False)
            comment = criterion.get('comment', '')
            
            try:
                result = False
                
                if criterion_type == 'url_contains':
                    # URL包含特定字符串
                    value = criterion.get('value')
                    current_url = page.url
                    result = value in current_url if value else False
                    
                elif criterion_type == 'url_matches':
                    # URL匹配正则表达式
                    import re
                    pattern = criterion.get('value')
                    current_url = page.url
                    result = bool(re.search(pattern, current_url)) if pattern else False
                    
                elif criterion_type == 'element_exists':
                    # 元素存在
                    selector = criterion.get('selector')
                    timeout = criterion.get('timeout', 5000)
                    if selector:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout, state='attached')
                            result = True
                        except:
                            result = False
                    
                elif criterion_type == 'element_visible':
                    # 元素可见
                    selector = criterion.get('selector')
                    timeout = criterion.get('timeout', 5000)
                    if selector:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout, state='visible')
                            result = True
                        except:
                            result = False
                    
                elif criterion_type == 'element_text_contains':
                    # 元素文本包含特定内容
                    selector = criterion.get('selector')
                    value = criterion.get('value')
                    timeout = criterion.get('timeout', 5000)
                    if selector and value:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout, state='visible')
                            text = await page.locator(selector).first.inner_text()
                            result = value.lower() in text.lower()
                        except:
                            result = False
                    
                elif criterion_type == 'page_contains_text':
                    # 页面包含文本
                    value = criterion.get('value')
                    if value:
                        try:
                            text = await page.inner_text('body')
                            result = value.lower() in text.lower()
                        except:
                            result = False
                    
                elif criterion_type == 'custom_js':
                    # 自定义JavaScript验证
                    script = criterion.get('script')
                    if script:
                        try:
                            result = await page.evaluate(script)
                            result = bool(result)
                        except:
                            result = False
                
                else:
                    logger.warning(f"Unknown success criterion type: {criterion_type}")
                    continue
                
                # 记录验证结果
                if result:
                    passed.append(f"{criterion_type}: {comment or 'passed'}")
                else:
                    if optional:
                        # 可选验证失败不影响整体
                        logger.debug(f"Optional criterion failed: {criterion_type}")
                    else:
                        failed.append(f"{criterion_type}: {comment or 'failed'}")
            
            except Exception as e:
                if not optional:
                    failed.append(f"{criterion_type}: Exception - {str(e)}")
                logger.debug(f"Criterion verification error: {e}")
        
        # 判断整体成功（所有非可选验证必须通过）
        success = len(failed) == 0
        
        return {
            'success': success,
            'reason': f"Failed: {', '.join(failed)}" if failed else "All criteria passed",
            'passed_criteria': passed,
            'failed_criteria': failed
        }
    
    async def _handle_errors(
        self,
        page,
        error_handlers: List[Dict[str, Any]],
        component: Dict[str, Any]
    ) -> bool:
        """
        处理错误（Phase 7.1: 错误处理器支持）
        
        Args:
            page: Playwright Page对象
            error_handlers: 错误处理器配置列表
            component: 组件配置
        
        Returns:
            bool: 是否成功处理错误
        """
        for handler in error_handlers:
            selector = handler.get('selector')
            action = handler.get('action', 'fail_task')
            message = handler.get('message', '')
            
            try:
                # 检查错误元素是否存在
                if selector:
                    element_exists = await self._check_element_exists_quick(page, selector)
                    if element_exists:
                        logger.warning(f"Error detected: {message}")
                        
                        if action == 'fail_task':
                            raise StepExecutionError(f"Error handler triggered: {message}")
                        elif action == 'retry_login':
                            logger.info("Retry login requested by error handler")
                            # TODO: 实现重新登录逻辑
                            return False
                        elif action == 'close_popup':
                            await self.popup_handler.close_popups(page, platform=component.get('platform'))
                            return True
            
            except Exception as e:
                logger.error(f"Error handler failed: {e}")
        
        return False
    
    async def _execute_step_with_retry(
        self, 
        page, 
        step: Dict[str, Any], 
        component: Dict[str, Any]
    ) -> Any:
        """
        执行步骤并支持重试（v4.7.0新增）
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component: 组件配置
            
        Returns:
            Any: 步骤执行结果
        """
        retry_config = step.get('retry', {})
        max_attempts = retry_config.get('max_attempts', 3)
        delay = retry_config.get('delay', 2000)  # 毫秒
        on_retry = retry_config.get('on_retry', 'wait')  # wait/close_popup
        
        last_error = None
        
        for attempt in range(1, max_attempts + 1):
            try:
                # 临时移除retry配置，避免递归
                step_copy = step.copy()
                step_copy.pop('retry', None)
                
                # 执行步骤
                result = await self._execute_step(page, step_copy, component)
                
                # 成功
                if attempt > 1:
                    logger.info(f"Step succeeded on retry attempt {attempt}/{max_attempts}")
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(f"Step failed on attempt {attempt}/{max_attempts}: {e}")
                
                # 最后一次尝试失败，抛出异常
                if attempt >= max_attempts:
                    logger.error(f"Step failed after {max_attempts} attempts")
                    raise
                
                # 执行重试前操作
                if on_retry == 'close_popup':
                    try:
                        await self.popup_handler.close_popups(page, platform=component.get('platform'))
                        logger.info("Closed popups before retry")
                    except Exception as popup_err:
                        logger.warning(f"Failed to close popups: {popup_err}")
                
                # 延迟后重试
                await asyncio.sleep(delay / 1000)
        
        # 理论上不会到达这里
        raise last_error
    
    async def _execute_with_fallback(
        self,
        page,
        step: Dict[str, Any],
        component: Dict[str, Any]
    ) -> Any:
        """
        使用降级策略执行步骤（Phase 2.5.5）
        
        尝试primary方法，失败后依次尝试fallback方法
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component: 组件配置
            
        Returns:
            Any: 步骤执行结果
            
        Example YAML:
            - action: click
              selector: button.primary-btn
              fallback_methods:
                - selector: button.secondary-btn
                  description: "备用按钮"
                - selector: a.link-btn
                  description: "链接按钮"
        """
        fallback_methods = step.get('fallback_methods', [])
        primary_selector = step.get('selector')
        
        # 尝试primary方法
        try:
            # 临时移除fallback_methods，避免递归
            step_copy = step.copy()
            step_copy.pop('fallback_methods', None)
            
            result = await self._execute_step(page, step_copy, component)
            logger.debug(f"Primary method succeeded: {primary_selector}")
            return result
        
        except Exception as primary_error:
            logger.warning(f"Primary method failed: {primary_selector} - {primary_error}")
            
            # 如果没有fallback方法，直接抛出异常
            if not fallback_methods:
                raise
            
            # 依次尝试fallback方法
            last_error = primary_error
            
            for i, fallback in enumerate(fallback_methods, 1):
                fallback_selector = fallback.get('selector')
                fallback_desc = fallback.get('description', f'fallback {i}')
                
                try:
                    logger.info(f"Trying fallback method {i}/{len(fallback_methods)}: {fallback_desc}")
                    
                    # 创建fallback步骤
                    fallback_step = step.copy()
                    fallback_step.pop('fallback_methods', None)  # 移除fallback配置
                    fallback_step['selector'] = fallback_selector  # 使用fallback选择器
                    
                    # 如果fallback有自己的timeout，使用它
                    if 'timeout' in fallback:
                        fallback_step['timeout'] = fallback['timeout']
                    
                    # 执行fallback步骤
                    result = await self._execute_step(page, fallback_step, component)
                    
                    logger.info(f"Fallback method succeeded: {fallback_desc} ({fallback_selector})")
                    return result
                
                except Exception as fallback_error:
                    logger.warning(f"Fallback method {i} failed: {fallback_desc} - {fallback_error}")
                    last_error = fallback_error
                    continue
            
            # 所有方法都失败
            logger.error(
                f"All methods failed (1 primary + {len(fallback_methods)} fallbacks) "
                f"for action: {step.get('action')}"
            )
            raise last_error
    
    async def _execute_export_component(
        self, 
        page, 
        component: Dict[str, Any], 
        step_popup_handler: StepPopupHandler,
        download_dir: Path
    ) -> Optional[str]:
        """
        执行导出组件并等待文件下载
        
        Args:
            page: Playwright Page对象
            component: 导出组件配置
            step_popup_handler: 步骤弹窗处理器
            download_dir: 下载目录
            
        Returns:
            Optional[str]: 下载的文件路径
        """
        steps = component.get('steps', [])
        download_path = None
        
        # 组件执行前检查弹窗
        popup_handling = component.get('popup_handling', {})
        if popup_handling.get('check_before_steps', True):
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
        
        for i, step in enumerate(steps):
            action = step.get('action')
            
            # 步骤执行前检查弹窗
            await step_popup_handler.before_step(page, step, component)
            
            try:
                if action == 'wait_for_download':
                    # 等待文件下载
                    timeout = step.get('timeout', self.DEFAULT_DOWNLOAD_TIMEOUT * 1000)
                    save_as = step.get('save_as')
                    
                    async with page.expect_download(timeout=timeout) as download_info:
                        # 下载会在前面的点击操作触发
                        pass
                    
                    download = await download_info.value
                    
                    # 确定保存路径
                    if save_as:
                        file_path = download_dir / save_as
                    else:
                        file_path = download_dir / download.suggested_filename
                    
                    await download.save_as(str(file_path))
                    download_path = str(file_path)
                    
                    logger.info(f"Downloaded file: {download_path}")
                
                else:
                    # 执行普通步骤
                    await self._execute_step(page, step, component)
            
            except Exception as e:
                # 错误时检查弹窗
                await step_popup_handler.on_error(page, step, component)
                
                # 检查是否是验证码
                if await self._check_verification(page):
                    screenshot_path = await self._save_verification_screenshot(page, component.get('platform'))
                    raise VerificationRequiredError('unknown', screenshot_path)
                
                raise StepExecutionError(f"Export step {i} failed: {e}") from e
            
            # 步骤执行后检查弹窗
            await step_popup_handler.after_step(page, step, component)
        
        # Phase 12.4: 如果没有 wait_for_download 步骤，自动扫描下载目录
        if download_path is None:
            logger.info("No wait_for_download step found, scanning download directory...")
            download_path = await self._scan_latest_download(download_dir, timeout=30)
            if download_path:
                logger.info(f"Auto-detected downloaded file: {download_path}")
        
        return download_path
    
    async def _scan_latest_download(
        self, 
        download_dir: Path, 
        timeout: int = 30,
        file_extensions: tuple = ('.xlsx', '.xls', '.csv', '.xlsm')
    ) -> Optional[str]:
        """
        扫描下载目录，查找最新下载的文件（兜底机制）
        
        Args:
            download_dir: 下载目录
            timeout: 超时时间（秒）
            file_extensions: 允许的文件扩展名
            
        Returns:
            Optional[str]: 最新文件的路径，如果未找到则返回None
        """
        import time
        
        start_time = time.time()
        
        # 记录执行前的文件列表
        before_files = set()
        for ext in file_extensions:
            before_files.update(download_dir.glob(f"*{ext}"))
        
        logger.debug(f"Before files count: {len(before_files)}")
        
        # 等待一段时间让文件下载完成
        await asyncio.sleep(2)
        
        # 轮询检查新文件
        check_interval = 1  # 每秒检查一次
        while time.time() - start_time < timeout:
            current_files = set()
            for ext in file_extensions:
                current_files.update(download_dir.glob(f"*{ext}"))
            
            new_files = current_files - before_files
            
            if new_files:
                # 过滤掉临时文件（.crdownload, .tmp等）
                valid_files = [
                    f for f in new_files 
                    if not any(f.name.endswith(ext) for ext in ['.crdownload', '.tmp', '.part'])
                ]
                
                if valid_files:
                    # 找到最新的文件（按修改时间）
                    latest_file = max(valid_files, key=lambda f: f.stat().st_mtime)
                    
                    # 检查文件是否完整（大小>0且不是临时文件）
                    if latest_file.stat().st_size > 0:
                        logger.info(f"Found new download: {latest_file.name} ({latest_file.stat().st_size} bytes)")
                        return str(latest_file)
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"No new download detected within {timeout} seconds")
        return None
    
    async def _check_verification(self, page) -> bool:
        """
        检查是否出现验证码
        
        Args:
            page: Playwright Page对象
            
        Returns:
            bool: 是否出现验证码
        """
        verification_selectors = [
            '[class*="captcha"]',
            '[class*="verify"]',
            '[class*="slider"]',
            '#captcha',
            '.captcha-container',
        ]
        
        for selector in verification_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=500):
                    return True
            except Exception:
                pass
        
        return False
    
    async def _save_verification_screenshot(self, page, platform: str = None) -> str:
        """
        保存验证码截图
        
        Args:
            page: Playwright Page对象
            platform: 平台代码
            
        Returns:
            str: 截图路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.screenshots_dir / f"verification_{platform}_{timestamp}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        
        await page.screenshot(path=str(screenshot_path))
        
        return str(screenshot_path)
    
    async def _process_files(
        self, 
        file_paths: List[str], 
        platform: str, 
        data_domains: List[str],
        granularity: str,
        account: Optional[Dict[str, Any]] = None,
        date_range: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """
        处理采集到的文件（v4.8.0更新：对齐数据同步模块要求）
        
        - 使用 StandardFileName.generate() 生成标准文件名
        - 移动到 data/raw/YYYY/ 目录
        - 使用 MetadataManager.create_meta_file() 生成 .meta.json 伴生文件
        - 调用 register_single_file() 注册到 catalog_files 表
        
        Args:
            file_paths: 文件路径列表
            platform: 平台代码
            data_domains: 数据域列表
            granularity: 粒度
            account: 账号信息（可选）
            date_range: 日期范围（可选）
            
        Returns:
            List[str]: 处理后的文件路径
        """
        from modules.core.file_naming import StandardFileName
        from modules.services.metadata_manager import MetadataManager
        
        processed = []
        
        # 提取账号信息
        account = account or {}
        account_label = account.get("label") or account.get("username") or "unknown"
        shop_id = account.get("shop_id") or account.get("store_name")
        
        # 提取日期范围
        date_range = date_range or {}
        date_from = date_range.get("start_date") or date_range.get("date_from")
        date_to = date_range.get("end_date") or date_range.get("date_to")
        
        for idx, file_path in enumerate(file_paths):
            try:
                source_path = Path(file_path)
                if not source_path.exists():
                    logger.warning(f"File not found: {file_path}")
                    continue
                
                # 推断数据域（从文件路径或data_domains列表）
                data_domain = self._infer_data_domain_from_path(file_path, data_domains, idx)
                sub_domain = self._infer_sub_domain_from_path(file_path)
                
                # 1. 生成标准文件名
                ext = source_path.suffix.lstrip('.') or 'xlsx'
                standard_filename = StandardFileName.generate(
                    source_platform=platform,
                    data_domain=data_domain,
                    granularity=granularity,
                    sub_domain=sub_domain,
                    ext=ext
                )
                
                # 2. 准备目标目录（data/raw/YYYY/）
                year = datetime.now().strftime("%Y")
                target_dir = Path("data/raw") / year
                target_dir.mkdir(parents=True, exist_ok=True)
                
                target_path = target_dir / standard_filename
                
                # 如果目标文件已存在，添加序号
                if target_path.exists():
                    base_name = target_path.stem
                    counter = 1
                    while target_path.exists():
                        target_path = target_dir / f"{base_name}_{counter}{target_path.suffix}"
                        counter += 1
                
                # 3. 移动文件
                shutil.move(str(source_path), str(target_path))
                logger.info(f"[OK] File moved: {source_path.name} -> {target_path}")
                
                # 4. 生成 .meta.json 伴生文件
                try:
                    business_metadata = {
                        "source_platform": platform,
                        "data_domain": data_domain,
                        "sub_domain": sub_domain,
                        "granularity": granularity,
                        "date_from": date_from,
                        "date_to": date_to,
                        "shop_id": shop_id
                    }
                    
                    collection_info = {
                        "method": "python_component",
                        "collection_platform": platform,
                        "account": account_label,
                        "shop_id": shop_id,
                        "original_path": str(source_path),
                        "collected_at": datetime.now().isoformat()
                    }
                    
                    meta_path = MetadataManager.create_meta_file(
                        file_path=target_path,
                        business_metadata=business_metadata,
                        collection_info=collection_info
                    )
                    logger.info(f"[OK] Meta file created: {meta_path.name}")
                    
                except Exception as meta_error:
                    logger.warning(f"[WARN] Failed to create meta file for {target_path}: {meta_error}")
                
                # 5. 注册到 catalog_files 表
                try:
                    from modules.services.catalog_scanner import register_single_file
                    catalog_id = register_single_file(str(target_path))
                    if catalog_id:
                        logger.info(f"[OK] File registered: {target_path.name} (id={catalog_id})")
                    else:
                        logger.warning(f"[WARN] File registration returned None: {target_path}")
                except Exception as reg_error:
                    logger.warning(f"[WARN] Failed to register file {target_path}: {reg_error}")
                
                processed.append(str(target_path))
            
            except Exception as e:
                logger.error(f"[FAIL] Failed to process file {file_path}: {e}")
        
        return processed
    
    def _infer_data_domain_from_path(self, file_path: str, data_domains: List[str], index: int) -> str:
        """
        从文件路径推断数据域
        
        Args:
            file_path: 文件路径
            data_domains: 数据域列表
            index: 文件索引
            
        Returns:
            str: 数据域
        """
        path_lower = file_path.lower()
        
        # 优先从路径中推断
        domain_keywords = {
            'orders': ['order', 'profit_statistics', '/stat/'],
            'products': ['product', 'goods', 'sku'],
            'inventory': ['warehouse', 'inventory', 'stock'],
            'finance': ['finance', 'settlement', 'payment'],
            'services': ['service', 'chat', 'cs', 'agent'],
            'analytics': ['analytics', 'traffic', 'overview', 'performance']
        }
        
        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in path_lower:
                    return domain
        
        # 降级：使用 data_domains 列表
        if data_domains and index < len(data_domains):
            # 处理可能包含子域的情况（如 "services.agent"）
            domain = data_domains[index]
            if '.' in domain:
                return domain.split('.')[0]
            return domain
        
        return "unknown"
    
    def _infer_sub_domain_from_path(self, file_path: str) -> str:
        """
        从文件路径推断子数据域
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 子数据域（空字符串表示无子域）
        """
        path_lower = file_path.lower()
        
        # 检测 services 子域
        if 'agent' in path_lower or 'ai_assistant' in path_lower:
            return 'agent'
        if 'ai' in path_lower and 'assistant' in path_lower:
            return 'ai_assistant'
        
        return ""
    
    async def _update_status(self, task_id: str, progress: int, message: str, current_domain: str = None) -> None:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            progress: 进度百分比(0-100)
            message: 状态消息
            current_domain: 当前采集域（v4.7.0）
        """
        logger.debug(f"Task {task_id}: {progress}% - {message}")
        
        # 现有回调
        if self.status_callback:
            try:
                # 尝试调用扩展版本的回调（带current_domain参数）
                try:
                    await self.status_callback(task_id, progress, message, current_domain)
                except TypeError:
                    # 降级到旧版本回调
                    await self.status_callback(task_id, progress, message)
            except Exception as e:
                logger.error(f"Status callback failed: {e}")
        
        # v4.7.4: 进度通过 HTTP 轮询获取，不再使用 WebSocket
    
    async def _check_cancelled(self, task_id: str) -> None:
        """
        检查任务是否被取消
        
        Args:
            task_id: 任务ID
            
        Raises:
            TaskCancelledError: 任务被取消
        """
        if self.is_cancelled_callback:
            try:
                is_cancelled = await self.is_cancelled_callback(task_id)
                if is_cancelled:
                    raise TaskCancelledError(f"Task {task_id} was cancelled")
            except TaskCancelledError:
                raise
            except Exception as e:
                logger.error(f"Cancelled callback failed: {e}")
    
    def get_task_context(self, task_id: str) -> Optional[TaskContext]:
        """
        获取任务上下文（用于任务恢复）
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[TaskContext]: 任务上下文
        """
        return self._task_contexts.get(task_id)
    
    async def resume_task(self, task_id: str, page, account: Dict[str, Any]) -> CollectionResult:
        """
        恢复暂停的任务
        
        Args:
            task_id: 任务ID
            page: Playwright Page对象
            account: 账号信息
            
        Returns:
            CollectionResult: 采集结果
        """
        context = self._task_contexts.get(task_id)
        
        if not context:
            return CollectionResult(
                task_id=task_id,
                status="failed",
                error_message="Task context not found",
            )
        
        # 重置验证码状态
        context.verification_required = False
        context.verification_type = None
        context.screenshot_path = None
        
        # 继续执行
        return await self.execute(
            task_id=task_id,
            platform=context.platform,
            account_id=context.account_id,
            account=account,
            data_domains=context.data_domains,
            date_range=context.date_range,
            granularity=context.granularity,
            page=page,
            context=context,
        )
    
    async def execute_parallel_domains(
        self,
        task_id: str,
        platform: str,
        account_id: str,
        account: Dict[str, Any],
        data_domains: List[str],
        date_range: Dict[str, str],
        granularity: str,
        browser,  # Playwright Browser对象
        max_parallel: int = 3,  # 最大并发数
        debug_mode: bool = False,
    ) -> CollectionResult:
        """
        ⭐ Phase 9.1: 并行执行多个数据域
        
        每个数据域使用独立的浏览器上下文（BrowserContext），共享登录Cookie
        
        Args:
            task_id: 任务ID
            platform: 平台代码
            account_id: 账号ID
            account: 账号信息
            data_domains: 数据域列表
            date_range: 日期范围
            granularity: 粒度
            browser: Playwright Browser对象
            max_parallel: 最大并发数（防止资源耗尽）
            debug_mode: 调试模式
            
        Returns:
            CollectionResult: 采集结果
        """
        start_time = datetime.now()
        logger.info(f"Task {task_id}: Starting PARALLEL collection for {len(data_domains)} domains (max_parallel={max_parallel})")
        
        # 创建任务上下文
        context = TaskContext(
            task_id=task_id,
            platform=platform,
            account_id=account_id,
            data_domains=data_domains,
            date_range=date_range,
            granularity=granularity,
        )
        self._task_contexts[task_id] = context
        
        # 创建任务下载目录
        task_download_dir = self.downloads_dir / task_id
        task_download_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 第一步：登录（使用主上下文）
        await self._update_status(task_id, 5, "正在登录...")
        
        login_context = await browser.new_context(
            accept_downloads=True,
            downloads_path=str(task_download_dir),
        )
        login_page = await login_context.new_page()
        
        try:
            # 执行登录组件
            login_component = self.component_loader.load(f"{platform}/login", {
                'account': account,
                'params': {'date_from': date_range.get('start', ''), 'date_to': date_range.get('end', ''), 'granularity': granularity},
                'platform': platform,
            })
            
            step_popup_handler = StepPopupHandler(self.popup_handler, platform)
            login_success = await self._execute_component(login_page, login_component, step_popup_handler)
            
            if not login_success:
                raise StepExecutionError("登录组件执行失败")
            
            # 获取登录后的Cookie和Storage
            cookies = await login_context.cookies()
            storage_state = await login_context.storage_state()
            
            logger.info(f"Task {task_id}: Login completed, extracted {len(cookies)} cookies")
            
        finally:
            await login_page.close()
            await login_context.close()
        
        # 2. 并行执行各个数据域
        await self._update_status(task_id, 15, f"开始并行采集 {len(data_domains)} 个数据域...")
        
        # 将数据域分组，每组max_parallel个
        domain_batches = []
        for i in range(0, len(data_domains), max_parallel):
            batch = data_domains[i:i+max_parallel]
            domain_batches.append(batch)
        
        logger.info(f"Task {task_id}: Split into {len(domain_batches)} batches (max_parallel={max_parallel})")
        
        # 批次执行
        for batch_index, batch in enumerate(domain_batches):
            logger.info(f"Task {task_id}: Processing batch {batch_index+1}/{len(domain_batches)} with {len(batch)} domains")
            
            # 为每个域创建异步任务
            tasks = []
            for domain in batch:
                task = self._execute_single_domain_parallel(
                    task_id=task_id,
                    platform=platform,
                    account=account,
                    data_domain=domain,
                    date_range=date_range,
                    granularity=granularity,
                    browser=browser,
                    storage_state=storage_state,
                    task_download_dir=task_download_dir,
                    domain_index=data_domains.index(domain),
                    total_domains=len(data_domains),
                )
                tasks.append(task)
            
            # 并行执行这一批
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for i, result in enumerate(results):
                domain = batch[i]
                if isinstance(result, Exception):
                    error_msg = f"{type(result).__name__}: {str(result)}"
                    logger.error(f"Task {task_id}: Domain {domain} failed - {error_msg}")
                    context.failed_domains.append({"domain": domain, "error": error_msg})
                elif result:
                    # 成功
                    file_path, success = result
                    if success:
                        context.completed_domains.append(domain)
                        if file_path:
                            context.collected_files.append(file_path)
                        logger.info(f"Task {task_id}: Domain {domain} completed")
                    else:
                        context.failed_domains.append({"domain": domain, "error": "Execution failed"})
        
        # 3. 处理采集到的文件
        await self._update_status(task_id, 95, "正在处理文件...")
        processed_files = await self._process_files(
            context.collected_files,
            platform,
            data_domains,
            granularity,
            account=account,
            date_range=date_range
        )
        
        # 4. 生成最终结果
        duration = (datetime.now() - start_time).total_seconds()
        completed_count = len(context.completed_domains)
        failed_count = len(context.failed_domains)
        
        if completed_count == 0 and failed_count > 0:
            final_status = "failed"
            final_message = f"采集失败，0/{len(data_domains)} 个域成功"
        elif failed_count > 0:
            final_status = "partial_success"
            final_message = f"部分成功，{completed_count}/{len(data_domains)} 个域成功，{failed_count} 个失败"
        else:
            final_status = "completed"
            final_message = f"采集完成，共采集 {len(processed_files)} 个文件"
        
        await self._update_status(task_id, 100, final_message)
        logger.info(f"Task {task_id}: Parallel execution completed in {duration:.1f}s - {final_status}")
        
        # 清理
        self._task_contexts.pop(task_id, None)
        
        return CollectionResult(
            task_id=task_id,
            status=final_status,
            files_collected=len(processed_files),
            collected_files=processed_files,
            duration_seconds=duration,
            completed_domains=context.completed_domains,
            failed_domains=context.failed_domains,
            total_domains=len(data_domains),
        )
    
    async def _execute_single_domain_parallel(
        self,
        task_id: str,
        platform: str,
        account: Dict[str, Any],
        data_domain: str,
        date_range: Dict[str, str],
        granularity: str,
        browser,
        storage_state: Dict,
        task_download_dir: Path,
        domain_index: int,
        total_domains: int,
    ) -> tuple:
        """
        ⭐ Phase 9.1: 在独立浏览器上下文中执行单个数据域采集
        
        Returns:
            tuple: (file_path, success)
        """
        domain_context = None
        domain_page = None
        
        try:
            # 使用共享的storage_state创建新上下文（包含登录Cookie）
            domain_context = await browser.new_context(
                storage_state=storage_state,
                accept_downloads=True,
                downloads_path=str(task_download_dir),
            )
            domain_page = await domain_context.new_page()
            
            logger.info(f"Task {task_id}: [{domain_index+1}/{total_domains}] Starting {data_domain} in parallel context")
            
            # 更新进度（每个域独立报告）
            progress = 20 + int(70 * domain_index / total_domains)
            await self._update_status(task_id, progress, f"[并行] 正在采集 {data_domain}...", data_domain)
            
            # 准备参数
            params = {
                'account': account,
                'params': {
                    'date_from': date_range.get('start', ''),
                    'date_to': date_range.get('end', ''),
                    'granularity': granularity,
                    'data_domain': data_domain,
                },
                'task': {
                    'id': task_id,
                    'download_dir': str(task_download_dir),
                    'screenshot_dir': str(self.screenshots_dir / task_id),
                },
                'platform': platform,
            }
            
            # 加载并执行导出组件
            component_name = f"{platform}/{data_domain}_export"
            export_component = self.component_loader.load(component_name, params)
            
            # 检查组件是否标记为parallel_safe
            if not export_component.get('parallel_safe', False):
                logger.warning(f"Task {task_id}: {component_name} is not marked as parallel_safe, executing anyway")
            
            step_popup_handler = StepPopupHandler(self.popup_handler, platform)
            
            file_path = await self._execute_export_component(
                domain_page,
                export_component,
                step_popup_handler,
                task_download_dir
            )
            
            logger.info(f"Task {task_id}: [{domain_index+1}/{total_domains}] {data_domain} completed successfully")
            return (file_path, True)
        
        except Exception as e:
            logger.error(f"Task {task_id}: [{domain_index+1}/{total_domains}] {data_domain} failed - {e}")
            return (None, False)
        
        finally:
            # 清理
            if domain_page:
                try:
                    await domain_page.close()
                except:
                    pass
            if domain_context:
                try:
                    await domain_context.close()
                except:
                    pass


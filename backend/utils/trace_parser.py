"""
Trace 解析器 - Playwright Trace 文件解析

v4.7.5: Inspector API 支持
- 解析 Playwright Trace 文件（.zip）
- 提取操作步骤并转换为组件 YAML 格式
- 符合 Playwright 官方 Trace 格式规范

Trace 文件结构:
- trace.trace: JSON 格式的事件流
- resources/: 截图和 DOM 快照
- trace.network: 网络请求日志

参考: https://playwright.dev/docs/trace-viewer
"""

import json
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedAction:
    """解析后的操作"""
    action_type: str  # click, fill, goto, wait, etc.
    selector: Optional[str] = None
    selectors: List[Dict[str, Any]] = field(default_factory=list)  # Phase 10: 多选择器
    value: Optional[str] = None
    url: Optional[str] = None
    timeout: Optional[int] = None
    timestamp: Optional[float] = None
    duration_ms: Optional[int] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None
    text_content: Optional[str] = None  # Phase 10: 元素文本
    element_role: Optional[str] = None  # Phase 10: 元素角色
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceParseResult:
    """Trace 解析结果"""
    success: bool
    actions: List[ParsedAction] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)  # YAML 格式步骤
    start_url: Optional[str] = None
    end_url: Optional[str] = None
    total_duration_ms: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TraceParser:
    """
    Playwright Trace 解析器
    
    功能:
    1. 解压并解析 Trace ZIP 文件
    2. 提取用户操作事件
    3. 转换为组件步骤格式
    4. 支持截图和 DOM 快照提取
    
    使用方式:
        parser = TraceParser()
        result = parser.parse("path/to/trace.zip")
        steps = result.steps  # YAML 格式步骤
    """
    
    # 支持的操作类型映射（Trace 事件 -> 组件步骤）
    ACTION_MAPPING = {
        'click': 'click',
        'fill': 'fill',
        'type': 'fill',  # type 通常等同于 fill
        'press': 'keyboard',
        'goto': 'navigate',
        'navigate': 'navigate',
        'waitForNavigation': 'wait',
        'waitForSelector': 'wait',
        'waitForTimeout': 'wait',
        'waitForLoadState': 'wait',
        'selectOption': 'select',
        'check': 'check',
        'uncheck': 'uncheck',
        'hover': 'hover',
        'scroll': 'scroll',
        'screenshot': 'screenshot',
    }
    
    # 需要忽略的内部事件
    IGNORED_EVENTS = {
        'frameAttached',
        'frameDetached',
        'pageCreated',
        'pageClosed',
        'browserContextCreated',
        'browserContextClosed',
        'console',
        'dialog',
        'download',
        'error',
        'log',
    }
    
    def __init__(self, output_dir: str = None):
        """
        初始化 Trace 解析器
        
        Args:
            output_dir: 解压输出目录（默认：temp/traces）
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent.parent / 'temp' / 'traces'
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"TraceParser initialized: output_dir={self.output_dir}")
    
    def parse(self, trace_path: str) -> TraceParseResult:
        """
        解析 Trace 文件
        
        Args:
            trace_path: Trace 文件路径（.zip）
            
        Returns:
            TraceParseResult: 解析结果
        """
        trace_path = Path(trace_path)
        
        if not trace_path.exists():
            return TraceParseResult(
                success=False,
                error=f"Trace file not found: {trace_path}"
            )
        
        if not trace_path.suffix == '.zip':
            return TraceParseResult(
                success=False,
                error=f"Invalid trace file format (expected .zip): {trace_path}"
            )
        
        try:
            # 1. 解压 Trace 文件
            extract_dir = self._extract_trace(trace_path)
            
            # 2. 解析事件流
            events = self._parse_trace_events(extract_dir)
            
            # 3. 提取用户操作
            actions = self._extract_actions(events)
            
            # 4. 转换为组件步骤
            steps = self._convert_to_steps(actions)
            
            # 5. 提取元数据
            metadata = self._extract_metadata(events)
            
            # 计算总时长
            total_duration = 0
            if actions:
                first_ts = actions[0].timestamp or 0
                last_ts = actions[-1].timestamp or 0
                total_duration = int((last_ts - first_ts) * 1000)
            
            logger.info(f"Trace parsed successfully: {len(actions)} actions, {len(steps)} steps")
            
            return TraceParseResult(
                success=True,
                actions=actions,
                steps=steps,
                start_url=metadata.get('start_url'),
                end_url=metadata.get('end_url'),
                total_duration_ms=total_duration,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Failed to parse trace: {e}", exc_info=True)
            return TraceParseResult(
                success=False,
                error=str(e)
            )
    
    def _extract_trace(self, trace_path: Path) -> Path:
        """
        解压 Trace 文件
        
        Args:
            trace_path: Trace 文件路径
            
        Returns:
            Path: 解压目录
        """
        # 创建解压目录（使用时间戳避免冲突）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        extract_dir = self.output_dir / f"trace_{timestamp}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # 解压
        with zipfile.ZipFile(trace_path, 'r') as zf:
            zf.extractall(extract_dir)
        
        logger.debug(f"Trace extracted to: {extract_dir}")
        return extract_dir
    
    def _parse_trace_events(self, extract_dir: Path) -> List[Dict[str, Any]]:
        """
        解析 Trace 事件流
        
        Args:
            extract_dir: 解压目录
            
        Returns:
            List[Dict]: 事件列表
        """
        events = []
        
        # 查找 trace 文件（可能是 trace.trace 或 trace.json）
        trace_files = list(extract_dir.glob('*.trace')) + list(extract_dir.glob('*.json'))
        
        for trace_file in trace_files:
            try:
                content = trace_file.read_text(encoding='utf-8')
                
                # Trace 文件可能是 NDJSON 格式（每行一个 JSON）
                for line in content.strip().split('\n'):
                    if line.strip():
                        try:
                            event = json.loads(line)
                            events.append(event)
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                logger.warning(f"Failed to parse trace file {trace_file}: {e}")
        
        logger.debug(f"Parsed {len(events)} events from trace")
        return events
    
    def _extract_actions(self, events: List[Dict[str, Any]]) -> List[ParsedAction]:
        """
        从事件流中提取用户操作
        
        Args:
            events: 事件列表
            
        Returns:
            List[ParsedAction]: 操作列表
        """
        actions = []
        
        for event in events:
            # 获取事件类型
            event_type = event.get('type', '')
            method = event.get('method', '')
            
            # 跳过忽略的事件
            if event_type in self.IGNORED_EVENTS or method in self.IGNORED_EVENTS:
                continue
            
            # 处理 action 类型事件
            if event_type == 'action' or 'action' in event:
                action_data = event.get('action', event)
                action = self._parse_action_event(action_data)
                if action:
                    actions.append(action)
            
            # 处理 before/after 类型事件（Playwright 新版格式）
            elif event_type in ('before', 'after') and 'apiName' in event:
                action = self._parse_api_event(event)
                if action:
                    actions.append(action)
        
        # 按时间戳排序
        actions.sort(key=lambda a: a.timestamp or 0)
        
        logger.debug(f"Extracted {len(actions)} user actions")
        return actions
    
    def _parse_action_event(self, action_data: Dict[str, Any]) -> Optional[ParsedAction]:
        """
        解析 action 类型事件
        
        Args:
            action_data: action 事件数据
            
        Returns:
            ParsedAction or None
        """
        action_type = action_data.get('action', action_data.get('name', ''))
        
        # 跳过不支持的操作
        if action_type not in self.ACTION_MAPPING:
            return None
        
        # 提取选择器
        selector = None
        if 'selector' in action_data:
            selector = action_data['selector']
        elif 'params' in action_data and 'selector' in action_data['params']:
            selector = action_data['params']['selector']
        
        # 提取值
        value = None
        if 'value' in action_data:
            value = action_data['value']
        elif 'params' in action_data and 'value' in action_data['params']:
            value = action_data['params']['value']
        elif 'text' in action_data:
            value = action_data['text']
        
        # 提取 URL（用于导航）
        url = None
        if 'url' in action_data:
            url = action_data['url']
        elif 'params' in action_data and 'url' in action_data['params']:
            url = action_data['params']['url']
        
        # 提取超时
        timeout = None
        if 'timeout' in action_data:
            timeout = action_data['timeout']
        elif 'params' in action_data and 'timeout' in action_data['params']:
            timeout = action_data['params']['timeout']
        
        # Phase 10: 提取文本内容和元素角色
        text_content = None
        element_role = None
        
        # 尝试从 selector 解析角色和名称
        if selector and selector.startswith('role='):
            import re
            match = re.search(r'role=(\w+)\[name=["\']?([^"\'\]]+)', selector)
            if match:
                element_role = match.group(1)
                text_content = match.group(2)
        
        # 从 text= 选择器提取文本
        if selector and selector.startswith('text='):
            text_content = selector[5:].strip('"\'')
        
        return ParsedAction(
            action_type=self.ACTION_MAPPING.get(action_type, action_type),
            selector=selector,
            value=value,
            url=url,
            timeout=timeout,
            timestamp=action_data.get('startTime', action_data.get('timestamp')),
            duration_ms=action_data.get('duration'),
            text_content=text_content,
            element_role=element_role,
            metadata=action_data
        )
    
    def _parse_api_event(self, event: Dict[str, Any]) -> Optional[ParsedAction]:
        """
        解析 API 事件（Playwright 新版格式）
        
        Args:
            event: API 事件数据
            
        Returns:
            ParsedAction or None
        """
        api_name = event.get('apiName', '')
        
        # 提取方法名（如 page.click -> click）
        if '.' in api_name:
            method = api_name.split('.')[-1]
        else:
            method = api_name
        
        # 跳过不支持的操作
        if method not in self.ACTION_MAPPING:
            return None
        
        params = event.get('params', {})
        selector = params.get('selector')
        
        # Phase 10: 提取文本内容和元素角色
        text_content = None
        element_role = None
        
        if selector:
            import re
            # 尝试从 role= 选择器解析
            match = re.search(r'role=(\w+)\[name=["\']?([^"\'\]]+)', selector)
            if match:
                element_role = match.group(1)
                text_content = match.group(2)
            # 从 text= 选择器提取
            elif selector.startswith('text='):
                text_content = selector[5:].strip('"\'')
        
        return ParsedAction(
            action_type=self.ACTION_MAPPING.get(method, method),
            selector=selector,
            value=params.get('value') or params.get('text'),
            url=params.get('url'),
            timeout=params.get('timeout'),
            timestamp=event.get('time', event.get('startTime')),
            duration_ms=event.get('duration'),
            text_content=text_content,
            element_role=element_role,
            metadata=event
        )
    
    def _convert_to_steps(self, actions: List[ParsedAction]) -> List[Dict[str, Any]]:
        """
        将操作转换为组件步骤格式
        
        Args:
            actions: 操作列表
            
        Returns:
            List[Dict]: YAML 格式步骤
        """
        steps = []
        step_id = 1
        
        for action in actions:
            step = self._action_to_step(action, step_id)
            if step:
                steps.append(step)
                step_id += 1
        
        return steps
    
    def _action_to_step(self, action: ParsedAction, step_id: int) -> Optional[Dict[str, Any]]:
        """
        将单个操作转换为步骤
        
        v4.8.0: 支持多选择器生成（Phase 10）
        
        Args:
            action: 操作
            step_id: 步骤 ID
            
        Returns:
            Dict: 步骤配置
        """
        step = {
            'id': step_id,
            'action': action.action_type,
        }
        
        # 根据操作类型添加不同字段
        if action.action_type == 'navigate':
            if action.url:
                step['url'] = action.url
                step['wait_until'] = 'domcontentloaded'
                step['comment'] = f"Navigate to {action.url}"
            else:
                return None
        
        elif action.action_type == 'click':
            if action.selector or action.selectors:
                # Phase 10: 添加多选择器
                selectors = self._generate_multi_selectors(action)
                if selectors:
                    step['selectors'] = selectors
                if action.selector:
                    step['selector'] = action.selector  # 保留传统选择器作为降级
                step['max_retries'] = 2
                step['comment'] = f"Click {self._format_selector_comment(action.selector or action.text_content or 'element')}"
            else:
                return None
        
        elif action.action_type == 'fill':
            if action.selector or action.selectors:
                # Phase 10: 添加多选择器
                selectors = self._generate_multi_selectors(action)
                if selectors:
                    step['selectors'] = selectors
                if action.selector:
                    step['selector'] = action.selector
                step['value'] = action.value or ''
                step['max_retries'] = 2
                step['comment'] = f"Fill {self._format_selector_comment(action.selector or 'input')}"
            else:
                return None
        
        elif action.action_type == 'wait':
            if action.timeout:
                step['type'] = 'timeout'
                step['timeout'] = action.timeout
                step['comment'] = f"Wait {action.timeout}ms"
            elif action.selector:
                step['type'] = 'selector'
                step['selector'] = action.selector
                step['comment'] = f"Wait for {self._format_selector_comment(action.selector)}"
            else:
                step['type'] = 'navigation'
                step['comment'] = "Wait for page load"
        
        elif action.action_type == 'select':
            if action.selector or action.selectors:
                # Phase 10: 添加多选择器
                selectors = self._generate_multi_selectors(action)
                if selectors:
                    step['selectors'] = selectors
                if action.selector:
                    step['selector'] = action.selector
                step['value'] = action.value or ''
                step['comment'] = f"Select {action.value}"
            else:
                return None
        
        elif action.action_type == 'keyboard':
            step['key'] = action.value or ''
            step['comment'] = f"Press key {action.value}"
        
        elif action.action_type == 'hover':
            if action.selector:
                step['selector'] = action.selector
                step['comment'] = f"Hover {self._format_selector_comment(action.selector)}"
            else:
                return None
        
        elif action.action_type == 'scroll':
            step['direction'] = 'down'
            step['distance'] = 300
            step['comment'] = "Scroll page"
        
        else:
            # 未知操作类型
            logger.warning(f"Unknown action type: {action.action_type}")
            return None
        
        return step
    
    def _generate_multi_selectors(self, action: ParsedAction) -> List[Dict[str, Any]]:
        """
        生成多重选择器（Phase 10）
        
        按优先级生成：
        1. role + name（最稳定）
        2. 文本匹配（较稳定）
        3. CSS 选择器（可能变化）
        
        Args:
            action: 操作对象
            
        Returns:
            List[Dict]: 选择器列表，按优先级排序
        """
        selectors = []
        
        # 如果已有 selectors，直接使用
        if action.selectors:
            return action.selectors
        
        # 1. Role + Name（最稳定）
        if action.element_role and action.text_content:
            selectors.append({
                'type': 'role',
                'value': f'{action.element_role}[name="{action.text_content}"]',
                'priority': 1
            })
        
        # 2. 文本匹配（较稳定）
        if action.text_content and len(action.text_content) < 50:
            selectors.append({
                'type': 'text',
                'value': action.text_content,
                'priority': 2
            })
        
        # 3. CSS 选择器（降级）
        if action.selector:
            selectors.append({
                'type': 'css',
                'value': action.selector,
                'priority': 3
            })
        
        return selectors
    
    def _format_selector_comment(self, selector: str) -> str:
        """
        格式化选择器为可读注释
        
        Args:
            selector: 选择器字符串
            
        Returns:
            str: 可读注释
        """
        if not selector:
            return "元素"
        
        # 提取角色和名称
        if selector.startswith('role='):
            import re
            match = re.search(r'role=(\w+)\[name=([^\]]+)\]', selector)
            if match:
                return f"{match.group(1)} '{match.group(2)}'"
        
        # 提取文本
        if selector.startswith('text='):
            return f"文本 '{selector[5:]}'"
        
        # 提取占位符
        if selector.startswith('placeholder='):
            return f"占位符 '{selector[12:]}'"
        
        # CSS 选择器
        if len(selector) > 30:
            return selector[:30] + "..."
        
        return selector
    
    def _extract_metadata(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        从事件流中提取元数据
        
        Args:
            events: 事件列表
            
        Returns:
            Dict: 元数据
        """
        metadata = {
            'start_url': None,
            'end_url': None,
            'pages': [],
            'resources_count': 0,
        }
        
        # 查找导航事件
        for event in events:
            if event.get('type') == 'action' or 'action' in event:
                action = event.get('action', event)
                if action.get('action') == 'goto' or action.get('name') == 'goto':
                    url = action.get('url') or (action.get('params', {}).get('url'))
                    if url:
                        if metadata['start_url'] is None:
                            metadata['start_url'] = url
                        metadata['end_url'] = url
                        metadata['pages'].append(url)
        
        return metadata


    def generate_python_skeleton(
        self,
        result: TraceParseResult,
        platform: str,
        component_type: str,
        data_domain: str = None,
        class_name: str = None,
    ) -> str:
        """
        v4.8.0: 生成 Python 组件骨架代码
        
        根据 Trace 解析结果生成 Python 组件类的骨架代码。
        
        Args:
            result: Trace 解析结果
            platform: 平台代码（shopee/tiktok/miaoshou）
            component_type: 组件类型（login/navigation/export 等）
            data_domain: 数据域（orders/products 等，仅 export 组件需要）
            class_name: 自定义类名（默认根据 component_type 生成）
        
        Returns:
            str: Python 组件代码
        
        Example:
            parser = TraceParser()
            result = parser.parse("trace.zip")
            code = parser.generate_python_skeleton(
                result, "shopee", "orders_export", "orders"
            )
        """
        # 生成类名
        if class_name is None:
            class_name = ''.join(
                word.capitalize() for word in component_type.split('_')
            ) + 'Component'
        
        # 生成文件头注释
        code_lines = [
            '"""',
            f'{platform.capitalize()} {component_type.replace("_", " ").title()} Component',
            '',
            f'Platform: {platform}',
            f'Type: {component_type}',
        ]
        if data_domain:
            code_lines.append(f'Data Domain: {data_domain}')
        code_lines.extend([
            '',
            'Auto-generated from Trace recording.',
            'Please review and customize as needed.',
            '"""',
            '',
            'from typing import Dict, Any, Optional',
            'from modules.core.logger import get_logger',
            '',
            f'logger = get_logger(__name__)',
            '',
            '',
        ])
        
        # 生成类定义
        code_lines.extend([
            f'class {class_name}:',
            f'    """',
            f'    {platform.capitalize()} {component_type.replace("_", " ").title()} Component',
            f'    ',
            f'    Auto-generated from Trace file.',
            f'    """',
            f'    ',
            f'    # Component metadata (required)',
            f'    platform = "{platform}"',
            f'    component_type = "{component_type}"',
        ])
        
        if data_domain:
            code_lines.append(f'    data_domain = "{data_domain}"')
        
        code_lines.extend([
            f'    ',
            f'    # Optional metadata',
            f'    description = "{platform.capitalize()} {component_type.replace("_", " ")}"',
            f'    version = "1.0.0"',
            f'    ',
        ])
        
        # 生成 __init__ 方法
        code_lines.extend([
            f'    def __init__(self, ctx=None):',
            f'        """',
            f'        Initialize component.',
            f'        ',
            f'        Args:',
            f'            ctx: Execution context (optional)',
            f'        """',
            f'        self.ctx = ctx',
            f'        self.logger = ctx.logger if ctx else logger',
            f'    ',
        ])
        
        # 生成 run 方法
        code_lines.extend([
            f'    async def run(self, page, account: Dict[str, Any], params: Dict[str, Any], **kwargs) -> Dict[str, Any]:',
            f'        """',
            f'        Execute component logic.',
            f'        ',
            f'        Args:',
            f'            page: Playwright Page object',
            f'            account: Account info (username, password, etc.)',
            f'            params: Execution parameters (date_from, date_to, etc.)',
            f'            **kwargs: Additional arguments',
            f'        ',
            f'        Returns:',
            f'            Dict: Execution result with "success" and optional "file_path"',
            f'        """',
            f'        self.logger.info(f"[{class_name}] Starting execution...")',
            f'        ',
            f'        try:',
        ])
        
        # 根据步骤生成代码
        if result.steps:
            for step in result.steps:
                step_code = self._step_to_python_code(step, indent=12)
                if step_code:
                    code_lines.append(step_code)
        else:
            code_lines.append(f'            # TODO: Implement component logic')
            code_lines.append(f'            pass')
        
        # 生成返回值和异常处理
        code_lines.extend([
            f'            ',
            f'            self.logger.info(f"[{class_name}] Execution completed successfully")',
            f'            return {{"success": True}}',
            f'            ',
            f'        except Exception as e:',
            f'            self.logger.error(f"[{class_name}] Execution failed: {{e}}")',
            f'            return {{"success": False, "error": str(e)}}',
        ])
        
        return '\n'.join(code_lines)
    
    def _step_to_python_code(self, step: Dict[str, Any], indent: int = 12) -> str:
        """
        将步骤转换为 Python 代码行
        
        Args:
            step: 步骤配置
            indent: 缩进空格数
        
        Returns:
            str: Python 代码行
        """
        indent_str = ' ' * indent
        action = step.get('action', '')
        comment = step.get('comment', '')
        
        lines = []
        
        # 添加注释
        if comment:
            lines.append(f'{indent_str}# {comment}')
        
        if action == 'navigate':
            url = step.get('url', '')
            wait_until = step.get('wait_until', 'domcontentloaded')
            lines.append(f'{indent_str}await page.goto("{url}", wait_until="{wait_until}")')
            lines.append(f'{indent_str}await page.wait_for_timeout(1000)')
        
        elif action == 'click':
            selector = step.get('selector', '')
            if selector.startswith('role='):
                # 使用 get_by_role
                import re
                match = re.search(r'role=(\w+)\[name=["\']?([^"\'\]]+)', selector)
                if match:
                    role = match.group(1)
                    name = match.group(2)
                    lines.append(f'{indent_str}await page.get_by_role("{role}", name="{name}").click()')
                else:
                    lines.append(f'{indent_str}await page.locator("{selector}").click()')
            elif selector.startswith('text='):
                text = selector[5:].strip('"\'')
                lines.append(f'{indent_str}await page.get_by_text("{text}").click()')
            else:
                lines.append(f'{indent_str}await page.locator("{selector}").click()')
        
        elif action == 'fill':
            selector = step.get('selector', '')
            value = step.get('value', '')
            
            # 检查是否应该使用变量
            if '{{' in value and '}}' in value:
                # 转换模板变量为 Python 变量访问
                py_value = value.replace('{{account.', 'account["').replace('{{params.', 'params["').replace('}}', '"]')
            else:
                py_value = f'"{value}"'
            
            if selector.startswith('role='):
                import re
                match = re.search(r'role=(\w+)\[name=["\']?([^"\'\]]+)', selector)
                if match:
                    role = match.group(1)
                    name = match.group(2)
                    lines.append(f'{indent_str}await page.get_by_role("{role}", name="{name}").fill({py_value})')
                else:
                    lines.append(f'{indent_str}await page.locator("{selector}").fill({py_value})')
            elif selector.startswith('placeholder='):
                placeholder = selector[12:].strip('"\'')
                lines.append(f'{indent_str}await page.get_by_placeholder("{placeholder}").fill({py_value})')
            else:
                lines.append(f'{indent_str}await page.locator("{selector}").fill({py_value})')
        
        elif action == 'wait':
            wait_type = step.get('type', 'timeout')
            if wait_type == 'timeout':
                timeout = step.get('timeout', 1000)
                lines.append(f'{indent_str}await page.wait_for_timeout({timeout})')
            elif wait_type == 'selector':
                selector = step.get('selector', '')
                lines.append(f'{indent_str}await page.wait_for_selector("{selector}", state="visible")')
            else:
                lines.append(f'{indent_str}await page.wait_for_load_state("networkidle")')
        
        elif action == 'select':
            selector = step.get('selector', '')
            value = step.get('value', '')
            lines.append(f'{indent_str}await page.locator("{selector}").select_option("{value}")')
        
        elif action == 'keyboard':
            key = step.get('key', '')
            lines.append(f'{indent_str}await page.keyboard.press("{key}")')
        
        elif action == 'hover':
            selector = step.get('selector', '')
            lines.append(f'{indent_str}await page.locator("{selector}").hover()')
        
        elif action == 'scroll':
            direction = step.get('direction', 'down')
            distance = step.get('distance', 300)
            if direction == 'down':
                lines.append(f'{indent_str}await page.mouse.wheel(0, {distance})')
            else:
                lines.append(f'{indent_str}await page.mouse.wheel(0, -{distance})')
        
        else:
            lines.append(f'{indent_str}# TODO: Implement action "{action}"')
        
        return '\n'.join(lines) if lines else ''


def parse_trace_file(trace_path: str) -> TraceParseResult:
    """
    便捷函数：解析 Trace 文件
    
    Args:
        trace_path: Trace 文件路径
        
    Returns:
        TraceParseResult: 解析结果
    """
    parser = TraceParser()
    return parser.parse(trace_path)


def generate_component_from_trace(
    trace_path: str,
    platform: str,
    component_type: str,
    data_domain: str = None,
    output_path: str = None,
) -> str:
    """
    v4.8.0: 便捷函数 - 从 Trace 文件生成 Python 组件
    
    Args:
        trace_path: Trace 文件路径
        platform: 平台代码
        component_type: 组件类型
        data_domain: 数据域（可选）
        output_path: 输出文件路径（可选，如果提供则保存文件）
    
    Returns:
        str: 生成的 Python 代码
    """
    parser = TraceParser()
    result = parser.parse(trace_path)
    
    if not result.success:
        raise ValueError(f"Failed to parse trace: {result.error}")
    
    code = parser.generate_python_skeleton(
        result=result,
        platform=platform,
        component_type=component_type,
        data_domain=data_domain,
    )
    
    if output_path:
        from pathlib import Path
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(code, encoding='utf-8')
        logger.info(f"Component saved to: {output_path}")
    
    return code


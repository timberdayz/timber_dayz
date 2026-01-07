# Python 组件编写模板

> v4.8.0: 数据采集模块异步化改造

本文档提供 Python 组件的编写模板和规范。

## 组件模板

### 基础组件模板

```python
"""
{Platform} {ComponentType} Component

Platform: {platform}
Type: {component_type}
Data Domain: {data_domain} (if export component)
"""

from typing import Dict, Any, Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)


class {ClassName}Component:
    """
    {Platform} {ComponentType} 组件
    
    功能描述：
    - 功能点 1
    - 功能点 2
    """
    
    # 组件元数据（必需）
    platform = "{platform}"
    component_type = "{component_type}"
    data_domain = "{data_domain}"  # 仅 export 组件需要
    
    # 可选元数据
    description = "{Platform} {component_type} component"
    version = "1.0.0"
    
    def __init__(self, ctx=None):
        """
        初始化组件
        
        Args:
            ctx: 执行上下文（可选）
        """
        self.ctx = ctx
        self.logger = ctx.logger if ctx else logger
    
    async def run(
        self, 
        page, 
        account: Dict[str, Any], 
        params: Dict[str, Any], 
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行组件逻辑
        
        Args:
            page: Playwright Page 对象
            account: 账号信息 {
                'username': str,
                'password': str,  # 已解密
                'store_name': str,
                ...
            }
            params: 执行参数 {
                'date_from': str,
                'date_to': str,
                'granularity': str,
                'data_domain': str,
                ...
            }
            **kwargs: 额外参数
        
        Returns:
            Dict: 执行结果 {
                'success': bool,
                'file_path': str (可选),
                'error': str (可选),
                'data': Any (可选)
            }
        """
        self.logger.info(f"[{self.__class__.__name__}] Starting execution...")
        
        try:
            # 1. 执行业务逻辑
            # await page.goto("https://example.com")
            # await page.get_by_role("button", name="Submit").click()
            
            # 2. 返回成功结果
            self.logger.info(f"[{self.__class__.__name__}] Execution completed")
            return {"success": True}
            
        except Exception as e:
            self.logger.error(f"[{self.__class__.__name__}] Execution failed: {e}")
            return {"success": False, "error": str(e)}
```

### 登录组件模板

```python
"""
{Platform} Login Component

Platform: {platform}
Type: login
"""

from typing import Dict, Any
from modules.core.logger import get_logger

logger = get_logger(__name__)


class LoginComponent:
    """
    {Platform} 登录组件
    """
    
    platform = "{platform}"
    component_type = "login"
    description = "{Platform} login component"
    version = "1.0.0"
    
    def __init__(self, ctx=None):
        self.ctx = ctx
        self.logger = ctx.logger if ctx else logger
    
    async def run(
        self, 
        page, 
        account: Dict[str, Any], 
        params: Dict[str, Any], 
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行登录逻辑
        """
        self.logger.info(f"[LoginComponent] Starting login for {account.get('username')}")
        
        try:
            username = account.get('username', '')
            password = account.get('password', '')  # 已由适配层解密
            login_url = account.get('login_url', '')
            
            # 1. 导航到登录页
            await page.goto(login_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            # 2. 填写用户名
            await page.get_by_role("textbox", name="用户名").fill(username)
            
            # 3. 填写密码
            await page.get_by_role("textbox", name="密码").fill(password)
            
            # 4. 点击登录按钮
            await page.get_by_role("button", name="登录").click()
            
            # 5. 等待登录完成
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(2000)
            
            # 6. 验证登录成功
            # 可以检查 URL、元素存在等
            
            self.logger.info("[LoginComponent] Login completed successfully")
            return {"success": True}
            
        except Exception as e:
            self.logger.error(f"[LoginComponent] Login failed: {e}")
            return {"success": False, "error": str(e)}
```

### 导出组件模板

```python
"""
{Platform} {DataDomain} Export Component

Platform: {platform}
Type: export
Data Domain: {data_domain}
"""

from typing import Dict, Any, Optional
from pathlib import Path
from modules.core.logger import get_logger

logger = get_logger(__name__)


class {DataDomain}ExportComponent:
    """
    {Platform} {DataDomain} 数据导出组件
    """
    
    platform = "{platform}"
    component_type = "export"
    data_domain = "{data_domain}"
    description = "{Platform} {data_domain} data export"
    version = "1.0.0"
    
    def __init__(self, ctx=None):
        self.ctx = ctx
        self.logger = ctx.logger if ctx else logger
    
    async def run(
        self, 
        page, 
        account: Dict[str, Any], 
        params: Dict[str, Any], 
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行数据导出逻辑
        """
        self.logger.info(f"[{self.__class__.__name__}] Starting export...")
        
        try:
            date_from = params.get('date_from', '')
            date_to = params.get('date_to', '')
            download_dir = params.get('download_dir', 'temp/downloads')
            
            # 1. 导航到数据页面
            # await page.goto("https://platform.com/data", wait_until='networkidle')
            
            # 2. 设置日期范围（可调用子组件）
            # date_picker = self.ctx.adapter.date_picker() if self.ctx else None
            # if date_picker:
            #     await date_picker.run(page, params)
            
            # 3. 点击导出按钮
            # await page.get_by_role("button", name="导出").click()
            
            # 4. 等待下载完成
            # async with page.expect_download() as download_info:
            #     await page.get_by_role("button", name="确认导出").click()
            # download = await download_info.value
            # file_path = Path(download_dir) / download.suggested_filename
            # await download.save_as(str(file_path))
            
            self.logger.info(f"[{self.__class__.__name__}] Export completed")
            return {
                "success": True,
                # "file_path": str(file_path)
            }
            
        except Exception as e:
            self.logger.error(f"[{self.__class__.__name__}] Export failed: {e}")
            return {"success": False, "error": str(e)}
```

## 组件开发规范

### 1. 异步方法（必须）

所有组件的 `run` 方法必须是异步的：

```python
# 正确
async def run(self, page, account, params, **kwargs):
    await page.goto(url)
    await page.click(selector)

# 错误
def run(self, page, account, params, **kwargs):  # 缺少 async
    page.goto(url)  # 缺少 await
```

### 2. 使用 Playwright 官方 API

优先使用 `get_by_role`、`get_by_text` 等官方推荐的定位器：

```python
# 推荐
await page.get_by_role("button", name="登录").click()
await page.get_by_text("确认").click()
await page.get_by_placeholder("请输入用户名").fill(username)

# 不推荐
await page.locator("button.login-btn").click()
await page.click("button.login-btn")
```

### 3. 日志输出（禁止 Emoji）

使用 ASCII 符号代替 Emoji：

```python
# 正确
self.logger.info("[OK] Login successful")
self.logger.error("[FAIL] Login failed")
self.logger.warning("[WARN] Password expired")

# 错误
self.logger.info("✅ Login successful")  # 会导致 Windows 编码错误
self.logger.error("❌ Login failed")
```

### 4. 错误处理

使用 try-except 包装，返回标准结果：

```python
try:
    # 业务逻辑
    return {"success": True, "file_path": str(file_path)}
except Exception as e:
    self.logger.error(f"[{self.__class__.__name__}] Error: {e}")
    return {"success": False, "error": str(e)}
```

### 5. 组件元数据（必须）

每个组件类必须定义元数据属性：

```python
class MyComponent:
    # 必需
    platform = "shopee"         # 平台代码
    component_type = "export"   # 组件类型
    
    # 如果是 export 组件
    data_domain = "orders"      # 数据域
    
    # 可选
    description = "Description"
    version = "1.0.0"
```

### 6. 调用子组件

通过适配器调用子组件（如日期选择器）：

```python
async def run(self, page, account, params, **kwargs):
    # 如果有执行上下文，可以调用子组件
    if self.ctx and self.ctx.adapter:
        date_picker = self.ctx.adapter.date_picker()
        await date_picker.run(page, params)
```

## 组件目录结构

```
modules/platforms/
├── shopee/
│   └── components/
│       ├── __init__.py
│       ├── login.py
│       ├── navigation.py
│       ├── date_picker.py
│       ├── orders_export.py
│       ├── products_export.py
│       └── ...
├── tiktok/
│   └── components/
│       ├── login.py
│       └── ...
└── miaoshou/
    └── components/
        ├── login.py
        └── ...
```

## 从 Trace 生成组件

使用 TraceParser 从录制文件生成组件骨架：

```python
from backend.utils.trace_parser import generate_component_from_trace

code = generate_component_from_trace(
    trace_path="temp/recordings/trace.zip",
    platform="shopee",
    component_type="orders_export",
    data_domain="orders",
    output_path="modules/platforms/shopee/components/orders_export.py"
)
```

## 验证组件

使用 ComponentLoader 验证组件是否符合规范：

```python
from modules.apps.collection_center.component_loader import ComponentLoader

loader = ComponentLoader()

# 加载组件类
component_class = loader.load_python_component("shopee", "login")

# 验证组件
result = loader.validate_python_component(component_class)
if result['valid']:
    print("Component is valid")
    print(f"Metadata: {result['metadata']}")
else:
    print(f"Errors: {result['errors']}")
```


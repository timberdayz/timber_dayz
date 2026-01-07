"""
录制模板生成器

为不同平台生成Playwright录制模板，支持：
- 妙手ERP登录模板
- Shopee登录模板  
- Amazon登录模板
- 数据采集模板
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from modules.utils.logger import get_logger

logger = get_logger(__name__)


def _auto_format_script(script_path: Path):
    """自动格式化生成的脚本，修复常见的缩进和语法问题"""
    try:
        content = script_path.read_text(encoding='utf-8')

        # 1. 统一缩进：将Tab转为4个空格
        content = content.expandtabs(4)

        # 2. 修复常见的缩进问题
        lines = content.splitlines()
        fixed_lines = []

        for i, line in enumerate(lines):
            # 移除行尾空白
            line = line.rstrip()

            # 修复注释掉的函数定义后的缩进问题
            if line.strip().startswith('# def ') and i + 1 < len(lines):
                # 确保后续行也是注释
                next_line = lines[i + 1].strip()
                if next_line.startswith("'''") or next_line.startswith('"""'):
                    # 修复三引号注释
                    fixed_lines.append(line)
                    fixed_lines.append('    #     ' + next_line)
                    # 跳过下一行的处理
                    lines[i + 1] = ''
                    continue

            # 修复注释函数后的错误缩进
            if (line.strip().startswith("'''") or line.strip().startswith('"""')) and i > 0:
                prev_line = lines[i - 1].strip()
                if prev_line.startswith('# def '):
                    # 这是注释函数的文档字符串，应该被注释
                    line = '    #     ' + line.strip()

            # 修复孤立的pass语句缩进
            if line.strip() == 'pass' and i > 0:
                # 检查前面几行是否有注释函数定义
                for j in range(max(0, i-3), i):
                    if lines[j].strip().startswith('# def '):
                        # 这是注释函数的pass，应该被注释
                        line = '    #     pass'
                        break

            fixed_lines.append(line)

        # 3. 重新组合内容
        formatted_content = '\n'.join(fixed_lines)

        # 4. 语法检查
        try:
            compile(formatted_content, str(script_path), 'exec')
            # 语法正确，保存格式化后的内容
            script_path.write_text(formatted_content, encoding='utf-8')
            logger.debug(f"✅ 脚本自动格式化完成: {script_path}")
        except SyntaxError as se:
            logger.warning(f"⚠️ 脚本语法检查失败，保持原内容: {se}")
            # 语法错误时不覆盖原文件

    except Exception as e:
        logger.warning(f"⚠️ 自动格式化失败: {e}")
        # 格式化失败不影响主流程

def create_platform_recording_template(account: Dict, platform: str, 
                                     recording_type: str, data_type_key: Optional[str]) -> Optional[Path]:
    """创建平台录制模板"""
    try:
        # 创建模板目录
        platform_dir = platform.lower().replace(" ", "_")
        template_dir = Path(f"temp/recordings/{platform_dir}")
        template_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名 - 使用安全的ASCII字符
        account_name = account.get('store_name', account.get('username', 'unknown'))
        # 更严格的文件名安全处理，只保留ASCII字母数字和基本符号
        safe_name = "".join(c if c.isascii() and (c.isalnum() or c in '._-') else '_' for c in account_name)
        # 如果处理后为空或太短，使用默认名称
        if not safe_name or len(safe_name.strip('_')) < 2:
            safe_name = f"account_{hash(account_name) % 10000}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 新命名规范：{平台}_{账号}_{数据类型}_complete_{时间戳}.py（当录制类型为complete时）
        if recording_type == "complete" and data_type_key:
            filename = f"{platform_dir}_{safe_name}_{data_type_key}_complete_{timestamp}.py"
        else:
            filename = f"{safe_name}_{recording_type}_{timestamp}.py"
        
        template_path = template_dir / filename
        
        # 生成模板内容
        content = _generate_template_content(account, platform, recording_type, data_type_key)

        template_path.write_text(content, encoding='utf-8')

        # 自动格式化生成的脚本（防止缩进错误）
        _auto_format_script(template_path)

        return template_path
        
    except Exception as e:
        print(f"❌ 创建录制模板失败: {e}")
        return None

def _generate_template_content(account: Dict, platform: str, 
                             recording_type: str, data_type_key: Optional[str]) -> str:
    """生成模板内容"""
    
    # 基础信息
    account_name = account.get('store_name', account.get('username', 'unknown'))
    login_url = account.get('login_url', '')
    username = account.get('username', '')
    password = account.get('password', '')
    
    # 模板头部
    header = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
{platform}平台录制模板
录制类型: {recording_type}
账号: {account_name}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

from playwright.sync_api import sync_playwright
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

'''

    # 录制器类
    recorder_class = f'''
class {platform.replace(' ', '')}Recorder:
    """
    {platform}平台录制器
    """
    
    def __init__(self, account_config: dict):
        self.account_config = account_config
        self.browser = None
        self.context = None
        self.page = None
    
    def execute_recording(self, page):
        """执行录制逻辑"""
        try:
            logger.info(f"开始执行{platform}录制")
            
{_get_recording_logic(platform, recording_type, data_type_key)}
            
            logger.info(f"✅ {platform}录制完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ {platform}录制失败: {{e}}")
            return False
'''

    # 主函数
    main_function = f'''
def main():
    """主函数"""
    account_config = {{
        'username': '{username}',
        'password': '{password}',
        'login_url': '{login_url}',
        'store_name': '{account_name}'
    }}
    
    print("🚀 启动{platform}录制...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={{"width": 1920, "height": 1080}},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        try:
            recorder = {platform.replace(' ', '')}Recorder(account_config)
            page.goto(account_config['login_url'])
            
            result = recorder.execute_recording(page)
            print(f"录制结果: {{result}}")
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
'''

    return header + recorder_class + main_function

def _get_recording_logic(platform: str, recording_type: str, data_type_key: Optional[str]) -> str:
    """获取录制逻辑代码"""
    
    if recording_type == "login":
        return _get_login_logic(platform)
    elif recording_type == "login_auto":
        return _get_auto_login_logic(platform)
    elif recording_type == "collection":
        return _get_collection_logic(platform, data_type_key)
    elif recording_type == "complete":
        return _get_complete_logic(platform, data_type_key)
    else:
        return '''            # 在这里添加自定义录制逻辑
            page.pause()  # 暂停供用户录制'''

def _get_login_logic(platform: str) -> str:
    """获取登录录制逻辑"""
    return '''            # 登录流程录制
            logger.info("等待用户录制登录流程...")
            
            # 用户手动操作：
            # 1. 填写用户名和密码
            # 2. 处理验证码（如有）
            # 3. 点击登录按钮
            # 4. 等待登录成功
            
            page.pause()  # 暂停供用户录制登录操作
            
            logger.info("登录录制完成")'''

def _get_auto_login_logic(platform: str) -> str:
    """获取自动登录录制逻辑"""
    if platform == "Shopee":
        return '''            # Shopee自动登录演示
            logger.info("开始Shopee自动登录演示...")
            
            try:
                # 自动填写用户名
                username_selectors = [
                    'input[name="username"]',
                    'input[name="user"]', 
                    'input[name="email"]',
                    'input[placeholder*="用户名"]',
                    'input[placeholder*="手机号"]',
                    'input[placeholder*="邮箱"]'
                ]
                
                for selector in username_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.fill(selector, self.account_config['username'])
                            logger.info(f"✅ 用户名已填写: {self.account_config['username']}")
                            break
                    except:
                        continue
                
                # 自动填写密码
                password_selectors = [
                    'input[name="password"]',
                    'input[name="pwd"]',
                    'input[type="password"]',
                    'input[placeholder*="密码"]'
                ]
                
                for selector in password_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.fill(selector, self.account_config['password'])
                            logger.info("✅ 密码已填写")
                            break
                    except:
                        continue
                
                # 点击登录按钮
                login_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("登录")',
                    'button:has-text("登入")',
                    'button:has-text("Login")',
                    '.login-btn'
                ]
                
                for selector in login_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.click(selector)
                            logger.info("✅ 登录按钮已点击")
                            break
                    except:
                        continue
                
                # 等待登录结果
                logger.info("⏳ 等待登录完成...")
                time.sleep(5)
                
                # 检查验证码弹窗
                verification_selectors = [
                    '.verification-popup',
                    '.captcha-modal',
                    '[data-testid="verification"]',
                    'div:has-text("验证码")',
                    'div:has-text("verification")'
                ]
                
                has_verification = False
                for selector in verification_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            has_verification = True
                            logger.info(f"📱 检测到验证码弹窗: {selector}")
                            break
                    except:
                        continue
                
                if has_verification:
                    logger.info("📱 检测到验证码，启动智能处理...")
                    # 这里可以添加智能验证码处理逻辑
                    print("💡 验证码处理演示：")
                    print("  1. 检测验证码类型（邮箱/短信）")
                    print("  2. 自动获取验证码")
                    print("  3. 自动填写验证码")
                    print("  4. 自动提交")
                    
                    # 暂停让用户观察
                    page.pause()
                else:
                    logger.info("✅ 未检测到验证码需求")
                
                # 检查登录结果
                current_url = page.url
                if "seller.shopee" in current_url:
                    logger.info("✅ 登录成功，已进入Shopee卖家后台")
                else:
                    logger.warning("⚠️ 登录状态待确认")
                    
            except Exception as e:
                logger.error(f"❌ 自动登录演示失败: {e}")
                print("💡 请手动完成登录流程")
                page.pause()'''
    
    elif platform in ["妙手ERP", "miaoshou", "miaoshou_erp"]:
        return '''            # 妙手ERP自动登录演示
            logger.info("开始妙手ERP自动登录演示...")
            
            try:
                # 自动填写登录信息
                username = self.account_config['username']
                password = self.account_config['password']
                
                # 查找并填写用户名
                username_selectors = [
                    'input[name="username"]',
                    'input[name="user"]',
                    'input[name="email"]',
                    'input[name="phone"]',
                    'input[type="text"]',
                    'input[placeholder*="用户名"]',
                    'input[placeholder*="手机号"]',
                    'input[placeholder*="邮箱"]'
                ]
                
                for selector in username_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.fill(selector, username)
                            logger.info(f"✅ 用户名已填写: {username}")
                            break
                    except:
                        continue
                
                # 查找并填写密码
                password_selectors = [
                    'input[name="password"]',
                    'input[name="pwd"]',
                    'input[type="password"]',
                    'input[placeholder*="密码"]'
                ]
                
                for selector in password_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.fill(selector, password)
                            logger.info("✅ 密码已填写")
                            break
                    except:
                        continue
                
                # 查找并点击登录按钮
                login_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("登录")',
                    'button:has-text("登入")',
                    'button:has-text("Login")',
                    '.login-btn',
                    '#login',
                    '.submit-btn'
                ]
                
                for selector in login_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.click(selector)
                            logger.info("✅ 登录按钮已点击")
                            break
                    except:
                        continue
                
                # 等待登录结果
                logger.info("⏳ 等待登录完成...")
                time.sleep(5)
                
                # 检查验证码
                captcha_selectors = [
                    'input[name="captcha"]',
                    'input[placeholder*="验证码"]',
                    'input[placeholder*="captcha"]'
                ]
                
                need_captcha = False
                for selector in captcha_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            need_captcha = True
                            break
                    except:
                        continue
                
                if need_captcha:
                    logger.info("📱 检测到验证码，启动智能处理...")
                    print("💡 验证码处理演示：")
                    print("  1. 自动请求邮箱验证码")
                    print("  2. 从邮箱获取验证码")
                    print("  3. 自动填写验证码")
                    print("  4. 提交登录")
                    
                    page.pause()
                else:
                    logger.info("✅ 未检测到验证码需求")
                    
            except Exception as e:
                logger.error(f"❌ 自动登录演示失败: {e}")
                print("💡 请手动完成登录流程")
                page.pause()'''
    
    else:
        return '''            # 通用自动登录演示
            logger.info("开始通用自动登录演示...")
            
            # 自动填写用户名和密码
            try:
                page.fill('input[name="username"], input[name="user"], input[type="text"]', 
                         self.account_config['username'])
                page.fill('input[name="password"], input[type="password"]', 
                         self.account_config['password'])
                page.click('button[type="submit"], input[type="submit"], button:has-text("登录")')
                
                logger.info("✅ 自动登录演示完成")
                time.sleep(3)
                
            except Exception as e:
                logger.error(f"❌ 自动登录失败: {e}")
                print("💡 请手动完成登录流程")
                
            page.pause()'''

def _get_collection_logic(platform: str, data_type_key: Optional[str]) -> str:
    """获取数据采集录制逻辑"""
    data_type_desc = data_type_key or "通用数据"
    
    return f'''            # {data_type_desc}采集录制
            logger.info("开始{data_type_desc}采集录制...")
            
            # 自动登录（跳过录制）
            logger.info("执行自动登录...")
            # 这里应该有自动登录逻辑
            
            # 等待登录完成
            time.sleep(5)
            
            # 进入数据采集录制阶段
            logger.info("✅ 登录完成，开始录制数据采集操作")
            print("📊 请在浏览器中录制以下操作：")
            print("  1. 导航到{data_type_desc}页面")
            print("  2. 设置筛选条件（日期范围等）")
            print("  3. 执行数据查询/导出操作")
            print("  4. 完成后点击Resume继续")
            
            page.pause()  # 暂停供用户录制数据采集操作
            
            logger.info("{data_type_desc}采集录制完成")'''

def _get_complete_logic(platform: str, data_type_key: Optional[str]) -> str:
    """获取完整流程录制逻辑"""
    data_type_desc = data_type_key or "数据"
    
    return f'''            # 完整流程录制（登录 + {data_type_desc}采集）
            logger.info("开始完整流程录制...")
            
            print("🔄 请在浏览器中录制完整流程：")
            print("  第一阶段: 登录流程")
            print("    1. 填写用户名和密码")
            print("    2. 处理验证码（如有）")
            print("    3. 点击登录按钮")
            print("    4. 等待登录成功")
            print("  第二阶段: {data_type_desc}采集")
            print("    5. 导航到{data_type_desc}页面")
            print("    6. 设置筛选条件")
            print("    7. 执行数据操作")
            print("    8. 完成后点击Resume继续")
            
            page.pause()  # 暂停供用户录制完整流程
            
            logger.info("完整流程录制完成")'''

def create_miaoshou_account_override_template(account: Dict) -> Path:
    """创建妙手ERP账号覆盖模板"""
    try:
        # 创建模板目录
        template_dir = Path("temp/recordings/miaoshou")
        template_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        account_name = account.get('store_name', account.get('username', 'unknown'))
        safe_name = "".join(c for c in account_name if c.isalnum() or c in '._-')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_account_override_{timestamp}.py"
        
        template_path = template_dir / filename
        
        # 生成模板内容
        content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
妙手ERP账号覆盖模板
账号: {account.get('store_name', 'unknown')}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

用途: 为该账号创建专用的采集逻辑，覆盖默认行为
"""

def get_account_override():
    """
    获取账号特定的覆盖配置
    
    Returns:
        dict: 账号覆盖配置
    """
    
    return {{
        # 基本信息
        'account_id': '{account.get('account_id', '')}',
        'store_name': '{account.get('store_name', '')}',
        'platform': '{account.get('platform', 'miaoshou')}',
        
        # 登录配置
        'login_config': {{
            'url': '{account.get('login_url', '')}',
            'username': '{account.get('username', '')}',
            'password': '{account.get('password', '')}',
            'auto_login': True,
            'handle_captcha': True
        }},
        
        # 采集配置
        'collection_config': {{
            'data_types': ['sales', 'operations', 'financial'],
            'date_range_default': '30_days',
            'export_format': 'excel',
            'batch_size': 1000
        }},
        
        # 元素选择器（如需自定义）
        'selectors': {{
            'username_input': 'input[name="username"]',
            'password_input': 'input[name="password"]',
            'login_button': 'button[type="submit"]',
            'captcha_input': 'input[name="captcha"]'
        }},
        
        # 等待时间配置
        'timeouts': {{
            'page_load': 30000,
            'element_wait': 10000,
            'captcha_wait': 60000
        }},
        
        # 错误处理
        'error_handling': {{
            'max_retries': 3,
            'retry_delay': 5,
            'screenshot_on_error': True
        }}
    }}


def get_custom_login_logic():
    """
    自定义登录逻辑（可选）
    
    如果该账号需要特殊的登录处理，可以在这里定义
    """
    
    return {{
        'pre_login_actions': [],  # 登录前的特殊操作
        'post_login_actions': [], # 登录后的特殊操作
        'captcha_handler': None,  # 自定义验证码处理器
        'verification_handler': None  # 自定义验证处理器
    }}


def get_custom_collection_logic():
    """
    自定义采集逻辑（可选）
    
    如果该账号需要特殊的采集处理，可以在这里定义
    """
    
    return {{
        'data_sources': {{
            'sales': {{
                'url_pattern': '/sales/report',
                'selectors': {{
                    'date_start': 'input[name="start_date"]',
                    'date_end': 'input[name="end_date"]',
                    'export_button': 'button:has-text("导出")'
                }}
            }},
            'operations': {{
                'url_pattern': '/operations/dashboard',
                'selectors': {{
                    'filter_button': '.filter-btn',
                    'download_link': 'a[href*="download"]'
                }}
            }}
        }},
        'custom_processors': []  # 自定义数据处理器
    }}


# 主配置导出
ACCOUNT_CONFIG = get_account_override()
CUSTOM_LOGIN = get_custom_login_logic()
CUSTOM_COLLECTION = get_custom_collection_logic()

# 验证配置
def validate_config():
    """验证配置有效性"""
    try:
        assert ACCOUNT_CONFIG['account_id'], "账号ID不能为空"
        assert ACCOUNT_CONFIG['login_config']['url'], "登录URL不能为空"
        assert ACCOUNT_CONFIG['login_config']['username'], "用户名不能为空"
        print("✅ 账号配置验证通过")
        return True
    except AssertionError as e:
        print(f"❌ 配置验证失败: {{e}}")
        return False
    except Exception as e:
        print(f"❌ 配置验证异常: {{e}}")
        return False

if __name__ == "__main__":
    print("🔧 妙手ERP账号覆盖配置")
    print("=" * 40)
    validate_config()
    print(f"账号: {{ACCOUNT_CONFIG['store_name']}}")
    print(f"平台: {{ACCOUNT_CONFIG['platform']}}")
    print(f"自动登录: {{ACCOUNT_CONFIG['login_config']['auto_login']}}")
    print(f"数据类型: {{', '.join(ACCOUNT_CONFIG['collection_config']['data_types'])}}")
'''
        
        template_path.write_text(content, encoding='utf-8')
        return template_path
        
    except Exception as e:
        print(f"❌ 创建妙手ERP模板失败: {e}")
        return None 

def generate_script_from_events(account: Dict, platform: str, recording_type: str, events_file: Path, output_dir: Path) -> Path:
    """根据事件文件生成可回放的Playwright脚本

    Args:
        account: 账号信息，需包含login_url/username/password
        platform: 平台名
        recording_type: 录制类型
        events_file: 事件JSONL文件路径
        output_dir: 输出目录

    Returns:
        Path: 生成的脚本文件路径
    """
    import json

    output_dir.mkdir(parents=True, exist_ok=True)

    account_name = account.get('store_name', account.get('username', 'unknown'))
    safe_name = "".join(c if c.isascii() and (c.isalnum() or c in '._-') else '_' for c in account_name)
    if not safe_name or len(safe_name.strip('_')) < 2:
        safe_name = f"account_{hash(account_name) % 10000}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{platform.lower()}_{recording_type}_{timestamp}.py"
    script_path = output_dir / filename

    # 读取事件
    events: list[dict] = []
    for line in events_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue

    # 生成脚本主体
    header = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于录制事件自动生成的回放脚本
平台: {platform}
录制类型: {recording_type}
账号: {account_name}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ACCOUNT = {{
    'username': {account.get('username', '')!r},
    'password': {account.get('password', '')!r},
    'login_url': {account.get('login_url', '')!r},
    'store_name': {account_name!r}
}}

TRACE_PATH = Path('temp/media/{timestamp}_{safe_name}_{platform.lower()}_trace.zip')

'''

    # 可选：网络拦截占位
    network_helpers = '''def setup_network_interception(page):
    """可选：设置网络拦截规则（按需手动补充）"""
    # 示例：
    # page.route("**/*", lambda route: route.continue_())
    pass

'''

    body_prefix = '''def run(page):
    logger.info("开始回放录制事件...")
    setup_network_interception(page)
'''

    # 将事件转换为playwright指令
    def emit_action(ev: dict) -> str:
        t = ev.get('type')
        sel = ev.get('selector') or ''
        val = ev.get('value')
        url = ev.get('url')
        comment = ev.get('comment')
        if comment:
            return f"    # {comment}\n"
        if t == 'goto' and url:
            return f"    page.goto({url!r})\n"
        if t == 'click' and sel:
            return f"    page.click({sel!r})\n"
        if t == 'fill' and sel is not None:
            # 屏蔽敏感字段的直接明文：若包含password等，优先使用账号配置
            if 'password' in (ev.get('name') or '').lower() or 'password' in sel.lower():
                return f"    page.fill({sel!r}, ACCOUNT['password'])\n"
            if 'username' in (ev.get('name') or '').lower() or 'login' in sel.lower():
                return f"    page.fill({sel!r}, ACCOUNT['username'])\n"
            val_str = repr(val) if val is not None else "''"
            return f"    page.fill({sel!r}, {val_str})\n"
        if t == 'select' and sel is not None:
            return f"    page.select_option({sel!r}, {val!r})\n"
        if t == 'check' and sel:
            return f"    page.check({sel!r})\n"
        if t == 'uncheck' and sel:
            return f"    page.uncheck({sel!r})\n"
        if t == 'wait_for_selector' and sel:
            return f"    page.wait_for_selector({sel!r})\n"
        if t == 'sleep' and isinstance(val, (int, float)):
            return f"    time.sleep({float(val)})\n"
        if t == 'new_page':
            return "    # 新页面打开事件（请按需补充处理逻辑，如使用 context.on('page') 监听）\n"
        if t == 'download':
            return "    # 下载事件占位：可在此添加下载监听与保存逻辑\n"
        if t == 'request' or t == 'response':
            return "    # 网络事件占位：如需断言/过滤，请在setup_network_interception中实现\n"
        return "    # 未识别事件，已忽略\n"

    body_actions = []
    # 基本起始导航
    body_actions.append("    page.goto(ACCOUNT['login_url'])\n")
    for ev in events:
        body_actions.append(emit_action(ev))

    body_suffix = '''    logger.info("回放结束")
'''

    main_block = '''def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        try:
            run(page)
        finally:
            context.tracing.stop(path=str(TRACE_PATH))
            browser.close()


if __name__ == '__main__':
    main()
'''

    content = header + network_helpers + body_prefix + "".join(body_actions) + body_suffix + "\n" + main_block
    script_path.write_text(content, encoding='utf-8')

    # 自动格式化生成的脚本（防止缩进错误）
    _auto_format_script(script_path)

    return script_path
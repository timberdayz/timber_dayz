"""
妙手ERP库存数据采集录制工具
专门用于录制妙手ERP的库存导出操作

使用方法：
    python tools/record_miaoshou_inventory.py

录制流程：
1. 自动打开妙手ERP登录页面
2. 手动完成登录（包括验证码）
3. 手动导航到库存页面
4. 手动操作导出数据
5. 录制器自动捕获操作并生成YAML
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

# 账号信息
MIAOSHOU_ACCOUNT = {
    "account_id": "miaoshou_real_001",
    "platform": "miaoshou",
    "login_url": "https://erp.91miaoshou.com/login",
    "username": "18876067809",
    "password": "Wei5201314@",
}


async def start_recording():
    """启动录制会话"""
    from playwright.async_api import async_playwright
    
    print("=" * 60)
    print("妙手ERP库存数据采集录制工具")
    print("=" * 60)
    print()
    print(f"账号: {MIAOSHOU_ACCOUNT['account_id']}")
    print(f"用户名: {MIAOSHOU_ACCOUNT['username']}")
    print(f"登录URL: {MIAOSHOU_ACCOUNT['login_url']}")
    print()
    print("请按照以下步骤操作：")
    print("-" * 60)
    print("步骤1: 浏览器将自动打开妙手ERP登录页面")
    print("步骤2: 请手动完成登录（输入账号密码，处理验证码）")
    print("步骤3: 登录成功后，导航到【库存管理】页面")
    print("步骤4: 设置筛选条件（如日期范围）")
    print("步骤5: 点击【导出】按钮下载数据")
    print("步骤6: 下载完成后，关闭浏览器结束录制")
    print("-" * 60)
    print()
    input("按 Enter 键开始录制...")
    print()
    
    async with async_playwright() as p:
        # 启动带录制功能的浏览器
        browser = await p.chromium.launch(
            headless=False,  # 必须有界面
            slow_mo=100,  # 减慢操作便于观察
            args=[
                '--start-maximized',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        # 创建新的浏览器上下文，设置下载路径
        downloads_dir = Path(__file__).parent.parent / "downloads" / "miaoshou" / datetime.now().strftime("%Y%m%d")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True,
        )
        
        # 设置下载行为
        page = await context.new_page()
        
        # 监听下载事件
        downloaded_files = []
        
        async def handle_download(download):
            """处理下载事件"""
            suggested_filename = download.suggested_filename
            save_path = downloads_dir / suggested_filename
            print(f"\n[下载] 检测到文件下载: {suggested_filename}")
            await download.save_as(str(save_path))
            downloaded_files.append({
                'filename': suggested_filename,
                'path': str(save_path),
                'time': datetime.now().isoformat()
            })
            print(f"[下载] 文件已保存: {save_path}")
        
        page.on("download", handle_download)
        
        # 监听控制台消息（用于调试）
        page.on("console", lambda msg: print(f"[Console] {msg.text}") if msg.type == "error" else None)
        
        # 导航到登录页面
        print(f"\n正在打开妙手ERP登录页面...")
        await page.goto(MIAOSHOU_ACCOUNT['login_url'], wait_until='networkidle')
        print("页面已打开，请开始操作...")
        print()
        print("[提示] 完成所有操作后，直接关闭浏览器窗口结束录制")
        print()
        
        # 等待浏览器被关闭
        try:
            await page.wait_for_event('close', timeout=0)  # 无限等待
        except:
            pass
        
        # 录制结束
        print()
        print("=" * 60)
        print("录制完成！")
        print("=" * 60)
        
        if downloaded_files:
            print(f"\n下载的文件数量: {len(downloaded_files)}")
            for f in downloaded_files:
                print(f"  - {f['filename']}")
                print(f"    路径: {f['path']}")
            
            print()
            print("下一步操作：")
            print("1. 检查下载的文件是否正确")
            print("2. 文件将自动注册到catalog_files表")
            print()
            
            # 返回下载信息
            return {
                'status': 'success',
                'downloads': downloaded_files,
                'downloads_dir': str(downloads_dir)
            }
        else:
            print("\n[警告] 未检测到文件下载")
            print("请确保完成了导出操作")
            return {
                'status': 'no_downloads',
                'downloads': [],
                'downloads_dir': str(downloads_dir)
            }


async def register_downloaded_files(downloads_info):
    """将下载的文件注册到数据库"""
    if not downloads_info.get('downloads'):
        print("没有文件需要注册")
        return
    
    from backend.services.file_registration_service import FileRegistrationService
    from backend.models.database import SessionLocal
    
    print("\n正在注册文件到数据库...")
    
    with SessionLocal() as db:
        service = FileRegistrationService(db)
        
        for file_info in downloads_info['downloads']:
            file_path = Path(file_info['path'])
            if not file_path.exists():
                print(f"[跳过] 文件不存在: {file_path}")
                continue
            
            try:
                # 检测文件信息
                metadata = {
                    'platform': 'miaoshou',
                    'account_id': MIAOSHOU_ACCOUNT['account_id'],
                    'data_domain': 'inventory',  # 库存数据域
                    'granularity': 'snapshot',  # 快照类型
                    'file_name': file_info['filename'],
                    'file_path': str(file_path),
                }
                
                # 注册文件
                result = service.register_file(metadata)
                print(f"[成功] 文件已注册: {file_info['filename']}")
                print(f"       file_id: {result.get('file_id')}")
                
            except Exception as e:
                print(f"[失败] 注册失败: {file_info['filename']} - {e}")
    
    print("\n文件注册完成！")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='妙手ERP库存数据采集录制工具')
    parser.add_argument('--register-only', action='store_true', help='仅注册已下载的文件')
    parser.add_argument('--downloads-dir', type=str, help='下载文件目录')
    args = parser.parse_args()
    
    if args.register_only:
        # 仅注册模式
        if args.downloads_dir:
            downloads_info = {
                'status': 'success',
                'downloads': [
                    {'filename': f.name, 'path': str(f)}
                    for f in Path(args.downloads_dir).glob('*')
                    if f.is_file()
                ],
                'downloads_dir': args.downloads_dir
            }
            asyncio.run(register_downloaded_files(downloads_info))
        else:
            print("请指定 --downloads-dir 参数")
    else:
        # 录制模式
        result = asyncio.run(start_recording())
        
        if result['status'] == 'success' and result['downloads']:
            print()
            register = input("是否立即注册下载的文件到数据库？(y/n): ")
            if register.lower() == 'y':
                asyncio.run(register_downloaded_files(result))


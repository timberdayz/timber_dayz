"""
账号管理应用主类

实现多平台账号的统一管理功能。
"""

from modules.core.base_app import BaseApplication
from modules.core.logger import get_logger
from .handlers import AccountHandler
from .validators import AccountValidator

logger = get_logger(__name__)


class AccountManagerApp(BaseApplication):
    """账号管理应用"""

    # 类级元数据 - 供注册器读取，避免实例化副作用
    NAME = "账号管理"
    VERSION = "1.0.0"
    DESCRIPTION = "多平台账号统一管理，支持添加、编辑、验证账号"

    def __init__(self):
        """初始化账号管理应用"""
        super().__init__()
        self.name = "账号管理"
        self.version = "1.0.0"
        self.description = "多平台账号统一管理，支持添加、编辑、验证账号"
        
        # 初始化处理器和验证器
        self.handler = AccountHandler()
        self.validator = AccountValidator()
        
        logger.info(f"初始化 {self.name} v{self.version}")
    
    def run(self) -> bool:
        """运行账号管理应用"""
        try:
            logger.info(f"启动 {self.name}")
            self.show_menu()
            return True
        except Exception as e:
            logger.error(f"{self.name} 运行异常: {e}")
            return False
    
    def _custom_health_check(self) -> bool:
        """账号管理模块的健康检查"""
        try:
            # 检查处理器状态
            if not self.handler.health_check():
                logger.warning("账号处理器健康检查失败")
                return False
            
            # 检查账号配置文件
            if not self.handler.check_config_files():
                logger.warning("账号配置文件检查失败")
                return False
            
            return True
        except Exception as e:
            logger.error(f"账号管理健康检查异常: {e}")
            return False
    
    def _show_custom_menu(self):
        """显示账号管理自定义菜单"""
        while True:
            print(f"\n📋 {self.name} - 功能菜单")
            print("-" * 40)
            print("1. 📝 查看所有账号")
            print("2. ➕ 添加新账号")
            print("3. ✏️  编辑账号")
            print("4. 🗑️  删除账号")
            print("5. ✅ 验证账号状态")
            print("6. 📊 账号统计")
            print("7. 🔄 同步账号配置")
            print("8. 📁 导入账号")
            print("9. 📤 导出账号")
            print("0. 🔙 返回主菜单")
            
            choice = input("\n请选择操作 (0-9): ").strip()
            
            try:
                if choice == "1":
                    self._list_accounts()
                elif choice == "2":
                    self._add_account()
                elif choice == "3":
                    self._edit_account()
                elif choice == "4":
                    self._delete_account()
                elif choice == "5":
                    self._verify_accounts()
                elif choice == "6":
                    self._show_statistics()
                elif choice == "7":
                    self._sync_accounts()
                elif choice == "8":
                    self._import_accounts()
                elif choice == "9":
                    self._export_accounts()
                elif choice == "0":
                    break
                else:
                    print("❌ 无效选择，请重新输入")
                
                if choice != "0":
                    input("\n按回车键继续...")
            
            except Exception as e:
                logger.error(f"菜单操作异常: {e}")
                print(f"❌ 操作失败: {e}")
                input("\n按回车键继续...")
    
    def _list_accounts(self):
        """列出所有账号"""
        print(f"\n📋 账号列表")
        print("-" * 50)
        
        try:
            accounts = self.handler.get_all_accounts()
            
            if not accounts:
                print("暂无账号配置")
                return
            
            for i, account in enumerate(accounts, 1):
                platform = account.get('platform', '未知')
                username = account.get('username', '未设置')
                status = account.get('status', '未知')
                
                status_icon = "✅" if status == "active" else "❌" if status == "error" else "⚪"
                print(f"{i:2d}. {status_icon} {platform:10s} | {username:20s} | {status}")
        
        except Exception as e:
            logger.error(f"列出账号失败: {e}")
            print(f"❌ 获取账号列表失败: {e}")
    
    def _add_account(self):
        """添加新账号"""
        print(f"\n➕ 添加新账号")
        print("-" * 30)
        
        try:
            # 获取用户输入
            platform = input("平台名称 (如 shopee, amazon): ").strip()
            if not platform:
                print("❌ 平台名称不能为空")
                return
            
            username = input("用户名/邮箱: ").strip()
            if not username:
                print("❌ 用户名不能为空")
                return
            
            password = input("密码: ").strip()
            if not password:
                print("❌ 密码不能为空")
                return
            
            # 构建账号数据
            account_data = {
                "platform": platform.lower(),
                "username": username,
                "password": password,
                "status": "pending"
            }
            
            # 验证账号数据
            if not self.validator.validate_account(account_data):
                print("❌ 账号数据验证失败")
                return
            
            # 添加账号
            success = self.handler.add_account(account_data)
            
            if success:
                print(f"✅ 账号添加成功: {platform} - {username}")
            else:
                print("❌ 账号添加失败")
        
        except Exception as e:
            logger.error(f"添加账号失败: {e}")
            print(f"❌ 添加账号失败: {e}")
    
    def _edit_account(self):
        """编辑账号"""
        print(f"\n✏️  编辑账号")
        print("-" * 30)
        print("功能开发中...")
    
    def _delete_account(self):
        """删除账号"""
        print(f"\n🗑️  删除账号")
        print("-" * 30)
        print("功能开发中...")
    
    def _verify_accounts(self):
        """验证账号状态"""
        print(f"\n✅ 验证账号状态")
        print("-" * 30)
        
        try:
            print("正在验证所有账号...")
            results = self.handler.verify_all_accounts()
            
            print(f"\n📊 验证结果:")
            for platform, result in results.items():
                status_icon = "✅" if result['success'] else "❌"
                print(f"   {status_icon} {platform}: {result['message']}")
        
        except Exception as e:
            logger.error(f"验证账号失败: {e}")
            print(f"❌ 验证账号失败: {e}")
    
    def _show_statistics(self):
        """显示账号统计"""
        print(f"\n📊 账号统计")
        print("-" * 30)
        
        try:
            stats = self.handler.get_statistics()
            
            print(f"总账号数: {stats['total']}")
            print(f"活跃账号: {stats['active']}")
            print(f"错误账号: {stats['error']}")
            print(f"待验证账号: {stats['pending']}")
            
            if stats['platforms']:
                print(f"\n平台分布:")
                for platform, count in stats['platforms'].items():
                    print(f"   {platform}: {count}")
        
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            print(f"❌ 获取统计失败: {e}")
    
    def _sync_accounts(self):
        """同步账号配置"""
        print(f"\n🔄 同步账号配置")
        print("-" * 30)
        print("功能开发中...")
    
    def _import_accounts(self):
        """导入账号"""
        print(f"\n📁 导入账号")
        print("-" * 30)
        print("功能开发中...")
    
    def _export_accounts(self):
        """导出账号"""
        print(f"\n📤 导出账号")
        print("-" * 30)
        print("功能开发中...") 
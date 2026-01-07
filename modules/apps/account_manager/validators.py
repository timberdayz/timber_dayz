"""
账号管理验证器

验证账号数据的格式和有效性。
"""

import re
from typing import Dict, Any, List
from modules.core.logger import get_logger
from modules.core.exceptions import ValidationError

logger = get_logger(__name__)


class AccountValidator:
    """账号验证器"""
    
    def __init__(self):
        """初始化验证器"""
        # 支持的平台列表
        self.supported_platforms = [
            'shopee', 'amazon', 'ebay', 'aliexpress', 
            'wish', 'lazada', 'tokopedia', 'miaoshou'
        ]
        
        # 邮箱正则表达式
        self.email_pattern = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
        
        logger.debug("账号验证器初始化完成")
    
    def validate_account(self, account_data: Dict[str, Any]) -> bool:
        """
        验证账号数据
        
        Args:
            account_data: 账号数据字典
            
        Returns:
            bool: 验证是否通过
            
        Raises:
            ValidationError: 验证失败时抛出异常
        """
        try:
            # 验证必需字段
            self._validate_required_fields(account_data)
            
            # 验证平台
            self._validate_platform(account_data.get('platform'))
            
            # 验证用户名
            self._validate_username(account_data.get('username'))
            
            # 验证密码
            self._validate_password(account_data.get('password'))
            
            # 验证状态
            if 'status' in account_data:
                self._validate_status(account_data.get('status'))
            
            logger.debug(f"账号数据验证通过: {account_data.get('platform')} - {account_data.get('username')}")
            return True
        
        except ValidationError as e:
            logger.warning(f"账号数据验证失败: {e}")
            raise
        except Exception as e:
            logger.error(f"账号验证异常: {e}")
            raise ValidationError(f"账号验证异常: {e}")
    
    def validate_account_list(self, accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        验证账号列表
        
        Args:
            accounts: 账号列表
            
        Returns:
            List[Dict[str, Any]]: 验证结果列表，包含错误信息
        """
        results = []
        
        for i, account in enumerate(accounts):
            result = {
                "index": i,
                "account": account,
                "valid": False,
                "errors": []
            }
            
            try:
                self.validate_account(account)
                result["valid"] = True
            except ValidationError as e:
                result["errors"].append(str(e))
            except Exception as e:
                result["errors"].append(f"验证异常: {e}")
            
            results.append(result)
        
        return results
    
    def _validate_required_fields(self, account_data: Dict[str, Any]):
        """验证必需字段"""
        required_fields = ['platform', 'username', 'password']
        
        for field in required_fields:
            if field not in account_data:
                raise ValidationError(f"缺少必需字段: {field}")
            
            if not account_data[field] or str(account_data[field]).strip() == '':
                raise ValidationError(f"字段 {field} 不能为空")
    
    def _validate_platform(self, platform: str):
        """验证平台名称"""
        if not platform:
            raise ValidationError("平台名称不能为空")
        
        platform = platform.lower().strip()
        
        if platform not in self.supported_platforms:
            logger.warning(f"不支持的平台: {platform}")
            # 这里只警告，不阻止添加新平台
    
    def _validate_username(self, username: str):
        """验证用户名"""
        if not username:
            raise ValidationError("用户名不能为空")
        
        username = username.strip()
        
        # 长度检查
        if len(username) < 3:
            raise ValidationError("用户名长度不能少于3个字符")
        
        if len(username) > 100:
            raise ValidationError("用户名长度不能超过100个字符")
        
        # 如果是邮箱格式，验证邮箱
        if '@' in username:
            if not self.email_pattern.match(username):
                raise ValidationError("邮箱格式不正确")
    
    def _validate_password(self, password: str):
        """验证密码"""
        if not password:
            raise ValidationError("密码不能为空")
        
        password = password.strip()
        
        # 长度检查
        if len(password) < 6:
            raise ValidationError("密码长度不能少于6个字符")
        
        if len(password) > 100:
            raise ValidationError("密码长度不能超过100个字符")
        
        # 密码强度检查（可选）
        # self._validate_password_strength(password)
    
    def _validate_status(self, status: str):
        """验证状态"""
        valid_statuses = ['active', 'inactive', 'pending', 'error', 'suspended']
        
        if status and status not in valid_statuses:
            raise ValidationError(f"无效的状态值: {status}，有效值: {', '.join(valid_statuses)}")
    
    def _validate_password_strength(self, password: str):
        """验证密码强度（可选）"""
        # 检查是否包含数字
        if not re.search(r'\d', password):
            raise ValidationError("密码必须包含至少一个数字")
        
        # 检查是否包含字母
        if not re.search(r'[a-zA-Z]', password):
            raise ValidationError("密码必须包含至少一个字母")
        
        # 检查特殊字符（可选）
        # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        #     raise ValidationError("密码建议包含特殊字符")
    
    def get_supported_platforms(self) -> List[str]:
        """获取支持的平台列表"""
        return self.supported_platforms.copy()
    
    def add_supported_platform(self, platform: str):
        """添加支持的平台"""
        platform = platform.lower().strip()
        if platform not in self.supported_platforms:
            self.supported_platforms.append(platform)
            logger.info(f"添加支持的平台: {platform}")
    
    def validate_import_data(self, import_data: Any) -> bool:
        """验证导入数据格式"""
        try:
            if not isinstance(import_data, dict):
                raise ValidationError("导入数据必须是字典格式")
            
            if 'accounts' not in import_data:
                raise ValidationError("导入数据必须包含 'accounts' 字段")
            
            accounts = import_data['accounts']
            if not isinstance(accounts, list):
                raise ValidationError("accounts 字段必须是列表格式")
            
            # 验证每个账号
            for i, account in enumerate(accounts):
                try:
                    self.validate_account(account)
                except ValidationError as e:
                    raise ValidationError(f"第 {i+1} 个账号验证失败: {e}")
            
            return True
        
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"导入数据验证异常: {e}") 
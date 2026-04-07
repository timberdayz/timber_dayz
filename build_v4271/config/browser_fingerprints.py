"""
浏览器指纹配置文件
为每个账号提供固定的浏览器指纹，防止重复验证
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
import base64
import hashlib

# 加密密钥（生产环境应该从环境变量获取）
# 使用正确的Fernet密钥
ENCRYPTION_KEY = b'Jp60wm4km2kpb_GesdABfpNwukNCAGehZ0LSqyEvEJg='

class BrowserFingerprintManager:
    """浏览器指纹管理器"""
    
    def __init__(self, config_dir: Path = None):
        """
        初始化浏览器指纹管理器
        
        Args:
            config_dir: 配置文件目录
        """
        if config_dir is None:
            config_dir = Path(__file__).parent
        
        self.config_dir = config_dir
        self.fingerprints_file = config_dir / "encrypted_fingerprints.key"
        self.cipher = Fernet(ENCRYPTION_KEY)
        
        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_fingerprint_id(self, account_id: str, platform: str) -> str:
        """生成指纹ID"""
        return f"{platform}_{account_id}"
    
    def _encrypt_data(self, data: str) -> str:
        """加密数据"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def _decrypt_data(self, encrypted_data: str) -> str:
        """解密数据"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
    
    def _load_fingerprints(self) -> Dict[str, Any]:
        """加载指纹配置"""
        if not self.fingerprints_file.exists():
            return {}
        
        try:
            with open(self.fingerprints_file, 'r', encoding='utf-8') as f:
                encrypted_data = f.read()
                if encrypted_data:
                    decrypted_data = self._decrypt_data(encrypted_data)
                    return json.loads(decrypted_data)
        except Exception as e:
            print(f"⚠️ 加载指纹配置失败: {e}")
        
        return {}
    
    def _save_fingerprints(self, fingerprints: Dict[str, Any]) -> bool:
        """保存指纹配置"""
        try:
            data_json = json.dumps(fingerprints, ensure_ascii=False, indent=2)
            encrypted_data = self._encrypt_data(data_json)
            
            with open(self.fingerprints_file, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
            
            return True
        except Exception as e:
            print(f"❌ 保存指纹配置失败: {e}")
            return False
    
    def get_fingerprint(self, account_id: str, platform: str) -> Optional[Dict[str, Any]]:
        """
        获取账号的浏览器指纹
        
        Args:
            account_id: 账号ID
            platform: 平台名称
            
        Returns:
            浏览器指纹配置
        """
        fingerprints = self._load_fingerprints()
        fingerprint_id = self._generate_fingerprint_id(account_id, platform)
        
        return fingerprints.get(fingerprint_id)
    
    def set_fingerprint(self, account_id: str, platform: str, fingerprint: Dict[str, Any]) -> bool:
        """
        设置账号的浏览器指纹
        
        Args:
            account_id: 账号ID
            platform: 平台名称
            fingerprint: 浏览器指纹配置
            
        Returns:
            是否设置成功
        """
        fingerprints = self._load_fingerprints()
        fingerprint_id = self._generate_fingerprint_id(account_id, platform)
        
        fingerprints[fingerprint_id] = {
            'account_id': account_id,
            'platform': platform,
            'fingerprint': fingerprint,
            'created_at': str(__import__('datetime').datetime.now()),
            'updated_at': str(__import__('datetime').datetime.now())
        }
        
        return self._save_fingerprints(fingerprints)
    
    def generate_default_fingerprint(self, account_id: str, platform: str) -> Dict[str, Any]:
        """
        生成默认的浏览器指纹
        
        Args:
            account_id: 账号ID
            platform: 平台名称
            
        Returns:
            默认浏览器指纹配置
        """
        # 基于账号ID生成固定的指纹
        seed = hashlib.md5(f"{account_id}_{platform}".encode()).hexdigest()
        
        # 生成固定的用户代理
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        
        # 基于seed选择固定的用户代理
        user_agent_index = int(seed[:2], 16) % len(user_agents)
        user_agent = user_agents[user_agent_index]
        
        # 生成固定的屏幕分辨率
        screen_resolutions = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 1280, "height": 720}
        ]
        
        screen_index = int(seed[2:4], 16) % len(screen_resolutions)
        screen_resolution = screen_resolutions[screen_index]
        
        # 生成固定的时区
        timezones = [
            "Asia/Shanghai",
            "Asia/Hong_Kong",
            "Asia/Singapore",
            "Asia/Tokyo",
            "America/New_York"
        ]
        
        timezone_index = int(seed[4:6], 16) % len(timezones)
        timezone = timezones[timezone_index]
        
        # 生成固定的语言设置
        languages = [
            ["zh-CN", "zh", "en-US", "en"],
            ["en-US", "en"],
            ["zh-TW", "zh", "en-US", "en"],
            ["zh-HK", "zh", "en-US", "en"]
        ]
        
        language_index = int(seed[6:8], 16) % len(languages)
        language = languages[language_index]
        
        # 生成固定的字体列表
        fonts = [
            "Arial, Helvetica, sans-serif",
            "Microsoft YaHei, Arial, sans-serif",
            "PingFang SC, Microsoft YaHei, sans-serif",
            "Helvetica Neue, Arial, sans-serif",
            "Segoe UI, Tahoma, Geneva, Verdana, sans-serif"
        ]
        
        font_index = int(seed[8:10], 16) % len(fonts)
        font = fonts[font_index]
        
        # 生成固定的Canvas指纹
        canvas_fingerprint = hashlib.md5(f"canvas_{seed}".encode()).hexdigest()
        
        # 生成固定的WebGL指纹
        webgl_fingerprint = hashlib.md5(f"webgl_{seed}".encode()).hexdigest()
        
        return {
            "user_agent": user_agent,
            "screen": screen_resolution,
            "timezone": timezone,
            "language": language,
            "font": font,
            "canvas_fingerprint": canvas_fingerprint,
            "webgl_fingerprint": webgl_fingerprint,
            "platform": "Win32",
            "hardware_concurrency": 8,
            "device_memory": 8,
            "max_touch_points": 0,
            "color_depth": 24,
            "pixel_depth": 24,
            "cookie_enabled": True,
            "do_not_track": None,
            "webdriver": False,
            "plugins": [
                "PDF Viewer",
                "Chrome PDF Plugin",
                "Chrome PDF Viewer",
                "Native Client"
            ],
            "mime_types": [
                "application/pdf",
                "application/x-google-chrome-pdf"
            ]
        }
    
    def ensure_fingerprint(self, account_id: str, platform: str) -> Dict[str, Any]:
        """
        确保账号有浏览器指纹，如果没有则生成默认指纹
        
        Args:
            account_id: 账号ID
            platform: 平台名称
            
        Returns:
            浏览器指纹配置
        """
        fingerprint = self.get_fingerprint(account_id, platform)
        
        if not fingerprint:
            # 生成默认指纹
            default_fingerprint = self.generate_default_fingerprint(account_id, platform)
            self.set_fingerprint(account_id, platform, default_fingerprint)
            return default_fingerprint
        
        return fingerprint['fingerprint']
    
    def list_fingerprints(self) -> Dict[str, Any]:
        """列出所有指纹配置"""
        return self._load_fingerprints()
    
    def delete_fingerprint(self, account_id: str, platform: str) -> bool:
        """
        删除账号的浏览器指纹
        
        Args:
            account_id: 账号ID
            platform: 平台名称
            
        Returns:
            是否删除成功
        """
        fingerprints = self._load_fingerprints()
        fingerprint_id = self._generate_fingerprint_id(account_id, platform)
        
        if fingerprint_id in fingerprints:
            del fingerprints[fingerprint_id]
            return self._save_fingerprints(fingerprints)
        
        return True
    
    def clear_all_fingerprints(self) -> bool:
        """清除所有指纹配置"""
        return self._save_fingerprints({})


# 全局实例
fingerprint_manager = BrowserFingerprintManager()


def get_account_fingerprint(account_id: str, platform: str) -> Dict[str, Any]:
    """
    获取账号的浏览器指纹
    
    Args:
        account_id: 账号ID
        platform: 平台名称
        
    Returns:
        浏览器指纹配置
    """
    return fingerprint_manager.ensure_fingerprint(account_id, platform)


def set_account_fingerprint(account_id: str, platform: str, fingerprint: Dict[str, Any]) -> bool:
    """
    设置账号的浏览器指纹
    
    Args:
        account_id: 账号ID
        platform: 平台名称
        fingerprint: 浏览器指纹配置
        
    Returns:
        是否设置成功
    """
    return fingerprint_manager.set_fingerprint(account_id, platform, fingerprint)


if __name__ == "__main__":
    # 测试代码
    print("🧪 浏览器指纹管理器测试")
    print("=" * 50)
    
    # 测试生成指纹
    test_account = "test_account_001"
    test_platform = "shopee"
    
    fingerprint = get_account_fingerprint(test_account, test_platform)
    print(f"✅ 生成指纹成功: {test_account}@{test_platform}")
    print(f"   用户代理: {fingerprint['user_agent']}")
    print(f"   屏幕分辨率: {fingerprint['screen']}")
    print(f"   时区: {fingerprint['timezone']}")
    
    # 测试列表
    all_fingerprints = fingerprint_manager.list_fingerprints()
    print(f"\n📋 当前指纹数量: {len(all_fingerprints)}")
    
    # 测试删除
    if fingerprint_manager.delete_fingerprint(test_account, test_platform):
        print(f"✅ 删除指纹成功: {test_account}@{test_platform}")
    
    print("\n🎉 测试完成") 
"""
代理配置文件 - 类似local_accounts.py的设计模式
为不同地区和平台配置代理服务器

使用方法：
1. 修改下面的PROXY_CONFIG配置
2. 系统会自动读取并应用到对应的账号
3. 支持按地区、平台、账号类型分配代理

安全提示：
- 此文件包含敏感信息，已添加到.gitignore
- 生产环境请使用加密存储
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta


# 代理配置主体 - 按地区分类
PROXY_CONFIG = {
    # 中国地区代理 - 用于中国账号或需要中国IP的场景
    "china": {
        "name": "中国代理",
        "description": "适用于中国Shopee卖家端、中国Amazon账号等",
        "providers": [
            {
                "provider_name": "tianqi_ip",
                "provider_type": "api",  # api | static | rotation
                "enabled": False,
                "priority": 2,  # 优先级，数字越小优先级越高
                "api_config": {
                    "api_url": "http://api.tianqiip.com/getip",
                    "secret": "新secret",
                    "sign": "新sign",
                    "params": {
                        "num": 1,
                        "type": "json",
                        "region": "440000",  # 广东地区
                        "port": 1,
                        "time": 60,  # 1小时有效期
                        "mr": 1,
                        "tl": 1
                    }
                },
                "rotation_interval": 3600,  # 1小时轮换一次
                "max_concurrent": 5,  # 最大并发使用数
                "notes": "天启IP - 1小时有效期，适合短期使用"
            },
            # 静态代理配置 - 直接使用获取到的代理地址
            {
                "provider_name": "tianqi_static",
                "provider_type": "static",  # 静态代理类型
                "enabled": False,  # 暂时禁用，因为当前客户端IP被识别为非国内
                "priority": 1,  # 设置为最高优先级，优先使用静态代理
                "static_config": {
                    "proxy_list": [
                        {
                            "host": "61.132.231.167",
                            "port": 52000,
                            "protocol": "http",
                            "username": "19150113371",  # 请填入代理用户名
                            "password": "qq1164483861",  # 请填入代理密码
                            "location": "四川成都",
                            "valid_until": None,  # 根据你的代理有效期设置，None表示长期有效
                            "notes": "天启IP四川成都代理 - 错误430：客户端IP非国内，需要使用国内IP访问"
                        }
                    ]
                },
                "notes": "天启IP静态代理 - 当前暂时无法使用（客户端IP非国内）"
            },
            {
                "provider_name": "backup_domestic_proxy",
                "provider_type": "static",
                "enabled": True,  # 启用备用国内代理
                "priority": 1,
                "static_config": {
                    "proxy_list": [
                        {
                            "host": "127.0.0.1",  # 本地开发用，实际使用时替换为可用的国内代理
                            "port": 1080,
                            "protocol": "http",
                            "username": "",
                            "password": "",
                            "location": "本地开发",
                            "valid_until": None,
                            "notes": "备用代理 - 开发测试用"
                        }
                    ]
                },
                "notes": "备用国内代理 - 替代天启IP使用"
            }
            # 可以添加更多备用代理提供商
            # {
            #     "provider_name": "backup_china_proxy",
            #     "provider_type": "static",
            #     "enabled": False,
            #     "priority": 2,
            #     "static_proxies": [
            #         {"ip": "1.2.3.4", "port": 8080, "username": "", "password": "", "protocol": "http"}
            #     ]
            # }
        ]
    },
    
    # 新加坡地区代理 - 用于新加坡账号
    "singapore": {
        "name": "新加坡代理",
        "description": "适用于新加坡Shopee买家端、新加坡Amazon账号等",
        "providers": [
            {
                "provider_name": "singapore_proxy_service",
                "provider_type": "api",
                "enabled": False,  # 暂未配置，设置为False
                "priority": 1,
                "api_config": {
                    "api_url": "https://your-singapore-proxy-api.com/getip",
                    "api_key": "your_singapore_api_key",
                    "params": {
                        "region": "440000",
                        "duration": 3600
                    }
                },
                "notes": "新加坡代理服务 - 需要时配置"
            }
        ]
    },
    
    # 马来西亚地区代理
    "malaysia": {
        "name": "马来西亚代理",
        "description": "适用于马来西亚Shopee账号",
        "providers": [
            {
                "provider_name": "malaysia_proxy_service",
                "provider_type": "api",
                "enabled": False,
                "priority": 1,
                "api_config": {
                    "api_url": "https://your-malaysia-proxy-api.com/getip",
                    "api_key": "your_malaysia_api_key"
                },
                "notes": "马来西亚代理服务 - 需要时配置"
            }
        ]
    },
    
    # 美国地区代理
    "usa": {
        "name": "美国代理",
        "description": "适用于美国Amazon账号、美国eBay账号等",
        "providers": [
            {
                "provider_name": "usa_proxy_service",
                "provider_type": "api",
                "enabled": False,
                "priority": 1,
                "api_config": {
                    "api_url": "https://your-usa-proxy-api.com/getip",
                    "api_key": "your_usa_api_key"
                },
                "notes": "美国代理服务 - 需要时配置"
            }
        ]
    }
}


# 平台账号类型与代理地区映射规则
ACCOUNT_PROXY_MAPPING = {
    # Shopee平台映射规则
    "Shopee": {
        # 按账号地区映射
        "region_mapping": {
            "CN": "china",      # 中国Shopee账号使用中国代理
            "SG": "singapore",  # 新加坡Shopee账号使用新加坡代理
            "MY": "malaysia",   # 马来西亚Shopee账号使用马来西亚代理
            "TH": "singapore",  # 泰国Shopee账号使用新加坡代理
            "VN": "singapore",  # 越南Shopee账号使用新加坡代理
            "PH": "singapore",  # 菲律宾Shopee账号使用新加坡代理
            "ID": "singapore",  # 印尼Shopee账号使用新加坡代理
            "TW": "china",      # 台湾Shopee账号使用中国代理
        },
        # 按账号类型映射
        "account_type_mapping": {
            "seller": {  # 卖家端
                "CN": "china",
                "default": "singapore"
            },
            "buyer": {   # 买家端
                "SG": "singapore",
                "MY": "malaysia",
                "default": "singapore"
            }
        }
    },
    
    # Amazon平台映射规则
    "Amazon": {
        "region_mapping": {
            "CN": "china",      # 中国Amazon账号使用中国代理
            "US": "usa",        # 美国Amazon账号使用美国代理
            "SG": "singapore",  # 新加坡Amazon账号使用新加坡代理
        }
    },
    
    # 妙手ERP平台映射规则
    "妙手ERP": {
        "region_mapping": {
            "CN": "china",      # 中国妙手ERP账号使用中国代理
            "default": "china"  # 默认使用中国代理
        }
    }
}


# 代理使用策略配置
PROXY_STRATEGY = {
    # 全局策略
    "global": {
        "enable_smart_switching": True,    # 启用智能切换
        "fallback_to_direct": True,       # 代理失败时回退到直连
        "max_retry_attempts": 3,          # 最大重试次数
        "retry_delay": 5,                 # 重试延迟(秒)
        "health_check_interval": 300,     # 健康检查间隔(秒)
        "proxy_timeout": 30,              # 代理连接超时(秒)
    },
    
    # 按平台策略
    "platform_specific": {
        "Shopee": {
            "force_proxy": True,           # 是否强制使用代理
            "smart_detection": True,       # 智能检测是否需要代理
            "preferred_protocol": "http",  # 优先协议
        },
        "Amazon": {
            "force_proxy": False,
            "smart_detection": True,
            "preferred_protocol": "https",
        },
        "妙手ERP": {
            "force_proxy": False,
            "smart_detection": True,
            "preferred_protocol": "http",
        }
    }
}


def get_proxy_config() -> Dict[str, Any]:
    """获取代理配置"""
    return PROXY_CONFIG


def get_account_proxy_mapping() -> Dict[str, Any]:
    """获取账号代理映射规则"""
    return ACCOUNT_PROXY_MAPPING


def get_proxy_strategy() -> Dict[str, Any]:
    """获取代理策略配置"""
    return PROXY_STRATEGY


def get_region_proxy_providers(region: str) -> List[Dict[str, Any]]:
    """
    获取指定地区的代理提供商
    
    Args:
        region: 地区代码 (china, singapore, malaysia, usa)
        
    Returns:
        代理提供商列表，按优先级排序
    """
    region_config = PROXY_CONFIG.get(region, {})
    providers = region_config.get("providers", [])
    
    # 只返回启用的提供商，并按优先级排序
    enabled_providers = [p for p in providers if p.get("enabled", False)]
    enabled_providers.sort(key=lambda x: x.get("priority", 999))
    
    return enabled_providers


def get_account_proxy_region(platform: str, account_region: str, account_type: str = None) -> str:
    """
    根据账号信息获取应该使用的代理地区
    
    Args:
        platform: 平台名称
        account_region: 账号地区
        account_type: 账号类型 (seller, buyer)
        
    Returns:
        代理地区代码
    """
    platform_mapping = ACCOUNT_PROXY_MAPPING.get(platform, {})
    
    # 优先检查账号类型映射
    if account_type and "account_type_mapping" in platform_mapping:
        type_mapping = platform_mapping["account_type_mapping"].get(account_type, {})
        if account_region in type_mapping:
            return type_mapping[account_region]
        if "default" in type_mapping:
            return type_mapping["default"]
    
    # 检查地区映射
    region_mapping = platform_mapping.get("region_mapping", {})
    if account_region in region_mapping:
        return region_mapping[account_region]
    
    # 返回默认地区
    if "default" in region_mapping:
        return region_mapping["default"]
    
    # 最后的默认值
    return "china"


# 使用示例和说明
USAGE_EXAMPLES = {
    "快速配置新代理": {
        "description": "如何添加新的代理提供商",
        "example": """
# 1. 在PROXY_CONFIG中添加新地区或更新现有地区
# 2. 在对应地区的providers中添加新的代理配置
# 3. 设置enabled=True启用代理
# 4. 调整priority设置优先级

# 示例：更新天启IP的配置
PROXY_CONFIG["china"]["providers"][0]["api_config"]["secret"] = "新的secret"
PROXY_CONFIG["china"]["providers"][0]["api_config"]["sign"] = "新的sign"
        """
    },
    
    "账号代理映射": {
        "description": "如何为不同账号配置代理",
        "example": """
# 自动映射示例：
# - Shopee中国卖家账号 → 自动使用中国代理
# - Shopee新加坡买家账号 → 自动使用新加坡代理
# - Amazon美国账号 → 自动使用美国代理

# 配置方法：在local_accounts.py中设置账号的region字段即可
        """
    },
    
    "代理轮换": {
        "description": "短期代理的自动轮换机制",
        "example": """
# 系统会根据rotation_interval自动轮换代理
# 天启IP配置为3600秒(1小时)轮换一次
# 可以根据代理服务的有效期调整这个值
        """
    }
}


if __name__ == "__main__":
    # 测试配置加载
    print("🔧 代理配置测试")
    print(f"✅ 配置的地区数量: {len(PROXY_CONFIG)}")
    
    for region, config in PROXY_CONFIG.items():
        enabled_count = len([p for p in config["providers"] if p.get("enabled", False)])
        print(f"  📍 {config['name']}: {enabled_count} 个启用的代理提供商")
    
    print(f"✅ 支持的平台数量: {len(ACCOUNT_PROXY_MAPPING)}")
    print("🎯 配置加载完成") 
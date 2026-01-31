#!/usr/bin/env python3
"""
Metabase 配置初始化脚本

功能：
- 读取 config/metabase_config.yaml 配置文件
- 通过 Metabase API 创建/更新 Models 和 Questions
- 支持幂等操作：存在则更新，不存在则创建
- 通过名称（而非 ID）唯一标识资源

使用方式：
    python scripts/init_metabase.py [--dry-run] [--verbose]

参数：
    --dry-run   仅打印将要执行的操作，不实际执行
    --verbose   显示详细日志
    --config    配置文件路径（默认：config/metabase_config.yaml）

环境变量：
    METABASE_URL        Metabase 服务地址（默认：http://localhost:3000）
    METABASE_API_KEY    Metabase API Key（推荐）
    METABASE_USERNAME   Metabase 用户名（不推荐，仅开发环境）
    METABASE_PASSWORD   Metabase 密码（不推荐，仅开发环境）
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
import yaml

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 自动加载 .env 文件
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # dotenv 不是必须的，可以通过环境变量直接设置

from modules.core.logger import get_logger

logger = get_logger(__name__)


class MetabaseAPIError(Exception):
    """Metabase API 错误"""
    pass


class MetabaseInitializer:
    """Metabase 配置初始化器（幂等操作）"""

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        username: str = None,
        password: str = None,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        self.base_url = (base_url or os.getenv("METABASE_URL", "http://localhost:3000")).rstrip("/")
        self.api_key = api_key or os.getenv("METABASE_API_KEY")
        self.username = username or os.getenv("METABASE_USERNAME")
        self.password = password or os.getenv("METABASE_PASSWORD")
        self.dry_run = dry_run
        self.verbose = verbose
        
        self.session = requests.Session()
        self.session_token = None
        self._database_id_cache: dict[str, int] = {}
        self._collection_id_cache: dict[str, int] = {}
        self._card_cache: dict[str, dict] = {}  # 名称 -> Card 信息

    def _log(self, message: str, level: str = "info"):
        """日志输出"""
        if self.verbose or level in ("warning", "error"):
            log_func = getattr(logger, level, logger.info)
            log_func(message)

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: dict = None,
        params: dict = None,
    ) -> dict | list | None:
        """发送 API 请求"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        # 认证方式
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.session_token:
            headers["X-Metabase-Session"] = self.session_token
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30,
            )
            
            if response.status_code == 401:
                raise MetabaseAPIError("认证失败，请检查 API Key 或用户名密码")
            
            if response.status_code >= 400:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                except Exception:
                    pass
                raise MetabaseAPIError(f"API 请求失败 ({response.status_code}): {error_msg}")
            
            if response.text:
                return response.json()
            return None
            
        except requests.RequestException as e:
            raise MetabaseAPIError(f"网络请求失败: {e}")

    def authenticate(self) -> bool:
        """认证到 Metabase"""
        if self.api_key:
            self._log("使用 API Key 认证")
            # 验证 API Key 是否有效
            try:
                self._api_request("GET", "/api/user/current")
                self._log("API Key 认证成功")
                return True
            except MetabaseAPIError:
                self._log("API Key 认证失败", "error")
                return False
        
        if self.username and self.password:
            self._log("使用用户名密码认证")
            try:
                response = self._api_request(
                    "POST",
                    "/api/session",
                    data={"username": self.username, "password": self.password},
                )
                self.session_token = response.get("id")
                self._log("用户名密码认证成功")
                return True
            except MetabaseAPIError as e:
                self._log(f"用户名密码认证失败: {e}", "error")
                return False
        
        self._log("未提供认证信息", "error")
        return False

    def wait_for_metabase(self, timeout: int = 120, interval: int = 5) -> bool:
        """等待 Metabase 服务就绪"""
        self._log(f"等待 Metabase 服务就绪（最多 {timeout} 秒）...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/api/health",
                    timeout=5,
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "ok":
                        self._log("Metabase 服务已就绪")
                        return True
            except Exception:
                pass
            
            self._log(f"Metabase 尚未就绪，{interval} 秒后重试...")
            time.sleep(interval)
        
        self._log("等待 Metabase 超时", "error")
        return False

    def get_database_id(self, database_name: str) -> int | None:
        """通过名称获取数据库 ID"""
        if database_name in self._database_id_cache:
            return self._database_id_cache[database_name]
        
        response = self._api_request("GET", "/api/database")
        # 处理新版 Metabase API 返回格式: {"data": [...], "total": N}
        databases = response.get("data", response) if isinstance(response, dict) else response
        for db in databases:
            if db.get("name") == database_name:
                self._database_id_cache[database_name] = db["id"]
                return db["id"]
        
        return None

    def get_collection_id(self, collection_name: str) -> int | None:
        """通过名称获取 Collection ID"""
        if collection_name in self._collection_id_cache:
            return self._collection_id_cache[collection_name]
        
        collections = self._api_request("GET", "/api/collection")
        for col in collections:
            if col.get("name") == collection_name:
                self._collection_id_cache[collection_name] = col["id"]
                return col["id"]
        
        return None

    def ensure_collection_exists(self, name: str, description: str = None, parent_name: str = None) -> int:
        """确保 Collection 存在，返回 Collection ID"""
        existing_id = self.get_collection_id(name)
        if existing_id:
            self._log(f"Collection '{name}' 已存在 (ID: {existing_id})")
            return existing_id
        
        if self.dry_run:
            self._log(f"[DRY-RUN] 将创建 Collection: {name}")
            return -1
        
        # 获取父 Collection ID
        parent_id = None
        if parent_name:
            parent_id = self.get_collection_id(parent_name)
            if not parent_id:
                self._log(f"父 Collection '{parent_name}' 不存在，先创建", "warning")
                parent_id = self.ensure_collection_exists(parent_name)
        
        # 创建 Collection
        data = {
            "name": name,
            "description": description or name,  # Metabase 要求 description 非空
        }
        if parent_id:
            data["parent_id"] = parent_id
        
        result = self._api_request("POST", "/api/collection", data=data)
        collection_id = result["id"]
        self._collection_id_cache[name] = collection_id
        self._log(f"创建 Collection '{name}' (ID: {collection_id})")
        return collection_id

    def find_card_by_name(self, name: str) -> dict | None:
        """通过名称查找 Card（Model 或 Question）"""
        if name in self._card_cache:
            return self._card_cache[name]
        
        # 搜索 Card
        response = self._api_request(
            "GET",
            "/api/card",
            params={"q": name},
        )
        
        # 处理新版 Metabase API 返回格式: {"data": [...], "total": N}
        cards = response.get("data", response) if isinstance(response, dict) else response
        
        for card in cards:
            if card.get("name") == name:
                self._card_cache[name] = card
                return card
        
        return None

    def get_model_id_by_name(self, model_name: str) -> int | None:
        """通过 Model 名称获取 Model ID"""
        card = self.find_card_by_name(model_name)
        if card and card.get("type") == "model":
            return card["id"]
        return None

    def resolve_model_references(self, sql_content: str) -> tuple[str, dict[str, dict]]:
        """
        解析并替换 SQL 中的 {{MODEL:xxx}} 占位符，同时生成 Card 引用的 template-tags
        
        将 {{MODEL:Orders Model}} 替换为 {{#39}}（实际的 Model ID），
        并返回对应的 template-tags 配置，以便 Metabase 正确识别 Card 引用
        
        Args:
            sql_content: 包含 {{MODEL:xxx}} 占位符的 SQL 内容
            
        Returns:
            (resolved_sql, card_template_tags) 元组：
            - resolved_sql: 替换后的 SQL 内容
            - card_template_tags: Card 引用的 template-tags 配置
        """
        # 匹配 {{MODEL:xxx}} 格式的占位符
        pattern = r'\{\{MODEL:([^}]+)\}\}'
        matches = re.findall(pattern, sql_content)
        
        card_template_tags = {}
        
        if not matches:
            return sql_content, card_template_tags
        
        resolved_sql = sql_content
        for model_name in matches:
            model_name = model_name.strip()
            model_id = self.get_model_id_by_name(model_name)
            
            if model_id:
                # 替换为 Metabase 的 Model 引用语法
                placeholder = f'{{{{MODEL:{model_name}}}}}'
                replacement = f'{{{{#{model_id}}}}}'
                resolved_sql = resolved_sql.replace(placeholder, replacement)
                self._log(f"解析 Model 引用: '{model_name}' -> ID {model_id}")
                
                # 生成 Card 引用的 template-tag 配置
                # 关键：type 必须是 "card"，card-id 是实际的 Model ID
                tag_name = f"#{model_id}"
                card_template_tags[tag_name] = {
                    "id": tag_name,
                    "name": tag_name,
                    "display-name": model_name,
                    "type": "card",
                    "card-id": model_id,
                }
            else:
                self._log(f"警告: 未找到 Model '{model_name}'，保留原占位符", "warning")
        
        return resolved_sql, card_template_tags

    def read_sql_file(self, sql_file_path: str) -> str:
        """读取 SQL 文件内容"""
        full_path = PROJECT_ROOT / sql_file_path
        if not full_path.exists():
            raise FileNotFoundError(f"SQL 文件不存在: {full_path}")
        
        return full_path.read_text(encoding="utf-8")

    def ensure_model_exists(self, model_config: dict, database_id: int) -> int:
        """确保 Model 存在，返回 Model ID"""
        name = model_config["name"]
        sql_file = model_config["sql_file"]
        description = model_config.get("description", "")
        collection_name = model_config.get("collection")
        
        # 查找现有 Card
        existing = self.find_card_by_name(name)
        
        if self.dry_run:
            if existing:
                self._log(f"[DRY-RUN] Model '{name}' 已存在，将检查是否需要更新")
            else:
                self._log(f"[DRY-RUN] 将创建 Model: {name}")
            return existing["id"] if existing else -1
        
        # 读取 SQL 文件
        sql_content = self.read_sql_file(sql_file)
        
        # 获取 Collection ID
        collection_id = None
        if collection_name:
            collection_id = self.ensure_collection_exists(collection_name)
        
        # 构建 Card 数据
        card_data = {
            "name": name,
            "description": description,
            "display": "table",
            "dataset_query": {
                "type": "native",
                "native": {
                    "query": sql_content,
                },
                "database": database_id,
            },
            "type": "model",  # 标记为 Model
            "visualization_settings": {},
        }
        if collection_id:
            card_data["collection_id"] = collection_id
        
        if existing:
            # 检查 SQL 是否变化
            existing_sql = existing.get("dataset_query", {}).get("native", {}).get("query", "")
            if existing_sql.strip() == sql_content.strip():
                self._log(f"Model '{name}' 无变化，跳过更新")
                return existing["id"]
            
            # 更新 Model
            self._api_request("PUT", f"/api/card/{existing['id']}", data=card_data)
            self._log(f"更新 Model '{name}' (ID: {existing['id']})")
            return existing["id"]
        else:
            # 创建 Model
            result = self._api_request("POST", "/api/card", data=card_data)
            card_id = result["id"]
            self._card_cache[name] = result
            self._log(f"创建 Model '{name}' (ID: {card_id})")
            return card_id

    def ensure_question_exists(self, question_config: dict, database_id: int) -> int:
        """确保 Question 存在，返回 Question ID"""
        name = question_config["name"]
        display_name = question_config.get("display_name", name)
        sql_file = question_config["sql_file"]
        description = question_config.get("description", "") or display_name  # Metabase 要求 description 非空
        collection_name = question_config.get("collection")
        parameters = question_config.get("parameters", [])
        
        # 查找现有 Card
        existing = self.find_card_by_name(display_name)
        
        if self.dry_run:
            if existing:
                self._log(f"[DRY-RUN] Question '{display_name}' 已存在，将检查是否需要更新")
            else:
                self._log(f"[DRY-RUN] 将创建 Question: {display_name}")
            return existing["id"] if existing else -1
        
        # 检查 SQL 文件是否存在
        sql_path = PROJECT_ROOT / sql_file
        if not sql_path.exists():
            self._log(f"Question '{display_name}' 的 SQL 文件不存在: {sql_file}，跳过", "warning")
            return -1
        
        # 读取 SQL 文件
        sql_content = self.read_sql_file(sql_file)
        
        # 解析并替换 {{MODEL:xxx}} 占位符，同时获取 Card 引用的 template-tags
        sql_content, card_template_tags = self.resolve_model_references(sql_content)
        
        # 获取 Collection ID
        collection_id = None
        if collection_name:
            collection_id = self.ensure_collection_exists(collection_name)
        
        # 构建模板标签（参数）
        # 首先添加 Card 引用的 template-tags（关键：让 Metabase 识别 {{#ID}} 为 Model 引用）
        template_tags = dict(card_template_tags)
        
        # 然后添加用户定义的参数
        for param in parameters:
            param_name = param["name"]
            param_type = param.get("type", "text")
            
            # Metabase 参数类型映射
            type_mapping = {
                "text": "text",
                "number": "number",
                "date": "date",
            }
            mb_type = type_mapping.get(param_type, "text")
            
            template_tags[param_name] = {
                "id": param_name,
                "name": param_name,
                "display-name": param.get("display_name", param_name),
                "type": mb_type,
                "required": param.get("required", False),
            }
            if param.get("default") is not None:
                template_tags[param_name]["default"] = param["default"]
        
        # 构建 Card 数据
        card_data = {
            "name": display_name,
            "description": description,
            "display": "table",
            "dataset_query": {
                "type": "native",
                "native": {
                    "query": sql_content,
                    "template-tags": template_tags,
                },
                "database": database_id,
            },
            "type": "question",
            "visualization_settings": {},
        }
        if collection_id:
            card_data["collection_id"] = collection_id
        
        if existing:
            # 检查 SQL 是否变化
            existing_sql = existing.get("dataset_query", {}).get("native", {}).get("query", "")
            if existing_sql.strip() == sql_content.strip():
                self._log(f"Question '{display_name}' 无变化，跳过更新")
                return existing["id"]
            
            # 更新 Question
            self._api_request("PUT", f"/api/card/{existing['id']}", data=card_data)
            self._log(f"更新 Question '{display_name}' (ID: {existing['id']})")
            return existing["id"]
        else:
            # 创建 Question
            result = self._api_request("POST", "/api/card", data=card_data)
            card_id = result["id"]
            self._card_cache[display_name] = result
            self._log(f"创建 Question '{display_name}' (ID: {card_id})")
            return card_id

    def initialize_from_config(self, config_path: str) -> dict:
        """从配置文件初始化 Metabase"""
        # 读取配置文件
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = PROJECT_ROOT / config_path
        # [FIX] Docker 容器内：若相对路径解析后不存在，尝试 /app/config/metabase_config.yaml
        if not config_file.exists() and "/app/config" not in str(config_file):
            docker_path = Path("/app/config/metabase_config.yaml")
            if docker_path.exists():
                config_file = docker_path
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")
        
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 等待 Metabase 就绪
        if not self.wait_for_metabase():
            raise MetabaseAPIError("Metabase 服务不可用")
        
        # 认证
        if not self.authenticate():
            raise MetabaseAPIError("Metabase 认证失败")
        
        # 获取数据库 ID
        database_name = config.get("database", {}).get("name", "西虹ERP数据库")
        database_id = self.get_database_id(database_name)
        if not database_id:
            self._log(f"数据库 '{database_name}' 不存在，请先在 Metabase 中添加数据源", "error")
            raise MetabaseAPIError(f"数据库 '{database_name}' 不存在")
        
        self._log(f"使用数据库: {database_name} (ID: {database_id})")
        
        # 创建 Collections
        collections = config.get("collections", [])
        for col_config in collections:
            self.ensure_collection_exists(
                name=col_config["name"],
                description=col_config.get("description"),
                parent_name=col_config.get("parent"),
            )
        
        # 创建 Models
        models = config.get("models", [])
        model_results = {}
        for model_config in models:
            try:
                model_id = self.ensure_model_exists(model_config, database_id)
                model_results[model_config["name"]] = model_id
            except Exception as e:
                self._log(f"创建 Model '{model_config['name']}' 失败: {e}", "error")
                model_results[model_config["name"]] = None
        
        # 创建 Questions
        questions = config.get("questions", [])
        question_results = {}
        for question_config in questions:
            try:
                question_id = self.ensure_question_exists(question_config, database_id)
                question_results[question_config["name"]] = question_id
            except Exception as e:
                self._log(f"创建 Question '{question_config['name']}' 失败: {e}", "error")
                question_results[question_config["name"]] = None
        
        return {
            "models": model_results,
            "questions": question_results,
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Metabase 配置初始化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="config/metabase_config.yaml",
        help="配置文件路径（默认：config/metabase_config.yaml）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将要执行的操作，不实际执行",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志",
    )
    parser.add_argument(
        "--url",
        help="Metabase 服务地址（覆盖环境变量）",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Metabase 配置初始化")
    print("=" * 60)
    
    if args.dry_run:
        print("[DRY-RUN 模式] 不会实际执行任何操作")
    
    try:
        initializer = MetabaseInitializer(
            base_url=args.url,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        
        results = initializer.initialize_from_config(args.config)
        
        print("\n" + "=" * 60)
        print("初始化完成")
        print("=" * 60)
        
        print("\nModels:")
        for name, model_id in results["models"].items():
            status = f"ID: {model_id}" if model_id and model_id > 0 else "跳过/失败"
            print(f"  - {name}: {status}")
        
        print("\nQuestions:")
        for name, question_id in results["questions"].items():
            status = f"ID: {question_id}" if question_id and question_id > 0 else "跳过/失败"
            print(f"  - {name}: {status}")
        
        # 统计
        model_success = sum(1 for v in results["models"].values() if v and v > 0)
        question_success = sum(1 for v in results["questions"].values() if v and v > 0)
        
        print(f"\n统计: Models {model_success}/{len(results['models'])}, Questions {question_success}/{len(results['questions'])}")
        
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] 初始化失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

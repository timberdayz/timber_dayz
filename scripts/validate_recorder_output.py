from pathlib import Path
import ast
import sys


ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.steps_to_python import generate_python_code
from modules.apps.collection_center.component_loader import ComponentLoader


def main() -> None:
    steps = [
        {
            "action": "navigate",
            "url": "https://example.com/login",
            "comment": "open login page",
        },
        {
            "action": "fill",
            "selector": "input[name='username']",
            "value": "{{account.username}}",
            "comment": "fill username",
        },
        {
            "action": "click",
            "selector": "button[type='submit']",
            "comment": "click submit",
        },
        {
            "action": "click",
            "selector": ".optional-popup-close",
            "optional": True,
            "comment": "close optional popup",
        },
    ]

    code = generate_python_code(
        platform="shopee",
        component_type="login",
        component_name="recorder_test_login",
        steps=steps,
    )
    print("[generate_python_code] len:", len(code))

    # 语法校验
    ast.parse(code)
    print("[ast] syntax ok")

    # 写入组件文件
    root = ROOT
    component_path = (
        root
        / "modules"
        / "platforms"
        / "shopee"
        / "components"
        / "recorder_test_login.py"
    )
    component_path.write_text(code, encoding="utf-8")
    print("[write] component saved to:", component_path)

    # 通过 ComponentLoader 验证可加载
    loader = ComponentLoader()
    cls = loader.load_python_component("shopee", "recorder_test_login")
    print("[load_python_component] loaded:", cls, "module:", cls.__module__)


if __name__ == "__main__":
    main()


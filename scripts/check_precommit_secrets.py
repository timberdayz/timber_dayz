"""
Cross-platform pre-commit secret file check.

Blocks obvious sensitive file types from being committed by mistake.

⚠️ 2026-11-13（批次 C2）—— 本门禁**曾经拦不住真正的泄露**：
   公开仓库里长期跟踪着 ``.env.production.passwords.txt``（生产密钥备份）
   与 ``.env.cleaned``（带解密密钥的部署产物），
   而当时的 :func:`is_blocked` 只拦「文件名**恰好**是 ``.env``」与
   「后缀是 ``.key`` / ``.enc``」⇒ 这两个文件（后缀分别是 ``.txt`` 与
   名字不以 ``.env`` 结尾）**全部绕过**。
   ⇒ 现在按**规则**拦，不再按文件名逐个补。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_BASENAMES = {
    "env.template",
    ".env.template",
    ".env.example",
    # ⚠️ ``.env.limiter`` 是**例外**：它是限流器的**运行期配置**（不是密钥文件）——
    #    ``backend/middleware/rate_limiter.py`` 直接读它，且必须保持**纯 ASCII**
    #    （Windows 下 starlette 用 gbk 解 UTF-8 的 .env 会抛 UnicodeDecodeError）。
    #    里面只有 ``RATE_LIMIT_ENABLED`` 一个开关，没有口令 ⇒ 允许入库。
    ".env.limiter",
}
ALLOWED_SUFFIXES = {
    ".example",
    ".template",
}

#: 文件名里出现这些词 ⇒ 疑似含密钥/口令。
#:
#: ⚠️ 只在**数据类扩展名**上生效 —— 文档（``.md``）与脚本（``.py`` / ``.sh``）
#:    名字里带 password / secret 是正常的（如
#:    ``scripts/reset_passwords.py``、``docs/.../PASSWORD_AND_REGISTRY_CHECK.md``），
#:    一刀切会把正常的代码与文档也拦下来 ⇒ 门禁被绕过（大家习惯性 --no-verify）。
SENSITIVE_NAME_TOKENS = (
    "password",
    "passwd",
    "secret",
    "credential",
)

#: 这些扩展名 = 装着数据的文件 ⇒ 与「疑似敏感名」组合时一律拦。
SENSITIVE_CONTENT_SUFFIXES = {
    ".txt",
    ".env",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".dat",
    ".csv",
    ".xml",
}

#: 加密文件与密钥/证书后缀 —— 一律拦（密文本身也是敏感资产）。
BLOCKED_SUFFIXES = {
    ".key",
    ".enc",
    ".pem",
    ".crt",
    ".p12",
    ".pfx",
}


def is_blocked(path: Path) -> bool:
    """这个文件该不该被拦下（不许进仓库）。

    判定顺序（后一条不覆盖前一条的"放行"）：

    1. 模板与样例外 ⇒ 放行（``.env.example`` / ``env.template`` / ``*.example``）；
    2. **``.env`` 家族** ⇒ 拦（``.env`` / ``.env.cleaned`` /
       ``.env.production.passwords.txt`` / ``.env.local`` …）；
    3. **疑似敏感名 + 数据类扩展名** ⇒ 拦（``xxx.passwords.txt`` / ``my_secrets.json`` …）；
    4. **加密文件 / 密钥证书后缀** ⇒ 拦（``.enc`` / ``.key`` / ``.pem`` …）。
    """
    name = path.name
    lower_name = name.lower()

    if lower_name in ALLOWED_BASENAMES:
        return False

    if any(lower_name.endswith(suffix) for suffix in ALLOWED_SUFFIXES):
        return False

    # 规则 2：.env 家族
    if lower_name == ".env" or lower_name.startswith(".env."):
        return True

    # 规则 3：疑似敏感名 + 数据类扩展名
    if path.suffix.lower() in SENSITIVE_CONTENT_SUFFIXES and any(
        token in lower_name for token in SENSITIVE_NAME_TOKENS
    ):
        return True

    # 规则 4：加密文件 / 密钥证书
    return path.suffix.lower() in BLOCKED_SUFFIXES


def staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [PROJECT_ROOT / path for path in paths]


def main() -> int:
    blocked: list[Path] = []

    for path in staged_files():
        if not path.exists() or not path.is_file():
            continue
        if is_blocked(path):
            blocked.append(path.relative_to(PROJECT_ROOT))

    if blocked:
        print("[FAIL] Sensitive files detected:")
        for path in sorted(blocked):
            print(f"  - {path}")
        print("[INFO] Remove or ignore these files before commit.")
        return 1

    print("[PASS] No blocked secret files detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

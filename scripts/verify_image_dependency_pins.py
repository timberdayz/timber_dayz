"""
校验已构建的后端镜像是否携带预期版本的依赖。

背景（v7.12.7 生产事故）：
    2026-11-03 发布 v7.12.7 后，生产 celery-worker 与 celery-beat 崩溃循环，
    定时任务（自动入库、低库存告警、数据库备份）停摆约 30 分钟。
    根因不是业务代码：旧 Dockerfile.backend 分两步安装依赖，根 requirements.txt 里
    `celery>=5.3.0` / `redis>=5.0.0` 是浮动范围，而 celery 的传递依赖 kombu
    没有被任何文件钉住 —— kombu 5.6.2（v7.12.6 构建当天解析到的最新版）
    -> 5.7.0（v7.12.7 构建当天上游刚好发版）。kombu 5.7.0 的 redis transport
    硬性要求 redis-py>=6.1.0，但 redis-py 被 backend/requirements.txt 钉在 5.0.1，
    于是 worker 启动即抛：
        kombu.exceptions.VersionMismatch: Redis transport requires redis-py
        versions 6.1.0 or later. You have 5.0.1
    pip 在安装期不报这个冲突，所以镜像构建一直是绿的，坏镜像一路推到了生产。

v7.12.9 的改造（依赖单一真相源 + 锁文件）：
    1. `requirements.lock.txt` 成为生产运行时依赖的**唯一真相源**：完整传递依赖
       闭包，全部用 `==` 钉死，生产镜像只安装它。基线由本脚本**从 lock 文件自动
       推导**，不再手工维护 CRITICAL_PACKAGES 列表（手抄就是下一个漂移源）。
    2. `requirements.txt` 只声明运行时**直接依赖**，同样全部 `==` 钉死；它与
       lock 文件必须逐包一致，本脚本做交叉校验。
    3. `backend/requirements.txt` 已删除 —— 它与根清单重复且互相矛盾（26 个包），
       其中 alembic 钉 1.12.1、根清单要求 >=1.13.0，镜像里实际装的是 1.20.1。
    4. `requirements-dev.txt` 承载开发/测试工具（pytest / black / testcontainers 等），
       **不进生产镜像**。

本脚本的作用：
    把"静默漂移"变成"构建失败"。构建完成后比对镜像内实际安装的版本与基线，
    不一致就 exit 1，让 CI 在推 CNB 镜像和执行生产部署之前就拦住。

用法：
    python scripts/verify_image_dependency_pins.py --image <镜像名或镜像ID>

基线维护约定：
    只有在明确接受某个依赖升级时才修改 `requirements.lock.txt`，并在同一次提交里
    说明原因（见 docs/guides/RELEASE_CHECKLIST.md）。本脚本的基线由该文件自动
    推导，因此升级只需改一处；lock 与 requirements.txt 不一致同样失败。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 生产运行时依赖的唯一真相源：完整传递依赖闭包，全部 == 钉死。
LOCK_FILE = PROJECT_ROOT / "requirements.lock.txt"

# 运行时直接依赖清单（只声明直接依赖，版本同样 == 钉死）。
RUNTIME_REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"

# 生产镜像的 Dockerfile：必须只安装 lock 文件。
DOCKERFILES = (
    PROJECT_ROOT / "Dockerfile.backend",
    PROJECT_ROOT / "Dockerfile.collection",
)

PIN_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*==\s*([^\s;#]+)"
)
# 任何非 `==` 的版本约束（浮动范围 / 兼容约束）都是漂移源，一律视为违规。
FLOATING_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(>=|<=|~=|>|<|!=)\s*([^\s;#]+)"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify pinned dependency versions inside a built backend image"
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Built backend image reference (name:tag or image id)",
    )
    return parser.parse_args(argv)


def parse_pins(path: Path) -> dict[str, str]:
    """读取一个 requirements 文件里的全部 `name==version` 钉版（忽略 extras 后缀）。"""
    pins: dict[str, str] = {}
    if not path.exists():
        return pins
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0]
        match = PIN_PATTERN.match(line)
        if match:
            pins[match.group(1).lower()] = match.group(3).strip()
    return pins


def parse_floating_specs(path: Path) -> list[str]:
    """返回文件里所有使用浮动范围（非 `==`）的依赖声明。"""
    offenders: list[str] = []
    if not path.exists():
        return offenders
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0]
        if not line.strip():
            continue
        match = FLOATING_PATTERN.match(line)
        if match:
            offenders.append(line.strip())
    return offenders


def load_lock_pins() -> dict[str, str]:
    """从 requirements.lock.txt 推导基线（自动推导，避免手抄错误）。"""
    return parse_pins(LOCK_FILE)


# 基线 = requirements.lock.txt 的全部钉版（v7.12.9 起自动推导，不再手抄）。
CRITICAL_PACKAGES: dict[str, str] = load_lock_pins()


def collect_declared_pins() -> tuple[dict[str, str], list[str]]:
    """交叉校验 requirements.txt 的直接依赖声明与 lock 文件是否一致。

    只比较 requirements.txt 里声明过的包：lock 文件里还有大量传递依赖
    （kombu / amqp / billiard / greenlet ...），它们不是项目直接依赖，
    不应该出现在 requirements.txt 里。
    """
    declared: dict[str, str] = parse_pins(RUNTIME_REQUIREMENTS_FILE)
    conflicts: list[str] = []
    baseline = load_lock_pins()

    for name, version in sorted(declared.items()):
        expected = baseline.get(name)
        if expected is None:
            conflicts.append(
                f"{name}: requirements.txt 声明了 {version}，但 requirements.lock.txt 里没有这个包"
            )
        elif expected != version:
            conflicts.append(
                f"{name}: requirements.txt 钉 {version}，requirements.lock.txt 钉 {expected}（两者需同步）"
            )
    return declared, conflicts


def check_dockerfiles() -> list[str]:
    """检查生产镜像的 Dockerfile：必须只安装 lock 文件，不允许二次安装。"""
    failures: list[str] = []
    for dockerfile in DOCKERFILES:
        if not dockerfile.exists():
            failures.append(f"{dockerfile.name}: 文件不存在")
            continue
        content = dockerfile.read_text(encoding="utf-8")
        name = dockerfile.name
        if "pip install -r requirements.lock.txt" not in content:
            failures.append(f"{name}: 未安装 requirements.lock.txt")
        for raw_line in content.splitlines():
            line = raw_line.split("#", 1)[0]
            if "pip install" not in line:
                continue
            if "-r requirements.lock.txt" in line:
                continue
            if "pip install --upgrade pip" in line:
                continue
            failures.append(f"{name}: 存在 lock 之外的依赖安装命令：{line.strip()}")
    return failures


def read_image_versions(image: str) -> dict[str, str]:
    """读取镜像内 pip 已安装的包版本。"""
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "pip",
            image,
            "list",
            "--format=freeze",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"failed to read packages from image {image!r}:\n{completed.stderr.strip()}"
        )
    versions: dict[str, str] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if "==" not in line:
            continue
        name, _, version = line.partition("==")
        versions[name.strip().lower()] = version.strip()
    return versions


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not LOCK_FILE.exists():
        print(f"[FAIL] 缺少依赖锁文件：{LOCK_FILE}")
        return 1

    baseline = load_lock_pins()
    if not baseline:
        print(f"[FAIL] 依赖锁文件没有任何钉版：{LOCK_FILE}")
        return 1

    declared, conflicts = collect_declared_pins()
    failures: list[str] = list(conflicts)
    failures.extend(check_dockerfiles())

    for path in (LOCK_FILE, RUNTIME_REQUIREMENTS_FILE):
        for offender in parse_floating_specs(path):
            failures.append(f"{path.name}: 存在浮动版本范围：{offender}")

    installed = read_image_versions(args.image)

    print(f"[dependency-pins] image: {args.image}")
    print(f"[dependency-pins] baseline: {LOCK_FILE.name} ({len(baseline)} 个钉版)")
    for name, expected in sorted(baseline.items()):
        actual = installed.get(name)
        status = "OK"
        if actual is None:
            failures.append(f"{name}: 镜像内未安装（期望 {expected}）")
            status = "MISSING"
        elif actual != expected:
            failures.append(f"{name}: 镜像内为 {actual}，期望 {expected}")
            status = "MISMATCH"
        elif declared.get(name) is not None and declared[name] != expected:
            failures.append(
                f"{name}: 依赖文件钉 {declared[name]}，基线为 {expected}（两者需同步）"
            )
            status = "BASELINE-DRIFT"
        print(f"  {name:<24} baseline={expected:<12} image={actual or '-':<12} {status}")

    # 镜像里出现 lock 之外的包 = 有人绕过锁文件装了东西，同样要拦住。
    for name in sorted(set(installed) - set(baseline)):
        failures.append(
            f"{name}: 镜像内为 {installed[name]}，但不在 requirements.lock.txt 中（锁外安装）"
        )
        print(f"  {name:<24} baseline={'-':<12} image={installed[name]:<12} EXTRA")

    if failures:
        print("[FAIL] 镜像依赖版本校验未通过：")
        for item in failures:
            print(f"  - {item}")
        print(
            "[HINT] 若这是有意接受的升级，请同步更新 requirements.lock.txt 与 "
            "requirements.txt 的钉版，并重跑本门禁；"
            "否则请把依赖钉死，避免随上游发版漂移。"
        )
        return 1

    print(
        f"[PASS] {len(baseline)} 个依赖版本与 {LOCK_FILE.name} 一致，"
        "镜像内无锁外依赖。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

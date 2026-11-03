"""
校验已构建的后端镜像是否携带预期版本的依赖。

背景（v7.12.7 生产事故）：
    2026-11-03 发布 v7.12.7 后，生产 celery-worker 与 celery-beat 崩溃循环，
    定时任务（自动入库、低库存告警、数据库备份）停摆约 30 分钟。
    根因不是业务代码：Dockerfile.backend 分两步安装依赖，根 requirements.txt 里
    `celery>=5.3.0` / `redis>=5.0.0` 是浮动范围，而 celery 的传递依赖 kombu
    没有被任何文件钉住 —— kombu 5.6.2（v7.12.6 构建当天解析到的最新版）
    -> 5.7.0（v7.12.7 构建当天上游刚好发版）。kombu 5.7.0 的 redis transport
    硬性要求 redis-py>=6.1.0，但 redis-py 被 backend/requirements.txt 钉在 5.0.1，
    于是 worker 启动即抛：
        kombu.exceptions.VersionMismatch: Redis transport requires redis-py
        versions 6.1.0 or later. You have 5.0.1
    pip 在安装期不报这个冲突，所以镜像构建一直是绿的，坏镜像一路推到了生产。

本脚本的作用：
    把"静默漂移"变成"构建失败"。构建完成后比对镜像内实际安装的版本与基线，
    不一致就 exit 1，让 CI 在推 CNB 镜像和执行生产部署之前就拦住。

用法：
    python scripts/verify_image_dependency_pins.py --image <镜像名或镜像ID>

基线维护约定：
    只有在明确接受某个依赖升级时才修改 CRITICAL_PACKAGES，并在同一次提交里
    说明原因（见 docs/guides/RELEASE_CHECKLIST.md）。本文件的基线必须与
    requirements.txt / backend/requirements.txt / Dockerfile.backend 中的钉版
    一致，脚本会交叉校验，不一致同样失败。

已知未覆盖项（见 RELEASE_CHECKLIST.md 的"依赖版本漂移"条目）：
    numpy / pandas / starlette / pydantic / sqlalchemy / playwright / alembic
    目前仍是浮动或分散在两份 requirements 里，尚未纳入本基线。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 基线 = v7.12.6 生产验证通过的组合（celery 那一组），叠加 v7.12.7 上线后
# 核对过的 API 进程管理器版本。OSV 对 kombu 5.6.2 / redis 5.0.1 无任何漏洞公告。
CRITICAL_PACKAGES: dict[str, str] = {
    # Celery 全链路：v7.12.7 事故点，必须钉死
    "celery": "5.3.4",
    "kombu": "5.6.2",
    "amqp": "5.4.1",
    "billiard": "4.3.1",
    "redis": "5.0.1",
    # API 进程管理器：漂移会直接打挂整个 API，同样必须钉死
    "gunicorn": "26.2.0",
    "uvicorn": "0.54.0",
}

# 钉版来源文件：包名 -> 文件相对路径（用于交叉校验）
REQUIREMENT_FILES = (
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "backend" / "requirements.txt",
)

PIN_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*==\s*([^\s;#]+)"
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


def parse_dockerfile_pins() -> dict[str, str]:
    """读取 Dockerfile.backend 里 `pip install` 命令上的钉版。"""
    dockerfile = PROJECT_ROOT / "Dockerfile.backend"
    pins: dict[str, str] = {}
    if not dockerfile.exists():
        return pins
    for raw_line in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0]
        if "pip install" not in line:
            continue
        for match in re.finditer(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^\s\\]+)", line
        ):
            pins[match.group(1).lower()] = match.group(3).strip()
    return pins


def collect_declared_pins() -> tuple[dict[str, str], list[str]]:
    """汇总三处声明的钉版，并报告关键包之间互相冲突的项。

    只检查 CRITICAL_PACKAGES 覆盖的包：仓库里本来就存在若干历史遗留的版本分歧
    （fastapi / alembic / numpy 等），那些不在本次门禁范围内，不应让门禁永远失败。
    """
    declared: dict[str, str] = {}
    conflicts: list[str] = []
    sources: list[tuple[str, Path]] = [
        (str(path.relative_to(PROJECT_ROOT)), path) for path in REQUIREMENT_FILES
    ]
    for label, path in sources:
        for name, version in parse_pins(path).items():
            if name not in CRITICAL_PACKAGES:
                continue
            existing = declared.get(name)
            if existing is not None and existing != version:
                conflicts.append(
                    f"{name}: {label} 钉 {version}，此前已声明 {existing}"
                )
                continue
            declared[name] = version
    for name, version in parse_dockerfile_pins().items():
        if name not in CRITICAL_PACKAGES:
            continue
        existing = declared.get(name)
        if existing is not None and existing != version:
            conflicts.append(
                f"{name}: Dockerfile.backend 钉 {version}，此前已声明 {existing}"
            )
            continue
        declared[name] = version
    return declared, conflicts


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

    declared, conflicts = collect_declared_pins()
    installed = read_image_versions(args.image)

    failures: list[str] = []
    if conflicts:
        failures.extend(conflicts)

    print(f"[dependency-pins] image: {args.image}")
    for name, expected in sorted(CRITICAL_PACKAGES.items()):
        actual = installed.get(name)
        declared_version = declared.get(name)
        status = "OK"
        if actual is None:
            failures.append(f"{name}: 镜像内未安装（期望 {expected}）")
            status = "MISSING"
        elif actual != expected:
            failures.append(f"{name}: 镜像内为 {actual}，期望 {expected}")
            status = "MISMATCH"
        elif declared_version is not None and declared_version != expected:
            failures.append(
                f"{name}: 依赖文件钉 {declared_version}，基线为 {expected}（两者需同步）"
            )
            status = "BASELINE-DRIFT"
        print(f"  {name:<12} baseline={expected:<10} image={actual or '-':<10} {status}")

    if failures:
        print("[FAIL] 镜像依赖版本校验未通过：")
        for item in failures:
            print(f"  - {item}")
        print(
            "[HINT] 若这是有意接受的升级，请同步更新 "
            "scripts/verify_image_dependency_pins.py 的 CRITICAL_PACKAGES 与 "
            "requirements.txt / backend/requirements.txt 的钉版；"
            "否则请把依赖钉死，避免随上游发版漂移。"
        )
        return 1

    print(f"[PASS] {len(CRITICAL_PACKAGES)} 个关键依赖版本与基线一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

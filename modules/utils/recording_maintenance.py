from __future__ import annotations

"""录制与诊断文件维护工具

策略：
- 绝不删除，仅归档到 backups/ 目录
- 按平台/数据类型/时间排序，保留每类最近 N 个，其余归档
- 支持 dry_run 显示计划

目录：
- 录制脚本：.diag/recipes/*.json 或 temp/development/recordings/*.py（可扩展）
- 诊断快照：输出目录下的 .diag/*
"""
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple
import shutil
import time
from datetime import datetime, timedelta
import zipfile


@dataclass
class RetentionPolicy:
    per_category_keep: int = 10  # 每类（平台/数据类型）保留最近N个
    dry_run: bool = False


class RecordingMaintenance:
    def __init__(self, project_root: Path | None = None, policy: RetentionPolicy | None = None, platform_filter: str | None = None) -> None:
        self.root = project_root or Path.cwd()
        self.policy = policy or RetentionPolicy()
        self.platform_filter = (platform_filter or "").lower() or None
        self.backups = self.root / "backups" / time.strftime("%Y%m%d_recordings_archive")
        self.backups.mkdir(parents=True, exist_ok=True)
        self.actions: list[str] = []  # 记录计划/实际归档动作
        # 从配置读取默认策略
        try:
            from modules.core.config import get_config_value
            keep = get_config_value('simple_config', 'collection.maintenance.per_category_keep', self.policy.per_category_keep)
            dry = get_config_value('simple_config', 'collection.maintenance.dry_run_default', True)
            if isinstance(keep, int):
                self.policy.per_category_keep = keep
            if isinstance(dry, bool):
                self.policy.dry_run = dry
        except Exception:
            pass

    def _list_recipe_files(self) -> List[Path]:
        candidates = []
        # 配方目录
        for p in self.root.rglob(".diag/recipes/*.json"):
            candidates.append(p)
        # 录制脚本（可选目录，若不存在忽略）
        rec_dir = self.root / "temp" / "development" / "recordings"
        if rec_dir.exists():
            for p in rec_dir.rglob("*.py"):
                candidates.append(p)
        return candidates

    def _list_diag_dirs(self) -> List[Path]:
        dirs = []
        for p in (self.root / "temp" / "outputs").rglob(".diag"):
            if p.is_dir():
                dirs.append(p)
        return dirs

    def _list_media_dirs(self) -> List[Path]:
        """列出媒体文件目录（截图/录屏）"""
        dirs = []
        for sub in ["temp/media", "temp/outputs", "temp/logs"]:
            base = self.root / sub
            if base.exists():
                dirs.append(base)
        return dirs

    def _list_recording_files(self) -> Tuple[List[Path], List[Path]]:
        """返回 (py_list, pyc_list) for temp/recordings/**/*"""
        py_list: List[Path] = []
        pyc_list: List[Path] = []
        base = self.root / "temp" / "recordings"
        if not base.exists():
            return py_list, pyc_list
        for p in base.rglob("*.py"):
            py_list.append(p)
        for p in base.rglob("__pycache__/*.pyc"):
            pyc_list.append(p)
        return py_list, pyc_list

    def _category_key(self, p: Path) -> Tuple[str, str]:
        # 平台过滤（若设置）
        if self.platform_filter:
            try:
                if self.platform_filter not in [s.lower() for s in p.parts]:
                    return ("__skip__", "__skip__")
            except Exception:
                pass
        # 简化分类：平台 + 数据类型（从路径中提取）
        path_str = str(p.as_posix())
        platform = "unknown"
        data_type = "unknown"
        # 例如 temp/outputs/shopee/<account>/<shop>/<data_type>/...
        parts = p.parts
        if "outputs" in parts:
            try:
                idx = parts.index("outputs")
                platform = parts[idx + 1]
                data_type = parts[idx + 4]
            except Exception:
                pass
        return platform, data_type

    def enforce(self) -> None:
        # 从配置读取保留天数
        try:
            from modules.core.config import get_config_value
            retention = get_config_value('simple_config', 'collection.maintenance.retention_days', {}) or {}
            dev_days = int(retention.get('development', 7))
            out_days = int(retention.get('outputs', 30))
            media_days = int(retention.get('media', 90))
            log_days = int(retention.get('logs', 180))
        except Exception:
            dev_days, out_days, media_days, log_days = 7, 30, 90, 180

        now = datetime.now()
        def older_than(p: Path, days: int) -> bool:
            try:
                return (now - datetime.fromtimestamp(p.stat().st_mtime)) > timedelta(days=days)
            except Exception:
                return False

        # 处理配方文件
        recipes = self._list_recipe_files()
        grouped: dict[Tuple[str, str], List[Path]] = {}
        for f in recipes:
            key = self._category_key(f)
            if key == ("__skip__", "__skip__"):
                continue
            grouped.setdefault(key, []).append(f)

        for key, files in grouped.items():
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            keep = files[: self.policy.per_category_keep]
            archive = files[self.policy.per_category_keep :]
            if archive:
                for f in archive:
                    rel = f.relative_to(self.root)
                    target_dir = self.backups / rel.parent
                    target_dir.mkdir(parents=True, exist_ok=True)
                    plan = f"ARCHIVE {f} -> {target_dir / f.name}"
                    if self.policy.dry_run:
                        print(f"[DRY_RUN] {plan}")
                        self.actions.append(f"DRY_RUN {plan}")
                    else:
                        shutil.move(str(f), str(target_dir / f.name))
                        self.actions.append(plan)

        # 处理诊断目录（.diag）
        diag_dirs = self._list_diag_dirs()
        # 同平台/数据类型下，按父目录时间排序归档多余
        grouped_dirs: dict[Tuple[str, str], List[Path]] = {}
        for d in diag_dirs:
            key = self._category_key(d)
            if key == ("__skip__", "__skip__"):
                continue
            grouped_dirs.setdefault(key, []).append(d.parent)
        for key, parents in grouped_dirs.items():
            unique_parents = sorted(set(parents), key=lambda x: x.stat().st_mtime, reverse=True)
            keep = unique_parents[: self.policy.per_category_keep]
            archive = unique_parents[self.policy.per_category_keep :]
            for parent in archive:
                rel = parent.relative_to(self.root)
                target_dir = self.backups / rel
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                plan = f"ARCHIVE DIR {parent} -> {target_dir}"
                if self.policy.dry_run:
                    print(f"[DRY_RUN] {plan}")
                    self.actions.append(f"DRY_RUN {plan}")
                else:
                    shutil.move(str(parent), str(target_dir))
                    self.actions.append(plan)

        # 处理录制脚本（temp/recordings）：按类别（平台/类型）保留 N 个，其余归档
        py_list, pyc_list = self._list_recording_files()
        def _rec_key(p: Path) -> Tuple[str, str, str]:
            # 平台/账号或店铺/类型(login|complete|collection_*|other)
            parts = p.parts
            platform = parts[parts.index('recordings') + 1] if 'recordings' in parts else 'unknown'
            name = p.stem
            # 类型识别
            if 'login' in name:
                kind = 'login'
            elif 'complete' in name:
                kind = 'complete'
            elif 'collection_' in name:
                kind = name.split('collection_')[1].split('_')[0]
                kind = f'collection_{kind}'
            else:
                kind = 'other'
            # 账号/店铺提取（尽力从前缀取一段）
            account = name.split('_')[0]
            return platform, kind, account
        grouped_rec: dict[Tuple[str, str, str], List[Path]] = {}
        for f in py_list:
            key = _rec_key(f)
            grouped_rec.setdefault(key, []).append(f)
        for key, files in grouped_rec.items():
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            archive = files[self.policy.per_category_keep :]
            for f in archive:
                rel = f.relative_to(self.root)
                target_dir = self.backups / rel.parent
                target_dir.mkdir(parents=True, exist_ok=True)
                plan = f"ARCHIVE RECORDING {f} -> {target_dir / f.name}"
                if self.policy.dry_run:
                    print(f"[DRY_RUN] {plan}")
                    self.actions.append(f"DRY_RUN {plan}")
                else:
                    shutil.move(str(f), str(target_dir / f.name))
                    self.actions.append(plan)
        # __pycache__ 归档
        for f in pyc_list:
            rel = f.relative_to(self.root)
            target_dir = self.backups / rel.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            plan = f"ARCHIVE PYC {f} -> {target_dir / f.name}"
            if self.policy.dry_run:
                print(f"[DRY_RUN] {plan}")
                self.actions.append(f"DRY_RUN {plan}")
            else:
                shutil.move(str(f), str(target_dir / f.name))
                self.actions.append(plan)

        # 处理媒体/日志类大文件目录（按天数阈值归档）
        for base in self._list_media_dirs():
            for p in base.rglob("*"):
                try:
                    if not p.is_file():
                        continue
                    rel = p.relative_to(self.root)
                    days = media_days
                    if "/logs/" in rel.as_posix():
                        days = log_days
                    elif "/development/" in rel.as_posix():
                        days = dev_days
                    elif "/outputs/" in rel.as_posix():
                        days = out_days
                    if older_than(p, days):
                        target = self.backups / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        plan = f"ARCHIVE OLD {p} -> {target}"
                        if self.policy.dry_run:
                            print(f"[DRY_RUN] {plan}")
                            self.actions.append(f"DRY_RUN {plan}")
                        else:
                            shutil.move(str(p), str(target))
                            self.actions.append(plan)
                except Exception:
                    continue

        # 备份轮转：压缩旧的 backups/* 子目录（按配置）
        try:
            from modules.core.config import get_config_value
            backup_cfg = get_config_value('simple_config', 'collection.maintenance.backups', {}) or {}
            rotate_days = int(backup_cfg.get('days', 90))
            enable_zip = bool(backup_cfg.get('compress', True))
            purge_after_zip = bool(backup_cfg.get('purge_after_zip', False))
        except Exception:
            rotate_days, enable_zip, purge_after_zip = 90, True, False

        # 允许 CLI 覆盖（仅当前运行生效）
        override_purge = getattr(self, "_override_purge", None)
        if override_purge is True:
            purge_after_zip = True
        override_rotate = getattr(self, "_override_rotate_days", None)
        if isinstance(override_rotate, int) and override_rotate > 0:
            rotate_days = override_rotate

        backups_root = self.root / "backups"
        for sub in backups_root.iterdir() if backups_root.exists() else []:
            try:
                if not sub.is_dir():
                    continue
                if not older_than(sub, rotate_days):
                    continue
                if enable_zip:
                    zip_path = backups_root / f"{sub.name}.zip"
                    plan = f"ZIP {sub} -> {zip_path}"
                    if self.policy.dry_run:
                        print(f"[DRY_RUN] {plan}")
                        self.actions.append(f"DRY_RUN {plan}")
                    else:
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for f in sub.rglob('*'):
                                if f.is_file():
                                    zf.write(f, f.relative_to(backups_root))
                        self.actions.append(plan)
                        if purge_after_zip:
                            shutil.rmtree(sub, ignore_errors=True)
                            self.actions.append(f"PURGE {sub}")
                else:
                    # 仅报告可压缩项
                    plan = f"ROTATE ELIGIBLE {sub} (older than {rotate_days}d)"
                    print(f"[DRY_RUN] {plan}")
                    self.actions.append(f"DRY_RUN {plan}")
            except Exception:
                continue


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Recordings/Diagnostics maintenance (archive-only)")
    parser.add_argument("--platform", help="filter platform (e.g., shopee, miaoshou, tiktok)", default=None)
    parser.add_argument("--keep", type=int, help="per-category keep count (override config)", default=None)
    parser.add_argument("--apply", action="store_true", help="apply changes (disable dry-run)")
    parser.add_argument("--purge-plan", action="store_true", help="plan purge-after-zip (DRY-RUN unless --apply)")
    parser.add_argument("--rotate-days", type=int, help="override backups rotate days for this run", default=None)
    args = parser.parse_args()

    tool = RecordingMaintenance(platform_filter=args.platform)
    if args.keep is not None:
        tool.policy.per_category_keep = args.keep
    if args.apply:
        tool.policy.dry_run = False
    if args.purge_plan:
        setattr(tool, "_override_purge", True)
    if args.rotate_days is not None:
        setattr(tool, "_override_rotate_days", int(args.rotate_days))

    # 统计归档前容量
    def _dir_size(p: Path) -> int:
        total = 0
        if p.exists():
            for f in p.rglob("*"):
                try:
                    if f.is_file():
                        total += f.stat().st_size
                except Exception:
                    pass
        return total

    outputs_dir = tool.root / "temp" / "outputs"
    before_size = _dir_size(outputs_dir)

    tool.enforce()

    after_size = _dir_size(outputs_dir)
    saved = before_size - after_size if before_size >= after_size else 0
    mode = "APPLY" if not tool.policy.dry_run else "DRY-RUN"
    print(f"[OK] 维护完成 [{mode}]：归档前 {before_size/1024/1024:.2f} MB，归档后 {after_size/1024/1024:.2f} MB，表观释放 {saved/1024/1024:.2f} MB（移动至 backups）")

    # 写出报告
    try:
        reports_dir = tool.root / "temp" / "logs" / "maintenance"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        report = reports_dir / f"{ts}_recordings_archive_report.txt"
        report.write_text(
            "\n".join([
                f"Mode: {mode}",
                f"Before: {before_size} bytes",
                f"After: {after_size} bytes",
                f"Saved: {saved} bytes",
                "",
                "Actions:",
                *tool.actions,
            ]),
            encoding="utf-8"
        )
        print(f"[NOTE] 报告已生成: {report}")
    except Exception:
        pass

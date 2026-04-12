from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from modules.components.export.base import build_standard_output_root


_ALLOWED_DOWNLOAD_SUFFIXES = {".xlsx", ".xls", ".csv", ".zip"}


def _candidate_scan_roots(ctx: Any, out_root: Path) -> list[Path]:
    cfg = (getattr(ctx, "config", None) or {}) if ctx is not None else {}
    roots: list[Path] = [out_root]

    configured_root = str(cfg.get("downloads_path") or "").strip()
    if configured_root:
        candidate = Path(configured_root)
        if candidate not in roots:
            roots.append(candidate)
    return roots


def _snapshot_files(roots: Iterable[Path]) -> set[str]:
    snapshot: set[str] = set()
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            for child in root.iterdir():
                if child.is_file():
                    snapshot.add(str(child.resolve()))
        except Exception:
            continue
    return snapshot


def _filename_matches_hints(path: Path, filename_hints: tuple[str, ...]) -> bool:
    if not filename_hints:
        return True
    name = path.name.lower()
    return any(str(hint or "").strip().lower() in name for hint in filename_hints)


def _sorted_recent_candidates(
    *,
    roots: Iterable[Path],
    seen_paths: set[str],
    started_at: float,
    filename_hints: tuple[str, ...],
) -> list[Path]:
    candidates: list[Path] = []
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            for child in root.iterdir():
                if not child.is_file():
                    continue
                if str(child.resolve()) in seen_paths:
                    continue
                if child.suffix.lower() not in _ALLOWED_DOWNLOAD_SUFFIXES:
                    continue
                try:
                    if child.stat().st_size <= 0:
                        continue
                except OSError:
                    continue
                if not _filename_matches_hints(child, filename_hints):
                    continue
                candidates.append(child)
        except Exception:
            continue
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)


def _target_download_path(out_root: Path, suggested_filename: str) -> Path:
    candidate = out_root / suggested_filename
    if not candidate.exists():
        return candidate

    stem = Path(suggested_filename).stem or "download"
    suffix = "".join(Path(suggested_filename).suffixes) or ".xlsx"
    index = 1
    while True:
        retry_candidate = out_root / f"{stem}-{index}{suffix}"
        if not retry_candidate.exists():
            return retry_candidate
        index += 1


async def _save_download_object(
    *,
    download: Any,
    out_root: Path,
    suggested_filename: str,
) -> str | None:
    target = _target_download_path(out_root, suggested_filename)
    try:
        await download.save_as(str(target))
    except Exception:
        return None
    try:
        if not target.exists():
            return None
        if target.stat().st_size <= 0:
            return None
    except OSError:
        return None
    return str(target)


def _adopt_downloaded_file(
    *,
    found_file: Path,
    out_root: Path,
) -> str | None:
    try:
        if not found_file.exists() or found_file.stat().st_size <= 0:
            return None
    except OSError:
        return None

    if found_file.parent == out_root:
        return str(found_file)

    target = _target_download_path(out_root, found_file.name)
    try:
        shutil.copy2(found_file, target)
    except Exception:
        return None

    try:
        if not target.exists() or target.stat().st_size <= 0:
            return None
    except OSError:
        return None
    return str(target)


async def reconcile_downloaded_file(
    *,
    ctx: Any,
    data_type: str,
    granularity: str,
    subtype: str | None = None,
    started_at: float,
    seen_paths: set[str],
    timeout_ms: int = 12000,
    poll_ms: int = 500,
    filename_hints: tuple[str, ...] = (),
) -> str | None:
    out_root = build_standard_output_root(
        ctx,
        data_type=data_type,
        granularity=granularity,
        subtype=subtype,
    )
    out_root.mkdir(parents=True, exist_ok=True)
    roots = _candidate_scan_roots(ctx, out_root)

    waited = 0
    while waited <= timeout_ms:
        recent = _sorted_recent_candidates(
            roots=roots,
            seen_paths=seen_paths,
            started_at=started_at,
            filename_hints=filename_hints,
        )
        if recent:
            adopted = _adopt_downloaded_file(found_file=recent[0], out_root=out_root)
            if adopted:
                return adopted
        await asyncio.sleep(poll_ms / 1000)
        waited += poll_ms
    return None


async def capture_direct_download_artifact(
    *,
    page: Any,
    click_action: Callable[[], Awaitable[Any]],
    ctx: Any,
    data_type: str,
    granularity: str,
    subtype: str | None = None,
    timeout_ms: int = 10000,
    reconcile_timeout_ms: int = 12000,
    filename_hints: tuple[str, ...] = (),
    suggested_filename: str,
) -> str | None:
    out_root = build_standard_output_root(
        ctx,
        data_type=data_type,
        granularity=granularity,
        subtype=subtype,
    )
    out_root.mkdir(parents=True, exist_ok=True)

    roots = _candidate_scan_roots(ctx, out_root)
    seen_paths = _snapshot_files(roots)
    started_at = time.time()

    context_waiter: asyncio.Task[Any] | None = None
    context = getattr(page, "context", None)
    if context is not None and hasattr(context, "wait_for_event"):
        try:
            context_waiter = asyncio.create_task(
                context.wait_for_event("download", timeout=timeout_ms)
            )
        except Exception:
            context_waiter = None

    clicked = False
    download = None
    try:
        if hasattr(page, "expect_download"):
            try:
                async with page.expect_download(timeout=timeout_ms) as download_info:
                    await click_action()
                    clicked = True
                download = await download_info.value
            except Exception:
                download = None
        if not clicked:
            await click_action()
            clicked = True
    finally:
        if download is None and context_waiter is not None:
            try:
                download = await context_waiter
            except Exception:
                download = None
        elif context_waiter is not None and not context_waiter.done():
            context_waiter.cancel()

    if download is not None:
        persisted = await _save_download_object(
            download=download,
            out_root=out_root,
            suggested_filename=getattr(download, "suggested_filename", None) or suggested_filename,
        )
        if persisted:
            return persisted

    return await reconcile_downloaded_file(
        ctx=ctx,
        data_type=data_type,
        granularity=granularity,
        subtype=subtype,
        started_at=started_at,
        seen_paths=seen_paths,
        timeout_ms=reconcile_timeout_ms,
        filename_hints=filename_hints,
    )

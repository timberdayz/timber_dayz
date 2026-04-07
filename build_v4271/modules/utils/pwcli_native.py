from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parents[2]
PWCLI_ROOT = REPO_ROOT / "output" / "playwright" / ".pwcli_native"
SESSIONS_DIR = PWCLI_ROOT / "sessions"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
SUPPORTED_PLATFORM_PREFIXES = {"miaoshou", "shopee", "tiktok"}

CONSOLE_INIT_SCRIPT = """
(() => {
  if (window.__pwcliConsoleInstalled) return;
  window.__pwcliConsoleInstalled = true;
  window.__pwcliConsoleBuffer = window.__pwcliConsoleBuffer || [];
  const levels = ['debug', 'log', 'info', 'warn', 'error'];
  for (const level of levels) {
    const original = console[level] ? console[level].bind(console) : null;
    if (!original) continue;
    console[level] = (...args) => {
      try {
        const text = args.map((value) => {
          if (typeof value === 'string') return value;
          try {
            return JSON.stringify(value);
          } catch (error) {
            return String(value);
          }
        }).join(' ');
        window.__pwcliConsoleBuffer.push({ level, text, ts: Date.now() });
        if (window.__pwcliConsoleBuffer.length > 300) {
          window.__pwcliConsoleBuffer.splice(0, window.__pwcliConsoleBuffer.length - 300);
        }
      } catch (error) {
      }
      return original(...args);
    };
  }
})();
"""

SNAPSHOT_SCRIPT = """
(() => {
  const items = [];
  const seen = new Set();
  const roleMap = { button: 'button', a: 'link', textarea: 'textbox', select: 'combobox', label: 'label' };
  const isVisible = (element) => {
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const text = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const xpath = (element) => {
    if (element.id) return `//*[@id=${JSON.stringify(element.id)}]`;
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === current.tagName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${current.tagName.toLowerCase()}[${index}]`);
      current = current.parentElement;
    }
    return '/' + parts.join('/');
  };
  for (const element of Array.from(document.querySelectorAll('*'))) {
    if (!(element instanceof HTMLElement) || !isVisible(element)) continue;
    const tag = element.tagName.toLowerCase();
    const role = element.getAttribute('role') || roleMap[tag] || '';
    const value = text(
      element.getAttribute('aria-label') ||
      element.getAttribute('placeholder') ||
      element.innerText ||
      element.textContent ||
      element.getAttribute('title') ||
      element.value ||
      ''
    );
    const clickable =
      ['button', 'a', 'input', 'textarea', 'select'].includes(tag) ||
      ['button', 'link', 'textbox', 'combobox', 'menuitem', 'tab'].includes(role) ||
      element.hasAttribute('onclick') ||
      window.getComputedStyle(element).cursor === 'pointer';
    const semanticText = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'label', 'p'].includes(tag);
    if ((!clickable && !semanticText) || !value) continue;
    const path = xpath(element);
    if (seen.has(path)) continue;
    seen.add(path);
    items.push({
      tag,
      role,
      text: value,
      placeholder: element.getAttribute('placeholder') || '',
      type: element.getAttribute('type') || '',
      xpath: path
    });
    if (items.length >= 240) break;
  }
  return items;
})();
"""


def ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_token(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in str(value or "").strip())
    return cleaned.strip("-_") or "default"


def session_manager_safe_token(value: str) -> str:
    text = str(value or "").strip()
    safe = "".join(ch for ch in text if ch.isalnum() or ch in ("_", "-"))
    return safe or "default"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def resolve_session_platform(session: str) -> str | None:
    token = sanitize_token(session).split("-", 1)[0]
    return token if token in SUPPORTED_PLATFORM_PREFIXES else None


def output_playwright_root() -> Path:
    return REPO_ROOT / "output" / "playwright"


def platform_profile_root(platform: str) -> Path:
    return output_playwright_root() / "profiles" / platform


def platform_state_path(platform: str) -> Path:
    return output_playwright_root() / "state" / f"{platform}.json"


def runtime_account_profile_dir(platform: str, account_id: str) -> Path:
    return REPO_ROOT / "profiles" / session_manager_safe_token(platform.lower()) / session_manager_safe_token(account_id)


def runtime_account_state_path(platform: str, account_id: str) -> Path:
    return (
        REPO_ROOT
        / "data"
        / "sessions"
        / platform.lower()
        / str(account_id).strip()
        / "storage_state.json"
    )


def resolve_default_profile_dir(session: str, account_id: str | None) -> Path | None:
    platform = resolve_session_platform(session)
    if not platform:
        return None
    if account_id:
        return runtime_account_profile_dir(platform, account_id)
    return platform_profile_root(platform).resolve()


def resolve_default_state_config(session: str, account_id: str | None) -> dict[str, Any]:
    platform = resolve_session_platform(session)
    if not platform:
        return {}
    if account_id:
        return {
            "platform": platform,
            "account_id": account_id,
            "default_state_mode": "session_manager",
            "default_state_path": str(runtime_account_state_path(platform, account_id)),
        }
    return {
        "platform": platform,
        "account_id": None,
        "default_state_mode": "raw_json",
        "default_state_path": str(platform_state_path(platform).resolve()),
    }


def load_storage_state_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("storage_state"), dict):
        return payload["storage_state"]
    return payload


def _write_raw_storage_state(path: Path, storage_state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_default_storage_state_from_context(metadata: dict[str, Any], context) -> None:
    state_path = str(metadata.get("default_state_path") or "").strip()
    state_mode = str(metadata.get("default_state_mode") or "").strip().lower()
    if not state_path or not state_mode:
        return

    storage_state = context.storage_state()
    if state_mode == "session_manager":
        from modules.utils.sessions.session_manager import SessionManager

        platform = str(metadata.get("platform") or "").strip().lower()
        account_id = str(metadata.get("account_id") or "").strip()
        if platform and account_id:
            SessionManager(base_path=REPO_ROOT / "data" / "sessions").save_session(platform, account_id, storage_state)
        return

    _write_raw_storage_state(Path(state_path), storage_state)


def _apply_storage_state_payload(context, metadata: dict[str, Any], payload: dict[str, Any]) -> None:
    cookies = payload.get("cookies", [])
    if cookies:
        context.add_cookies(cookies)
    for origin in payload.get("origins", []):
        local_storage = origin.get("localStorage", [])
        if not local_storage:
            continue
        temp_page = context.new_page()
        try:
            temp_page.goto(origin["origin"], wait_until="domcontentloaded", timeout=60000)
            try:
                temp_page.evaluate(
                    "(entries) => { for (const item of entries) { localStorage.setItem(item.name, item.value); } }",
                    local_storage,
                )
            except Exception as exc:
                if not _is_navigation_context_error(exc):
                    raise
                temp_page.goto(origin["origin"], wait_until="domcontentloaded", timeout=60000)
                temp_page.evaluate(
                    "(entries) => { for (const item of entries) { localStorage.setItem(item.name, item.value); } }",
                    local_storage,
                )
        finally:
            temp_page.close()
    ensure_page(context, metadata)


def maybe_load_default_storage_state(context, metadata: dict[str, Any]) -> bool:
    state_path = str(metadata.get("default_state_path") or "").strip()
    if not state_path:
        return False
    path = Path(state_path)
    if not path.exists():
        return False
    try:
        payload = load_storage_state_payload(path)
    except json.JSONDecodeError:
        print(f"Warning: ignoring invalid storage state file: {path}", file=sys.stderr)
        return False
    _apply_storage_state_payload(context, metadata, payload)
    return True


def session_name_from_argv(argv: list[str]) -> tuple[str, list[str]]:
    session = os.getenv("PLAYWRIGHT_CLI_SESSION", "default")
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg in ("-s", "--session"):
            session = argv[idx + 1]
            idx += 2
            continue
        if arg.startswith("-s="):
            session = arg.split("=", 1)[1]
            idx += 1
            continue
        if arg.startswith("--session="):
            session = arg.split("=", 1)[1]
            idx += 1
            continue
        return sanitize_token(session), argv[idx:]
    return sanitize_token(session), []


def session_dir(session: str) -> Path:
    return SESSIONS_DIR / sanitize_token(session)


def session_meta_path(session: str) -> Path:
    return session_dir(session) / "session.json"


def session_snapshot_path(session: str) -> Path:
    return session_dir(session) / "last_snapshot.json"


def load_session(session: str) -> dict[str, Any] | None:
    path = session_meta_path(session)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(session: str, metadata: dict[str, Any]) -> None:
    directory = session_dir(session)
    directory.mkdir(parents=True, exist_ok=True)
    session_meta_path(session).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def remove_session(session: str) -> None:
    session_meta_path(session).unlink(missing_ok=True)


def bundled_chromium_path() -> str:
    with sync_playwright() as playwright:
        return playwright.chromium.executable_path


def is_process_alive(pid: int) -> bool:
    result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False)
    return str(pid) in result.stdout


def kill_process(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True, text=True, check=False)


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_debug_port(port: int, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for browser debug endpoint on port {port}")


def connect_browser(metadata: dict[str, Any]):
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{metadata['port']}")
    return playwright, browser


def ensure_context(browser):
    return browser.contexts[0]


def ensure_page(context, metadata: dict[str, Any]):
    if not context.pages:
        page = context.new_page()
        metadata["current_page_index"] = 0
        return page
    index = int(metadata.get("current_page_index", 0) or 0)
    index = min(max(index, 0), len(context.pages) - 1)
    metadata["current_page_index"] = index
    return context.pages[index]


def install_console_buffer(context, page) -> None:
    context.add_init_script(CONSOLE_INIT_SCRIPT)
    try:
        page.evaluate(CONSOLE_INIT_SCRIPT)
    except Exception:
        pass


def _is_navigation_context_error(error: Exception) -> bool:
    return "Execution context was destroyed" in str(error)


def _safe_page_title(page) -> str:
    try:
        return page.title()
    except Exception as exc:
        if _is_navigation_context_error(exc):
            return "(unavailable during navigation)"
        return "(unavailable)"


def _safe_console_entries(page) -> list[dict[str, Any]]:
    try:
        entries = page.evaluate("() => window.__pwcliConsoleBuffer || []")
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def page_summary(page) -> str:
    entries = _safe_console_entries(page)
    errors = sum(1 for item in entries if item.get("level") == "error")
    warnings = sum(1 for item in entries if item.get("level") == "warn")
    lines = [
        "### Page",
        f"- Page URL: {page.url}",
        f"- Page Title: {_safe_page_title(page)}",
    ]
    if errors or warnings:
        lines.append(f"- Console: {errors} errors, {warnings} warnings")
    return "\n".join(lines)


def classify(entry: dict[str, Any]) -> str:
    if entry.get("role"):
        return str(entry["role"])
    if entry.get("tag") == "input":
        if str(entry.get("type") or "").lower() in {"checkbox", "radio"}:
            return str(entry["type"]).lower()
        return "textbox"
    if entry.get("tag") == "textarea":
        return "textbox"
    if entry.get("tag") == "select":
        return "combobox"
    return str(entry.get("tag") or "element")


def display_name(entry: dict[str, Any]) -> str:
    return str(entry.get("text") or entry.get("placeholder") or "").strip()


def format_snapshot(page, session: str) -> str:
    try:
        entries = page.evaluate(SNAPSHOT_SCRIPT)
    except Exception:
        entries = []
    refs = {}
    for index, entry in enumerate(entries, start=1):
        refs[f"e{index}"] = entry
    session_snapshot_path(session).write_text(
        json.dumps({"refs": refs, "generated_at": timestamp()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [page_summary(page), "### Snapshot"]
    for ref, entry in refs.items():
        name = display_name(entry)
        kind = classify(entry)
        if name:
            lines.append(f'- {kind} "{name}" [ref={ref}]')
        else:
            lines.append(f"- {kind} [ref={ref}]")
    return "\n".join(lines)


def read_ref(session: str, ref: str) -> dict[str, Any]:
    path = session_snapshot_path(session)
    if not path.exists():
        raise SystemExit("No snapshot refs available. Run `pwcli snapshot` first.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    refs = payload.get("refs", {})
    if ref not in refs:
        raise SystemExit(f"Unknown ref '{ref}'. Run `pwcli snapshot` again.")
    return refs[ref]


def locator_for_ref(page, session: str, ref: str):
    entry = read_ref(session, ref)
    return page.locator(f"xpath={entry['xpath']}").first


def launch_browser(
    session: str,
    url: str | None,
    headed: bool,
    profile_dir: Path | None,
    *,
    account_id: str | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    user_data_dir = profile_dir or (session_dir(session) / "profile")
    profile_explicit = profile_dir is not None
    if user_data_dir.exists() and not profile_explicit:
        shutil.rmtree(user_data_dir, ignore_errors=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    port = allocate_port()
    executable_path = bundled_chromium_path()
    command = [
        executable_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headed:
        command.append("--start-maximized")
    else:
        command.append("--headless=new")
    command.append("about:blank")

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    )
    wait_for_debug_port(port)

    metadata = {
        "session": session,
        "pid": process.pid,
        "port": port,
        "browser_type": "chromium",
        "executable_path": executable_path,
        "user_data_dir": str(user_data_dir),
        "headed": headed,
        "profile_explicit": profile_explicit,
        "current_page_index": 0,
    }
    metadata.update(resolve_default_state_config(session, account_id))
    save_session(session, metadata)

    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        install_console_buffer(context, page)
        maybe_load_default_storage_state(context, metadata)
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        save_default_storage_state_from_context(metadata, context)
    finally:
        playwright.stop()
    save_session(session, metadata)
    return metadata


def require_session(session: str) -> dict[str, Any]:
    metadata = load_session(session)
    if not metadata:
        raise SystemExit(f"No browser session found for '{session}'")
    if not is_process_alive(int(metadata["pid"])):
        remove_session(session)
        raise SystemExit(f"Browser session '{session}' is stale")
    return metadata


def parse_open_args(args: list[str]) -> tuple[str | None, bool, Path | None, str | None]:
    url = None
    headed = True
    profile_dir = None
    account_id = os.getenv("PWCLI_ACCOUNT_ID", "").strip() or None
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--headed":
            headed = True
            idx += 1
            continue
        if arg == "--headless":
            headed = False
            idx += 1
            continue
        if arg == "--profile":
            profile_dir = Path(args[idx + 1]).expanduser().resolve()
            idx += 2
            continue
        if arg.startswith("--profile="):
            profile_dir = Path(arg.split("=", 1)[1]).expanduser().resolve()
            idx += 1
            continue
        if arg == "--account-id":
            account_id = str(args[idx + 1]).strip() or None
            idx += 2
            continue
        if arg.startswith("--account-id="):
            account_id = arg.split("=", 1)[1].strip() or None
            idx += 1
            continue
        if not arg.startswith("--") and url is None:
            url = arg
        idx += 1
    return url, headed, profile_dir, account_id


def command_open(session: str, args: list[str]) -> int:
    url, headed, profile_dir, account_id = parse_open_args(args)
    if profile_dir is None:
        profile_dir = resolve_default_profile_dir(session, account_id)
    existing = load_session(session)
    if existing and is_process_alive(int(existing["pid"])):
        kill_process(int(existing["pid"]))
        remove_session(session)
    metadata = launch_browser(session, url, headed, profile_dir, account_id=account_id)

    print(
        f"### Browser `{metadata['session']}` opened with pid {metadata['pid']}.\n"
        f"- {metadata['session']}:\n"
        f"  - browser-type: {metadata['browser_type']}\n"
        f"  - user-data-dir: {metadata['user_data_dir']}\n"
        f"  - headed: {str(metadata['headed']).lower()}"
    )
    playwright, browser = connect_browser(metadata)
    try:
        page = ensure_page(ensure_context(browser), metadata)
        print("---")
        print(page_summary(page))
    finally:
        playwright.stop()
    return 0


def command_list() -> int:
    ensure_dirs()
    print("### Browsers")
    metas = sorted(SESSIONS_DIR.glob("*/session.json"))
    if not metas:
        print("- none")
        return 0
    for meta_path in metas:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if is_process_alive(int(metadata["pid"])):
            print(
                f"- {metadata['session']}:\n"
                f"  - status: open\n"
                f"  - browser-type: {metadata['browser_type']}\n"
                f"  - user-data-dir: {metadata['user_data_dir']}\n"
                f"  - headed: {str(metadata['headed']).lower()}"
            )
        else:
            print(f"- {metadata['session']}:\n  - status: closed")
    return 0


def command_close(session: str) -> int:
    metadata = require_session(session)
    playwright = None
    try:
        playwright, browser = connect_browser(metadata)
        save_default_storage_state_from_context(metadata, ensure_context(browser))
    except Exception:
        pass
    finally:
        if playwright is not None:
            playwright.stop()
    kill_process(int(metadata["pid"]))
    remove_session(session)
    print(f"Browser '{session}' closed")
    return 0


def command_close_all() -> int:
    ensure_dirs()
    for meta_path in SESSIONS_DIR.glob("*/session.json"):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if is_process_alive(int(metadata["pid"])):
            kill_process(int(metadata["pid"]))
        meta_path.unlink(missing_ok=True)
    print("All browser sessions closed")
    return 0


def command_reload(session: str) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        page.reload(wait_until="domcontentloaded", timeout=60000)
        print(page_summary(page))
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def command_snapshot(session: str, filename: str | None = None) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        content = format_snapshot(page, session)
        if filename:
            target = Path(filename)
            if not target.is_absolute():
                target = Path.cwd() / target
            target.write_text(content, encoding="utf-8")
            print(target)
        else:
            print(content)
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def command_click(session: str, ref: str, button: str = "left", double: bool = False) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        locator = locator_for_ref(page, session, ref)
        if double:
            locator.dblclick(button=button, timeout=30000)
        else:
            locator.click(button=button, timeout=30000)
        print(page_summary(page))
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def command_fill(session: str, ref: str, text_value: str) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        locator_for_ref(page, session, ref).fill(text_value, timeout=30000)
        print(f"Filled {ref}")
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def command_press(session: str, key: str) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        ensure_page(context, metadata).keyboard.press(key)
        print(f"Pressed {key}")
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def command_screenshot(session: str, ref: str | None = None) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        target = Path.cwd() / f"page-{timestamp()}.png"
        if ref:
            locator_for_ref(page, session, ref).screenshot(path=str(target))
        else:
            page.screenshot(path=str(target), full_page=True)
        print(target)
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def command_state_save(session: str, filename: str | None) -> int:
    metadata = require_session(session)
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        state_mode = str(metadata.get("default_state_mode") or "").strip().lower()
        default_state_path = str(metadata.get("default_state_path") or "").strip()
        synced_default = False
        if filename:
            target = Path(filename)
            if not target.is_absolute():
                target = Path.cwd() / target
            context.storage_state(path=str(target))
            print(target)
        elif state_mode == "session_manager" and default_state_path:
            save_default_storage_state_from_context(metadata, context)
            synced_default = True
            print(default_state_path)
        else:
            target = Path(default_state_path or "storage-state.json")
            if not target.is_absolute():
                target = Path.cwd() / target
            context.storage_state(path=str(target))
            print(target)
        if not synced_default:
            save_default_storage_state_from_context(metadata, context)
    finally:
        playwright.stop()
    return 0


def command_state_load(session: str, filename: str) -> int:
    metadata = require_session(session)
    payload = load_storage_state_payload(Path(filename))
    playwright, browser = connect_browser(metadata)
    try:
        context = ensure_context(browser)
        page = ensure_page(context, metadata)
        _apply_storage_state_payload(context, metadata, payload)
        page.reload(wait_until="domcontentloaded", timeout=60000)
        print(f"Loaded storage state from {filename}")
        save_default_storage_state_from_context(metadata, context)
    finally:
        save_session(session, metadata)
        playwright.stop()
    return 0


def usage() -> str:
    return (
        "Usage: pwcli <command> [args]\n"
        "Usage: pwcli -s=<session> <command> [args]\n\n"
        "Commands:\n"
        "  open [url] [--headed] [--profile <dir>] [--account-id <id>]\n"
        "  list\n"
        "  close\n"
        "  close-all\n"
        "  reload\n"
        "  snapshot [--filename <path>]\n"
        "  click <ref> [button]\n"
        "  fill <ref> <text>\n"
        "  press <key>\n"
        "  screenshot [ref]\n"
        "  state-save [filename]\n"
        "  state-load <filename>\n"
    )


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    session, args = session_name_from_argv(raw_args)
    if not args or args[0] in {"--help", "-h", "help"}:
        print(usage())
        return 0

    command = args[0]
    command_args = args[1:]
    if command == "open":
        return command_open(session, command_args)
    if command == "list":
        return command_list()
    if command in {"close-all", "kill-all"}:
        return command_close_all()
    if command == "close":
        return command_close(session)
    if command == "reload":
        return command_reload(session)
    if command == "snapshot":
        filename = command_args[1] if command_args[:1] == ["--filename"] and len(command_args) > 1 else None
        return command_snapshot(session, filename)
    if command == "click":
        return command_click(session, command_args[0], command_args[1] if len(command_args) > 1 else "left", False)
    if command == "fill":
        return command_fill(session, command_args[0], command_args[1])
    if command == "press":
        return command_press(session, command_args[0])
    if command == "screenshot":
        return command_screenshot(session, command_args[0] if command_args else None)
    if command == "state-save":
        return command_state_save(session, command_args[0] if command_args else None)
    if command == "state-load":
        return command_state_load(session, command_args[0])
    print(f"Unsupported command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

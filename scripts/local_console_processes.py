from __future__ import annotations

import json
import locale
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import psutil

LOCAL_COLLECTION = "local-collection"
INSPECTION_PANEL = "inspection-panel"
SERVICE_IDS = (LOCAL_COLLECTION, INSPECTION_PANEL)

FRONTEND_URL_PATTERN = re.compile(r"\[前端\]\s*主界面:\s*(https?://\S+)")
INSPECTION_URL_PREFIX = "PWCLI inspection panel: "
READY_URLS = (
    "http://127.0.0.1:8001/healthz/ready",
    "http://127.0.0.1:18001/healthz/ready",
    "http://127.0.0.1:18011/healthz/ready",
)

CONNECTION_SECRET_PATTERN = re.compile(
    r"(?P<prefix>[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@]+(?P<suffix>@)",
    re.IGNORECASE,
)
ASSIGNMENT_SECRET_PATTERN = re.compile(
    r"(?P<name>password|secret|api[_-]?key|access[_-]?token|token)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;&]+)",
    re.IGNORECASE,
)
QUERY_SECRET_PATTERN = re.compile(
    r"(?P<prefix>[?&](?:access_token|token)=)[^&\s]+", re.IGNORECASE
)
PROTOCOL_MARKER_PATTERN = re.compile(
    r"^XIHONG_(?P<name>STAGE|FAILURE_CODE|FAILURE_SUMMARY|RECOVERY_HINT|SOURCE_EXIT_CODE)=(?P<value>.*)$"
)


def decode_output_line(value: bytes | str) -> str:
    if isinstance(value, str):
        return value
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gb18030"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def redact_output_line(line: str) -> str:
    redacted = CONNECTION_SECRET_PATTERN.sub(
        r"\g<prefix><redacted>\g<suffix>", line
    )
    redacted = QUERY_SECRET_PATTERN.sub(r"\g<prefix><redacted>", redacted)
    return ASSIGNMENT_SECRET_PATTERN.sub(
        r"\g<name>\g<separator><redacted>", redacted
    )


class UnknownServiceError(ValueError):
    pass


class ProcessOwnershipError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceSpec:
    service_id: str
    label: str
    description: str
    command: tuple[str, ...]
    command_markers: tuple[str, ...]
    stop_process_tree: bool
    log_filename: str


@dataclass
class ManagedRecord:
    pid: int
    create_time: float
    started_at: float
    state: str = "starting"
    launch_url: str | None = None
    last_error: str | None = None
    failure_code: str | None = None
    source_exit_code: int | None = None
    wrapper_exit_code: int | None = None
    last_failure_summary: str | None = None
    recovery_hint: str | None = None
    launch_stage: str | None = None
    last_success_at: float | None = None


def build_service_specs(
    repo_root: Path, python_executable: str | None = None
) -> dict[str, ServiceSpec]:
    python_executable = python_executable or sys.executable
    collection_script = repo_root / "scripts" / "start_collection_formal.ps1"
    collection_script_text = str(collection_script).replace("'", "''")
    inspection_script = repo_root / "scripts" / "pwcli_inspection_panel.py"
    return {
        LOCAL_COLLECTION: ServiceSpec(
            service_id=LOCAL_COLLECTION,
            label="本地采集系统",
            description="数据采集、云端同步与本地测试",
            command=(
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "$OutputEncoding=[Console]::OutputEncoding="
                    "[System.Text.UTF8Encoding]::new($false); "
                    f"& '{collection_script_text}'"
                ),
            ),
            command_markers=("start_collection_formal.ps1",),
            stop_process_tree=True,
            log_filename="local-collection.log",
        ),
        INSPECTION_PANEL: ServiceSpec(
            service_id=INSPECTION_PANEL,
            label="巡店与会话",
            description="人工巡店并保存平台登录会话",
            command=(
                python_executable,
                "-u",
                str(inspection_script),
                "--no-browser",
            ),
            command_markers=("pwcli_inspection_panel.py", "--no-browser"),
            stop_process_tree=False,
            log_filename="inspection-panel.log",
        ),
    }


def probe_service_readiness(service_id: str) -> bool:
    if service_id != LOCAL_COLLECTION:
        return False
    for url in READY_URLS:
        try:
            with urllib.request.urlopen(url, timeout=0.4) as response:
                if response.status == 200:
                    return True
        except Exception:
            continue
    return False


class LocalProcessSupervisor:
    def __init__(
        self,
        *,
        repo_root: Path,
        state_path: Path,
        log_dir: Path,
        python_executable: str | None = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        process_resolver: Callable[[int], Any] = psutil.Process,
        process_iterator: Callable[[], Iterable[Any]] | None = None,
        readiness_probe: Callable[[str], bool] = probe_service_readiness,
        wait_for_processes: Callable[..., Any] = psutil.wait_procs,
        url_opener: Callable[[str], Any] = webbrowser.open,
        time_provider: Callable[[], float] = time.time,
        startup_timeout_seconds: float = 240,
        output_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.state_path = state_path
        self.log_dir = log_dir
        self.specs = build_service_specs(self.repo_root, python_executable)
        self._popen_factory = popen_factory
        self._process_resolver = process_resolver
        self._process_iterator = process_iterator or self._default_process_iterator
        self._readiness_probe = readiness_probe
        self._wait_for_processes = wait_for_processes
        self._url_opener = url_opener
        self._time_provider = time_provider
        self._startup_timeout_seconds = startup_timeout_seconds
        self._output_sink = output_sink or (lambda _line: None)
        self._records: dict[str, ManagedRecord] = {}
        self._handles: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load_state()

    def _default_process_iterator(self) -> Iterable[Any]:
        return psutil.process_iter()

    def _spec(self, service_id: str) -> ServiceSpec:
        try:
            return self.specs[service_id]
        except KeyError as exc:
            raise UnknownServiceError(service_id) from exc

    def _read_state_document(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _load_state(self) -> None:
        services = self._read_state_document().get("services", {})
        if not isinstance(services, dict):
            return
        for service_id, payload in services.items():
            if service_id not in self.specs or not isinstance(payload, dict):
                continue
            try:
                self._records[service_id] = ManagedRecord(
                    pid=int(payload["pid"]),
                    create_time=float(payload["create_time"]),
                    started_at=float(payload.get("started_at") or 0),
                    state=str(payload.get("state") or "starting"),
                    launch_url=payload.get("launch_url"),
                    last_error=payload.get("last_error"),
                    failure_code=payload.get("failure_code"),
                    source_exit_code=_optional_int(payload.get("source_exit_code")),
                    wrapper_exit_code=_optional_int(payload.get("wrapper_exit_code")),
                    last_failure_summary=payload.get("last_failure_summary"),
                    recovery_hint=payload.get("recovery_hint"),
                    launch_stage=payload.get("launch_stage"),
                    last_success_at=payload.get("last_success_at"),
                )
            except (KeyError, TypeError, ValueError):
                continue

    def _save_state(self) -> None:
        document = self._read_state_document()
        document["services"] = {
            service_id: asdict(record)
            for service_id, record in self._records.items()
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(self.state_path)

    def _append_startup_audit(self, service_id: str, record: ManagedRecord) -> None:
        """Append only redacted protocol evidence for local failure trend analysis."""
        if not record.failure_code:
            return
        payload = {
            "service_id": service_id,
            "failure_code": record.failure_code,
            "failure_summary": record.last_failure_summary,
            "recovery_hint": record.recovery_hint,
            "launch_stage": record.launch_stage,
            "source_exit_code": record.source_exit_code,
            "wrapper_exit_code": record.wrapper_exit_code,
            "recorded_at": self._time_provider(),
        }
        audit_path = self.log_dir / "startup-audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(payload, ensure_ascii=True) + "\n")

    @staticmethod
    def _process_is_running(process: Any) -> bool:
        try:
            return bool(process.is_running())
        except Exception:
            return False

    @staticmethod
    def _command_text(process: Any) -> str:
        try:
            return " ".join(str(part) for part in process.cmdline()).lower()
        except Exception:
            return ""

    def _matches_spec(self, process: Any, spec: ServiceSpec) -> bool:
        command_text = self._command_text(process)
        return bool(command_text) and all(
            marker.lower() in command_text for marker in spec.command_markers
        )

    def _resolve_owned_process(
        self, service_id: str, record: ManagedRecord
    ) -> Any | None:
        spec = self._spec(service_id)
        try:
            process = self._process_resolver(record.pid)
            if not self._process_is_running(process):
                return None
            if abs(float(process.create_time()) - record.create_time) > 0.01:
                raise ProcessOwnershipError(
                    f"{spec.label} 的进程身份已变化，已拒绝停止"
                )
            if not self._matches_spec(process, spec):
                raise ProcessOwnershipError(
                    f"{spec.label} 的进程命令不匹配，已拒绝停止"
                )
            return process
        except ProcessOwnershipError:
            raise
        except Exception:
            return None

    def _find_external_process(self, service_id: str) -> Any | None:
        spec = self._spec(service_id)
        for process in self._process_iterator():
            if self._process_is_running(process) and self._matches_spec(process, spec):
                return process
        return None

    def _snapshot(
        self,
        service_id: str,
        *,
        state: str,
        record: ManagedRecord | None = None,
        managed: bool = False,
    ) -> dict[str, Any]:
        spec = self._spec(service_id)
        return {
            "id": service_id,
            "label": spec.label,
            "description": spec.description,
            "state": state,
            "managed": managed,
            "pid": record.pid if record else None,
            "launch_url": record.launch_url if record else None,
            "last_error": record.last_error if record else None,
            "failure_code": record.failure_code if record else None,
            "source_exit_code": record.source_exit_code if record else None,
            "wrapper_exit_code": record.wrapper_exit_code if record else None,
            "last_failure_summary": record.last_failure_summary if record else None,
            "recovery_hint": record.recovery_hint if record else None,
            "launch_stage": record.launch_stage if record else None,
            "last_success_at": record.last_success_at if record else None,
            "log_available": (self.log_dir / spec.log_filename).exists(),
        }

    def status(self, service_id: str) -> dict[str, Any]:
        self._spec(service_id)
        with self._lock:
            record = self._records.get(service_id)
            if record is not None:
                if record.state == "failed":
                    return self._snapshot(
                        service_id, state="failed", record=record, managed=False
                    )
                try:
                    process = self._resolve_owned_process(service_id, record)
                except ProcessOwnershipError as exc:
                    record.state = "failed"
                    record.last_error = str(exc)
                    self._save_state()
                    return self._snapshot(
                        service_id, state="failed", record=record, managed=False
                    )
                if process is None:
                    handle = self._handles.get(service_id)
                    exit_code = handle.poll() if handle is not None else None
                    record.state = "failed" if exit_code not in (None, 0) else "stopped"
                    if record.state == "failed" and not record.last_error:
                        record.last_error = f"进程已退出，退出码 {exit_code}"
                    if record.state == "failed":
                        record.wrapper_exit_code = exit_code
                    if record.state == "stopped":
                        self._records.pop(service_id, None)
                    self._handles.pop(service_id, None)
                    self._save_state()
                    return self._snapshot(
                        service_id,
                        state=record.state,
                        record=record,
                        managed=False,
                    )
                if service_id == INSPECTION_PANEL and record.launch_url:
                    record.state = "running"
                elif self._readiness_probe(service_id):
                    was_running = record.state == "running"
                    record.state = "running"
                    if not was_running:
                        record.last_success_at = self._time_provider()
                elif (
                    record.state == "starting"
                    and self._time_provider() - record.started_at
                    > self._startup_timeout_seconds
                ):
                    record.state = "failed"
                    record.last_error = (
                        f"启动超时（超过 {int(self._startup_timeout_seconds)} 秒）"
                    )
                    record.failure_code = "startup_timeout"
                    record.last_failure_summary = record.last_error
                    self._terminate_owned_process(service_id, process)
                    self._handles.pop(service_id, None)
                elif record.state not in {"stopping", "failed"}:
                    record.state = "starting"
                self._save_state()
                return self._snapshot(
                    service_id, state=record.state, record=record, managed=True
                )

            if self._find_external_process(service_id) is not None:
                return self._snapshot(service_id, state="external-running")
            return self._snapshot(service_id, state="stopped")

    def all_statuses(self) -> list[dict[str, Any]]:
        return [self.status(service_id) for service_id in SERVICE_IDS]

    def start(self, service_id: str) -> dict[str, Any]:
        spec = self._spec(service_id)
        with self._lock:
            current = self.status(service_id)
            if current["state"] in {"starting", "running", "external-running"}:
                return current
            if current["state"] == "failed":
                self._records.pop(service_id, None)
                self._handles.pop(service_id, None)

            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / spec.log_filename
            log_path.write_text("", encoding="utf-8")
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONUNBUFFERED": "1",
                    "NO_COLOR": "1",
                    "CLICOLOR": "0",
                    "FORCE_COLOR": "0",
                }
            )
            process = self._popen_factory(
                list(spec.command),
                cwd=str(self.repo_root),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
            resolved = self._process_resolver(process.pid)
            record = ManagedRecord(
                pid=process.pid,
                create_time=float(resolved.create_time()),
                started_at=self._time_provider(),
            )
            self._records[service_id] = record
            self._handles[service_id] = process
            self._save_state()
            if process.stdout is not None:
                threading.Thread(
                    target=self._consume_output,
                    args=(service_id, process, process.stdout, log_path),
                    daemon=True,
                    name=f"local-console-{service_id}-output",
                ).start()
            return self._snapshot(
                service_id, state="starting", record=record, managed=True
            )

    def _consume_output(
        self,
        service_id: str,
        process: Any,
        output: Iterable[bytes | str],
        log_path: Path,
    ) -> None:
        with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            for raw_line in output:
                line = decode_output_line(raw_line)
                safe_line = redact_output_line(line)
                log_file.write(safe_line)
                log_file.flush()
                launch_url: str | None = None
                marker = PROTOCOL_MARKER_PATTERN.match(line.strip())
                if marker:
                    with self._lock:
                        record = self._records.get(service_id)
                        if record and record.pid == process.pid:
                            name = marker.group("name")
                            value = redact_output_line(marker.group("value").strip())
                            if name == "STAGE":
                                record.launch_stage = value
                            elif name == "FAILURE_CODE":
                                record.failure_code = value[:80]
                            elif name == "FAILURE_SUMMARY":
                                record.last_failure_summary = value[:500]
                                record.last_error = record.last_failure_summary
                            elif name == "RECOVERY_HINT":
                                record.recovery_hint = value[:300]
                            elif name == "SOURCE_EXIT_CODE":
                                record.source_exit_code = _optional_int(value)
                            self._save_state()
                            if name in {"FAILURE_CODE", "FAILURE_SUMMARY", "RECOVERY_HINT"}:
                                self._append_startup_audit(service_id, record)
                if service_id == INSPECTION_PANEL and line.startswith(
                    INSPECTION_URL_PREFIX
                ):
                    launch_url = line[len(INSPECTION_URL_PREFIX) :].strip()
                elif service_id == LOCAL_COLLECTION:
                    match = FRONTEND_URL_PATTERN.search(line)
                    if match:
                        launch_url = match.group(1)
                if launch_url:
                    with self._lock:
                        record = self._records.get(service_id)
                        if record and record.pid == process.pid:
                            record.launch_url = launch_url
                            if service_id == INSPECTION_PANEL:
                                record.state = "running"
                            self._save_state()
                self._output_sink(
                    f"[{self._spec(service_id).label}] {safe_line.rstrip()}"
                )

        exit_code = process.poll()
        if exit_code not in (None, 0):
            with self._lock:
                record = self._records.get(service_id)
                if record and record.pid == process.pid:
                    record.state = "failed"
                    if record.last_failure_summary is None:
                        record.last_error = f"进程已退出，退出码 {exit_code}"
                    else:
                        record.last_error = record.last_failure_summary
                    record.wrapper_exit_code = exit_code
                    if record.last_failure_summary is None:
                        record.last_failure_summary = record.last_error
                    self._append_startup_audit(service_id, record)
                    self._save_state()

    def stop(self, service_id: str) -> dict[str, Any]:
        spec = self._spec(service_id)
        with self._lock:
            record = self._records.get(service_id)
            if record is None:
                if self._find_external_process(service_id) is not None:
                    raise ProcessOwnershipError(
                        f"{spec.label} 由控制台外部启动，已拒绝停止"
                    )
                return self._snapshot(service_id, state="stopped")

            if record.state == "failed":
                self._records.pop(service_id, None)
                self._handles.pop(service_id, None)
                self._save_state()
                return self._snapshot(service_id, state="stopped")

            process = self._resolve_owned_process(service_id, record)
            if process is None:
                self._records.pop(service_id, None)
                self._handles.pop(service_id, None)
                self._save_state()
                return self._snapshot(service_id, state="stopped")

            record.state = "stopping"
            self._save_state()
            self._terminate_owned_process(service_id, process)

            self._records.pop(service_id, None)
            self._handles.pop(service_id, None)
            self._save_state()
            return self._snapshot(service_id, state="stopped")

    def _terminate_owned_process(self, service_id: str, process: Any) -> None:
        spec = self._spec(service_id)
        targets: list[Any] = []
        if spec.stop_process_tree:
            try:
                targets.extend(reversed(process.children(recursive=True)))
            except Exception:
                pass
        targets.append(process)
        for target in targets:
            try:
                target.terminate()
            except Exception:
                continue
        try:
            _gone, alive = self._wait_for_processes(targets, timeout=8)
        except Exception:
            alive = targets
        for target in alive:
            try:
                target.kill()
            except Exception:
                continue

    def stop_all(self) -> list[dict[str, Any]]:
        return [self.stop(service_id) for service_id in SERVICE_IDS]

    def open(self, service_id: str) -> dict[str, Any]:
        snapshot = self.status(service_id)
        launch_url = snapshot.get("launch_url")
        if snapshot["state"] != "running" or not launch_url:
            raise RuntimeError(f"{snapshot['label']} 还没有可打开的页面")
        self._url_opener(launch_url)
        return snapshot

    def read_log(self, service_id: str, max_lines: int = 80) -> list[str]:
        spec = self._spec(service_id)
        log_path = self.log_dir / spec.log_filename
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return lines[-max(1, min(max_lines, 200)) :]


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None

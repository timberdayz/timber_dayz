from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, expect
from sqlalchemy import select

from backend.services.component_test_service import ComponentTestService
from modules.apps.collection_center.transition_gates import (
    GateStatus,
    evaluate_export_complete,
)
from modules.core.db import PlatformAccount
from modules.core.logger import get_logger


logger = get_logger(__name__)


STEP_GROUP_SIGNAL_MAP = {
    "navigation": "navigation_ready",
    "date_picker": "date_picker_ready",
    "filters": "filters_ready",
}


class RecorderSegmentValidator:
    """Validate recorder step segments before they are saved as components."""

    def resolve_expected_signal(
        self,
        *,
        component_type: str,
        expected_signal: str,
        steps: List[Dict[str, Any]],
    ) -> str:
        normalized = str(expected_signal or "auto").strip().lower()
        if normalized and normalized != "auto":
            return normalized

        for step in steps:
            step_group = str(step.get("step_group") or "").strip().lower()
            resolved = STEP_GROUP_SIGNAL_MAP.get(step_group)
            if resolved:
                return resolved

        component_type_normalized = str(component_type or "").strip().lower()
        if component_type_normalized == "login":
            return "login_ready"
        if component_type_normalized == "export":
            return "export_complete"

        return "navigation_ready"

    def validate_selected_range(
        self,
        *,
        step_start: int,
        step_end: int,
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ids = [int(step.get("id")) for step in steps if step.get("id") is not None]
        expected_ids = list(range(step_start, step_end + 1))
        if ids != expected_ids:
            return {
                "success": False,
                "error_message": "selected steps must be contiguous",
            }

        return {
            "success": True,
            "validated_steps": len(steps),
        }

    def resolve_step_selector(self, step: Dict[str, Any]) -> Optional[str]:
        explicit = str(step.get("selector") or "").strip()
        if explicit:
            return explicit

        selectors = step.get("selectors") or []
        if not isinstance(selectors, list):
            return None

        for selector in selectors:
            if selector.get("type") == "css" and selector.get("value"):
                return str(selector["value"]).strip()

        for selector in selectors:
            value = str(selector.get("value") or "").strip()
            if value:
                return value

        return None

    def build_suggestions(self, *, resolved_signal: str) -> List[str]:
        suggestion_map = {
            "navigation_ready": [
                "补充 URL 变化与关键页面元素可见的双信号校验",
            ],
            "date_picker_ready": [
                "补充日期控件值变化或面板关闭后的可观察信号",
            ],
            "filters_ready": [
                "补充筛选结果区域刷新或筛选值已应用的可观察信号",
            ],
            "export_complete": [
                "改为使用真实下载文件落地且非空作为成功标准",
            ],
            "login_ready": [
                "补充登录态确认，而不是只判断点击成功",
            ],
        }
        return suggestion_map.get(resolved_signal, [])

    def build_gate_failure_result(
        self,
        *,
        resolved_signal: str,
        step_start: int,
        step_end: int,
        validated_steps: int,
        current_url: Optional[str],
        failure_step_id: Optional[int],
        failure_phase: Optional[str],
        error_message: str,
        screenshot_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "passed": False,
                "resolved_signal": resolved_signal,
                "step_start": step_start,
                "step_end": step_end,
                "validated_steps": validated_steps,
                "current_url": current_url,
                "failure_step_id": failure_step_id,
                "failure_phase": failure_phase,
                "error_message": error_message,
                "screenshot_url": screenshot_url,
                "suggestions": self.build_suggestions(resolved_signal=resolved_signal),
            },
        }

    def build_success_result(
        self,
        *,
        resolved_signal: str,
        step_start: int,
        step_end: int,
        validated_steps: int,
        current_url: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "passed": True,
                "resolved_signal": resolved_signal,
                "step_start": step_start,
                "step_end": step_end,
                "validated_steps": validated_steps,
                "current_url": current_url,
                "failure_step_id": None,
                "failure_phase": None,
                "error_message": None,
                "screenshot_url": None,
                "suggestions": self.build_suggestions(resolved_signal=resolved_signal),
            },
        }

    def _replace_variables(self, text: str, account_info: Dict[str, Any]) -> str:
        if not text:
            return text

        pattern = re.compile(r"\{\{account\.([a-zA-Z0-9_]+)\}\}")
        return pattern.sub(
            lambda match: str(account_info.get(match.group(1), match.group(0))),
            text,
        )

    async def _load_account_info(self, db, *, account_id: str) -> Dict[str, Any]:
        result = await db.execute(
            select(PlatformAccount).where(PlatformAccount.account_id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError("账号不存在")
        return ComponentTestService.prepare_account_info(account)

    async def _ensure_logged_in(self, page, *, platform: str, account_id: str, account_info: Dict[str, Any]) -> Optional[str]:
        from tools.test_component import ComponentTester, ComponentTestResult, TestStatus

        tester = ComponentTester(
            platform=platform,
            account_id=account_id,
            account_info=account_info,
            runtime_config={},
        )
        result = ComponentTestResult(
            component_name="recorder_segment",
            platform=platform,
            status=TestStatus.PENDING,
        )

        login_ready = await tester._check_login_gate(
            page=page,
            result=result,
            component_name=f"{platform}/login",
        )
        if login_ready:
            return None

        login_ok = await tester._run_login_before_non_login(
            browser=None,
            context=page.context,
            page=page,
            account_info=account_info,
            result=result,
        )
        if not login_ok:
            return result.error or "login gate not ready"

        login_ready = await tester._check_login_gate(
            page=page,
            result=result,
            component_name=f"{platform}/login",
        )
        if login_ready:
            return None
        return result.error or "login gate not ready"

    async def _execute_step(self, page, step: Dict[str, Any], account_info: Dict[str, Any]) -> None:
        action = str(step.get("action") or "").strip().lower()
        selector = self.resolve_step_selector(step)
        url = self._replace_variables(str(step.get("url") or "").strip(), account_info)
        value = self._replace_variables(str(step.get("value") or "").strip(), account_info)

        if action == "navigate":
            if not url:
                raise ValueError("navigate step missing url")
            await page.goto(url, wait_until="domcontentloaded")
            return

        if action == "wait":
            duration = step.get("duration")
            if duration:
                await page.wait_for_timeout(int(duration))
                return
            if not selector:
                raise ValueError("wait step missing selector or duration")
            await page.locator(selector).first.wait_for(state="visible", timeout=10000)
            return

        if action == "download":
            return

        if not selector:
            raise ValueError(f"{action} step missing selector")

        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=10000)

        if action == "click":
            await locator.click()
            return

        if action == "fill":
            await locator.fill(value)
            return

        raise ValueError(f"unsupported recorder step action: {action}")

    def _build_artifact_path(self, *, platform: str, signal: str) -> Path:
        output_dir = Path("temp") / "recordings" / "segment_validation"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return output_dir / f"{platform}_{signal}_{timestamp}.png"

    async def _evaluate_signal(
        self,
        *,
        page,
        resolved_signal: str,
        account_info: Dict[str, Any],
        steps: List[Dict[str, Any]],
        download_file_path: Optional[str],
    ) -> Optional[str]:
        if resolved_signal == "export_complete":
            gate = evaluate_export_complete(file_path=download_file_path)
            if gate.status is GateStatus.READY:
                return None
            return gate.reason

        if resolved_signal == "navigation_ready":
            expected_url = ""
            for step in reversed(steps):
                if str(step.get("action") or "").strip().lower() == "navigate":
                    expected_url = self._replace_variables(str(step.get("url") or "").strip(), account_info)
                    break
            if expected_url and expected_url not in page.url:
                return "target url not reached"
            await expect(page.locator("body")).to_be_visible(timeout=10000)
            return None

        if resolved_signal in {"date_picker_ready", "filters_ready"}:
            await expect(page.locator("body")).to_be_visible(timeout=10000)
            return None

        if resolved_signal == "login_ready":
            return None

        return None

    async def validate(self, request, db: Any = None) -> Dict[str, Any]:
        range_result = self.validate_selected_range(
            step_start=request.step_start,
            step_end=request.step_end,
            steps=request.steps,
        )
        if not range_result["success"]:
            return {
                "success": False,
                "error_message": range_result["error_message"],
            }

        resolved_signal = self.resolve_expected_signal(
            component_type=request.component_type,
            expected_signal=request.expected_signal,
            steps=request.steps,
        )

        if db is None:
            return self.build_success_result(
                resolved_signal=resolved_signal,
                step_start=request.step_start,
                step_end=request.step_end,
                validated_steps=range_result["validated_steps"],
                current_url=None,
            )

        account_info = await self._load_account_info(db, account_id=request.account_id)
        artifact_path = self._build_artifact_path(
            platform=request.platform,
            signal=resolved_signal,
        )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context(
                    accept_downloads=True,
                    locale="zh-CN",
                    viewport={"width": 1600, "height": 900},
                )
                page = await context.new_page()
                current_url = None
                download_file_path = None

                if request.component_type == "login":
                    login_url = account_info.get("login_url")
                    if login_url:
                        await page.goto(login_url, wait_until="domcontentloaded")
                else:
                    login_error = await self._ensure_logged_in(
                        page,
                        platform=request.platform,
                        account_id=request.account_id,
                        account_info=account_info,
                    )
                    if login_error:
                        await page.screenshot(path=str(artifact_path))
                        await context.close()
                        await browser.close()
                        return self.build_gate_failure_result(
                            resolved_signal=resolved_signal,
                            step_start=request.step_start,
                            step_end=request.step_end,
                            validated_steps=range_result["validated_steps"],
                            current_url=page.url,
                            failure_step_id=request.step_start,
                            failure_phase="login",
                            error_message=login_error,
                            screenshot_url=str(artifact_path),
                        )

                actionable_steps = [
                    step for step in request.steps
                    if str(step.get("action") or "").strip().lower() != "download"
                ]
                last_actionable_id = actionable_steps[-1]["id"] if actionable_steps else None

                for step in request.steps:
                    action = str(step.get("action") or "").strip().lower()
                    try:
                        if (
                            resolved_signal == "export_complete"
                            and action == "click"
                            and step.get("id") == last_actionable_id
                        ):
                            async with page.expect_download(timeout=30000) as download_info:
                                await self._execute_step(page, step, account_info)
                            download = await download_info.value
                            download_dir = artifact_path.parent
                            download_path = download_dir / download.suggested_filename
                            await download.save_as(str(download_path))
                            download_file_path = str(download_path)
                        else:
                            await self._execute_step(page, step, account_info)
                    except Exception as e:
                        await page.screenshot(path=str(artifact_path))
                        current_url = page.url
                        await context.close()
                        await browser.close()
                        return self.build_gate_failure_result(
                            resolved_signal=resolved_signal,
                            step_start=request.step_start,
                            step_end=request.step_end,
                            validated_steps=range_result["validated_steps"],
                            current_url=current_url,
                            failure_step_id=step.get("id"),
                            failure_phase=request.component_type,
                            error_message=str(e),
                            screenshot_url=str(artifact_path),
                        )

                current_url = page.url
                signal_error = await self._evaluate_signal(
                    page=page,
                    resolved_signal=resolved_signal,
                    account_info=account_info,
                    steps=request.steps,
                    download_file_path=download_file_path,
                )
                if signal_error:
                    await page.screenshot(path=str(artifact_path))
                    await context.close()
                    await browser.close()
                    return self.build_gate_failure_result(
                        resolved_signal=resolved_signal,
                        step_start=request.step_start,
                        step_end=request.step_end,
                        validated_steps=range_result["validated_steps"],
                        current_url=current_url,
                        failure_step_id=request.step_end,
                        failure_phase=request.component_type,
                        error_message=signal_error,
                        screenshot_url=str(artifact_path),
                    )

                await context.close()
                await browser.close()
                return self.build_success_result(
                    resolved_signal=resolved_signal,
                    step_start=request.step_start,
                    step_end=request.step_end,
                    validated_steps=range_result["validated_steps"],
                    current_url=current_url,
                )
        except Exception as e:
            logger.error("Recorder segment validation failed: %s", e, exc_info=True)
            return self.build_gate_failure_result(
                resolved_signal=resolved_signal,
                step_start=request.step_start,
                step_end=request.step_end,
                validated_steps=range_result["validated_steps"],
                current_url=None,
                failure_step_id=request.step_start,
                failure_phase=request.component_type,
                error_message=str(e),
            )

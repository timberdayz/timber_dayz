"""
组件录制 API 契约 (Contract-First)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RecorderStartRequest(BaseModel):
    """开始录制请求"""

    platform: str
    component_type: str
    account_id: str


class RecorderStepResponse(BaseModel):
    """录制步骤响应"""

    id: int
    action: str
    selector: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    comment: Optional[str] = None
    optional: bool = False


class RecorderStatusData(BaseModel):
    active: bool
    state: str
    gate_stage: Optional[str] = None
    ready_to_record: bool = False
    platform: Optional[str] = None
    component_type: Optional[str] = None
    steps_count: int = 0
    started_at: Optional[str] = None
    error_message: Optional[str] = None
    verification_type: Optional[str] = None
    verification_screenshot: Optional[str] = None


class RecorderStartResponse(BaseModel):
    success: bool
    message: str
    data: Optional[RecorderStatusData] = None


class RecorderStatusResponse(BaseModel):
    success: bool
    data: RecorderStatusData


class RecorderResumeRequest(BaseModel):
    captcha_code: Optional[str] = None
    otp: Optional[str] = None


class RecorderSaveRequest(BaseModel):
    """保存组件请求。component_name 由后端从 platform+component_type+data_domain+sub_domain 推导。"""

    platform: str
    component_type: str
    component_name: Optional[str] = None
    python_code: Optional[str] = None
    data_domain: Optional[str] = None
    sub_domain: Optional[str] = None
    success_criteria: Optional[Dict[str, Any]] = None
    yaml_content: Optional[str] = None


class GeneratePythonRequest(BaseModel):
    """生成 Python 代码请求。component_name 可选，由后端推导。"""

    platform: str
    component_type: str
    component_name: Optional[str] = None
    data_domain: Optional[str] = None
    sub_domain: Optional[str] = None
    steps: List[Dict[str, Any]]
    success_criteria: Optional[Dict[str, Any]] = None

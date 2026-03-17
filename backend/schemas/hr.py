"""
HR 人力资源管理 API 契约 (Contract-First)

包含：
- 我的收入 / 收入重算响应模型
- 部门 / 职位 / 员工管理
- 考勤 / 请假 / 加班
- 薪资结构 / 工资单
- 绩效与提成
- 员工店铺归属与提成配置
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ================================================================
# 我的收入 / 收入重算（add-performance-and-personal-income）
# ================================================================


class MyIncomeResponse(BaseModel):
    """我的收入响应；未关联员工时 linked=false，仅返回 linked 字段。"""

    linked: bool = Field(True, description="是否已关联员工档案")
    period: Optional[str] = Field(None, description="月份 YYYY-MM")
    base_salary: Optional[float] = Field(None, description="基本工资")
    commission_amount: Optional[float] = Field(None, description="提成金额")
    commission_rate: Optional[float] = Field(None, description="提成比例")
    performance_score: Optional[float] = Field(None, description="绩效得分")
    achievement_rate: Optional[float] = Field(None, description="达成率")
    total_income: Optional[float] = Field(None, description="总收入")
    breakdown: Optional[Dict[str, Any]] = Field(None, description="明细 breakdown")


class IncomeCalculationResponse(BaseModel):
    """员工 C 类收入数据重算结果。"""

    year_month: str = Field(..., description="计算月份 YYYY-MM")
    employee_count: int = Field(..., description="参与计算的员工数")
    commission_upserts: int = Field(
        ..., description="employee_commissions 写入/更新条数"
    )
    performance_upserts: int = Field(
        ..., description="employee_performance 写入/更新条数"
    )
    source: str = Field(..., description="数据来源说明")


# ================================================================
# 部门管理
# ================================================================


class DepartmentCreate(BaseModel):
    department_code: str = Field(
        ..., description="部门编码", min_length=1, max_length=64
    )
    department_name: str = Field(
        ..., description="部门名称", min_length=1, max_length=128
    )
    parent_id: Optional[int] = Field(None, description="上级部门ID")
    level: int = Field(1, ge=1, le=10, description="部门层级")
    sort_order: int = Field(0, ge=0, description="排序序号")
    manager_id: Optional[int] = Field(None, description="部门负责人ID")
    description: Optional[str] = Field(None, description="部门描述")
    status: str = Field("active", description="状态")


class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    level: Optional[int] = Field(None, ge=1, le=10)
    sort_order: Optional[int] = Field(None, ge=0)
    manager_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None


class DepartmentResponse(BaseModel):
    id: int
    department_code: str
    department_name: str
    parent_id: Optional[int]
    level: int
    sort_order: int
    manager_id: Optional[int]
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 职位管理
# ================================================================


class PositionCreate(BaseModel):
    position_code: str = Field(
        ..., description="职位编码", min_length=1, max_length=64
    )
    position_name: str = Field(
        ..., description="职位名称", min_length=1, max_length=128
    )
    position_level: int = Field(1, ge=1, le=10, description="职级")
    department_id: Optional[int] = Field(None, description="所属部门ID")
    min_salary: Optional[Decimal] = Field(None, ge=0, description="薪资下限")
    max_salary: Optional[Decimal] = Field(None, ge=0, description="薪资上限")
    description: Optional[str] = Field(None, description="职位描述")
    requirements: Optional[str] = Field(None, description="任职要求")
    status: str = Field("active", description="状态")


class PositionUpdate(BaseModel):
    position_name: Optional[str] = Field(None, min_length=1, max_length=128)
    position_level: Optional[int] = Field(None, ge=1, le=10)
    department_id: Optional[int] = None
    min_salary: Optional[Decimal] = Field(None, ge=0)
    max_salary: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    requirements: Optional[str] = None
    status: Optional[str] = None


class PositionResponse(BaseModel):
    id: int
    position_code: str
    position_name: str
    position_level: int
    department_id: Optional[int]
    min_salary: Optional[Decimal]
    max_salary: Optional[Decimal]
    description: Optional[str]
    requirements: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 员工管理（业界标准字段）
# ================================================================


class EmployeeCreate(BaseModel):
    """创建员工：employee_code 不传或为空时由后端自动生成（格式 EMP+年份后2位+4位流水号）"""

    employee_code: Optional[str] = Field(
        None, description="员工编号，不传则自动生成", max_length=64
    )
    name: str = Field(..., description="姓名", min_length=1, max_length=128)
    gender: Optional[str] = Field(None, description="性别:male/female/other")
    birth_date: Optional[date] = Field(None, description="出生日期")
    id_type: Optional[str] = Field("id_card", description="证件类型")
    id_number: Optional[str] = Field(None, description="证件号码")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    phone: Optional[str] = Field(None, description="手机号码")
    email: Optional[str] = Field(None, description="邮箱")
    address: Optional[str] = Field(None, description="现居地址")
    emergency_contact: Optional[str] = Field(None, description="紧急联系人")
    emergency_phone: Optional[str] = Field(None, description="紧急联系人电话")
    department_id: Optional[int] = Field(None, description="部门ID")
    position_id: Optional[int] = Field(None, description="职位ID")
    manager_id: Optional[int] = Field(None, description="直属上级ID")
    hire_date: Optional[date] = Field(None, description="入职日期")
    probation_end_date: Optional[date] = Field(None, description="试用期结束日期")
    contract_type: Optional[str] = Field(None, description="合同类型")
    contract_start_date: Optional[date] = Field(None, description="合同开始日期")
    contract_end_date: Optional[date] = Field(None, description="合同结束日期")
    bank_name: Optional[str] = Field(None, description="开户银行")
    bank_account: Optional[str] = Field(None, description="银行账号")
    status: str = Field("active", description="状态")
    user_id: Optional[int] = Field(
        None, description="关联登录账号 dim_users.user_id"
    )

    @field_validator(
        "birth_date",
        "hire_date",
        "probation_end_date",
        "contract_start_date",
        "contract_end_date",
        mode="before",
    )
    @classmethod
    def empty_str_to_none_date(cls, v):
        if v is None or v == "":
            return None
        return v

    @field_validator(
        "gender",
        "id_type",
        "id_number",
        "avatar_url",
        "phone",
        "email",
        "address",
        "emergency_contact",
        "emergency_phone",
        "contract_type",
        "bank_name",
        "bank_account",
        "employee_code",
        mode="before",
    )
    @classmethod
    def empty_str_to_none_str(cls, v):
        if v is not None and isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("department_id", "position_id", "manager_id", mode="before")
    @classmethod
    def empty_to_none_int(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, v):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "active"
        return v


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_id: Optional[int] = None
    hire_date: Optional[date] = None
    probation_end_date: Optional[date] = None
    regularization_date: Optional[date] = None
    leave_date: Optional[date] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    status: Optional[str] = None
    user_id: Optional[int] = Field(
        None, description="关联登录账号 dim_users.user_id"
    )


class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    name: str
    gender: Optional[str]
    birth_date: Optional[date]
    id_type: Optional[str]
    id_number: Optional[str]
    avatar_url: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    emergency_contact: Optional[str]
    emergency_phone: Optional[str]
    department_id: Optional[int]
    position_id: Optional[int]
    manager_id: Optional[int]
    hire_date: Optional[date]
    probation_end_date: Optional[date]
    regularization_date: Optional[date] = None
    leave_date: Optional[date] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    status: str
    username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 排班班次
# ================================================================


class WorkShiftCreate(BaseModel):
    shift_code: str = Field(..., description="班次编码", min_length=1, max_length=64)
    shift_name: str = Field(..., description="班次名称", min_length=1, max_length=128)
    start_time: str = Field(
        ..., description="上班时间(HH:MM)", pattern=r"^\d{2}:\d{2}$"
    )
    end_time: str = Field(
        ..., description="下班时间(HH:MM)", pattern=r"^\d{2}:\d{2}$"
    )
    work_hours: float = Field(8.0, ge=0, le=24, description="标准工作时长")
    break_hours: float = Field(1.0, ge=0, le=8, description="休息时长")
    late_tolerance: int = Field(15, ge=0, description="迟到容忍时间(分钟)")
    early_leave_tolerance: int = Field(15, ge=0, description="早退容忍时间(分钟)")
    is_flexible: bool = Field(False, description="是否弹性工时")
    status: str = Field("active", description="状态")


class WorkShiftResponse(BaseModel):
    id: int
    shift_code: str
    shift_name: str
    start_time: str
    end_time: str
    work_hours: float
    break_hours: float
    late_tolerance: int
    early_leave_tolerance: int
    is_flexible: bool
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 考勤记录
# ================================================================


class AttendanceRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    attendance_date: date = Field(..., description="考勤日期")
    clock_in_time: Optional[datetime] = Field(None, description="上班打卡时间")
    clock_out_time: Optional[datetime] = Field(None, description="下班打卡时间")
    clock_in_location: Optional[str] = Field(None, description="上班打卡位置")
    clock_out_location: Optional[str] = Field(None, description="下班打卡位置")
    clock_in_type: Optional[str] = Field("normal", description="上班打卡类型")
    clock_out_type: Optional[str] = Field("normal", description="下班打卡类型")
    shift_id: Optional[int] = Field(None, description="排班班次ID")
    work_hours: Optional[float] = Field(None, ge=0, le=24, description="实际工作时长")
    overtime_hours: Optional[float] = Field(0.0, ge=0, description="加班时长")
    status: str = Field("normal", description="考勤状态")
    remark: Optional[str] = Field(None, description="备注")


class AttendanceRecordUpdate(BaseModel):
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    clock_in_location: Optional[str] = None
    clock_out_location: Optional[str] = None
    clock_in_type: Optional[str] = None
    clock_out_type: Optional[str] = None
    shift_id: Optional[int] = None
    work_hours: Optional[float] = Field(None, ge=0, le=24)
    overtime_hours: Optional[float] = Field(None, ge=0)
    status: Optional[str] = None
    remark: Optional[str] = None


class AttendanceRecordResponse(BaseModel):
    id: int
    employee_code: str
    attendance_date: date
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    clock_in_location: Optional[str]
    clock_out_location: Optional[str]
    clock_in_type: Optional[str]
    clock_out_type: Optional[str]
    shift_id: Optional[int]
    work_hours: Optional[float]
    overtime_hours: Optional[float]
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 假期类型与请假记录
# ================================================================


class LeaveTypeCreate(BaseModel):
    leave_code: str = Field(..., description="假期编码", min_length=1, max_length=64)
    leave_name: str = Field(..., description="假期名称", min_length=1, max_length=128)
    is_paid: bool = Field(True, description="是否带薪")
    max_days_per_year: Optional[float] = Field(None, ge=0, description="年度最大天数")
    requires_approval: bool = Field(True, description="是否需要审批")
    description: Optional[str] = Field(None, description="假期说明")
    status: str = Field("active", description="状态")


class LeaveTypeResponse(BaseModel):
    id: int
    leave_code: str
    leave_name: str
    is_paid: bool
    max_days_per_year: Optional[float]
    requires_approval: bool
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeaveRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    leave_type_id: int = Field(..., description="假期类型ID")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    days: float = Field(..., gt=0, description="请假天数")
    reason: Optional[str] = Field(None, description="请假原因")


class LeaveRecordUpdate(BaseModel):
    approval_status: Optional[str] = Field(None, description="审批状态")
    approver_id: Optional[int] = Field(None, description="审批人ID")
    approval_remark: Optional[str] = Field(None, description="审批备注")


class LeaveRecordResponse(BaseModel):
    id: int
    employee_code: str
    leave_type_id: int
    start_date: date
    end_date: date
    days: float
    reason: Optional[str]
    approver_id: Optional[int]
    approval_status: str
    approval_time: Optional[datetime]
    approval_remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 加班记录
# ================================================================


class OvertimeRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    overtime_date: date = Field(..., description="加班日期")
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    hours: float = Field(..., gt=0, description="加班时长")
    overtime_type: str = Field(
        "workday", description="加班类型:workday/weekend/holiday"
    )
    reason: Optional[str] = Field(None, description="加班原因")


class OvertimeRecordUpdate(BaseModel):
    approval_status: Optional[str] = Field(None, description="审批状态")
    approver_id: Optional[int] = Field(None, description="审批人ID")


class OvertimeRecordResponse(BaseModel):
    id: int
    employee_code: str
    overtime_date: date
    start_time: datetime
    end_time: datetime
    hours: float
    overtime_type: str
    reason: Optional[str]
    approver_id: Optional[int]
    approval_status: str
    approval_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 薪资结构与工资单
# ================================================================


class SalaryStructureCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    base_salary: Decimal = Field(..., ge=0, description="基本工资")
    position_salary: Decimal = Field(0, ge=0, description="岗位工资")
    housing_allowance: Decimal = Field(0, ge=0, description="住房补贴")
    transport_allowance: Decimal = Field(0, ge=0, description="交通补贴")
    meal_allowance: Decimal = Field(0, ge=0, description="餐饮补贴")
    communication_allowance: Decimal = Field(0, ge=0, description="通讯补贴")
    other_allowance: Decimal = Field(0, ge=0, description="其他补贴")
    performance_ratio: float = Field(0, ge=0, le=1, description="绩效工资比例")
    commission_ratio: float = Field(0, ge=0, le=1, description="提成比例")
    social_insurance_base: Optional[Decimal] = Field(None, ge=0, description="社保基数")
    housing_fund_base: Optional[Decimal] = Field(None, ge=0, description="公积金基数")
    effective_date: date = Field(..., description="生效日期")
    status: str = Field("active", description="状态")


class SalaryStructureResponse(BaseModel):
    id: int
    employee_code: str
    base_salary: Decimal
    position_salary: Decimal
    housing_allowance: Decimal
    transport_allowance: Decimal
    meal_allowance: Decimal
    communication_allowance: Decimal
    other_allowance: Decimal
    performance_ratio: float
    commission_ratio: float
    social_insurance_base: Optional[Decimal]
    housing_fund_base: Optional[Decimal]
    effective_date: date
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PayrollRecordResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    base_salary: Decimal
    position_salary: Decimal
    performance_salary: Decimal
    overtime_pay: Decimal
    commission: Decimal
    allowances: Decimal
    bonus: Decimal
    gross_salary: Decimal
    social_insurance_personal: Decimal
    housing_fund_personal: Decimal
    income_tax: Decimal
    other_deductions: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    social_insurance_company: Decimal
    housing_fund_company: Decimal
    total_cost: Decimal
    status: str
    pay_date: Optional[date]
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 员工目标
# ================================================================


class EmployeeTargetCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    year_month: str = Field(
        ..., description="目标月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$"
    )
    target_type: str = Field(
        ..., description="目标类型(sales/orders/customers)", max_length=32
    )
    target_value: Decimal = Field(..., ge=0, description="目标值")


class EmployeeTargetUpdate(BaseModel):
    target_value: Optional[Decimal] = Field(None, ge=0)


class EmployeeTargetResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    target_type: str
    target_value: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 绩效与提成查询（只读）
# ================================================================


class EmployeePerformanceResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    actual_sales: Decimal
    achievement_rate: float
    performance_score: float
    calculated_at: datetime

    class Config:
        from_attributes = True


class EmployeeCommissionResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    sales_amount: Decimal
    commission_amount: Decimal
    commission_rate: float
    calculated_at: datetime

    class Config:
        from_attributes = True


class ShopCommissionResponse(BaseModel):
    id: int
    shop_id: str
    year_month: str
    sales_amount: Decimal
    commission_amount: Decimal
    commission_rate: float
    calculated_at: datetime

    class Config:
        from_attributes = True


# ================================================================
# 个人资料更新（我的档案）
# ================================================================


class MeProfileUpdate(BaseModel):
    """我的档案：仅允许自助修改的字段"""

    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=128)
    address: Optional[str] = Field(None, max_length=512)
    emergency_contact: Optional[str] = Field(None, max_length=128)
    emergency_phone: Optional[str] = Field(None, max_length=32)


# ================================================================
# 员工店铺归属与提成配置
# ================================================================


class EmployeeShopAssignmentCreate(BaseModel):
    """新增归属（按月份）"""

    year_month: str = Field(
        ..., pattern=r"^\d{4}-\d{2}$", description="适用月份 YYYY-MM"
    )
    employee_code: str = Field(..., min_length=1, max_length=64)
    platform_code: str = Field(..., min_length=1, max_length=32)
    shop_id: str = Field(..., min_length=1, max_length=256)
    commission_ratio: Optional[float] = Field(None, ge=0, le=1)
    role: Optional[str] = Field(None, max_length=32)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    @field_validator("effective_to")
    @classmethod
    def effective_to_ge_from(cls, v, info):
        if v is not None and info.data.get("effective_from") is not None:
            if v < info.data["effective_from"]:
                raise ValueError("effective_to 须 >= effective_from")
        return v


class EmployeeShopAssignmentUpdate(BaseModel):
    """更新归属"""

    commission_ratio: Optional[float] = Field(None, ge=0, le=1)
    role: Optional[str] = Field(None, max_length=32)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")

    @field_validator("effective_to")
    @classmethod
    def effective_to_ge_from(cls, v, info):
        if v is not None and info.data.get("effective_from") is not None:
            if v < info.data["effective_from"]:
                raise ValueError("effective_to 须 >= effective_from")
        return v


class EmployeeShopAssignmentResponse(BaseModel):
    """归属响应"""

    id: int
    year_month: str
    employee_code: str
    employee_name: Optional[str] = None
    platform_code: str
    shop_id: str
    shop_name: Optional[str] = None
    commission_ratio: Optional[float] = None
    role: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CopyFromPrevMonthBody(BaseModel):
    """复制上月配置请求"""

    year_month: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="目标月份 YYYY-MM（将上月配置复制到该月）",
    )


class ShopCommissionConfigUpdate(BaseModel):
    """店铺可分配利润率更新"""

    allocatable_profit_rate: float = Field(
        ..., ge=0, le=1, description="可分配利润率 0-1，如 0.8 表示 80%"
    )

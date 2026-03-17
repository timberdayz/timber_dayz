"""
HR管理API路由 - 聚合入口

v4.21.0: 拆分为五个子模块以保持每文件 <= 15 个端点:
  - hr_department.py:  部门与职位管理 (9 endpoints)
  - hr_employee.py:    员工档案与我的信息 (10 endpoints)
  - hr_attendance.py:  考勤管理 (12 endpoints)
  - hr_salary.py:      薪资与目标管理 (6 endpoints)
  - hr_commission.py:  绩效提成与店铺分配 (12 endpoints)

本文件作为向后兼容的聚合入口，main.py 仍通过 hr_management.router 挂载。
"""

from fastapi import APIRouter

from backend.routers.hr_department import router as hr_department_router
from backend.routers.hr_employee import router as hr_employee_router
from backend.routers.hr_attendance import router as hr_attendance_router
from backend.routers.hr_salary import router as hr_salary_router
from backend.routers.hr_commission import router as hr_commission_router

router = APIRouter()
router.include_router(hr_department_router)
router.include_router(hr_employee_router)
router.include_router(hr_attendance_router)
router.include_router(hr_salary_router)
router.include_router(hr_commission_router)

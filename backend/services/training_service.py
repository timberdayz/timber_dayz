from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.encryption_service import get_encryption_service
from backend.services.employee_task_notifications import notify_task_assigned
from backend.services.employee_task_repository import EmployeeTaskRepository
from backend.services.employee_task_service import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    STATUS_REJECTED,
    EmployeeTaskService,
)
from modules.core.db import Employee, TrainingAssignment, TrainingFeishuConfig, TrainingProgram, TrainingResult


class TrainingService:
    MODULE_NAME = "培训管理"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption_service = get_encryption_service()

    async def get_overview(self) -> dict:
        assignments = (await self.list_assignments())["items"]
        return {
            "module_name": self.MODULE_NAME,
            "summary": self._build_summary(assignments),
            "items": assignments,
        }

    async def list_programs(self) -> dict:
        result = await self.db.execute(select(TrainingProgram).order_by(TrainingProgram.id.asc()))
        return {"items": [self._program_to_dict(row) for row in result.scalars().all()]}

    async def create_program(self, payload: dict) -> dict:
        program = TrainingProgram(**payload)
        self.db.add(program)
        await self.db.flush()
        program.program_id = program.program_id or f"program-{program.id:03d}"
        await self.db.commit()
        await self.db.refresh(program)
        return self._program_to_dict(program)

    async def bind_program_feishu(self, program_id: str, payload: dict) -> dict:
        program = await self._get_program_by_program_id(program_id)
        program.external_course_id = payload.get("course_id")
        program.external_exam_id = payload.get("exam_id")
        await self.db.commit()
        await self.db.refresh(program)
        return {
            "program_id": program.program_id,
            "external_course_id": program.external_course_id,
            "external_exam_id": program.external_exam_id,
        }

    async def list_assignments(self) -> dict:
        result = await self.db.execute(
            select(TrainingAssignment, TrainingProgram.name)
            .join(TrainingProgram, TrainingProgram.id == TrainingAssignment.program_pk)
            .order_by(TrainingAssignment.id.asc())
        )
        items = []
        for assignment, program_name in result.all():
            items.append(await self._assignment_to_dict(assignment, program_name=program_name))
        return {"items": items}

    async def create_assignment(self, payload: dict) -> dict:
        program = await self._get_program_by_name(payload["program_name"])
        assignment = TrainingAssignment(
            program_pk=program.id,
            employee_name=payload["employee_name"],
            employee_code=payload["employee_code"],
            department=payload["department"],
            role_name=payload["role_name"],
            learning_status=payload["learning_status"],
            current_status=payload["current_status"],
            due_date=payload["due_date"],
            supervisor_name=payload["supervisor_name"],
            task_id=None,
            note=payload.get("note", ""),
        )
        self.db.add(assignment)
        await self.db.flush()
        assignment.assignment_id = assignment.assignment_id or f"assign-{assignment.id:03d}"
        assignment.task_id = await self._maybe_create_employee_task(assignment, program_name=program.name)
        await self.db.commit()
        await self.db.refresh(assignment)
        return await self._assignment_to_dict(assignment, program_name=program.name)

    async def list_results(self) -> dict:
        result = await self.db.execute(
            select(TrainingAssignment, TrainingProgram.name, TrainingResult)
            .join(TrainingProgram, TrainingProgram.id == TrainingAssignment.program_pk)
            .outerjoin(TrainingResult, TrainingResult.assignment_pk == TrainingAssignment.id)
            .order_by(TrainingAssignment.id.asc())
        )
        items = []
        for assignment, program_name, training_result in result.all():
            items.append(
                {
                    "assignment_id": assignment.assignment_id,
                    "employee_name": assignment.employee_name,
                    "employee_code": assignment.employee_code,
                    "program_name": program_name,
                    "exam_score": training_result.exam_score if training_result else None,
                    "is_passed": assignment.current_status == "已通过",
                    "current_status": assignment.current_status,
                    "updated_at": self._format_updated_at(training_result.updated_at if training_result else assignment.updated_at),
                    "note": training_result.note if training_result and training_result.note else (assignment.note or ""),
                }
            )
        return {"items": items}

    async def update_result(self, assignment_id: str, payload: dict) -> dict:
        assignment = await self._get_assignment_by_assignment_id(assignment_id)
        result = await self._get_result_by_assignment_pk(assignment.id)
        if result is None:
            result = TrainingResult(assignment_pk=assignment.id)
            self.db.add(result)
            await self.db.flush()

        result.exam_score = payload.get("exam_score")
        result.note = payload.get("note", "")
        assignment.current_status = payload["current_status"]
        assignment.note = payload.get("note", "")
        await self._sync_assignment_task_status(assignment, result_score=result.exam_score, note=result.note or "")
        await self.db.commit()
        await self.db.refresh(assignment)
        await self.db.refresh(result)
        return {
            "assignment_id": assignment.assignment_id,
            "exam_score": result.exam_score,
            "current_status": assignment.current_status,
            "note": result.note or "",
            "updated_at": self._format_updated_at(result.updated_at),
        }

    async def get_my_overview(self, employee_code: str | None = None) -> dict:
        target_code = employee_code
        if target_code is None:
            result = await self.db.execute(select(TrainingAssignment).order_by(TrainingAssignment.id.asc()).limit(1))
            first_assignment = result.scalar_one_or_none()
            if first_assignment is None:
                return {"employee_name": "", "summary": self._build_summary([]), "items": []}
            target_code = first_assignment.employee_code

        result = await self.db.execute(
            select(TrainingAssignment, TrainingProgram.name)
            .join(TrainingProgram, TrainingProgram.id == TrainingAssignment.program_pk)
            .where(TrainingAssignment.employee_code == target_code)
            .order_by(TrainingAssignment.id.asc())
        )
        items = [await self._assignment_to_dict(assignment, program_name=program_name) for assignment, program_name in result.all()]
        return {
            "employee_name": items[0]["employee_name"] if items else "",
            "summary": self._build_summary(items),
            "items": items,
        }

    async def get_assignment_detail(self, assignment_id: str) -> dict:
        assignment = await self._get_assignment_by_assignment_id(assignment_id)
        program = await self.db.get(TrainingProgram, assignment.program_pk)
        data = await self._assignment_to_dict(assignment, program_name=program.name if program else "")
        data["category"] = program.category if program else ""
        data["target_role"] = program.target_role if program else ""
        data["external_platform"] = program.external_platform if program else ""
        data["completion_rule"] = program.completion_rule if program else ""
        data["learning_url"] = program.learning_url if program else ""
        data["exam_url"] = program.exam_url if program else ""
        data["materials_url"] = program.materials_url if program else ""
        data["external_course_id"] = program.external_course_id if program else ""
        data["external_exam_id"] = program.external_exam_id if program else ""
        data["status"] = program.status if program else ""
        return data

    async def get_feishu_config(self) -> dict:
        result = await self.db.execute(select(TrainingFeishuConfig).where(TrainingFeishuConfig.provider_code == "feishu"))
        config = result.scalar_one_or_none()
        if config is None:
            return {
                "provider_code": "feishu",
                "app_id": "",
                "tenant_key": "",
                "base_url": "https://open.feishu.cn",
                "is_enabled": False,
                "has_secret": False,
            }
        return {
            "provider_code": config.provider_code,
            "app_id": config.app_id,
            "tenant_key": config.tenant_key,
            "base_url": config.base_url,
            "is_enabled": config.is_enabled,
            "has_secret": bool(config.app_secret_encrypted),
        }

    async def upsert_feishu_config(self, payload: dict, *, updated_by_user_id: int | None) -> dict:
        result = await self.db.execute(select(TrainingFeishuConfig).where(TrainingFeishuConfig.provider_code == "feishu"))
        config = result.scalar_one_or_none()
        if config is None:
            config = TrainingFeishuConfig(provider_code="feishu", app_id=payload["app_id"])
            self.db.add(config)
            await self.db.flush()

        config.app_id = payload["app_id"]
        config.tenant_key = payload.get("tenant_key")
        config.base_url = payload.get("base_url")
        config.is_enabled = payload.get("is_enabled", False)
        config.updated_by_user_id = updated_by_user_id
        if payload.get("app_secret"):
            config.app_secret_encrypted = self.encryption_service.encrypt_password(payload["app_secret"])

        await self.db.commit()
        await self.db.refresh(config)
        return {
            "provider_code": config.provider_code,
            "app_id": config.app_id,
            "tenant_key": config.tenant_key,
            "base_url": config.base_url,
            "is_enabled": config.is_enabled,
            "has_secret": bool(config.app_secret_encrypted),
        }

    async def sync_feishu_results(self, payload: dict) -> dict:
        program = await self._get_program_by_program_id(payload["program_id"])
        updated_count = 0
        skipped_count = 0
        for item in payload["results"]:
            assignment_result = await self.db.execute(
                select(TrainingAssignment).where(
                    TrainingAssignment.program_pk == program.id,
                    TrainingAssignment.employee_code == item["employee_code"],
                )
            )
            assignment = assignment_result.scalar_one_or_none()
            if assignment is None:
                skipped_count += 1
                continue
            await self.update_result(
                assignment.assignment_id,
                {
                    "exam_score": item.get("exam_score"),
                    "current_status": "已通过" if item.get("is_passed") else "未通过",
                    "note": item.get("note", ""),
                },
            )
            updated_count += 1
        return {
            "program_id": program.program_id,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
        }

    async def _get_program_by_name(self, program_name: str) -> TrainingProgram:
        result = await self.db.execute(select(TrainingProgram).where(TrainingProgram.name == program_name))
        program = result.scalar_one_or_none()
        if program is None:
            raise ValueError(f"Program {program_name} not found")
        return program

    async def _get_program_by_program_id(self, program_id: str) -> TrainingProgram:
        result = await self.db.execute(select(TrainingProgram).where(TrainingProgram.program_id == program_id))
        program = result.scalar_one_or_none()
        if program is None:
            raise ValueError(f"Program {program_id} not found")
        return program

    async def _get_assignment_by_assignment_id(self, assignment_id: str) -> TrainingAssignment:
        result = await self.db.execute(select(TrainingAssignment).where(TrainingAssignment.assignment_id == assignment_id))
        assignment = result.scalar_one_or_none()
        if assignment is None:
            raise ValueError(f"Assignment {assignment_id} not found")
        return assignment

    async def _get_result_by_assignment_pk(self, assignment_pk: int) -> TrainingResult | None:
        result = await self.db.execute(select(TrainingResult).where(TrainingResult.assignment_pk == assignment_pk))
        return result.scalar_one_or_none()

    async def _assignment_to_dict(self, assignment: TrainingAssignment, *, program_name: str) -> dict:
        result = await self._get_result_by_assignment_pk(assignment.id)
        return {
            "assignment_id": assignment.assignment_id,
            "employee_name": assignment.employee_name,
            "employee_code": assignment.employee_code,
            "department": assignment.department,
            "role_name": assignment.role_name,
            "program_name": program_name,
            "learning_status": assignment.learning_status,
            "current_status": assignment.current_status,
            "due_date": assignment.due_date,
            "supervisor_name": assignment.supervisor_name,
            "task_id": assignment.task_id,
            "note": assignment.note or "",
            "exam_score": result.exam_score if result else None,
            "updated_at": self._format_updated_at(result.updated_at if result else assignment.updated_at),
        }

    async def _maybe_create_employee_task(self, assignment: TrainingAssignment, *, program_name: str) -> str | None:
        user_id = await self._resolve_employee_user_id(assignment.employee_code)
        if not user_id:
            return None
        task_id = f"training:{assignment.assignment_id}"
        await EmployeeTaskService(self.db).create_task(
            task_id=task_id,
            task_type="training_assignment",
            task_category="execution",
            title=f"{program_name} - {assignment.employee_name}",
            owner_user_id=user_id,
            created_by=None,
            source_type="system",
            source_module="training",
            source_record_type="training_assignment",
            source_record_id=assignment.assignment_id,
            description=f"{assignment.employee_name} 的培训任务：{program_name}",
            priority="medium",
            completion_schema={"kind": "training_assignment", "required_fields": ["learning_status", "current_status"]},
        )
        await notify_task_assigned(
            db=self.db,
            recipient_id=user_id,
            task_id=task_id,
            task_type="training_assignment",
            source_module="training",
            source_record_type="training_assignment",
            source_record_id=assignment.assignment_id,
            title=f"新培训任务：{program_name}",
            content=f"请在截止日期前完成 {program_name}",
        )
        return task_id

    async def _resolve_employee_user_id(self, employee_code: str) -> int | None:
        result = await self.db.execute(select(Employee).where(Employee.employee_code == employee_code, Employee.status == "active"))
        employee = result.scalar_one_or_none()
        if employee is None or not employee.user_id:
            return None
        return int(employee.user_id)

    async def _sync_assignment_task_status(self, assignment: TrainingAssignment, *, result_score: int | None, note: str) -> None:
        if not assignment.task_id:
            return
        repository = EmployeeTaskRepository(self.db)
        task = await repository.get_task_by_task_id(assignment.task_id)
        if task is None:
            return
        mapped_status = {
            "待学习": STATUS_PENDING,
            "学习中": STATUS_IN_PROGRESS,
            "待考试": STATUS_IN_PROGRESS,
            "已通过": STATUS_COMPLETED,
            "未通过": STATUS_REJECTED,
        }.get(assignment.current_status)
        if not mapped_status:
            return
        await repository.update_task(
            task,
            status=mapped_status,
            completion_payload={"exam_score": result_score, "current_status": assignment.current_status},
            result_comment=note,
        )
        await repository.create_log(
            task_pk=task.id,
            actor_user_id=task.owner_user_id,
            action="training_sync",
            message="Training result synced to employee task",
            details_json={"status": mapped_status, "assignment_id": assignment.assignment_id},
        )

    @staticmethod
    def _program_to_dict(program: TrainingProgram) -> dict:
        return {
            "program_id": program.program_id,
            "name": program.name,
            "category": program.category,
            "target_role": program.target_role,
            "external_platform": program.external_platform,
            "completion_rule": program.completion_rule,
            "learning_url": program.learning_url,
            "exam_url": program.exam_url,
            "materials_url": program.materials_url,
            "external_course_id": program.external_course_id,
            "external_exam_id": program.external_exam_id,
            "status": program.status,
        }

    @staticmethod
    def _build_summary(items: list[dict]) -> dict:
        return {
            "total_count": len(items),
            "pending_count": sum(1 for item in items if item["current_status"] == "待学习"),
            "studying_count": sum(1 for item in items if item["current_status"] == "学习中"),
            "pending_exam_count": sum(1 for item in items if item["current_status"] == "待考试"),
            "passed_count": sum(1 for item in items if item["current_status"] == "已通过"),
            "failed_count": sum(1 for item in items if item["current_status"] == "未通过"),
            "overdue_count": sum(1 for item in items if item["current_status"] == "已逾期"),
        }

    @staticmethod
    def _format_updated_at(value) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y-%m-%d %H:%M")

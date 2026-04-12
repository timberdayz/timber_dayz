from __future__ import annotations

from datetime import datetime, timezone

from backend.schemas.approval_center import ApprovalActionLogPayload, ApprovalInstancePayload, ApprovalStepPayload
from backend.services.approval_center_repository import ApprovalCenterRepository
from backend.services.employee_task_service import EmployeeTaskService
from sqlalchemy.ext.asyncio import AsyncSession


class ApprovalCenterService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ApprovalCenterRepository(db)
        self.task_service = EmployeeTaskService(db)

    async def submit_approval(
        self,
        *,
        template_code: str,
        applicant_user_id: int,
        business_key: str,
        form_payload: dict,
        approver_user_id: int,
    ) -> dict:
        template = await self.repository.get_template_by_code(template_code)
        if template is None:
            raise ValueError(f"Approval template not found: {template_code}")

        approval_id = f"approval:{template_code}:{business_key}"
        instance = await self.repository.create_instance(
            approval_id=approval_id,
            template_code=template_code,
            applicant_user_id=applicant_user_id,
            business_key=business_key,
            status="submitted",
            current_step=1,
            submitted_at=datetime.now(timezone.utc),
        )
        await self.repository.create_step(
            approval_pk=instance.id,
            step_order=1,
            approver_type="user",
            approver_user_id=approver_user_id,
            status="pending",
        )
        await self.repository.create_action_log(
            approval_pk=instance.id,
            step_pk=None,
            actor_user_id=applicant_user_id,
            action_type="submit",
            comment="Approval submitted",
        )
        await self.task_service.create_task(
            task_id=f"approval-task:{approval_id}:1",
            task_type="approval_pending",
            task_category="approval",
            title=f"Approval pending: {template.template_name}",
            owner_user_id=approver_user_id,
            created_by=applicant_user_id,
            source_type="system",
            source_module="approval-center",
            source_record_type="approval_instance",
            source_record_id=approval_id,
            completion_schema={"form_payload": form_payload},
        )
        await self.db.commit()
        return await self.get_approval_detail(approval_id)

    async def approve_step(self, approval_id: str, *, actor_user_id: int, comment: str | None = None) -> dict:
        instance = await self._get_instance(approval_id)
        step = await self.repository.get_pending_step(instance.id)
        if step is None:
            raise ValueError("No pending approval step found")
        await self.repository.update_step(step, status="approved", acted_at=datetime.now(timezone.utc))
        await self.repository.update_instance(
            instance,
            status="approved",
            current_step=step.step_order,
            finished_at=datetime.now(timezone.utc),
        )
        await self.repository.create_action_log(
            approval_pk=instance.id,
            step_pk=step.id,
            actor_user_id=actor_user_id,
            action_type="approve",
            comment=comment,
        )
        await self.db.commit()
        return await self.get_approval_detail(approval_id)

    async def reject_step(self, approval_id: str, *, actor_user_id: int, comment: str | None = None) -> dict:
        instance = await self._get_instance(approval_id)
        step = await self.repository.get_pending_step(instance.id)
        if step is None:
            raise ValueError("No pending approval step found")
        await self.repository.update_step(step, status="rejected", acted_at=datetime.now(timezone.utc))
        await self.repository.update_instance(
            instance,
            status="rejected",
            current_step=step.step_order,
            finished_at=datetime.now(timezone.utc),
        )
        await self.repository.create_action_log(
            approval_pk=instance.id,
            step_pk=step.id,
            actor_user_id=actor_user_id,
            action_type="reject",
            comment=comment,
        )
        await self.db.commit()
        return await self.get_approval_detail(approval_id)

    async def withdraw_approval(self, approval_id: str, *, actor_user_id: int, comment: str | None = None) -> dict:
        instance = await self._get_instance(approval_id)
        if instance.applicant_user_id != actor_user_id:
            raise ValueError("Only the applicant may withdraw this approval")
        await self.repository.update_instance(
            instance,
            status="cancelled",
            finished_at=datetime.now(timezone.utc),
        )
        await self.repository.create_action_log(
            approval_pk=instance.id,
            step_pk=None,
            actor_user_id=actor_user_id,
            action_type="withdraw",
            comment=comment,
        )
        await self.db.commit()
        return await self.get_approval_detail(approval_id)

    async def get_approval_detail(self, approval_id: str) -> dict:
        instance = await self._get_instance(approval_id)
        steps = await self.repository.list_steps(instance.id)
        logs = await self.repository.list_action_logs(instance.id)
        return ApprovalInstancePayload(
            approval_id=instance.approval_id,
            template_code=instance.template_code,
            applicant_user_id=instance.applicant_user_id,
            business_key=instance.business_key,
            status=instance.status,
            current_step=instance.current_step,
            submitted_at=instance.submitted_at,
            finished_at=instance.finished_at,
            steps=[
                ApprovalStepPayload(
                    step_order=step.step_order,
                    approver_type=step.approver_type,
                    approver_user_id=step.approver_user_id,
                    status=step.status,
                    acted_at=step.acted_at,
                )
                for step in steps
            ],
            timeline=[
                ApprovalActionLogPayload(
                    action_type=log.action_type,
                    actor_user_id=log.actor_user_id,
                    comment=log.comment,
                    created_at=log.created_at,
                )
                for log in logs
            ],
        ).model_dump()

    async def _get_instance(self, approval_id: str):
        instance = await self.repository.get_instance_by_approval_id(approval_id)
        if instance is None:
            raise ValueError(f"Approval not found: {approval_id}")
        return instance

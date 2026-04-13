from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from backend.schemas.approval_center import ApprovalActionLogPayload, ApprovalInstancePayload, ApprovalStepPayload
from backend.services.approval_center_repository import ApprovalCenterRepository
from backend.services.employee_task_service import EmployeeTaskService
from sqlalchemy.ext.asyncio import AsyncSession
from modules.core.db import DimRole, DimUser, user_roles


USER_REGISTRATION_TEMPLATE_CODE = "user_registration_approval"
MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE = "monthly_profit_settlement_approval"
FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE = "follow_investment_settlement_approval"


async def _ensure_template(
    db: AsyncSession,
    *,
    template_code: str,
    template_name: str,
    business_type: str,
    target_route: str,
    form_schema: dict,
) -> None:
    repository = ApprovalCenterRepository(db)
    template = await repository.get_template_by_code(template_code)
    if template is not None:
        return
    await repository.create_template(
        template_code=template_code,
        template_name=template_name,
        business_type=business_type,
        enabled=True,
        target_route=target_route,
        approval_mode="single",
        form_schema=form_schema,
    )
    await db.flush()


async def _ensure_user_registration_template(db: AsyncSession) -> None:
    await _ensure_template(
        db,
        template_code=USER_REGISTRATION_TEMPLATE_CODE,
        template_name="User Registration Approval",
        business_type="user_registration",
        target_route="/approval-center/user-registration",
        form_schema={"fields": ["username", "email"]},
    )


async def _ensure_monthly_profit_settlement_template(db: AsyncSession) -> None:
    await _ensure_template(
        db,
        template_code=MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE,
        template_name="Monthly Profit Settlement Approval",
        business_type="monthly_profit_settlement",
        target_route="/financial-management",
        form_schema={"fields": ["settlement_id", "period_month"]},
    )


async def _ensure_follow_investment_settlement_template(db: AsyncSession) -> None:
    await _ensure_template(
        db,
        template_code=FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE,
        template_name="Follow Investment Settlement Approval",
        business_type="follow_investment_settlement",
        target_route="/financial-management",
        form_schema={"fields": ["settlement_id", "period_month", "platform_code", "shop_id"]},
    )


async def _resolve_admin_approver_user_id(db: AsyncSession) -> int:
    result = await db.execute(
        select(DimUser.user_id)
        .where(
            DimUser.is_superuser == True,
            DimUser.is_active == True,
            DimUser.status == "active",
        )
        .order_by(DimUser.user_id.asc())
    )
    superuser_id = result.scalars().first()
    if superuser_id is not None:
        return int(superuser_id)

    result = await db.execute(
        select(user_roles.c.user_id)
        .join(DimRole, user_roles.c.role_id == DimRole.role_id)
        .join(DimUser, DimUser.user_id == user_roles.c.user_id)
        .where(
            DimRole.role_code == "admin",
            DimUser.is_active == True,
            DimUser.status == "active",
        )
        .order_by(user_roles.c.user_id.asc())
    )
    admin_user_id = result.scalars().first()
    if admin_user_id is None:
        raise ValueError("No active admin approver is available for user registration approval")
    return int(admin_user_id)


async def submit_user_registration_approval(
    *,
    db: AsyncSession,
    applicant_user_id: int,
    username: str,
    email: str,
) -> dict:
    await _ensure_user_registration_template(db)
    service = ApprovalCenterService(db)
    business_key = f"user:{applicant_user_id}"
    existing = await service.repository.get_latest_instance_by_template_and_business_key(
        template_code=USER_REGISTRATION_TEMPLATE_CODE,
        business_key=business_key,
    )
    if existing is not None and existing.status in {"submitted", "in_review"}:
        return await service.get_approval_detail(existing.approval_id)

    approver_user_id = await _resolve_admin_approver_user_id(db)
    approval_id = (
        f"approval:{USER_REGISTRATION_TEMPLATE_CODE}:{business_key}:"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    )
    return await service.submit_approval(
        approval_id=approval_id,
        template_code=USER_REGISTRATION_TEMPLATE_CODE,
        applicant_user_id=applicant_user_id,
        business_key=business_key,
        form_payload={"username": username, "email": email},
        approver_user_id=approver_user_id,
    )


async def submit_monthly_profit_settlement_approval(
    *,
    db: AsyncSession,
    applicant_user_id: int,
    settlement_id: int,
    period_month: str,
) -> dict:
    await _ensure_monthly_profit_settlement_template(db)
    service = ApprovalCenterService(db)
    business_key = f"settlement:{settlement_id}"
    existing = await service.repository.get_latest_instance_by_template_and_business_key(
        template_code=MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE,
        business_key=business_key,
    )
    if existing is not None and existing.status in {"submitted", "in_review"}:
        return await service.get_approval_detail(existing.approval_id)

    approver_user_id = await _resolve_admin_approver_user_id(db)
    approval_id = (
        f"approval:{MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE}:{business_key}:"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    )
    return await service.submit_approval(
        approval_id=approval_id,
        template_code=MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE,
        applicant_user_id=applicant_user_id,
        business_key=business_key,
        form_payload={"settlement_id": settlement_id, "period_month": period_month},
        approver_user_id=approver_user_id,
    )


async def sync_monthly_profit_settlement_approval_decision(
    *,
    db: AsyncSession,
    settlement_id: int,
    actor_user_id: int,
    action: str,
    comment: str | None = None,
) -> dict | None:
    service = ApprovalCenterService(db)
    instance = await service.repository.get_latest_instance_by_template_and_business_key(
        template_code=MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE,
        business_key=f"settlement:{settlement_id}",
    )
    if instance is None:
        return None
    if action == "approve":
        return await service.approve_step(instance.approval_id, actor_user_id=actor_user_id, comment=comment)
    if action == "reject":
        return await service.reject_step(instance.approval_id, actor_user_id=actor_user_id, comment=comment)
    raise ValueError(f"Unsupported monthly profit settlement approval action: {action}")


async def submit_follow_investment_settlement_approval(
    *,
    db: AsyncSession,
    applicant_user_id: int,
    settlement_id: int,
    period_month: str,
    platform_code: str,
    shop_id: str,
) -> dict:
    await _ensure_follow_investment_settlement_template(db)
    service = ApprovalCenterService(db)
    business_key = f"settlement:{settlement_id}"
    existing = await service.repository.get_latest_instance_by_template_and_business_key(
        template_code=FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE,
        business_key=business_key,
    )
    if existing is not None and existing.status in {"submitted", "in_review"}:
        return await service.get_approval_detail(existing.approval_id)

    approver_user_id = await _resolve_admin_approver_user_id(db)
    approval_id = (
        f"approval:{FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE}:{business_key}:"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    )
    return await service.submit_approval(
        approval_id=approval_id,
        template_code=FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE,
        applicant_user_id=applicant_user_id,
        business_key=business_key,
        form_payload={
            "settlement_id": settlement_id,
            "period_month": period_month,
            "platform_code": platform_code,
            "shop_id": shop_id,
        },
        approver_user_id=approver_user_id,
    )


async def sync_follow_investment_settlement_approval_decision(
    *,
    db: AsyncSession,
    settlement_id: int,
    actor_user_id: int,
    action: str,
    comment: str | None = None,
) -> dict | None:
    service = ApprovalCenterService(db)
    instance = await service.repository.get_latest_instance_by_template_and_business_key(
        template_code=FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE,
        business_key=f"settlement:{settlement_id}",
    )
    if instance is None:
        return None
    if action == "approve":
        return await service.approve_step(instance.approval_id, actor_user_id=actor_user_id, comment=comment)
    if action == "reject":
        return await service.reject_step(instance.approval_id, actor_user_id=actor_user_id, comment=comment)
    raise ValueError(f"Unsupported follow investment settlement approval action: {action}")


async def sync_user_registration_approval_decision(
    *,
    db: AsyncSession,
    user_id: int,
    actor_user_id: int,
    action: str,
    comment: str | None = None,
) -> dict | None:
    service = ApprovalCenterService(db)
    instance = await service.repository.get_latest_instance_by_template_and_business_key(
        template_code=USER_REGISTRATION_TEMPLATE_CODE,
        business_key=f"user:{user_id}",
    )
    if instance is None:
        return None
    if action == "approve":
        return await service.approve_step(
            instance.approval_id,
            actor_user_id=actor_user_id,
            comment=comment,
        )
    if action == "reject":
        return await service.reject_step(
            instance.approval_id,
            actor_user_id=actor_user_id,
            comment=comment,
        )
    raise ValueError(f"Unsupported user registration approval action: {action}")


class ApprovalCenterService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ApprovalCenterRepository(db)
        self.task_service = EmployeeTaskService(db)

    async def submit_approval(
        self,
        *,
        approval_id: str | None = None,
        template_code: str,
        applicant_user_id: int,
        business_key: str,
        form_payload: dict,
        approver_user_id: int,
    ) -> dict:
        template = await self.repository.get_template_by_code(template_code)
        if template is None:
            raise ValueError(f"Approval template not found: {template_code}")

        approval_id = approval_id or f"approval:{template_code}:{business_key}"
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

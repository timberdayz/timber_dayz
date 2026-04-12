# Training Management And Learning Platform Design

**Date:** 2026-04-12
**Last Updated:** 2026-04-12

## Goal

Design a practical company training architecture for XiHong ERP that supports:
- standardized learning and exam workflows
- employee onboarding training
- role certification training
- SOP continuous training
- management training
- effective reminder, confirmation, and tracking through the existing ERP task and notification systems

The design should help the company launch training operations quickly without turning the ERP into a full self-built LMS in the first phase.

## Problem Statement

The current ERP already covers most operational and management needs, but it is still management-heavy and training-light.

The business now needs a structured training mechanism for:
- new employee onboarding
- role skill certification
- store / operations SOP updates and recurring retraining
- management capability development

The repository already has:
- employee and organization data
- an employee collaboration task center
- a notification center
- role, shop, and department context

What it does not yet have is a formal training operating model that can answer:
- who must learn what
- when they must complete it
- what counts as passing
- who must confirm it
- how training completion affects business readiness

## Scope

This design covers:
- product positioning for training in the current ERP
- recommended boundary between ERP and external learning platforms
- first-phase training domain model
- integration with the existing task center and notification center
- state model and confirmation model for training tasks
- page structure for ERP training management
- rollout order and pilot strategy

This design does not cover:
- a full implementation plan
- building a custom course player in ERP
- building a custom exam engine in ERP
- deep API integration details for any one external platform in v1
- final KPI or compensation policy design for training outcomes

## Recommendation Summary

The recommended approach is a **dual-layer architecture**:

1. Use a mature external platform such as Feishu for learning and exams
2. Use XiHong ERP as the training management and business linkage control plane

This means:
- the external platform owns course delivery, exam delivery, study records, and mobile learning experience
- ERP owns training policy, assignment, due dates, reminder rules, confirmation, retraining, dashboards, and business linkage

This is the recommended first-phase path because it:
- launches faster
- avoids rebuilding mature LMS capabilities too early
- keeps company-specific training rules inside ERP
- fits the existing task-center and notification-center architecture already present in the repository

## Why Not Build A Full LMS Inside ERP First

Building a complete in-house LMS in phase 1 is not recommended.

Reasons:
- course playback, exam engines, mobile UX, reminder workflows, and study records are already solved well by mature platforms
- the company's immediate gap is training operations and training governance, not media playback
- training content and workflow are likely to evolve quickly in the early stage
- building the wrong platform too early would slow down actual training rollout

The ERP should focus on:
- training governance
- assignment and accountability
- organizational visibility
- linkage between training results and employee readiness

## Product Positioning

The new capability should be positioned as a **training management center**, not as:
- a standalone content portal
- a second notification center
- a replacement for an external LMS

Core principle:
- training business records are the source of truth for training status
- collaboration tasks are the execution shell around training work
- notifications are reminder shells around training tasks
- the external platform remains the execution surface for learning and exams

## Recommended Architecture

The first release should use four coordinated layers.

### 1. External Learning Layer

Owned by a mature platform such as Feishu.

Responsibilities:
- course delivery
- document / video / exam hosting
- learner study experience
- exam submission
- mobile learning convenience

This layer should not become the only source of organizational training truth.

### 2. ERP Training Domain Layer

Owned by XiHong ERP.

Responsibilities:
- training program definitions
- training package definitions
- assignment rules
- pass rules
- due dates
- retraining rules
- result tracking
- confirmation records
- management dashboards

This layer is the business source of truth for company training management.

### 3. Employee Collaboration Task Layer

Reuse the existing employee collaboration task center.

Responsibilities:
- who owns the current training action
- due date and urgency
- pending / in-progress / pending-confirmation / completed task workflow
- task timeline
- task deep-links into training detail pages

Training should be represented as a business task category rather than a detached message.

### 4. Notification Layer

Reuse the existing notification center.

Responsibilities:
- new training assignment reminders
- due-soon reminders
- overdue reminders
- failed-exam reminders
- retraining reminders
- confirmation pending reminders

Notification remains a delivery shell and should always route back to a task or training detail page.

## Training Types

The first release should explicitly support four training categories:

### 1. Onboarding Training

Purpose:
- align new hires on company context, rules, basic system usage, and business basics

Characteristics:
- standardized package
- short completion window
- usually mandatory

### 2. Role Certification Training

Purpose:
- determine whether an employee is ready to independently perform a role

Characteristics:
- tied to role qualification
- clear pass threshold
- can require supervisor confirmation
- can require periodic recertification

### 3. SOP Continuous Training

Purpose:
- ensure new process versions are understood and adopted

Characteristics:
- version-driven
- often retraining-based
- can be triggered by SOP changes

### 4. Management Training

Purpose:
- develop management capability rather than only knowledge recall

Characteristics:
- longer cycle
- may include assignments, case discussions, or supervisor evaluation
- not suitable to reduce to exam score only

## Object Boundaries

Training should be modeled as its own business domain. Do not collapse training semantics entirely into task tables.

### Training Domain Objects

Recommended first-phase objects:
- `training_program`
- `training_package`
- `training_assignment`
- `training_result`
- `training_confirmation`
- `training_version`
- `training_external_mapping`

These objects answer:
- what the training is
- who should take it
- what counts as passing
- what the latest business result is
- whether retraining is required

### Collaboration Task Objects

Reuse the existing collaboration task domain for:
- owner
- task state
- due date
- reminders
- execution timeline

The task layer should not become the only source for:
- scores
- package contents
- training versions
- course lists

### Notification Objects

Reuse the existing notification domain for delivery and read-state management.

### External Mapping Objects

A mapping layer is needed between ERP and the external learning platform for:
- external platform kind
- external course IDs
- external exam IDs
- launch URLs
- sync mode
- sync timestamps

## Recommended First-Phase Data Model

The first release should center on four main records.

### 1. `training_program`

Defines one training rule set.

Suggested fields:
- `id`
- `name`
- `category`
- `target_type`
- `is_required`
- `pass_score`
- `due_days`
- `retrain_cycle_days`
- `requires_confirmation`
- `confirmation_role_type`
- `version`
- `status`
- `description`

### 2. `training_package`

Groups the course and exam assets for assignment.

Suggested fields:
- `id`
- `program_id`
- `name`
- `external_platform`
- `external_course_ids`
- `external_exam_ids`
- `version`
- `status`
- `notes`

### 3. `training_assignment`

Represents one employee-facing training instance.

Suggested fields:
- `id`
- `program_id`
- `package_id`
- `employee_id`
- `job_id`
- `department_id`
- `store_id`
- `assigned_at`
- `due_at`
- `source`
- `business_status`
- `linked_task_id`

### 4. `training_result`

Stores current training outcome details.

Suggested fields:
- `id`
- `assignment_id`
- `employee_id`
- `completion_status`
- `exam_score`
- `is_passed`
- `completed_at`
- `result_source`
- `last_synced_at`
- `remark`

Optional supporting object:
- `training_confirmation` for supervisor / HR confirmation records

## Training State Model

Training should use a business-facing state model, then map into the existing collaboration-task state vocabulary.

Recommended training business states:
- `pending_study`
- `studying`
- `pending_exam`
- `pending_confirmation`
- `passed`
- `failed`
- `overdue`
- `retraining_required`
- `closed`

Recommended task-state mapping:
- `pending_study` -> `pending`
- `studying` -> `in_progress`
- `pending_exam` -> `in_progress`
- `pending_confirmation` -> `pending_confirmation`
- `passed` -> `completed`
- `failed` -> `rejected`
- `closed` -> `closed`

`overdue` should remain a training business flag or state and should not require creating a brand-new collaboration task vocabulary in v1.

## Completion And Confirmation Model

Different training types need different confirmation strictness.

### Onboarding Training

Default completion:
- finished learning
- passed basic exam

Optional confirmation:
- supervisor or mentor confirms practical onboarding completion where needed

### Role Certification Training

Default completion:
- finished learning
- passed certification exam

Optional confirmation:
- supervisor / role owner confirms readiness for independent execution

### SOP Continuous Training

Default completion:
- finished learning
- passed lightweight check or quiz

Optional confirmation:
- store manager or department lead confirms operational adoption for critical SOPs

### Management Training

Default completion should not depend on exam alone.

Recommended proof set:
- learning completion
- assignment / case submission
- supervisor evaluation or HRBP confirmation

## Notification And Task Integration

The design should reuse the current task-center and notification-center capabilities rather than building a separate reminder workflow.

### New Training Task Types

Recommended task types:
- `training_onboarding`
- `training_role_certification`
- `training_sop_retraining`
- `training_management_program`

### Recommended Training Notification Types

- `training_assigned`
- `training_due_soon`
- `training_overdue`
- `training_failed`
- `training_retraining_required`
- `training_confirmation_pending`

### Trigger Rules

Recommended first-phase triggers:
- create task and notification when training is assigned
- send due-soon reminder before deadline
- send overdue reminder after deadline
- send failed reminder after exam failure
- send confirmation reminder when supervisor action is required
- create a new retraining task when SOP version or certification cycle requires retraining

### Routing Rules

Notification click behavior should route to:
- training task detail page, or
- training detail page with task context

The employee should then jump to the external platform only from the training detail page, not from generic notifications directly.

## Page Structure

The ERP should provide a lightweight but operationally complete training management surface.

### 1. Training Overview

Audience:
- HR
- training administrators
- management

Responsibilities:
- global training counts
- completion rate
- overdue count
- failed count
- retraining queue

### 2. Training Programs

Responsibilities:
- define training programs
- set category, pass rules, due rules, and confirmation rules
- manage versions

### 3. Training Assignment Center

Responsibilities:
- assign by employee, role, department, or store
- support automatic and manual assignment
- support exception handling and re-assignment

### 4. Training Results

Responsibilities:
- review per-person and per-assignment status
- review score and pass result
- handle failure, retake, and confirmation edge cases

### 5. Training Dashboard

Responsibilities:
- aggregate by training type, role, department, or store
- show management-risk lists
- show overdue and incomplete populations

### 6. Training Task Detail

This is the key bridge page between training records and collaboration tasks.

It should show:
- training summary
- due date and status
- course and exam requirements
- external learning entry links
- result and score
- confirmation section
- timeline
- next actions

## Employee Experience

The first release should avoid creating a heavy standalone employee training portal inside ERP.

Preferred employee flow:
1. employee receives a training task in `我的任务`
2. employee opens training task detail
3. employee sees requirements and clicks into the external learning platform
4. learning or exam happens externally
5. result returns to ERP
6. employee and supervisor track status through ERP task and dashboard surfaces

Optional later addition:
- `我的学习` page for employees to review their own history

This is useful but not required in v1 if task entry already works well.

## Permission Model

The first release should use four responsibility layers.

### 1. System Administrator

Responsibilities:
- global configuration
- notification strategy
- permission control

### 2. Training Administrator / HR

Responsibilities:
- training program maintenance
- package maintenance
- assignment rules
- global reporting

### 3. Department Manager / Store Manager / Supervisor

Responsibilities:
- team progress visibility
- nudging and follow-up
- selected training confirmations

### 4. Employee

Responsibilities:
- view own training tasks
- enter learning and exams
- review own results

Training content governance and completion confirmation should remain separate responsibilities.

## Rollout Strategy

Do not launch all four training types at once.

Recommended rollout order:

1. onboarding training
2. role certification training
3. SOP continuous training
4. management training

Reasons:
- onboarding is the easiest to standardize
- role certification shows immediate business value
- SOP retraining adds version complexity
- management training requires richer evaluation than exam-only flows

## Pilot Strategy

The first release should begin with two pilot tracks.

### Pilot A: Onboarding Training

Recommended content examples:
- company introduction
- policy and rules
- ERP basic usage
- cross-border business basics
- compliance / security basics

Goal:
- validate end-to-end assignment, learning, exam, reminder, and completion workflow

### Pilot B: One Role Certification Track

Choose one role with clear qualification requirements, such as:
- operations specialist
- customer service specialist
- procurement specialist

Goal:
- validate that training result can support role-readiness management

## Phase-1 Milestones

### Milestone A: Workflow Available

- external platform selected
- two pilot training packages created
- ERP can assign training, create tasks, send notifications, and store results
- manual or semi-manual result import is acceptable

### Milestone B: Management Loop Closed

- training tasks appear in `我的任务`
- training reminders appear in the notification center
- supervisors can see incomplete, overdue, and failed populations
- dashboard provides baseline statistics

### Milestone C: Rule Linkage Established

- onboarding training auto-assigned on hire
- role certification triggered on role change or appointment
- SOP updates generate retraining
- selected training items support supervisor confirmation

## Success Criteria

Phase 1 should not be judged by number of pages built.

Recommended success criteria:
- new hires complete onboarding training within the defined time window
- the pilot role clearly distinguishes certified vs non-certified employees
- supervisors can identify incomplete and overdue team members
- employees can complete training through the existing task and notification workflow
- ERP becomes the management visibility layer for training outcomes

## Risks

### 1. Building A Detached Training Portal

If training becomes a separate isolated portal, employees may ignore it.

Mitigation:
- use the existing collaboration task entry
- keep ERP as the management shell

### 2. Turning Notifications Into The Main Control Plane

If notification records are treated as training truth, training reporting will become unreliable.

Mitigation:
- training domain remains the business SSOT
- notifications remain reminders only

### 3. Over-automating Too Early

If phase 1 waits for full platform API sync, rollout may stall.

Mitigation:
- allow manual or semi-manual result import first

### 4. Mixing Qualification Rules With Generic Completion Rules

Not every completed course implies role readiness.

Mitigation:
- make certification and confirmation rules explicit per training type

### 5. Attempting To Solve Management Training With Exams Alone

Management development usually requires richer proof.

Mitigation:
- support assignment, discussion, or supervisor evaluation in later iterations

## Recommended Outcome

XiHong ERP should evolve toward:
- one training management center inside ERP
- one external learning platform for study and exams
- one shared employee task center for accountability
- one shared notification center for reminders
- one clear business model linking training completion to employee readiness

This gives the company a practical first-phase training operating system without overbuilding a custom LMS before the training process itself is proven.

# 我的收入验收自动化报告

- 生成时间(UTC): 2026-05-27 12:50:24
- 执行方式: 直接调用路由函数 + 真实数据库会话

## 验收结果

- [OK] 6.5 已关联员工可查看本人收入: status=200, linked=True
- [OK] 6.7 月份切换可查历史: query=2026-04, period=2026-04
- [OK] 6.8a 非空样例数据: month=2026-04, commission_amount=0.0, performance_salary=15.0
- [OK] 6.8 非本人不可越权+审计可追溯: no_employee_param=True, audit_delta=1
- [OK] 6.8c 审计日志可检索(user_id+时间区间): hit=10
- [OK] 6.6 未关联用户返回引导态: status=200, linked=False

## 说明

- 本报告用于验收闭环；若出现 [WARN]/[FAIL]，需按结果补充人工点验或环境数据。

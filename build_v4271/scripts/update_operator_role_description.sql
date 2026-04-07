-- 更新"运营人员"角色描述
-- 移除错误的"用于新用户审批"描述
-- 执行时间: 2026-01-08

UPDATE dim_roles 
SET description = '日常操作人员角色，用于数据采集和业务操作',
    updated_at = NOW()
WHERE role_code = 'operator' 
  AND role_name = '运营人员'
  AND description LIKE '%用于新用户审批%';

-- 验证更新结果
SELECT role_id, role_name, role_code, description, updated_at 
FROM dim_roles 
WHERE role_code = 'operator';

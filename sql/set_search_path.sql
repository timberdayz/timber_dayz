-- ===================================================
-- 设置搜索路径（保持代码兼容）
-- ===================================================
-- 创建时间: 2025-11-26
-- 目的: 设置默认搜索路径，保持代码向后兼容

-- 为当前数据库设置默认搜索路径
ALTER DATABASE xihong_erp SET search_path = core, a_class, b_class, c_class, finance, public;

-- 为当前用户设置搜索路径（可选）
ALTER ROLE erp_user SET search_path = core, a_class, b_class, c_class, finance, public;

-- 验证：查看当前搜索路径
-- SHOW search_path;


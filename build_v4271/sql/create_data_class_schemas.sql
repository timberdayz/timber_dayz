-- ===================================================
-- 创建数据分类Schema
-- ===================================================
-- 创建时间: 2025-11-26
-- 目的: 按数据分类组织表，便于Metabase中清晰区分

-- 创建数据分类Schema
CREATE SCHEMA IF NOT EXISTS a_class;  -- A类数据（用户配置数据）
CREATE SCHEMA IF NOT EXISTS b_class;  -- B类数据（业务数据）
CREATE SCHEMA IF NOT EXISTS c_class;  -- C类数据（计算数据）
CREATE SCHEMA IF NOT EXISTS core;     -- 核心ERP表（系统必需）
CREATE SCHEMA IF NOT EXISTS finance;  -- 财务域表（可选）

-- 设置Schema注释（便于理解）
COMMENT ON SCHEMA a_class IS 'A类数据：用户配置数据（销售战役、目标管理、绩效配置等）';
COMMENT ON SCHEMA b_class IS 'B类数据：业务数据（从Excel采集的订单、产品、流量等数据）';
COMMENT ON SCHEMA c_class IS 'C类数据：计算数据（系统自动计算的达成率、健康度评分等）';
COMMENT ON SCHEMA core IS '核心ERP表：系统必需的管理表和维度表';
COMMENT ON SCHEMA finance IS '财务域表：采购、库存、发票、费用、税务、总账等';

-- 验证：查看创建的Schema
-- SELECT schema_name, schema_owner FROM information_schema.schemata 
-- WHERE schema_name IN ('a_class', 'b_class', 'c_class', 'core', 'finance')
-- ORDER BY schema_name;


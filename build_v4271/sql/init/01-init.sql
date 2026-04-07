-- ===================================================
-- 西虹ERP系统 - PostgreSQL初始化脚本
-- ===================================================
-- 功能：创建数据库、用户、权限和扩展
-- 执行时机：容器首次启动时自动执行
-- ===================================================

-- 设置客户端编码
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- 注意：本脚本在容器首次启动时执行，已连接到 POSTGRES_DB（xihong_erp）

-- ==================== 创建 Metabase 应用数据库 ====================
-- Metabase 官方建议：生产环境必须使用 PostgreSQL/MySQL，不要使用 H2
-- metabase_app 用于存储 Metabase 自己的配置（Models、Questions、Dashboards、用户设置等）
-- 与业务数据库 xihong_erp 完全独立；CREATE DATABASE 可在当前连接下执行
CREATE DATABASE metabase_app
    WITH
    OWNER = erp_user
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8'
    TEMPLATE = template0;

COMMENT ON DATABASE metabase_app IS 'Metabase 应用数据库：存储 Metabase 自己的配置（Models、Questions、Dashboards、用户设置等）';

GRANT ALL PRIVILEGES ON DATABASE metabase_app TO erp_user;

-- ==================== 创建Schema（业务库 xihong_erp）====================
-- 创建数据分类Schema（必须在创建表之前）
-- 注意：使用 IF NOT EXISTS 确保幂等性，可重复执行
CREATE SCHEMA IF NOT EXISTS a_class;  -- A类数据（用户配置数据）
CREATE SCHEMA IF NOT EXISTS b_class;  -- B类数据（业务数据）
CREATE SCHEMA IF NOT EXISTS c_class;  -- C类数据（计算数据）
CREATE SCHEMA IF NOT EXISTS core;     -- 核心ERP表（系统必需）
CREATE SCHEMA IF NOT EXISTS finance;  -- 财务域表（可选）

-- 设置Schema注释（便于理解和Metabase展示）
COMMENT ON SCHEMA a_class IS 'A类数据：用户配置数据（销售战役、目标管理、绩效配置等）';
COMMENT ON SCHEMA b_class IS 'B类数据：业务数据（从Excel采集的订单、产品、流量等数据）';
COMMENT ON SCHEMA c_class IS 'C类数据：计算数据（系统自动计算的达成率、健康度评分等）';
COMMENT ON SCHEMA core IS '核心ERP表：系统必需的管理表和维度表';
COMMENT ON SCHEMA finance IS '财务域表：采购、库存、发票、费用、税务、总账等';

-- ==================== 创建扩展 ====================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";       -- UUID生成
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- 文本相似度搜索
CREATE EXTENSION IF NOT EXISTS "btree_gin";       -- GIN索引支持

-- ==================== 设置搜索路径 ====================
-- 设置数据库级别的搜索路径（保持代码向后兼容，无需修改SQL查询即可访问表）
-- 注意：需要在数据库级别设置，但当前脚本在数据库创建后执行，需要使用ALTER DATABASE
-- 由于此时数据库已创建，这里使用DO块设置当前数据库的搜索路径
DO $$
BEGIN
    -- 设置当前数据库的搜索路径
    EXECUTE format('ALTER DATABASE %I SET search_path TO core, a_class, b_class, c_class, finance, public', current_database());
END
$$;

-- 设置用户级别的搜索路径（确保所有会话都使用正确的搜索路径）
ALTER ROLE erp_user SET search_path TO core, a_class, b_class, c_class, finance, public;
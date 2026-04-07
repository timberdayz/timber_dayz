-- ===================================================
-- 西虹ERP系统 - PostgreSQL初始化脚本
-- ===================================================
-- 功能：创建数据库、用户、权限和扩展
-- 执行时机：容器首次启动时自动执行
-- ===================================================

-- 设置客户端编码
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- ==================== 创建 Metabase 应用数据库 ====================
-- Metabase 官方建议：生产环境必须使用 PostgreSQL/MySQL，不要使用 H2
-- 参考：https://www.metabase.com/docs/latest/installation-and-operation/migrating-from-h2
-- 
-- metabase_app 数据库用于存储 Metabase 自己的配置：
-- - Models、Questions、Dashboards
-- - 用户账号和权限设置
-- - 数据源连接配置
-- 
-- 注意：此数据库与业务数据库 xihong_erp 完全独立
CREATE DATABASE metabase_app
    WITH 
    OWNER = erp_user
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8'
    TEMPLATE = template0;

COMMENT ON DATABASE metabase_app IS 'Metabase 应用数据库：存储 Metabase 自己的配置（Models、Questions、Dashboards、用户设置等）';

-- 授权 erp_user 完全访问 metabase_app 数据库
GRANT ALL PRIVILEGES ON DATABASE metabase_app TO erp_user;

-- ==================== 连接到业务数据库 ====================
-- 创建数据库（如果不存在）
-- 注意：通过环境变量POSTGRES_DB已创建，这里仅确认

-- 连接到目标数据库
\c xihong_erp

-- ==================== 创建Schema ====================
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

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";       -- UUID生成
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- 文本相似度搜索
CREATE EXTENSION IF NOT EXISTS "btree_gin";       -- GIN索引支持

-- 创建只读用户（用于报表和查询）
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'erp_reader') THEN
        CREATE USER erp_reader WITH PASSWORD 'reader_pass_2025';
    END IF;
END
$$;

-- 授权只读权限
GRANT CONNECT ON DATABASE xihong_erp TO erp_reader;
GRANT USAGE ON SCHEMA public TO erp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO erp_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO erp_reader;

-- 设置数据库参数
ALTER DATABASE xihong_erp SET timezone TO 'UTC';
ALTER DATABASE xihong_erp SET client_encoding TO 'UTF8';
ALTER DATABASE xihong_erp SET default_transaction_isolation TO 'read committed';

-- ==================== 设置搜索路径 ====================
-- 设置数据库级别的搜索路径（保持代码向后兼容，无需修改SQL查询即可访问表）
ALTER DATABASE xihong_erp SET search_path TO core, a_class, b_class, c_class, finance, public;

-- 设置用户级别的搜索路径（确保所有会话都使用正确的搜索路径）
ALTER ROLE erp_user SET search_path TO core, a_class, b_class, c_class, finance, public;
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'erp_reader') THEN
        ALTER ROLE erp_reader SET search_path TO core, a_class, b_class, c_class, finance, public;
    END IF;
END
$$;

-- 创建自定义函数：更新updated_at时间戳
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 输出初始化完成信息
DO $$
BEGIN
    RAISE NOTICE '===================================================';
    RAISE NOTICE '西虹ERP系统 - 数据库初始化完成';
    RAISE NOTICE '===================================================';
    RAISE NOTICE '数据库名称: xihong_erp';
    RAISE NOTICE '主用户: erp_user (读写权限)';
    RAISE NOTICE '只读用户: erp_reader (只读权限)';
    RAISE NOTICE '已安装扩展: uuid-ossp, pg_trgm, btree_gin';
    RAISE NOTICE '时区设置: UTC';
    RAISE NOTICE '编码: UTF8';
    RAISE NOTICE '===================================================';
    RAISE NOTICE '下一步: SQLAlchemy将自动创建表结构';
    RAISE NOTICE '===================================================';
END
$$;


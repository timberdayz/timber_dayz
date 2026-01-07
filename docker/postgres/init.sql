-- ===================================================
-- 西虹ERP系统 - PostgreSQL初始化脚本
-- ===================================================
-- 功能：创建数据库、用户、权限和扩展
-- 执行时机：容器首次启动时自动执行
-- ===================================================

-- 设置客户端编码
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- 创建数据库（如果不存在）
-- 注意：通过环境变量POSTGRES_DB已创建，这里仅确认

-- 连接到目标数据库
\c xihong_erp

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

